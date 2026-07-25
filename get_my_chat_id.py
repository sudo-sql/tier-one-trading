"""Helper: finds your Telegram chat ID automatically.

Usage:
  1. Put your bot token in config.yaml (telegram.bot_token)
  2. Run:  python get_my_chat_id.py
  3. Send your bot any message in Telegram
  4. Your chat ID prints here — paste it into config.yaml (admin_chat_id)
"""
import sys
import time

import requests
import yaml

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

token = cfg["telegram"].get("bot_token", "").strip()
if not token:
    sys.exit("First put your bot token in config.yaml under telegram.bot_token")

me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15).json()
if not me.get("ok"):
    sys.exit("That bot token was rejected by Telegram — recheck it (no spaces, full string).")

username = me["result"]["username"]
print(f"✅ Token OK — your bot is @{username}")
print(f"\nNow open Telegram, search @{username}, and send it any message.")
print("Waiting (up to 2 minutes)...\n")

offset = 0
deadline = time.time() + 120
while time.time() < deadline:
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates",
                     params={"offset": offset, "timeout": 20}, timeout=30).json()
    for upd in r.get("result", []):
        offset = upd["update_id"] + 1
        msg = upd.get("message")
        if msg:
            chat = msg["chat"]
            name = chat.get("first_name") or chat.get("username") or "?"
            print(f"🎯 Found it! {name}'s chat ID is:  {chat['id']}")
            print(f'\nPut this in config.yaml:\n  admin_chat_id: "{chat["id"]}"')
            sys.exit(0)

print("No message received in 2 minutes. Send the bot a message and run this again.")
