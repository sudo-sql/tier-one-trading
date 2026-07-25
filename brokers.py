"""Broker execution adapters — Robinhood and Webull.

⚠️  IMPORTANT: Neither broker offers an official US retail trading API.
These adapters use community libraries (robin_stocks, unofficial webull).
Using them violates broker terms of service and could get your account
restricted. That is why:

  * execution.auto_trade defaults to false  (signals only)
  * execution.dry_run   defaults to true    (simulates even when enabled)

Both flags must be flipped deliberately in config.yaml to place real
orders. All orders are LIMIT orders — never market — because slippage on
sub-$5 stocks would destroy the 3-5% edge.
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger("brokers")


class DryRunBroker:
    name = "dry-run"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def buy_limit(self, symbol: str, shares: int, limit: float, extended: bool) -> dict:
        log.info("[DRY RUN] BUY %d %s @ limit $%.4f (ext=%s)", shares, symbol, limit, extended)
        return {"status": "simulated", "side": "buy", "symbol": symbol,
                "shares": shares, "limit": limit}

    def sell_limit(self, symbol: str, shares: int, limit: float, extended: bool) -> dict:
        log.info("[DRY RUN] SELL %d %s @ limit $%.4f (ext=%s)", shares, symbol, limit, extended)
        return {"status": "simulated", "side": "sell", "symbol": symbol,
                "shares": shares, "limit": limit}


class RobinhoodBroker:
    name = "robinhood"

    def __init__(self, cfg: dict):
        import robin_stocks.robinhood as rh  # pip install robin_stocks
        self.rh = rh
        rcfg = cfg["execution"]["robinhood"]
        self.rh.login(rcfg["username"], rcfg["password"])  # caches MFA session

    def buy_limit(self, symbol, shares, limit, extended):
        return self.rh.orders.order_buy_limit(
            symbol, shares, limit,
            timeInForce="gfd", extendedHours=extended)

    def sell_limit(self, symbol, shares, limit, extended):
        return self.rh.orders.order_sell_limit(
            symbol, shares, limit,
            timeInForce="gfd", extendedHours=extended)


class WebullBroker:
    name = "webull"

    def __init__(self, cfg: dict):
        from webull import webull  # pip install webull
        wcfg = cfg["execution"]["webull"]
        self.wb = webull()
        self.wb.login(wcfg["email"], wcfg["password"])
        self.wb.get_trade_token(wcfg["trade_pin"])

    def buy_limit(self, symbol, shares, limit, extended):
        return self.wb.place_order(stock=symbol, action="BUY", orderType="LMT",
                                   enforce="GTC", quant=shares, price=limit,
                                   outsideRegularTradingHour=extended)

    def sell_limit(self, symbol, shares, limit, extended):
        return self.wb.place_order(stock=symbol, action="SELL", orderType="LMT",
                                   enforce="GTC", quant=shares, price=limit,
                                   outsideRegularTradingHour=extended)


def get_broker(cfg: dict):
    ex = cfg["execution"]
    if not ex["auto_trade"] or ex["dry_run"]:
        return DryRunBroker(cfg)
    if ex["broker"] == "robinhood":
        return RobinhoodBroker(cfg)
    if ex["broker"] == "webull":
        return WebullBroker(cfg)
    raise ValueError(f"Unknown broker: {ex['broker']}")


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "login-rh":
    # one-time interactive Robinhood login to cache the MFA session
    import yaml
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    import robin_stocks.robinhood as rh
    rh.login(cfg["execution"]["robinhood"]["username"],
             cfg["execution"]["robinhood"]["password"])
    print("Robinhood session cached.")
