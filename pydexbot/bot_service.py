import os
import yaml
import argparse
import time
import random
from decimal import Decimal
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
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
DEX_CONTRACT = config.get("dex_contract", "flon.swap")

TRADE_PERMISSION = config.get("trade_permission", "trade")

MIN_INTERVAL_SECONDS = config.get("min_interval_seconds", 4)
MAX_INTERVAL_SECONDS = config.get("max_interval_seconds", 12)
INTERVAL_JITTER_RATIO = config.get("interval_jitter_ratio", 0.35)
RETRY_MIN_INTERVAL_SECONDS = config.get("retry_min_interval_seconds", 10)
RETRY_MAX_INTERVAL_SECONDS = config.get("retry_max_interval_seconds", 30)
READY_JITTER_SECONDS = config.get("ready_jitter_seconds", 8)
VERBOSE = config.get("verbose", False)
SIDE_SEGMENT_SECONDS = int(config.get("side_segment_seconds", 900))
CORRECTION_BAND_MULTIPLIER = Decimal("2.0")
TARGET_SIDE_DEADBAND_RATIO = Decimal(str(config.get("target_side_deadband_ratio", "0.006")))
TARGET_SIDE_DEADBAND_RATIOS = {
    str(pair): Decimal(str(value))
    for pair, value in config.get("target_side_deadband_ratios", {}).items()
}
CANDLE_PLAN_ENABLED = bool(config.get("candle_plan_enabled", True))
CANDLE_SECONDS = int(config.get("candle_seconds", 300))
LOG_TIMEZONE = config.get("log_timezone", "Asia/Shanghai")

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

def format_no_fill_message(exc):
    text = str(exc)
    marker = "no fill:"
    idx = text.lower().find(marker)
    if idx < 0:
        return None
    line = text[idx:].splitlines()[0].strip()
    return line.rstrip('",')

def extract_transaction_id(trx):
    if not isinstance(trx, dict):
        return None
    for key in ("transaction_id", "trx_id", "id"):
        value = trx.get(key)
        if value:
            return str(value)
    processed = trx.get("processed")
    if isinstance(processed, dict):
        for key in ("transaction_id", "trx_id", "id"):
            value = processed.get(key)
            if value:
                return str(value)
    return None

def format_transaction_link(trx, submitted_at=None):
    tx_id = extract_transaction_id(trx)
    if not tx_id:
        return None
    if submitted_at is None:
        submitted_at = current_log_time()
    return f"[{submitted_at}](https://flonscan.io/m/transaction/{tx_id.upper()})"

def current_log_time():
    try:
        return datetime.now(ZoneInfo(LOG_TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return time.strftime('%Y-%m-%d %H:%M:%S')

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

def parse_asset(value):
    amount, symbol = str(value).strip().split()
    return Decimal(amount), symbol

def get_currency_balance(contract, account, symbol):
    resp = chainapi.get_table_rows(True, contract, account, "accounts", symbol, symbol, 1)
    for row in resp.get("rows", []):
        amount, row_symbol = parse_asset(row["balance"])
        if row_symbol == symbol:
            return amount
    return Decimal("0")

def get_single_table_row(code, scope, table, lower_bound):
    resp = chainapi.get_table_rows(True, code, scope, table, lower_bound, lower_bound, 1)
    if resp and resp.get("rows"):
        return resp["rows"][0]
    return None

def get_swap_market(trade_pair):
    row = get_single_table_row(DEX_CONTRACT, DEX_CONTRACT, "markets", trade_pair)
    if row and row.get("tpcode") == trade_pair:
        return row
    return None

def get_bot_market(trade_pair):
    row = get_single_table_row(TOKENX_MM_CONTRACT, TOKENX_MM_CONTRACT, "botmarkets", trade_pair)
    if row and row.get("trade_pair_name") == trade_pair:
        return row
    return None

def mix32(value):
    value &= 0xffffffff
    value ^= value >> 16
    value = (value * 0x7feb352d) & 0xffffffff
    value ^= value >> 15
    value = (value * 0x846ca68b) & 0xffffffff
    value ^= value >> 16
    return value & 0xffffffff

def calc_left_inventory_bps(bot_market, left_price):
    left_amount, _ = parse_asset(bot_market["left_pool"]["total_quantity"])
    right_amount, _ = parse_asset(bot_market["right_pool"]["total_quantity"])
    left_value = left_amount * left_price
    total_value = left_value + right_amount
    if total_value <= 0:
        return 5000
    return int(max(Decimal("0"), min(Decimal("10000"), left_value * Decimal("10000") / total_value)))

def get_target_side_deadband_ratio(trade_pair):
    return TARGET_SIDE_DEADBAND_RATIOS.get(trade_pair, TARGET_SIDE_DEADBAND_RATIO)

def opposite_side(side):
    return "right" if side == "left" else "left"

def planned_candle_side(trade_pair, now_seconds=None):
    if not CANDLE_PLAN_ENABLED or CANDLE_SECONDS <= 0:
        return None
    if now_seconds is None:
        now_seconds = int(time.time())

    candle_index = now_seconds // CANDLE_SECONDS
    candle_elapsed = now_seconds % CANDLE_SECONDS
    seed = utils.name_to_number(trade_pair) & 0xffffffff
    candle_rand = mix32(seed ^ ((candle_index * 2246822519) & 0xffffffff))
    body_side = "left" if (candle_rand & 1) == 0 else "right"
    wick_side = opposite_side(body_side)

    first_turn = CANDLE_SECONDS * 25 // 100
    second_turn = CANDLE_SECONDS * 55 // 100
    if candle_elapsed < first_turn:
        return body_side
    if candle_elapsed < second_turn:
        return wick_side
    return body_side

def predict_trade_side(trade_pair, market_config, swap_market, bot_market):
    target_price = Decimal(str(market_config.get("target_price") or "0"))
    fluctuation_ratio = Decimal(str(market_config.get("fluctuation_ratio") or "0"))
    left_amount, _ = parse_asset(swap_market["left_pool_quant"]["quantity"])
    right_amount, _ = parse_asset(swap_market["right_pool_quant"]["quantity"])
    if left_amount <= 0 or right_amount <= 0:
        return None

    left_price = right_amount / left_amount
    if target_price > 0:
        target_gap_ratio = abs(left_price - target_price) / target_price
        target_deadband_ratio = get_target_side_deadband_ratio(trade_pair)
        if target_gap_ratio > target_deadband_ratio and left_price < target_price:
            return "right"
        if target_gap_ratio > target_deadband_ratio and left_price > target_price:
            return "left"

    correction_ratio = min(fluctuation_ratio * CORRECTION_BAND_MULTIPLIER, Decimal("1"))
    min_price = target_price * (Decimal("1") - correction_ratio)
    max_price = target_price * (Decimal("1") + correction_ratio)
    if left_price < min_price:
        side = "right"
    elif left_price > max_price:
        side = "left"
    else:
        side = planned_candle_side(trade_pair)
        if side not in ("left", "right"):
            segment = int(time.time()) // SIDE_SEGMENT_SECONDS
            seed = utils.name_to_number(trade_pair) & 0xffffffff
            segment_rand = mix32(seed ^ ((segment * 2246822519) & 0xffffffff))
            side = "left" if (segment_rand & 1) == 0 else "right"

    return side

def side_required_balance(side, market_config, swap_market, bot_market):
    min_left_amount, _ = parse_asset(market_config["min_trade_amount"])
    left_amount, _ = parse_asset(swap_market["left_pool_quant"]["quantity"])
    right_amount, _ = parse_asset(swap_market["right_pool_quant"]["quantity"])
    left_price = right_amount / left_amount

    if side == "left":
        pool = bot_market["left_pool"]
        required_amount = min_left_amount
    else:
        pool = bot_market["right_pool"]
        required_amount = min_left_amount * left_price

    _, symbol = parse_asset(pool["balance"]["quantity"])
    pool_balance, _ = parse_asset(pool["balance"]["quantity"])
    return pool["balance"]["contract"], symbol, pool_balance, required_amount

def possible_trade_sides(market_config, swap_market):
    target_price = Decimal(str(market_config.get("target_price") or "0"))
    fluctuation_ratio = Decimal(str(market_config.get("fluctuation_ratio") or "0"))
    left_amount, _ = parse_asset(swap_market["left_pool_quant"]["quantity"])
    right_amount, _ = parse_asset(swap_market["right_pool_quant"]["quantity"])
    if left_amount <= 0 or right_amount <= 0:
        return ("left", "right")

    left_price = right_amount / left_amount
    correction_ratio = min(fluctuation_ratio * CORRECTION_BAND_MULTIPLIER, Decimal("1"))
    min_price = target_price * (Decimal("1") - correction_ratio)
    max_price = target_price * (Decimal("1") + correction_ratio)

    if left_price < min_price:
        return ("right",)
    if left_price > max_price:
        return ("left",)
    return ("left", "right")

def action_name_for_side(side):
    if side == "right":
        return "buy"
    if side == "left":
        return "sell"
    return "trade"

def build_trade_authorizations(selected_bot, trade_action):
    if trade_action in ("buy", "sell"):
        return {selected_bot: TRADE_PERMISSION}
    return {
        FEE_PAYER: TRADE_PERMISSION,
        selected_bot: TRADE_PERMISSION
    }

def choose_funded_bot(trade_pair, bots, market_config, log_file=None):
    swap_market = get_swap_market(trade_pair)
    bot_market = get_bot_market(trade_pair)
    if not market_config or not swap_market or not bot_market:
        selected = random.choice(bots)
        debug(f"Selected bot without market prefilter: {selected}", log_file)
        return selected, "trade", None

    side = predict_trade_side(trade_pair, market_config, swap_market, bot_market)
    if side not in ("left", "right"):
        selected = random.choice(bots)
        debug(f"Selected bot without side prediction: {selected}", log_file)
        return selected, "trade", None

    candidate_sides = (side,)
    requirements = {
        candidate_side: side_required_balance(candidate_side, market_config, swap_market, bot_market)
        for candidate_side in candidate_sides
    }
    eligible = []
    balances = {}
    for bot in bots:
        bot_balances = {}
        is_eligible = True
        for candidate_side, (contract, symbol, pool_balance, required_amount) in requirements.items():
            balance_key = f"{contract}:{symbol}"
            if balance_key not in bot_balances:
                bot_balances[balance_key] = get_currency_balance(contract, bot, symbol)
            available_amount = bot_balances[balance_key] + pool_balance
            if available_amount < required_amount:
                is_eligible = False
        balances[bot] = {key: str(value) for key, value in bot_balances.items()}
        if is_eligible:
            eligible.append(bot)

    if eligible:
        selected = random.choice(eligible)
        action_name = action_name_for_side(side)
        debug(
            f"Selected funded bot: {selected}, predicted_side={side}, "
            f"action={action_name}, balances={balances}",
            log_file,
        )
        return selected, action_name, side

    readable_sides = ",".join("sell" if candidate_side == "left" else "buy" for candidate_side in candidate_sides)
    required_text = ", ".join(
        f"{candidate_side}>={required_amount:.8f} {symbol}"
        for candidate_side, (_, symbol, _, required_amount) in requirements.items()
    )
    info(
        f"no_fill: no bot has enough balance for possible {readable_sides}; "
        f"required={required_text}, balances={balances}",
        log_file,
    )
    return None, action_name_for_side(side), side

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
        if "act" in trace and "name" in trace["act"] and trace["act"]["name"] in ("trade", "buy", "sell"):
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
                        result["trade_side"] = "sell"
                        result["execution_price"] = f"{price_reverted:.8f} {in_symbol}/{out_symbol}"
                        result["inverse_price"] = f"{price:.8f} {out_symbol}/{in_symbol}"
                        result["base_quantity"] = output_quantity
                        result["quote_quantity"] = input_quantity
                    else:
                        result["trade_side"] = "buy"
                        result["execution_price"] = f"{price:.8f} {out_symbol}/{in_symbol}"
                        result["inverse_price"] = f"{price_reverted:.8f} {in_symbol}/{out_symbol}"
                        result["base_quantity"] = input_quantity
                        result["quote_quantity"] = output_quantity
                    result["maker_account"] = bot_user
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
            selected_bot, trade_action, predicted_side = choose_funded_bot(trade_pair, bots, market_config, log_file)
            if not selected_bot:
                sleep_with_jitter(stop_event, RETRY_MIN_INTERVAL_SECONDS, RETRY_MAX_INTERVAL_SECONDS, log_file, "retry after no funded bot")
                continue
            debug(f"Selected bot: {selected_bot}, action={trade_action}, predicted_side={predicted_side}", log_file)

            action_data = {"bot": selected_bot, "trade_pair_name": trade_pair, "memo": memo}
            authorizations = build_trade_authorizations(selected_bot, trade_action)
            result = utils.push_action(TOKENX_MM_CONTRACT, trade_action, action_data, authorizations)
            submitted_at = current_log_time()
            debug(f"{trade_action} result: {result}", log_file)
            trade_info = parse_price_from_result(result)
            transaction_link = format_transaction_link(result, submitted_at)
            info(f"\n========== Trade Result ({trade_pair}) ==========" , log_file)
            if transaction_link:
                info(f"submitted_at    : {transaction_link}", log_file)
            if trade_info:
                max_key_len = max(len(str(k)) for k in trade_info.keys())
                for k, v in trade_info.items():
                    info(f"{k:<{max_key_len}} : {v}", log_file)
            else:
                info("no_fill: transaction accepted but no swap fill was emitted.", log_file)
            info("========== End Trade ==========" , log_file)
            sleep_with_jitter(stop_event, MIN_INTERVAL_SECONDS, MAX_INTERVAL_SECONDS, log_file, "next trade")
        except Exception as e:
            no_fill_message = format_no_fill_message(e)
            if no_fill_message:
                info(no_fill_message, log_file)
            else:
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
