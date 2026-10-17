#!/usr/bin/env python3
"""Replay the 2026-10-16 QQQ 0DTE put signal (S -6 at 09:51) on REAL option quotes (option_snaps, ~15-minute cadence) under the exit variants,
and the same for every other 0DTE SPY/QQQ snapshot day (Oct 8-16) with a synthetic 'signal' at 09:51 in both directions, to show how the
rules behave on real prices. Real quotes are 15 minutes apart, so a -45% stop is checked at that cadence (the bot checks every 1-2 minutes:
the real stop would have hit at least as early)."""
import sqlite3, json
import numpy as np, pandas as pd
from common import *


def path(sym, day, typ, strike):
    with db() as c:
        q = pd.read_sql("select ts, bid, ask, underlying from option_snaps where symbol=? and expiry=? and type=? and strike=? and substr(ts,1,10)=? order by ts",
                        c, params=(sym, day, typ, strike, day))
    q["ts"] = pd.to_datetime(q.ts, format="mixed"); q["mid"] = (q.bid + q.ask) / 2
    return q[q.bid > 0]


def simulate(q, entry_ts, half=0.02):
    q = q[q.ts >= entry_ts].reset_index(drop=True)
    if len(q) < 3:
        return None
    entry = q.mid.iloc[0] * (1 + half); bid = q.mid * (1 - half)
    pnl = bid / entry - 1
    mins = (q.ts - q.ts.iloc[0]).dt.total_seconds() / 60
    out = {"entry": round(entry, 3), "entry_ts": str(q.ts.iloc[0])[11:16], "n_marks": len(q)}
    end = q[q.ts.dt.hour * 60 + q.ts.dt.minute <= 15 * 60 + 45]
    i_end = end.index[-1]
    def first(cond):
        idx = np.where(cond.to_numpy() & (q.index <= i_end))[0]
        return int(idx[0]) if len(idx) else i_end
    rules = {
        "R0_written": first((pnl <= -0.45) | (pnl >= 1.0) | ((mins >= 30) & (pnl < 0.25)) | ((q.ts.dt.hour >= 12) & (pnl < 0.5))),
        "R1_hold_1545": i_end,
        "R2_tp2x_hold": first(q.mid >= 2 * entry),
        "R4_vwap_cross": None,
        "R6_stop45_only": first(pnl <= -0.45),
        "R3_stop70_tp2x": first((pnl <= -0.70) | (q.mid >= 2 * entry)),
    }
    for k, i in rules.items():
        if i is None:
            continue
        r = pnl.iloc[i]
        if k in ("R2_tp2x_hold", "R3_stop70_tp2x") and q.mid.iloc[i] >= 2 * entry:
            r = 1.0
        out[k] = dict(ret=round(float(r), 3), exit=str(q.ts.iloc[i])[11:16])
    out["max_mid"] = round(float(q.mid.max()), 2); out["min_pnl"] = round(float(pnl.min()), 3)
    return out


def main():
    res = {}
    # the actual case: QQQ 715P on 2026-10-16, signal 09:51 (first real mark at/after 09:51)
    q = path("QQQ", "2026-10-16", "put", 715.0)
    print("QQQ 2026-10-16 715P marks:"); print(q[["ts", "bid", "ask", "underlying"]].to_string(index=False))
    r = simulate(q, pd.Timestamp("2026-10-16 09:51"))
    print("\nexit variants on the real path:", json.dumps(r, indent=1)); res["qqq_715p_1016"] = r
    # other strikes that fit the 0.10-0.20 delta / $0.15-0.40 rule at 09:51 that day
    with db() as c:
        cands = pd.read_sql("select strike, bid, ask, underlying from option_snaps where symbol='QQQ' and expiry='2026-10-16' and type='put' and ts>='2026-10-16 09:50' and ts<='2026-10-16 10:00' and bid>0 order by ts, strike", c)
    print("\ncandidate puts 09:50-10:00:"); print(cands[(cands.ask >= 0.15) & (cands.ask <= 0.5)].to_string(index=False))
    # all snapshot days: ATM-ish single (nearest $1 strike to spot at 09:51) in BOTH directions, to show the rules on real prices
    rows = []
    with db() as c:
        days = pd.read_sql("select distinct symbol, expiry from option_snaps where expiry=substr(ts,1,10) and symbol in ('SPY','QQQ')", c)
    for _, (sym, day) in days.iterrows():
        with db() as c:
            snap = pd.read_sql("select ts, type, strike, bid, ask, underlying from option_snaps where symbol=? and expiry=? and substr(ts,1,10)=? and ts>=? and bid>0 order by ts", c, params=(sym, day, day, day + " 09:45"))
        if len(snap) == 0:
            continue
        t0 = snap.ts.iloc[0]; s0 = snap[snap.ts == t0]
        S = s0.underlying.iloc[0]
        for typ in ["call", "put"]:
            g = s0[s0.type == typ]
            if len(g) == 0:
                continue
            # 0.15-delta-ish: ask between 0.15 and 0.40, farthest OTM that qualifies; and ATM: nearest strike
            otm = g[(g.ask >= 0.15) & (g.ask <= 0.40)]
            picks = {"atm": g.iloc[(g.strike - S).abs().argsort()[:1]].strike.iloc[0]}
            if len(otm):
                picks["otm"] = otm.strike.min() if typ == "put" else otm.strike.max()
            for ctype, k in picks.items():
                r = simulate(path(sym, day, typ, k), pd.Timestamp(t0))
                if r:
                    rows.append(dict(sym=sym, day=day, type=typ, ctype=ctype, strike=k, **{kk: (v["ret"] if isinstance(v, dict) else v) for kk, v in r.items() if kk.startswith("R") or kk in ("entry", "max_mid")}))
    R = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print("\n== all 0DTE snapshot days, entry at the first mark >= 09:45, both directions (real quotes)")
    print(R.to_string(index=False))
    print("\nmeans by ctype:"); print(R.groupby("ctype")[[c for c in R.columns if c.startswith("R")]].mean().round(3).to_string())
    res["snapshot_days"] = R.to_dict("records")
    json.dump(res, open(os.path.join(OUT, "oct16_replay.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
