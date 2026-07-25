"""Signal engine.

Two setups, both long-only (sub-$5 stocks are hard/impossible to short
on Robinhood/Webull):

  1. VWAP mean-reversion — price dips >= vwap_discount_pct under VWAP
     with RSI oversold, in an uptrending or flat tape.
  2. Volume breakout — price clears the recent consolidation high on a
     volume surge.

Every signal carries an exact BUY ENTRY (limit price) and SELL ENTRY
(limit price) such that, after modeled slippage + spread + SEC/TAF fees,
the net gain lands in [net_target_pct_min, net_target_pct_max].
A signal is suppressed if the setup can't plausibly reach that target
(e.g., target above recent high, or spread too wide to clear costs).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

log = logging.getLogger("strategy")


# ---------------------------------------------------------------- costs

def round_trip_cost_pct(price: float, shares: int, cfg: dict) -> float:
    """Total round-trip cost as % of position value.

    Includes: slippage both sides, half-spread both sides (approximated
    via slippage config when live spread unknown), SEC fee + FINRA TAF
    on the sell, commissions (zero at RH/Webull).
    """
    c = cfg["costs"]
    notional = price * shares
    if notional <= 0:
        return math.inf
    slip = 2 * c["slippage_pct"]                       # % both sides
    sec = (notional / 1_000_000) * c["sec_fee_per_million"]
    taf = min(shares * c["finra_taf_per_share"], 8.30)
    comm = 2 * c["commission_per_trade"]
    fixed_pct = 100 * (sec + taf + comm) / notional
    return slip + fixed_pct


def compute_entries(last: float, spread_pct: float, cfg: dict) -> dict | None:
    """Return buy/sell/stop limit prices that net the target after costs."""
    s = cfg["strategy"]
    shares = max(1, int(cfg["sizing"]["capital_per_trade"] // last))
    cost_pct = round_trip_cost_pct(last, shares, cfg) + spread_pct  # half-spread x2
    if cost_pct >= s["net_target_pct_min"]:
        return None  # costs alone would eat the minimum target — skip

    buy = round(last * (1 + cfg["costs"]["slippage_pct"] / 100), 4)
    gross_needed_min = s["net_target_pct_min"] + cost_pct
    gross_needed_max = s["net_target_pct_max"] + cost_pct
    sell_min = round(buy * (1 + gross_needed_min / 100), 4)
    sell_max = round(buy * (1 + gross_needed_max / 100), 4)
    stop = round(buy * (1 - (s["stop_loss_pct"] + cost_pct / 2) / 100), 4)
    return {
        "shares": shares,
        "buy_entry": buy,
        "sell_entry": sell_min,        # primary target (min net %)
        "sell_stretch": sell_max,      # stretch target (max net %)
        "stop_loss": stop,
        "est_cost_pct": round(cost_pct, 3),
        "net_min_pct": s["net_target_pct_min"],
        "net_max_pct": s["net_target_pct_max"],
    }


# ---------------------------------------------------------------- indicators

def rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def session_vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    pv = (tp * df["Volume"]).cumsum()
    vv = df["Volume"].cumsum().replace(0, 1e-10)
    return pv / vv


# ---------------------------------------------------------------- signals

@dataclass
class Signal:
    symbol: str
    setup: str
    session: str
    last: float
    shares: int
    buy_entry: float
    sell_entry: float
    sell_stretch: float
    stop_loss: float
    est_cost_pct: float
    net_min_pct: float
    net_max_pct: float
    reason: str
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def fetch_bars(symbol: str, interval: str = "5m") -> pd.DataFrame | None:
    try:
        df = yf.download(symbol, period="1d", interval=interval,
                         prepost=True, progress=False, auto_adjust=False)
        if df is None or df.empty or len(df) < 15:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("%s: bar fetch failed: %s", symbol, e)
        return None


def evaluate(candidate: dict, session: str, cfg: dict) -> Signal | None:
    s = cfg["strategy"]
    sym = candidate["symbol"]
    df = fetch_bars(sym, s["bar_interval"])
    if df is None:
        return None

    close = df["Close"].astype(float)
    last = float(close.iloc[-1])
    if not (cfg["universe"]["min_price"] <= last <= cfg["universe"]["max_price"]):
        return None

    # live spread estimate from recent bar range (proxy when no L1 quotes)
    recent = df.tail(6)
    est_spread_pct = float(
        100 * (recent["High"] - recent["Low"]).mean() / max(last, 1e-9) / 4
    )
    if est_spread_pct > cfg["universe"]["max_spread_pct"]:
        return None

    r = rsi(close, s["rsi_period"])
    vwap = session_vwap(df)
    cur_rsi = float(r.iloc[-1])
    cur_vwap = float(vwap.iloc[-1])
    vol = df["Volume"].astype(float)
    avg_vol = float(vol.iloc[:-1].tail(s["breakout_lookback_bars"]).mean() or 0)
    cur_vol = float(vol.iloc[-1])

    setup = reason = None

    # --- Setup 1: VWAP mean-reversion
    discount = 100 * (cur_vwap - last) / cur_vwap if cur_vwap > 0 else 0
    if discount >= s["vwap_discount_pct"] and cur_rsi <= s["rsi_oversold"]:
        setup = "VWAP dip"
        reason = f"{discount:.1f}% under VWAP, RSI {cur_rsi:.0f}"

    # --- Setup 2: volume breakout
    if setup is None and len(close) > s["breakout_lookback_bars"] + 1:
        lookback_high = float(
            df["High"].iloc[:-1].tail(s["breakout_lookback_bars"]).max()
        )
        if (last > lookback_high and avg_vol > 0
                and cur_vol >= s["volume_surge_ratio"] * avg_vol
                and cur_rsi < 75):
            setup = "Volume breakout"
            reason = (f"broke {s['breakout_lookback_bars']}-bar high "
                      f"${lookback_high:.2f} on {cur_vol/avg_vol:.1f}x volume")

    if setup is None:
        return None

    entries = compute_entries(last, est_spread_pct, cfg)
    if entries is None:
        return None

    # sanity: target must be within today's demonstrated range * 1.5
    day_high = float(df["High"].max())
    day_low = float(df["Low"].min())
    day_range = day_high - day_low
    if entries["sell_entry"] > day_high + 0.5 * day_range:
        return None  # target beyond what this tape has shown — skip

    return Signal(symbol=sym, setup=setup, session=session, last=last,
                  reason=reason, **entries)
