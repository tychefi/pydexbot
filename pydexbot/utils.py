# EOS blockchain utility functions for account creation, key conversion, action push, and encryption
import time
import json
import base58
from pyflonkit import eosapi as chainapi, config as chain_config
from pyflonkit.eosBase import Transaction
from Crypto.Cipher import PKCS1_OAEP

SYSTEM_CONTRACT="flon"
MAIN_TOKEN_CONTRACT="flon.token"
MAIN_TOKEN="FLON"

def setup_flon_network(node_urls):
    for url in node_urls:
        chainapi.set_node(url)
    chain_config.config_network(SYSTEM_CONTRACT, MAIN_TOKEN_CONTRACT, MAIN_TOKEN)

def create_account(account_name, owner_key, transfer_amount, creator=SYSTEM_CONTRACT, token_contract=MAIN_TOKEN_CONTRACT, active_key=None):
    """
    Create a new EOS account and transfer initial token in one transaction.
    owner_key/active_key support account name or public key, active_key defaults to owner_key.
    """
    actions = []
    if active_key is None:
        active_key = owner_key
    def build_permission(key_or_name):
        # If string starts with 'F' and length > 12, treat as public key, else as account name
        if isinstance(key_or_name, str) and len(key_or_name) > 12:
            return {"keys": [{"key": key_or_name, "weight": 1}], "accounts": [], "waits": [], "threshold": 1}
        else:
            return {"keys": [], "accounts": [{"permission": {"actor": key_or_name, "permission": "active"}, "weight": 1}], "waits": [], "threshold": 1}
    owner = build_permission(owner_key)
    active = build_permission(active_key)
    args = {
        "creator": creator,
        "name": account_name,
        "owner": owner,
        "active": active
    }
    args = chainapi.pack_args("flon", 'newaccount', args)
    act = ["flon", 'newaccount', args, {creator:'active'}]
    actions.append(act)
    args = {
        "from": creator,
        "to": account_name,
        "quantity": transfer_amount,
        "memo": "init account"
    }
    args = chainapi.pack_args(token_contract, 'transfer', args)
    act = [token_contract, 'transfer', args, {creator:'active'}]
    actions.append(act)
    chainapi.push_actions(actions)
    print(f"Account {account_name} created and {transfer_amount} transferred in one transaction.")
    time.sleep(2)

def get_code_hash(contract):
    """
    Get the code hash of a contract account.
    """
    chain_info = chainapi.get_code_hash(contract)
    if chain_info and 'code_hash' in chain_info:
        return chain_info.get('code_hash')
    return None

def flon_pubkey_to_secp256k1(pubkey_str):
    """
    Convert EOS public key string to secp256k1 raw bytes.
    """
    raw = base58.b58decode(pubkey_str[2:])
    return raw[:33]

def push_action(contract, action_name, args, permissions=None):
    """
    Pack arguments and push an action to the blockchain.
    """
    args = chainapi.pack_args(contract, action_name, args)
    return chainapi.push_action(contract, action_name, args, permissions)

def encrypt_with_public_key(data, rsa_pubkey):
    """
    Encrypt data using RSA public key (PKCS1_OAEP). Returns ciphertext raw bytes.
    """
    cipher_rsa = PKCS1_OAEP.new(rsa_pubkey)
    if isinstance(data, str):
        data_bytes = data.encode()
    elif isinstance(data, bytes):
        data_bytes = data
    else:
        data_bytes = json.dumps(data, separators=(",", ":")).encode()
    return cipher_rsa.encrypt(data_bytes)

def name_to_number(name):
    """
    Convert EOS name to uint64 integer.
    """
    return int.from_bytes(Transaction.name_to_number(name), byteorder="little", signed=False)
"""
Utility functions for Quant Swap Bot
"""

def eosio_rpc_call(endpoint: str, payload: dict):
    # TODO: Implement EOSIO RPC call
    pass
