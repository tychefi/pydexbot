import os
import yaml
import argparse
import time
import random
from pyflonkit import eosapi as chainapi, wallet
from pydexbot import utils
import threading


# Parse config directory from command line
parser = argparse.ArgumentParser()
parser.add_argument('--config-dir', default=os.path.join(os.getcwd(), 'config'), help='Config directory path')
args, _ = parser.parse_known_args()
CONFIG_DIR = args.config_dir

def get_config_path(filename):
    return os.path.join(CONFIG_DIR, filename)

# Load config.yaml
CONFIG_PATH = get_config_path('config.yaml')
with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

NODE_URL = config["node_url"]
TRADE_PRIVKEY = config.get("trade_privkey")
TOKENX_MM_CONTRACT = config.get("tokenx_mm_contract")
BUYLOWSELLHI_CONTRACT = config.get("buylowsellhi_contract", "buylowsellhi")
TRADE_PAIRS = config.get("trade_pairs", [])
BOT_ADMIN = config.get("bot_admin")
TRADE_PERMISSION = config.get("trade_permission", "trade")

MIN_INTERVAL_SECONDS = config.get("min_interval_seconds")
MAX_INTERVAL_SECONDS = config.get("max_interval_seconds")
VERBOSE = config.get("verbose", False)

def log_message(level, msg, log_file=None):
    line = f"[{level}] {msg}"
    if log_file:
        with open(log_file, "a") as f:
            f.write(line + "\n")
    else:
        print(line)

def debug(msg, log_file=None):
    if VERBOSE:
        log_message("DEBUG", msg, log_file)

def info(msg, log_file=None):
    log_message("INFO", msg, log_file)

def error(msg, log_file=None):
    log_message("ERROR", msg, log_file)

def get_market_config(trade_pair):
    """
    Query market config from trademarkets table of buylowsellhi contract.
    Returns dict of market row if found, else None.
    """
    resp = chainapi.get_table_rows(
        True,
        BUYLOWSELLHI_CONTRACT,
        BUYLOWSELLHI_CONTRACT,
        "trademarkets",
        trade_pair,
        trade_pair,
        1
    )
    if resp and resp.get("rows"):
        return resp["rows"][0]
    return None

def parse_price_from_result(trx):
    result = {}
    if "processed" not in trx:
        return result
    if "action_traces" not in trx["processed"]:
        return result
    traces = trx["processed"]["action_traces"]
    for trace in traces:
        if "act" in trace and "name" in trace["act"] and trace["act"]["name"] == "trade":
            if "inline_traces" not in trace or not trace["inline_traces"]:
                continue
            if len(trace["inline_traces"]) < 2:
                continue

            after_swap = trace["inline_traces"][1]
            if "act" not in after_swap or "data" not in after_swap["act"]:
                continue
            after_swap_act = after_swap["act"]
            after_swap_data = after_swap_act["data"]
            bot_user = after_swap_data.get("bot", "")
            side = after_swap_data.get("side", "")

            swap_inlines = trace["inline_traces"][0].get("inline_traces", [])
            for inline in swap_inlines:
                if "act" not in inline or "data" not in inline["act"]:
                    continue
                act = inline["act"]
                act_data = act["data"]
                if act["name"] == "transfer" and act["name"] == "transfer" and act_data["from"] == "flon.swap" and act_data["memo"].startswith("flon swap by"):
                    # result["input_contract"] = act["account"]
                    input_quantity = act_data["quantity"]  # "0.514535 USDT"
                    memo = act_data["memo"]  # "swap:9.53418172 FLON:flon.usdt"

                    in_amount = float(input_quantity.split()[0])
                    in_symbol = input_quantity.split()[1]
                    # parse memo: "flon swap by 0.514535 USDT:18446744073709551615"
                    output_quantity = memo.split("by")[1].strip()  # "0.514535 USDT:18446744073709551615"
                    output_quantity = output_quantity.split(":")[0].strip()  # "0.514535 USDT"
                    out_amount = float(output_quantity.split()[0])
                    out_symbol = output_quantity.split()[1]
                    price = out_amount / in_amount if in_amount > 0 else 0
                    price_reverted = in_amount / out_amount if out_amount > 0 else 0
                    if side == "left":
                        result["price"] = f"{price_reverted:.8f} {in_symbol}/{out_symbol}"
                        result["price_reverted"] = f"{price:.8f} {out_symbol}/{in_symbol}"
                    else:
                        result["price"] = f"{price:.8f} {out_symbol}/{in_symbol}"
                        result["price_reverted"] = f"{price_reverted:.8f} {in_symbol}/{out_symbol}"
                    result["side"] = side
                    result["bot_user"] = bot_user
                    result["input_quantity"] = input_quantity
                    result["output_quantity"] = output_quantity
                    return result
    return result

def run_pair_worker(trade_pair):
    log_file = f"trade_{trade_pair.replace('.', '_')}.log"
    info(f"trade bot started for {trade_pair}")
    while True:
        try:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            memo = str(random.randint(0, 2**32 - 1))
            debug(f"[{timestamp}] trade: pair={trade_pair} memo={memo}")

            market_config = get_market_config(trade_pair)
            if market_config:
                paused = market_config.get("paused", 0)
                if paused:
                    info(f"Market {trade_pair} is paused, skipping this round.", log_file)
                    time.sleep(3)
                    continue

            result = utils.push_action(TOKENX_MM_CONTRACT, "trade", {"memo": memo}, { BOT_ADMIN: TRADE_PERMISSION })
            debug(f"trade result: {result}")
            sleep_time = random.randint(MIN_INTERVAL_SECONDS, MAX_INTERVAL_SECONDS)
            trade_info = parse_price_from_result(result)
            info(f"\n========== Trade Result ({trade_pair}) ==========" , log_file)
            if trade_info:
                max_key_len = max(len(str(k)) for k in trade_info.keys())
                for k, v in trade_info.items():
                    info(f"{k:<{max_key_len}} : {v}", log_file)
            else:
                info("ERROR: No trade info found.", log_file)
            info("========== End Trade ==========" , log_file)
            info(f"wait for: {sleep_time}s", log_file)
            time.sleep(sleep_time)
        except Exception as e:
            error(f"trade failed for {trade_pair}: {e}", log_file)
            time.sleep(3)

def run_bot_service():
    """
    Entry point for multi-pair trading bot service. Uses trade_pairs from config.yaml.
    Each trading pair runs in a separate thread with its own log file.
    """
    info("trade bot service started.")
    utils.setup_flon_network([NODE_URL])
    if not TRADE_PRIVKEY:
        error("trade_privkey not configured, please set trade_privkey in config.yaml")
        return
    wallet.import_key('tradewallet', TRADE_PRIVKEY)
    if not TRADE_PAIRS:
        error("trade_pairs not configured in config.yaml")
        return
    threads = []
    for trade_pair in TRADE_PAIRS:
        t = threading.Thread(target=run_pair_worker, args=(trade_pair,), daemon=True)
        t.start()
        threads.append(t)
    return threads

# ...existing code...
