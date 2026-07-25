"""Telegram notifications — broadcasts to ALL approved subscribers.

Subscribers live in subscribers.json (managed by telegram_bot.py via
invite codes). Every notification is also appended to notifications.jsonl
so the browser version shows the identical feed.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import requests

log = logging.getLogger("notify")

API = "https://api.telegram.org/bot{token}/{method}"
SUBSCRIBERS_FILE = "subscribers.json"
FEED_FILE = "notifications.jsonl"


def load_subscribers() -> dict:
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE) as f:
            return json.load(f)
    return {}


def save_subscribers(subs: dict):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(subs, f, indent=2)


def _recipients(cfg: dict) -> list[str]:
    ids = set(load_subscribers().keys())
    admin = str(cfg["telegram"].get("admin_chat_id") or "")
    if admin:
        ids.add(admin)
    return sorted(ids)


def _log_to_feed(kind: str, text: str):
    """Append to the shared feed the web app reads."""
    try:
        with open(FEED_FILE, "a") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "text": text,
            }) + "\n")
    except Exception as e:  # noqa: BLE001
        log.error("Feed write failed: %s", e)


def send_to_chat(cfg: dict, chat_id: str, text: str) -> bool:
    try:
        r = requests.post(
            API.format(token=cfg["telegram"]["bot_token"], method="sendMessage"),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        log.error("Telegram send to %s failed: %s", chat_id, e)
        return False


def _broadcast(cfg: dict, kind: str, text: str) -> bool:
    _log_to_feed(kind, text)
    if not cfg["telegram"].get("bot_token"):
        log.warning("Telegram not configured — printing instead:\n%s", text)
        print(text)
        return False
    recipients = _recipients(cfg)
    if not recipients:
        log.warning("No subscribers yet — set telegram.admin_chat_id in config.yaml")
        print(text)
        return False
    ok = 0
    for chat_id in recipients:
        if send_to_chat(cfg, chat_id, text):
            ok += 1
    log.info("Broadcast '%s' delivered to %d/%d subscribers", kind, ok, len(recipients))
    return ok > 0


def send_buy_signal(cfg: dict, sig) -> bool:
    mode = ("AUTO-TRADING" if cfg["execution"]["auto_trade"] and not cfg["execution"]["dry_run"]
            else "SIGNAL ONLY")
    text = (
        f"🟢 <b>BUY {sig.symbol}</b>  [{sig.session}] [{mode}]\n"
        f"Setup: {sig.setup} — {sig.reason}\n"
        f"Last: ${sig.last:.4f}\n"
        f"\n"
        f"BUY ENTRY (limit):  <b>${sig.buy_entry:.4f}</b>\n"
        f"SELL ENTRY (limit): <b>${sig.sell_entry:.4f}</b>  (+{sig.net_min_pct:.1f}% net)\n"
        f"Stretch target:     ${sig.sell_stretch:.4f}  (+{sig.net_max_pct:.1f}% net)\n"
        f"Stop loss:          ${sig.stop_loss:.4f}\n"
        f"\n"
        f"Size: {sig.shares} sh (~${sig.shares * sig.buy_entry:.0f})\n"
        f"Est. round-trip costs: {sig.est_cost_pct:.2f}% (already baked into targets)"
    )
    return _broadcast(cfg, "BUY", text)


def send_exit_signal(cfg: dict, symbol: str, kind: str, price: float, net_pct: float) -> bool:
    emoji = "🔴" if kind == "STOP" else "💰"
    text = (
        f"{emoji} <b>SELL {symbol}</b> — {kind}\n"
        f"Exit at: <b>${price:.4f}</b>\n"
        f"Net P/L: {net_pct:+.2f}% after est. fees/slippage"
    )
    return _broadcast(cfg, "SELL", text)


def send_status(cfg: dict, text: str) -> bool:
    return _broadcast(cfg, "STATUS", f"ℹ️ {text}")
