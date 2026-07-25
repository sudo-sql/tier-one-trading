"""Universe scanner: finds actively trading listed stocks at/under $5.

Pulls the full NASDAQ/NYSE/AMEX listing from Nasdaq's screener API
(OTC is simply never in this feed), then filters on price, liquidity,
and spread. Falls back to a cached universe file if the API is down.
"""
from __future__ import annotations

import json
import logging
import os
import time

import requests

log = logging.getLogger("scanner")

SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}
CACHE_FILE = "universe_cache.json"
CACHE_TTL = 6 * 3600  # re-pull listings every 6 hours


def _fetch_listings() -> list[dict]:
    """All US-listed common stocks from the Nasdaq screener (no OTC)."""
    params = {"tableonly": "true", "limit": "25", "offset": "0", "download": "true"}
    r = requests.get(SCREENER_URL, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    rows = r.json()["data"]["rows"]
    return rows


def _parse_row(row: dict) -> dict | None:
    try:
        price = float(str(row.get("lastsale", "")).replace("$", "").replace(",", ""))
        volume = float(str(row.get("volume", "0")).replace(",", "") or 0)
    except ValueError:
        return None
    symbol = (row.get("symbol") or "").strip()
    # skip units/warrants/rights/preferreds — messy fills, odd behavior
    if not symbol or any(c in symbol for c in ("^", "/", ".", "~")) or len(symbol) > 5:
        return None
    if len(symbol) == 5 and symbol[-1] in "WRUP":  # warrants, rights, units, pfd
        return None
    return {
        "symbol": symbol,
        "price": price,
        "volume": volume,
        "exchange": (row.get("exchange") or "").upper(),
        "name": row.get("name", ""),
    }


def get_universe(cfg: dict) -> list[dict]:
    """Return filtered candidate list, cheapest liquidity-weighted first."""
    ucfg = cfg["universe"]
    rows = None

    if os.path.exists(CACHE_FILE) and time.time() - os.path.getmtime(CACHE_FILE) < CACHE_TTL:
        with open(CACHE_FILE) as f:
            rows = json.load(f)
    else:
        try:
            rows = _fetch_listings()
            with open(CACHE_FILE, "w") as f:
                json.dump(rows, f)
        except Exception as e:  # noqa: BLE001
            log.warning("Listing fetch failed (%s); trying stale cache", e)
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE) as f:
                    rows = json.load(f)
    if not rows:
        log.error("No universe data available")
        return []

    allowed_exchanges = {e.upper() for e in ucfg["exchanges"]}
    out = []
    for raw in rows:
        p = _parse_row(raw)
        if p is None:
            continue
        # Nasdaq feed labels exchanges NASDAQ / NYSE / AMEX
        if allowed_exchanges and p["exchange"] and p["exchange"] not in allowed_exchanges:
            continue
        if not (ucfg["min_price"] <= p["price"] <= ucfg["max_price"]):
            continue
        if p["price"] * p["volume"] < ucfg["min_avg_dollar_volume"]:
            continue
        out.append(p)

    # rank by dollar volume so the most tradable names get scanned first
    out.sort(key=lambda x: x["price"] * x["volume"], reverse=True)
    top = out[: ucfg["scan_top_n"]]
    log.info("Universe: %d candidates ≤ $%.2f (scanning top %d)",
             len(out), ucfg["max_price"], len(top))
    return top
