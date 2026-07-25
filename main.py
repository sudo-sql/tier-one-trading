"""TierOne Trading — main loop.

Scans sub-$5 listed stocks during premarket, regular, and after-hours
sessions; sends Telegram buy/sell entry signals; optionally executes
limit orders through Robinhood or Webull (off by default).

Run:  python main.py
"""
from __future__ import annotations

import csv
import logging
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

import notify
import scanner
import strategy
import telegram_bot
from brokers import get_broker

ET = ZoneInfo("America/New_York")
log = logging.getLogger("main")


# ---------------------------------------------------------------- helpers

def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def current_session(cfg: dict) -> str | None:
    now = datetime.now(ET)
    if now.weekday() >= 5:  # weekend
        return None
    hm = now.strftime("%H:%M")
    for name in ("premarket", "regular", "afterhours"):
        s = cfg["sessions"][name]
        if s["start"] <= hm < s["end"]:
            return name
    return None


def append_csv(path: str, row: dict):
    exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            w.writeheader()
        w.writerow(row)


# ---------------------------------------------------------------- position tracking

class Positions:
    """Open positions. State kept in memory + CSV log.

    Note: the old PDT rule (3 day trades / $25k minimum) was eliminated
    effective June 4, 2026 (FINRA Notice 26-10), so no day-trade counting
    is done here.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.open: dict[str, dict] = {}
        self.last_signal: dict[str, datetime] = {}

    def can_open(self, symbol: str) -> bool:
        c = self.cfg
        if symbol in self.open:
            return False
        if len(self.open) >= c["sizing"]["max_open_positions"]:
            return False
        cooldown = timedelta(minutes=c["strategy"]["cooldown_minutes"])
        last = self.last_signal.get(symbol)
        return last is None or datetime.now(ET) - last > cooldown

    def record_entry(self, sig):
        self.open[sig.symbol] = {
            "buy": sig.buy_entry, "sell": sig.sell_entry,
            "stop": sig.stop_loss, "shares": sig.shares,
            "cost_pct": sig.est_cost_pct, "opened": datetime.now(ET),
        }
        self.last_signal[sig.symbol] = datetime.now(ET)

    def record_exit(self, symbol: str):
        self.open.pop(symbol, None)


# ---------------------------------------------------------------- exit monitor

def check_exits(cfg: dict, positions: Positions, broker, extended: bool):
    for symbol, pos in list(positions.open.items()):
        df = strategy.fetch_bars(symbol, "1m")
        if df is None:
            continue
        last = float(df["Close"].iloc[-1])
        net_pct = 100 * (last - pos["buy"]) / pos["buy"] - pos["cost_pct"]

        kind = None
        if last >= pos["sell"]:
            kind = "TARGET HIT"
        elif last <= pos["stop"]:
            kind = "STOP"
        if kind is None:
            continue

        broker.sell_limit(symbol, pos["shares"], round(last, 4), extended)
        notify.send_exit_signal(cfg, symbol, kind, last, net_pct)
        positions.record_exit(symbol)
        append_csv(cfg["logging"]["trade_log_csv"], {
            "ts": datetime.now(ET).isoformat(), "symbol": symbol,
            "side": "SELL", "kind": kind, "price": last,
            "shares": pos["shares"], "net_pct": round(net_pct, 2),
        })


# ---------------------------------------------------------------- main loop

def run():
    cfg = load_config()
    logging.basicConfig(
        level=getattr(logging, cfg["logging"]["level"]),
        format="%(asctime)s %(name)-8s %(levelname)-7s %(message)s")

    broker = get_broker(cfg)
    positions = Positions(cfg)
    telegram_bot.start(cfg)  # /invite, /start <code>, /subscribers, /revoke
    mode = ("LIVE AUTO-TRADE" if cfg["execution"]["auto_trade"]
            and not cfg["execution"]["dry_run"] else
            "auto-trade DRY RUN" if cfg["execution"]["auto_trade"] else
            "signals only")
    log.info("TierOne Trading started — mode: %s, broker: %s", mode, broker.name)
    notify.send_status(cfg, f"TierOne Trading online — mode: {mode}")

    universe: list[dict] = []
    universe_ts = 0.0
    daily = {"date": None, "cycles": 0, "evals": 0, "signals": 0}
    heartbeat_sent: str | None = None

    while True:
        session = current_session(cfg)
        today = datetime.now(ET).strftime("%Y-%m-%d")

        if session is None:
            # daily heartbeat: fires once, right after the last session ends
            if daily["date"] == today and heartbeat_sent != today:
                notify.send_status(cfg, (
                    f"Market day done — {daily['evals']} stock checks across "
                    f"{daily['cycles']} scan cycles, {daily['signals']} signal(s) sent. "
                    f"All quiet is normal; scanning resumes 7:00 AM ET next trading day."))
                heartbeat_sent = today
            log.info("Market closed; sleeping 10 min")
            time.sleep(600)
            continue

        if daily["date"] != today:
            daily = {"date": today, "cycles": 0, "evals": 0, "signals": 0}

        extended = session != "regular"
        interval = (cfg["sessions"]["extended_hours_scan_interval_seconds"]
                    if extended else cfg["sessions"]["scan_interval_seconds"])

        # refresh universe hourly
        if time.time() - universe_ts > 3600 or not universe:
            universe = scanner.get_universe(cfg)
            universe_ts = time.time()

        # 1) manage open positions first
        check_exits(cfg, positions, broker, extended)

        # 2) hunt for new entries
        daily["cycles"] += 1
        for cand in universe:
            if not positions.can_open(cand["symbol"]):
                continue
            daily["evals"] += 1
            sig = strategy.evaluate(cand, session, cfg)
            if sig is None:
                continue
            daily["signals"] += 1
            log.info("SIGNAL %s %s buy=%.4f sell=%.4f", sig.setup,
                     sig.symbol, sig.buy_entry, sig.sell_entry)
            notify.send_buy_signal(cfg, sig)
            append_csv(cfg["logging"]["signal_log_csv"], {
                "ts": sig.ts.isoformat(), "symbol": sig.symbol,
                "setup": sig.setup, "session": sig.session,
                "buy_entry": sig.buy_entry, "sell_entry": sig.sell_entry,
                "sell_stretch": sig.sell_stretch, "stop": sig.stop_loss,
                "shares": sig.shares, "est_cost_pct": sig.est_cost_pct,
            })
            if cfg["execution"]["auto_trade"]:
                broker.buy_limit(sig.symbol, sig.shares, sig.buy_entry, extended)
                append_csv(cfg["logging"]["trade_log_csv"], {
                    "ts": sig.ts.isoformat(), "symbol": sig.symbol,
                    "side": "BUY", "kind": sig.setup, "price": sig.buy_entry,
                    "shares": sig.shares, "net_pct": "",
                })
            positions.record_entry(sig)

        time.sleep(interval)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nStopped.")
