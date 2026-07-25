# TierOne Trading

Scans US-listed stocks trading at **$5 or less** (NASDAQ / NYSE / AMEX only — no OTC) across **premarket (7:00–9:30), regular (9:30–16:00), and after-hours (16:00–20:00) ET**, and sends **Telegram signals with exact buy and sell entry prices** that already account for slippage, spread, and SEC/FINRA fees. Targets **3–5% net profit per trade**. Optional auto-execution via Robinhood or Webull (off by default).

## Quick start

```
pip install -r requirements.txt
python main.py
```

Until Telegram is configured, signals print to the console.

## Telegram setup (5 minutes, free)

1. In Telegram, message **@BotFather** → `/newbot` → pick a name. Copy the **bot token**.
2. Message your new bot anything (e.g., "hi").
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and copy the `"chat":{"id": ...}` number.
4. Put both values in `config.yaml` under `telegram:`.

## What a signal looks like

```
🟢 BUY SNDL  [premarket] [SIGNAL ONLY]
Setup: VWAP dip — 1.4% under VWAP, RSI 27
Last: $1.9400

BUY ENTRY (limit):  $1.9449
SELL ENTRY (limit): $2.0163  (+3.0% net)
Stretch target:     $2.0552  (+5.0% net)
Stop loss:          $1.8896

Size: 51 sh (~$99)
Est. round-trip costs: 0.67% (already baked into targets)
```

The sell entry is computed so that after modeled slippage (0.25%/side), spread, and SEC + FINRA TAF sell fees, your **net** gain is at least the 3% floor. If costs would eat the edge (wide spread, illiquid name), no signal is sent.

## Strategy

Long-only, two setups:

**VWAP mean-reversion** — price ≥1% below session VWAP with RSI ≤ 30. **Volume breakout** — price clears the 30-bar consolidation high on ≥2x average volume.

Liquidity filters: ≥$500k daily dollar volume, estimated spread ≤1%, warrants/units/rights excluded. All tunable in `config.yaml`.

## Auto-trading (read before enabling)

`execution.auto_trade` is **false** by default, and `dry_run` is **true**. To place real orders you must flip both — deliberately.

**Know the risks:** Robinhood and Webull have **no official retail trading API**. This app uses community libraries (`robin_stocks`, `webull`) that automate the same endpoints their apps use. That **violates their terms of service** and accounts have been restricted for it. Use at your own risk, and consider keeping only your trading capital at that broker.

Steps: uncomment the broker lines in `requirements.txt`, `pip install` them, fill credentials in `config.yaml`, run `python brokers.py login-rh` once for Robinhood MFA, then set `auto_trade: true` (keep `dry_run: true` for a few sessions first). All orders are **limit orders** — never market.

## Guardrails built in

Max 3 open positions; max 3 day trades per rolling 5 days (**PDT rule** — with under $25k on a margin account, a 4th day trade flags your account; a cash account avoids PDT but T+1 settlement ties up funds); 90-min per-ticker cooldown; per-trade stop loss (~2.5% net); signals suppressed when the target exceeds 1.5x the day's demonstrated range.

## Honest caveats

- No strategy guarantees 3–5% per trade — that's the *target the math is built around*, not a promise. Expect losers; the stop loss caps them.
- Free data (yfinance) is delayed ~1–2 min in extended hours and thin premarket bars can be noisy. Validate in signal-only mode for a couple of weeks before trusting it with auto-execution.
- Extended-hours fills on Robinhood/Webull require limit orders (enforced here) and spreads are wider — expect fewer premarket/after-hours signals; that's the filters working.
- SEC fee rate (`sec_fee_per_million`) changes periodically — verify the current rate at sec.gov and update `config.yaml`.
- Sub-$5 stocks are volatile and occasionally halted. Position sizing ($25–100) keeps any single blowup small.

## Files

`main.py` loop/scheduler · `scanner.py` universe · `strategy.py` signals & cost math · `notify.py` Telegram · `brokers.py` execution · `config.yaml` all settings · `signals.csv` / `trades.csv` logs (created on first run)
