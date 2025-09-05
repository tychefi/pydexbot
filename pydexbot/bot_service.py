

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
VERBOSE = config.get("service", {}).get("verbose", True)

def debug(msg):
    if VERBOSE:
        print(f"[DEBUG] {msg}")

def info(msg):
    print(f"[INFO] {msg}")

def error(msg):
    print(f"[ERROR] {msg}")

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
            # Build action data
            action_data = {"memo": memo}
            # Permission format: contract@trade
            permission = f"{BOT_ADMIN}@{TRADE_PERMISSION}"
            # Submit transaction

            result = utils.push_action(TOKENX_MM_CONTRACT, "exectrade", {"memo": memo}, { BOT_ADMIN: TRADE_PERMISSION })
            info(f"exectrade result: {result}")
            sleep_time = random.randint(MIN_INTERVAL_SECONDS, MAX_INTERVAL_SECONDS)
            info(f"wait for: {sleep_time}s")
            time.sleep(sleep_time)
        except Exception as e:
            error(f"exectrade failed: {e}")
            time.sleep(3)

# ...existing code...
