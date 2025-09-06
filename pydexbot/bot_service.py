

import os
import yaml
import argparse
import time
import random
from pyflonkit import eosapi as chainapi, wallet
from pydexbot import utils



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
BOT_ADMIN = config.get("bot_admin")
TRADE_PERMISSION = config.get("trade_permission", "trade")

MIN_INTERVAL_SECONDS = config.get("min_interval_seconds")
MAX_INTERVAL_SECONDS = config.get("max_interval_seconds")
VERBOSE = config.get("verbose", False)

def debug(msg):
    if VERBOSE:
        print(f"[DEBUG] {msg}")

def info(msg):
    print(f"[INFO] {msg}")

def error(msg):
    print(f"[ERROR] {msg}")

def parse_price_from_result(trx):
    result = {}
    if "processed" not in trx:
        return result
    if "action_traces" not in trx["processed"]:
        return result
    traces = trx["processed"]["action_traces"]
    for trace in traces:
        if "act" in trace and "name" in trace["act"] and trace["act"]["name"] == "exectrade":
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

def run_bot_service():
    """
    Refer to run.bot.sh, loop to call exectrade action, sign and submit with pyflonkit, permission is contract@trade.
    Private key is read from config.yaml.
    """
    info("Exectrade bot started.")
    utils.setup_flon_network([NODE_URL])
    if not TRADE_PRIVKEY:
        error("trade_privkey not configured, please set trade_privkey in config.yaml")
        return
    wallet.import_key('tradewallet', TRADE_PRIVKEY)
    while True:
        try:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            memo = str(random.randint(0, 2**32 - 1))
            info(f"[{timestamp}] exectrade: memo={memo}")

            result = utils.push_action(TOKENX_MM_CONTRACT, "exectrade", {"memo": memo}, { BOT_ADMIN: TRADE_PERMISSION })
            debug(f"exectrade result: {result}")
            sleep_time = random.randint(MIN_INTERVAL_SECONDS, MAX_INTERVAL_SECONDS)
            trade_info = parse_price_from_result(result)
            info("\n========== Trade Result ==========")
            if trade_info:
                max_key_len = max(len(str(k)) for k in trade_info.keys())
                for k, v in trade_info.items():
                    info(f"{k:<{max_key_len}} : {v}")
            else:
                info("ERROR: No trade info found.")
            info("========== End Trade ==========")
            info(f"wait for: {sleep_time}s")
            time.sleep(sleep_time)
        except Exception as e:
            error(f"exectrade failed: {e}")
            time.sleep(3)

# ...existing code...
