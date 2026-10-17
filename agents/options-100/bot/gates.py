"""Volatility gates for options-100 (ROUTER.md, approved 2026-10-17).
Prints: prior ^VIX close, ^VIX9D/^VIX ratio, its 2-year bottom-tercile threshold, and the gate.
  term_gate BLOCK -> no long premium on any playbook today (0DTE straddle -30% in the bottom tercile vs -1% top).
  size_up   true  -> VIX >= 25 (the only band where long 0DTE premium was positive, +3-4%).
Usage: python3 agents/options-100/bot/gates.py [--json]"""
import json, os, sqlite3, sys
DB = os.path.join(os.path.dirname(__file__), "..", "data", "market.db")
c = sqlite3.connect(DB)
q = lambda s: dict(c.execute("SELECT ts, close FROM bars WHERE symbol=? AND interval='1d' AND ts < date('now','localtime') ORDER BY ts DESC LIMIT 504", (s,)).fetchall())
vix, v9 = q("^VIX"), q("^VIX9D")
days = sorted(set(vix) & set(v9))
ratios = sorted(v9[d] / vix[d] for d in days)
thr = ratios[len(ratios) // 3]
last = days[-1]; r = v9[last] / vix[last]
out = {"asof": last, "vix": round(vix[last], 2), "vix9d_vix": round(r, 3), "tercile_lo": round(thr, 3),
       "term_gate": "BLOCK" if r < thr else "PASS", "size_up": vix[last] >= 25}
print(json.dumps(out) if "--json" in sys.argv else " ".join(f"{k}={v}" for k, v in out.items()))
