#!/usr/bin/env python3
"""P5 shock detector: largest odds move among tracked iran/fed/midterms/trump markets between the latest snapshot
and the last snapshot at/before the prior 16:00 ET close (and vs. the snapshot ~15 min earlier). Prints SHOCK lines >= threshold."""
import sqlite3, sys, os
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "market.db")
thr = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
c = sqlite3.connect(DB); hits = []
for mid, q, topic, vol in c.execute("SELECT market_id, question, topic, volume FROM pm_markets WHERE source='poly' AND topic IN ('iran','fed','midterms','trump','oil') AND volume >= 1e6"):
    pts = c.execute("SELECT ts, prob FROM pm_prices WHERE source='poly' AND market_id=? AND length(ts)=16 ORDER BY ts DESC LIMIT 40", (mid,)).fetchall()
    if len(pts) < 2: continue
    last_ts, last = pts[0]
    day = last_ts[:10]
    prior_close = next((p for t, p in pts if t < day + " 09:30"), None)
    prev = pts[1][1]
    for ref, lab in ((prior_close, "since close"), (prev, "15m")):
        if ref is not None and abs(last - ref) * 100 >= thr:
            hits.append((abs(last - ref), f"SHOCK {(last-ref)*100:+.0f}pt {lab} now {last*100:.0f}% [{topic}] {q[:70]} #{mid}"))
for _, h in sorted(hits, reverse=True)[:5]: print(h)
if not hits: print(f"no shock (thr {thr:g}pt)")
