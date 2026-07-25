# TierOne Trading — Setup Guide

**Goal: signals in your Telegram by premarket Monday, July 6, 2026 (7:00 AM ET).**
Do Part 1 tonight — it takes about 15 minutes. Parts 2–4 (inviting others, browser version, .exe) can wait.

---

## Part 1 — Start receiving Telegram signals (do this tonight)

### Step 1. Install Python (skip if you have it)

1. Go to https://www.python.org/downloads/ and install Python 3.11+.
2. **Check the box "Add Python to PATH"** during install — this matters.

### Step 2. Install the app's libraries

Open **Command Prompt** (Windows key, type `cmd`, Enter), then:

```
cd C:\Users\tjcas\Desktop\TierOneTrading
pip install -r requirements.txt
```

### Step 3. Create your Telegram bot (2 minutes)

1. Open Telegram and search for **@BotFather** (blue checkmark).
2. Send it: `/newbot`
3. It asks for a display name — e.g. `TierOne Signals`
4. It asks for a username — must end in `bot`, e.g. `TierOneTcBot`
5. BotFather replies with a **token** like `7712345678:AAH9x...`. **Copy it.**

### Step 4. Get your chat ID (automatic)

1. Put your bot token in `config.yaml` first (see Step 5).
2. Run: `python get_my_chat_id.py`
3. Send your bot any message ("hi") — the script prints your chat ID.

(Manual alternative: open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser after messaging the bot and find `"chat":{"id":123456789`.)

### Step 5. Put both values in config.yaml

Open `config.yaml` in Notepad and fill in:

```yaml
telegram:
  bot_token: "7712345678:AAH9x..."
  admin_chat_id: "123456789"
```

Save the file.

### Step 6. Start the app

```
cd C:\Users\tjcas\Desktop\TierOneTrading
python main.py
```

You should get a Telegram message within seconds: *"TierOne Trading online — mode: signals only"*. If you got that message, **you're done — leave the window running.** Scanning starts automatically at 7:00 AM ET Monday (premarket) and runs through after-hours (8:00 PM ET). Weekends it just sleeps.

**Keep the PC awake:** Settings → System → Power → set "Put my device to sleep" to **Never** (or at least while plugged in). If the PC sleeps, signals stop.

**To stop the app:** press Ctrl+C in the window. To restart: `python main.py`.

---

## Part 2 — Inviting other people (Telegram, invite-only)

You're the admin (your `admin_chat_id`). Nobody receives anything without a code from you.

1. In Telegram, message **your own bot**: `/invite`
2. It replies with a one-time code, e.g. `9F3A61BC`.
3. Send your friend the bot's username and the code. They open Telegram, find the bot, and send: `/start 9F3A61BC`
4. They're in — they now get every signal you get. You get a notification when someone joins.

Admin commands (only work from your account):

| Command | What it does |
|---|---|
| `/invite` | new one-time invite code |
| `/subscribers` | list everyone subscribed |
| `/revoke <chat_id>` | remove someone |
| `/myid` | show a chat id (works for anyone) |

Each code works exactly once. Subscribers can leave with `/stop`.

---

## Part 3 — Browser version (later priority)

Shows the identical notification feed in a web page, behind a login. Account creation requires a **web invite code** (separate from Telegram codes).

**Run it locally:**

```
cd C:\Users\tjcas\Desktop\TierOneTrading
python webapp.py new-invite     ← makes a code for you or a friend
python webapp.py                ← starts the site
```

Before first run, open `config.yaml` and change `web.secret_key` to any long random string. Then visit `http://localhost:8321`, click "Create account", use the invite code. Keep `main.py` running in another window — it produces the feed the site displays. The page auto-refreshes every 30 seconds.

**Put it online** (so people can check it from anywhere):

- Easiest: a $5/month VPS (DigitalOcean, Hetzner, Lightsail). Install Python, copy this folder, run `python main.py` and `python webapp.py` in two `screen`/`tmux` sessions. Point a domain at it and add HTTPS with Caddy (`caddy reverse-proxy --from yourdomain.com --to localhost:8321`).
- Render/Railway also work but their free tiers sleep, which breaks a scanner that must run all day.
- One machine runs everything: the same `main.py` feeds Telegram *and* the website.

---

## Part 4 — Building the .exe and sharing via GitHub (later priority)

### Build

Double-click **`build_exe.bat`** (or run it in cmd). When it finishes, your program is `dist\TierOneTrading.exe`. It's the whole signal engine + Telegram bot in one file — no Python needed on the machine that runs it. `config.yaml` must sit in the same folder as the exe.

### Upload to your GitHub

1. Create a repo at github.com (private is fine — you control access).
2. In cmd:

```
cd C:\Users\tjcas\Desktop\TierOneTrading
git init
git add .
git commit -m "TierOne Trading"
git branch -M main
git remote add origin https://github.com/YOURUSERNAME/TierOneTrading.git
git push -u origin main
```

The included `.gitignore` keeps `config.yaml`, subscriber lists, and logs **out** of the repo — your bot token and any passwords never get uploaded. The repo contains `config.example.yaml` instead; people copy it to `config.yaml` and add their own values.

3. For the exe specifically: on GitHub go to **Releases → Draft a new release**, attach `dist\TierOneTrading.exe`. (Releases handle big binaries better than the repo itself.)

### How invited people install it

1. You add them as a collaborator on the private repo (Settings → Collaborators), or just send the Release link.
2. They download `TierOneTrading.exe` + `config.example.yaml`, rename it `config.yaml`.
3. **Two ways they can receive signals:**
   - **Simple (recommended):** they don't run anything. You just `/invite` them on Telegram — your machine does all the work.
   - **Independent:** they run the exe themselves with their *own* BotFather token and their own chat id in their config — a fully separate copy.

Note: Windows SmartScreen will warn on an unsigned exe — they click "More info → Run anyway."

---

## What changed re: PDT

The old Pattern Day Trader rule (max 3 day trades per 5 days under $25k) was **eliminated effective June 4, 2026** (FINRA Notice 26-10; SEC-approved). It's replaced by real-time intraday margin standards, and this app no longer counts or limits day trades. One caveat: brokers have until **October 2027** to phase in the new framework, so if Robinhood/Webull briefly still shows PDT-style warnings, that's their rollout lag, not this app.

---

## Troubleshooting

- **No "online" message on startup** → token or chat id is wrong. Re-check Step 4; make sure you messaged your bot at least once before calling getUpdates.
- **`pip` not recognized** → Python wasn't added to PATH; reinstall and check the box.
- **No signals all day** → normal on quiet days; the filters are strict on purpose (spread, liquidity, cost-clearing). Check `signals.csv` and the console log. Loosen `min_avg_dollar_volume` or `max_spread_pct` in config if you want more (lower-quality) signals.
- **Universe fetch failed** → the Nasdaq screener API hiccuped; the app retries and uses a 6-hour cache. Persistent? Tell me and I'll swap data sources.
- **Friend's /start code rejected** → codes are one-time; generate a fresh `/invite` per person.
