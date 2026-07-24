import os
import yaml
import argparse
import time
import random
from datetime import datetime, timezone
from pyflonkit import eosapi as chainapi, wallet
from pydexbot import utils
import threading
import signal


# Parse config directory from command line
parser = argparse.ArgumentParser()
parser.add_argument('--config-dir', default=os.path.join(os.getcwd(), 'config'), help='Config directory path')
parser.add_argument('--log-dir', default=os.path.join(os.getcwd(), 'logs'), help='Log directory path')
args, _ = parser.parse_known_args()
CONFIG_DIR = args.config_dir
LOG_DIR = args.log_dir

def get_config_path():
    # Prefer .config.yaml if exists
    config_path = os.path.join(CONFIG_DIR, ".config.yaml")
    if os.path.exists(config_path):
        return config_path
    return os.path.join(CONFIG_DIR, "config.example.yaml")

# Load config.example.yaml or override .config.yaml
CONFIG_PATH = get_config_path()
with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

NODE_URL = config["node_url"]
TRADE_PRIVKEY = config.get("trade_privkey")
TOKENX_MM_CONTRACT = config.get("tokenx_mm_contract")
BUYLOWSELLHI_CONTRACT = config.get("buylowsellhi_contract", "buylowsellhi")
TRADE_PAIRS = config.get("trade_pairs", [])
BOT_ADMIN = config.get("bot_admin")
FEE_PAYER = config.get("fee_payer")
BOT_MM_CONTRACT = config.get("bot_mm_contract", "bot.mm")

TRADE_PERMISSION = config.get("trade_permission", "trade")

MIN_INTERVAL_SECONDS = config.get("min_interval_seconds", 4)
MAX_INTERVAL_SECONDS = config.get("max_interval_seconds", 12)
INTERVAL_JITTER_RATIO = config.get("interval_jitter_ratio", 0.35)
RETRY_MIN_INTERVAL_SECONDS = config.get("retry_min_interval_seconds", 10)
RETRY_MAX_INTERVAL_SECONDS = config.get("retry_max_interval_seconds", 30)
READY_JITTER_SECONDS = config.get("ready_jitter_seconds", 8)
VERBOSE = config.get("verbose", False)

def log_message(level, msg, log_file=None):
    line = f"[{level}] {msg}"
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
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

def normalize_interval(min_seconds, max_seconds):
    min_seconds = float(min_seconds or 1)
    max_seconds = float(max_seconds or min_seconds)
    if min_seconds <= 0:
        min_seconds = 1
    if max_seconds < min_seconds:
        max_seconds = min_seconds
    return min_seconds, max_seconds

def next_interval_seconds(min_seconds, max_seconds):
    min_seconds, max_seconds = normalize_interval(min_seconds, max_seconds)
    base = random.uniform(min_seconds, max_seconds) if max_seconds > min_seconds else min_seconds
    jitter_ratio = max(float(INTERVAL_JITTER_RATIO or 0), 0)
    if jitter_ratio > 0:
        jitter_span = max(base * jitter_ratio, 1.0)
        base = random.uniform(max(1.0, base - jitter_span), base + jitter_span)
    return max(1.0, base)

def sleep_with_jitter(stop_event, min_seconds, max_seconds, log_file=None, reason="next round"):
    sleep_time = next_interval_seconds(min_seconds, max_seconds)
    info(f"wait for {reason}: {sleep_time:.1f}s", log_file)
    sleep_until(stop_event, sleep_time)

def sleep_until(stop_event, sleep_time):
    deadline = time.monotonic() + sleep_time
    while not stop_event.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(1.0, remaining))

def parse_chain_time_seconds(value):
    if not value:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    value = str(value).replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    return 0

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

def get_trade_schedule(trade_pair):
    """
    Query per-pair trade schedule from tokenx.mm schedules table.
    Returns dict of schedule row if found, else None.
    """
    resp = chainapi.get_table_rows(
        True,
        TOKENX_MM_CONTRACT,
        TOKENX_MM_CONTRACT,
        "schedules",
        trade_pair,
        trade_pair,
        1
    )
    if resp and resp.get("rows"):
        row = resp["rows"][0]
        if row.get("trade_pair_name") == trade_pair:
            return row
    return None

def seconds_until_trade_ready(trade_pair):
    schedule = get_trade_schedule(trade_pair)
    if not schedule:
        return 0
    last_traded_at = parse_chain_time_seconds(schedule.get("last_traded_at"))
    random_interval_seconds = int(schedule.get("random_interval_seconds") or 0)
    if last_traded_at <= 0 or random_interval_seconds <= 0:
        return 0
    next_trade_at = last_traded_at + random_interval_seconds
    return max(0, next_trade_at - int(time.time()))

def wait_for_contract_schedule(trade_pair, stop_event, log_file=None):
    wait_seconds = seconds_until_trade_ready(trade_pair)
    if wait_seconds <= 0:
        return False
    ready_jitter = max(float(READY_JITTER_SECONDS or 0), 0)
    sleep_time = wait_seconds + random.uniform(0, ready_jitter)
    info(f"wait for contract schedule: {sleep_time:.1f}s", log_file)
    sleep_until(stop_event, sleep_time)
    return True


def get_bots_from_group(group_name):
    """
    Read bots from botgroups table in bot.mm contract for the given group_name.
    Returns a list of bot names.
    """
    resp = chainapi.get_table_rows(
        True,
        BOT_MM_CONTRACT,
        BOT_MM_CONTRACT,
        "botgroups",
        group_name,
        group_name,
        1
    )
    if resp and resp.get("rows"):
        return resp["rows"][0].get("bots", [])
    return []

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

def run_pair_worker(trade_pair, stop_event):
    log_file = os.path.join(LOG_DIR, f"trade_{trade_pair.replace('.', '_')}.log")
    info(f"trade bot started for {trade_pair}")
    while not stop_event.is_set():
        try:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            memo = str(random.randint(0, 2**32 - 1))
            debug(f"[{timestamp}] trade: pair={trade_pair} memo={memo}")

            market_config = get_market_config(trade_pair)
            if market_config:
                paused = market_config.get("paused", 0)
                if paused:
                    info(f"Market {trade_pair} is paused, skipping this round.", log_file)
                    sleep_with_jitter(stop_event, RETRY_MIN_INTERVAL_SECONDS, RETRY_MAX_INTERVAL_SECONDS, log_file, "retry after paused market")
                    continue

            if wait_for_contract_schedule(trade_pair, stop_event, log_file):
                continue

            bots = get_bots_from_group(trade_pair)
            if not bots:
                error(f"No bots found in group {trade_pair}", log_file)
                sleep_with_jitter(stop_event, RETRY_MIN_INTERVAL_SECONDS, RETRY_MAX_INTERVAL_SECONDS, log_file, "retry after missing bots")
                continue
            selected_bot = random.choice(bots)
            debug(f"Selected bot: {selected_bot}", log_file)

            action_data = {"bot": selected_bot, "trade_pair_name": trade_pair, "memo": memo}
            authorizations = {
                FEE_PAYER: TRADE_PERMISSION,
                selected_bot: TRADE_PERMISSION
            }
            result = utils.push_action(TOKENX_MM_CONTRACT, "trade", action_data, authorizations)
            debug(f"trade result: {result}", log_file)
            trade_info = parse_price_from_result(result)
            info(f"\n========== Trade Result ({trade_pair}) ==========" , log_file)
            if trade_info:
                max_key_len = max(len(str(k)) for k in trade_info.keys())
                for k, v in trade_info.items():
                    info(f"{k:<{max_key_len}} : {v}", log_file)
            else:
                info("ERROR: No trade info found.", log_file)
            info("========== End Trade ==========" , log_file)
            sleep_with_jitter(stop_event, MIN_INTERVAL_SECONDS, MAX_INTERVAL_SECONDS, log_file, "next trade")
        except Exception as e:
            error(f"trade failed for {trade_pair}: {e}", log_file)
            sleep_with_jitter(stop_event, RETRY_MIN_INTERVAL_SECONDS, RETRY_MAX_INTERVAL_SECONDS, log_file, "retry after failure")

def run_bot_service():
    """
    Entry point for multi-pair trading bot service. Uses trade_pairs from config.example.yaml or .config.yaml.
    Each trading pair runs in a separate thread with its own log file.
    """
    info("trade bot service started.")
    utils.setup_flon_network([NODE_URL])
    if not TRADE_PRIVKEY:
        error("trade_privkey not configured, please set trade_privkey in config.example.yaml or config/.config.yaml")
        return
    wallet.import_key('tradewallet', TRADE_PRIVKEY)
    if not TRADE_PAIRS:
        error("trade_pairs not configured in config.example.yaml or config/.config.yaml")
        return
    stop_event = threading.Event()
    threads = []
    for trade_pair in TRADE_PAIRS:
        t = threading.Thread(target=run_pair_worker, args=(trade_pair, stop_event))
        t.start()
        threads.append(t)
    def handle_sigint(signum, frame):
        info("Received Ctrl-C, stopping all bots...")
        stop_event.set()
    signal.signal(signal.SIGINT, handle_sigint)
    for t in threads:
        t.join()

# ...existing code...
