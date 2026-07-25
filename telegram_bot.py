"""Telegram bot command listener — runs as a background thread.

Invite-only subscription system:

  ADMIN (you — telegram.admin_chat_id):
    /invite            → generates a one-time invite code
    /subscribers       → list who's subscribed
    /revoke <chat_id>  → kick a subscriber
    /myid              → shows your chat id (works for anyone)

  INVITEES (anyone you give a code to):
    /start <CODE>      → redeems the code, starts receiving signals
    /stop              → unsubscribe themselves

No code, no signals — the bot ignores everyone else. Not public.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone

import requests

import notify

log = logging.getLogger("tgbot")

API = "https://api.telegram.org/bot{token}/{method}"
INVITES_FILE = "invites.json"


def _load_invites() -> dict:
    if os.path.exists(INVITES_FILE):
        with open(INVITES_FILE) as f:
            return json.load(f)
    return {}


def _save_invites(inv: dict):
    with open(INVITES_FILE, "w") as f:
        json.dump(inv, f, indent=2)


def new_invite_code() -> str:
    inv = _load_invites()
    code = secrets.token_hex(4).upper()  # e.g. 9F3A61BC
    inv[code] = {"created": datetime.now(timezone.utc).isoformat(), "used_by": None}
    _save_invites(inv)
    return code


def _handle(cfg: dict, msg: dict):
    chat_id = str(msg["chat"]["id"])
    text = (msg.get("text") or "").strip()
    name = msg["chat"].get("first_name") or msg["chat"].get("username") or "unknown"
    admin = str(cfg["telegram"].get("admin_chat_id") or "")
    is_admin = admin and chat_id == admin
    reply = lambda t: notify.send_to_chat(cfg, chat_id, t)  # noqa: E731

    if text.startswith("/myid"):
        reply(f"Your chat id: <code>{chat_id}</code>")
        return

    if text.startswith("/start"):
        parts = text.split()
        subs = notify.load_subscribers()
        if chat_id in subs or is_admin:
            reply("✅ You're already receiving signals.")
            return
        if len(parts) < 2:
            reply("This bot is invite-only. Send: /start YOURCODE")
            return
        code = parts[1].strip().upper()
        inv = _load_invites()
        if code not in inv or inv[code]["used_by"]:
            reply("❌ Invalid or already-used invite code.")
            return
        inv[code]["used_by"] = chat_id
        _save_invites(inv)
        subs[chat_id] = {"name": name,
                         "joined": datetime.now(timezone.utc).isoformat(),
                         "invite": code}
        notify.save_subscribers(subs)
        reply("🎉 You're in! You'll now receive TierOne buy/sell signals here.\n"
              "Send /stop any time to unsubscribe.")
        if admin:
            notify.send_to_chat(cfg, admin, f"👤 {name} ({chat_id}) joined with code {code}")
        return

    if text.startswith("/stop"):
        subs = notify.load_subscribers()
        if subs.pop(chat_id, None):
            notify.save_subscribers(subs)
            reply("Unsubscribed. Ask for a new invite code to rejoin.")
        return

    # ----- admin commands -----
    if not is_admin:
        return  # silently ignore strangers

    if text.startswith("/invite"):
        code = new_invite_code()
        me = _get_me(cfg)
        uname = f"@{me['username']}" if me else "your bot"
        reply(f"🎟 One-time invite code: <code>{code}</code>\n\n"
              f"Send your friend this:\n"
              f"1. Open Telegram, search {uname}\n"
              f"2. Send it:  /start {code}")
    elif text.startswith("/subscribers"):
        subs = notify.load_subscribers()
        if not subs:
            reply("No subscribers yet (you always receive signals as admin).")
        else:
            lines = [f"• {v['name']} — <code>{k}</code>" for k, v in subs.items()]
            reply("Subscribers:\n" + "\n".join(lines))
    elif text.startswith("/revoke"):
        parts = text.split()
        if len(parts) < 2:
            reply("Usage: /revoke <chat_id>  (get ids from /subscribers)")
            return
        subs = notify.load_subscribers()
        gone = subs.pop(parts[1], None)
        notify.save_subscribers(subs)
        reply(f"Removed {gone['name']}." if gone else "That id wasn't subscribed.")
    elif text.startswith("/help"):
        reply("Admin commands: /invite /subscribers /revoke <id> /myid")


def _get_me(cfg: dict) -> dict | None:
    try:
        r = requests.get(API.format(token=cfg["telegram"]["bot_token"],
                                    method="getMe"), timeout=10)
        return r.json().get("result")
    except Exception:  # noqa: BLE001
        return None


def _poll_loop(cfg: dict):
    token = cfg["telegram"]["bot_token"]
    offset = 0
    log.info("Telegram command listener started")
    while True:
        try:
            r = requests.get(
                API.format(token=token, method="getUpdates"),
                params={"offset": offset, "timeout": 30},
                timeout=45,
            )
            for upd in r.json().get("result", []):
                offset = upd["update_id"] + 1
                if "message" in upd:
                    try:
                        _handle(cfg, upd["message"])
                    except Exception as e:  # noqa: BLE001
                        log.error("Command handling error: %s", e)
        except Exception as e:  # noqa: BLE001
            log.debug("Poll hiccup: %s", e)
            time.sleep(5)


def start(cfg: dict) -> threading.Thread | None:
    if not cfg["telegram"].get("bot_token"):
        log.warning("No bot token — Telegram listener not started")
        return None
    t = threading.Thread(target=_poll_loop, args=(cfg,), daemon=True,
                         name="telegram-bot")
    t.start()
    return t
