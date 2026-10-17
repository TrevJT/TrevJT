#!/usr/bin/env python3
"""Robustness for pm_shocks.py: one event per (60-minute bucket) across all signed iran/oil markets, so that one headline that moves
five markets counts once. Direction = sign of the |move|-weighted sum of risk-off impulses. Reports CL, QQQ, SPY returns 1h/4h/24h after,
plus a by-year split (the whole effect is 2026)."""
import numpy as np, pandas as pd
from common import *
import pm_shocks as P


def rsign(q, t):
    ql = q.lower()
    if t == "iran":
        return -1 if any(w in ql for w in ["ceasefire", "normal", "peace", "deal", "reopen", "returns to normal"]) else 1
    if t == "oil":
        return 1
    return 0


def main():
    p = P.load_pm(); p["ts"] = p.ts.dt.tz_localize("America/New_York")
    H = {s: P.hourly(s) for s in ["QQQ", "CL=F", "SPY"]}
    for pts in [5, 8]:
        e = P.events(p, pts)
        e["rs"] = [rsign(q, t) for q, t in zip(e.question, e.topic)]
        e = e[e.rs != 0].copy(); e["signed"] = np.sign(e.move) * e.rs
        e["bucket"] = e.ts.dt.floor("60min")
        c = e.groupby("bucket").apply(lambda g: pd.Series(dict(signed=np.sign((g.signed * g.move.abs()).sum()), n=len(g)))).reset_index()
        c = c[c.signed != 0]
        rows = []
        for sym, expect in [("CL=F", 1), ("QQQ", -1), ("SPY", -1)]:
            for hrs, label in [(1, "a1"), (4, "a4"), (24, "a24")]:
                x = []
                for t, sg in zip(c.bucket, c.signed):
                    rb, ra = P.asset_ret(H[sym], t, hrs); x.append(sg * expect * ra)
                x = np.array(x, float); x = x[np.isfinite(x)]
                rows.append(dict(pts=pts, sym=sym, h=label, n_clusters=len(x), mean_bp=round(x.mean() * 1e4, 1), hit=round((x > 0).mean(), 3), t=round(tstat(x), 2)))
        print(pd.DataFrame(rows).to_string(index=False))
        c["yr"] = c.bucket.dt.year
        for yr, g in c.groupby("yr"):
            x = []
            for t, sg in zip(g.bucket, g.signed):
                rb, ra = P.asset_ret(H["CL=F"], t, 24); x.append(sg * ra)
            x = np.array(x, float); x = x[np.isfinite(x)]
            print(f"  CL a24 {yr}: n={len(x)} mean={x.mean() * 1e4:+.1f}bp t={tstat(x):.2f}")


if __name__ == "__main__":
    main()
