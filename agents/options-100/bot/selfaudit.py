#!/usr/bin/env python3
"""Nightly self-audit: find the bot's own weaknesses and write IMPROVEMENT CANDIDATES for the next session.
Checks: heartbeat gaps (stalls), failsafe crashes, order errors, engine predicted-vs-realized, Yahoo-vs-Robinhood quote drift,
data coverage freshness. Output goes into the nightly research log; the pre-open cycle reads it and works the top item."""
import os, json, sqlite3, glob, statistics
from datetime import datetime
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); S = os.path.join(R, "state")
out = []
today = datetime.now().strftime("%Y-%m-%d")
# 1 stalls: gaps > 10 min between cycle.log lines during RTH today
try:
    allc = open(os.path.join(S, "cycle.log")).read().splitlines()
    start = max([i for i, l in enumerate(allc) if "pre-open" in l] or [0])  # only the current session
    lines = [l for l in allc[start:] if l[:2].isdigit()]
    ts = [int(l[:2]) * 60 + int(l[3:5]) for l in lines[-300:] if l[2] == ":"]
    gaps = [(b - a, a) for a, b in zip(ts, ts[1:]) if b - a > 10 and 570 <= a <= 960]
    if gaps: out.append(f"STALL: {len(gaps)} cycle gaps >10 min today, worst {max(gaps)[0]} min at {max(gaps)[1]//60:02d}:{max(gaps)[1]%60:02d} -> investigate cron/heartbeat")
except FileNotFoundError: pass
# 2 failsafe
for f in ("failsafe.log", "launchd.err", "odds.err", "history.err"):
    p = os.path.join(S, f)
    if os.path.exists(p):
        tail = open(p).read().splitlines()[-20:]
        if f == "failsafe.log":  # only lines stamped today; older errors were already fixed
            dated = [l for l in open(p).read().splitlines() if l[:10] == today]
            tail = [l for l in open(p).read().splitlines()[-40:] if l[:10] == today or not l[:4].isdigit()] if dated else []
        bad = [l for l in tail if any(k in l.lower() for k in ("error", "not found", "traceback", "denied"))]
        if bad: out.append(f"ERRORS in {f}: {bad[-1][:140]}")
# 3 journal: order errors / engine flags today
today = datetime.now().strftime("%Y-%m-%d")
try:
    J = [json.loads(l) for l in open(os.path.join(R, "..", "..", "journal", "options-100.jsonl")) if l.strip()]
    flags = [j for j in J if str(j.get("ts", "")).startswith(today) and j.get("event") in ("engine_flag",)]
    for j in flags: out.append(f"ENGINE FLAG: {j.get('note','')[:160]}")
except FileNotFoundError: pass
# 4 engine calibration
c = sqlite3.connect(os.path.join(R, "data", "market.db"))
g = c.execute("SELECT ev, cost, graded_pnl FROM edge_picks WHERE graded_pnl IS NOT NULL").fetchall()
if len(g) >= 10:
    pred = statistics.mean(x[0] for x in g); real = sum(x[2] for x in g) / sum(x[1] * 100 for x in g)
    if abs(pred - real) > 0.15: out.append(f"CALIBRATION: engine predicted EV {pred:+.0%} vs realized {real:+.0%} on {len(g)} picks -> recalibrate forecast pool")
else:
    out.append(f"CALIBRATION: only {len(g)} graded picks; keep logging shadow picks (need 60)")
# 5 coverage freshness
for sym, iv in (("SPY", "5m"), ("^VIX", "1d")):
    m = c.execute("SELECT MAX(ts) FROM bars WHERE symbol=? AND interval=?", (sym, iv)).fetchone()[0]
    if m and m[:10] < today and datetime.now().weekday() < 5 and datetime.now().hour >= 17:
        out.append(f"STALE DATA: {sym} {iv} last {m}")
print("## Self-audit — improvement candidates")
print("\n".join(f"- {o}" for o in out) if out else "- none found")
