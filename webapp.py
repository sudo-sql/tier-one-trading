"""TierOne Trading — browser version (invite-only, later priority).

Shows the exact same notifications sent via Telegram, in a web page.
Account creation requires an invite code you generate; not public.

Run the server:      python webapp.py
Create web invite:   python webapp.py new-invite
The signal engine (main.py) must be running on the same machine —
this app just reads notifications.jsonl that main.py/notify.py writes.

Deploy online: any host that runs Python (Render, Railway, a $5 VPS).
Copy the whole folder, run main.py and webapp.py side by side.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import datetime, timezone
from functools import wraps

import yaml
from flask import (Flask, jsonify, redirect, render_template_string,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

USERS_FILE = "web_users.json"
WEB_INVITES_FILE = "web_invites.json"
FEED_FILE = "notifications.jsonl"


def _load(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _save(path: str, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


with open("config.yaml") as f:
    CFG = yaml.safe_load(f)

app = Flask(__name__)
app.secret_key = CFG["web"]["secret_key"]


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "user" not in session:
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper


# ------------------------------------------------------------------ pages

BASE_CSS = """
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;
--dim:#8b949e;--green:#3fb950;--red:#f85149;--gold:#d29922;--accent:#58a6ff}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif;
min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:24px 12px}
.wrap{width:100%;max-width:640px}
h1{font-size:20px;letter-spacing:.5px;margin-bottom:2px}
.sub{color:var(--dim);font-size:13px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;
padding:16px;margin-bottom:12px;white-space:pre-wrap;font-variant-numeric:tabular-nums}
.card.BUY{border-left:3px solid var(--green)}
.card.SELL{border-left:3px solid var(--gold)}
.card.STATUS{border-left:3px solid var(--accent);color:var(--dim)}
.ts{color:var(--dim);font-size:12px;margin-bottom:6px}
input,button{width:100%;padding:10px 12px;margin-top:10px;border-radius:8px;
border:1px solid var(--border);background:#0d1117;color:var(--text);font-size:15px}
button{background:var(--accent);color:#0d1117;font-weight:600;border:none;cursor:pointer}
a{color:var(--accent);text-decoration:none;font-size:13px}
.topbar{display:flex;justify-content:space-between;align-items:baseline;width:100%;max-width:640px}
.err{color:var(--red);font-size:13px;margin-top:8px}
.empty{color:var(--dim);text-align:center;padding:40px 0}
b{color:var(--text)}
"""

FEED_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TierOne Signals</title><style>""" + BASE_CSS + """</style></head><body>
<div class="topbar"><div><h1>⚡ TierOne Signals</h1>
<div class="sub">same feed as Telegram · refreshes every 30s</div></div>
<a href="/logout">log out ({{user}})</a></div>
<div class="wrap" id="feed">{{ body|safe }}</div>
<script>
async function refresh(){
  const r = await fetch('/api/feed'); const html = await r.text();
  document.getElementById('feed').innerHTML = html;
}
setInterval(refresh, 30000);
</script></body></html>"""

AUTH_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TierOne — {{title}}</title><style>""" + BASE_CSS + """</style></head><body>
<div class="wrap" style="max-width:360px;margin-top:8vh">
<h1>⚡ TierOne Trading</h1><div class="sub">{{title}}</div>
<form method="post">
{% if mode == 'register' %}<input name="invite" placeholder="Invite code" required>{% endif %}
<input name="username" placeholder="Username" required>
<input name="password" type="password" placeholder="Password" required>
<button>{{title}}</button>
{% if error %}<div class="err">{{error}}</div>{% endif %}
</form>
<p style="margin-top:14px">{% if mode == 'register' %}
<a href="/login">Already have an account? Log in</a>
{% else %}<a href="/register">Have an invite code? Create account</a>{% endif %}</p>
</div></body></html>"""


def _render_feed_items() -> str:
    items = []
    if os.path.exists(FEED_FILE):
        with open(FEED_FILE) as f:
            for line in f:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    items = items[-100:][::-1]  # newest first, last 100
    if not items:
        return '<div class="empty">No signals yet — they\'ll appear here as they fire.</div>'
    out = []
    for it in items:
        ts = it["ts"][:16].replace("T", " ") + " UTC"
        # telegram HTML uses <b>/<code>; safe subset, render as-is
        out.append(f'<div class="card {it["kind"]}"><div class="ts">{ts}</div>{it["text"]}</div>')
    return "\n".join(out)


@app.route("/")
@login_required
def feed():
    return render_template_string(FEED_HTML, user=session["user"],
                                  body=_render_feed_items())


@app.route("/api/feed")
@login_required
def api_feed():
    return _render_feed_items()


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        users = _load(USERS_FILE)
        u = request.form["username"].strip().lower()
        if u in users and check_password_hash(users[u]["pw"], request.form["password"]):
            session["user"] = u
            return redirect(url_for("feed"))
        error = "Wrong username or password."
    return render_template_string(AUTH_HTML, title="Log in", mode="login", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        code = request.form["invite"].strip().upper()
        invites = _load(WEB_INVITES_FILE)
        if code not in invites or invites[code].get("used_by"):
            error = "Invalid or already-used invite code."
        else:
            users = _load(USERS_FILE)
            u = request.form["username"].strip().lower()
            if not u or u in users:
                error = "Username taken or empty."
            elif len(request.form["password"]) < 8:
                error = "Password must be at least 8 characters."
            else:
                users[u] = {"pw": generate_password_hash(request.form["password"]),
                            "created": datetime.now(timezone.utc).isoformat(),
                            "invite": code}
                invites[code]["used_by"] = u
                _save(USERS_FILE, users)
                _save(WEB_INVITES_FILE, invites)
                session["user"] = u
                return redirect(url_for("feed"))
    return render_template_string(AUTH_HTML, title="Create account",
                                  mode="register", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------------ CLI

def new_web_invite() -> str:
    invites = _load(WEB_INVITES_FILE)
    code = secrets.token_hex(4).upper()
    invites[code] = {"created": datetime.now(timezone.utc).isoformat(), "used_by": None}
    _save(WEB_INVITES_FILE, invites)
    return code


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "new-invite":
        print(f"Web invite code: {new_web_invite()}")
        print("Give this to one person — it works once, at /register.")
    else:
        if CFG["web"]["secret_key"] == "change-me-to-something-random":
            print("⚠️  Set web.secret_key in config.yaml to a random string first!")
        app.run(host=CFG["web"]["host"], port=CFG["web"]["port"])
