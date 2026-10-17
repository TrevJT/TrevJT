#!/usr/bin/env python3
"""Calibrate the 0DTE pricing shape from the live SPY/QQQ option snapshots in market.db (8 days, Oct 8-16 2026):
  1. k(t) = ATM-straddle-implied sd to the close / (VIX x sqrt(mins_left/yr))  by hour  -> common.k_spy
  2. the smile: IV(K)/IV(ATM) vs standardized moneyness z, OTM puts and calls       -> p1_exits.SMILE
  3. realized/implied E|move| on those days (SPY 0.82, QQQ 1.01) vs CBOE VIX1D 2023-26 (0.90-0.92): the week was cheap.
Re-run after ~60 sessions of option_snaps and refit k_spy / SMILE / the level from the larger sample."""
import sqlite3
import numpy as np, pandas as pd
from scipy.optimize import brentq
from common import *


def main():
    c = sqlite3.connect(DB)
    o = pd.read_sql("select ts,symbol,type,strike,bid,ask,underlying from option_snaps where expiry=substr(ts,1,10) and bid>0 and ask>0 and symbol in ('SPY','QQQ')", c)
    v = pd.read_sql("select ts,close from bars where symbol='^VIX' and interval='5m'", c); v["ts"] = pd.to_datetime(v.ts, format="mixed"); v = v.set_index("ts").close.sort_index()
    o["ts"] = pd.to_datetime(o.ts, format="mixed"); o["mid"] = (o.bid + o.ask) / 2
    cl = pd.read_sql("select symbol, ts, close from bars where interval='1m' and symbol in ('SPY','QQQ')", c); cl["ts"] = pd.to_datetime(cl.ts, format="mixed")
    closes = cl[cl.ts.dt.strftime("%H:%M") == "15:59"].assign(d=lambda x: x.ts.dt.date).set_index(["symbol", "d"]).close
    rows = []
    for (ts, sym), g in o.groupby(["ts", "symbol"]):
        S = g.underlying.iloc[0]
        if not np.isfinite(S) or S <= 0:
            continue
        strikes = g.strike.unique(); k0 = strikes[np.argmin(np.abs(strikes - S))]
        cp = g[g.strike == k0]
        if set(cp.type) != {"call", "put"}:
            continue
        st = cp.mid.sum(); emove = np.sqrt(max(st ** 2 - (S - k0) ** 2, 1e-9)) / S
        mins = (16 * 60) - (ts.hour * 60 + ts.minute)
        if mins <= 5:
            continue
        vix = v.asof(ts); vix_sd = vix / 100 * np.sqrt(mins / MINYR)
        cz = closes.get((sym, ts.date()), np.nan)
        rows.append(dict(ts=ts, sym=sym, mins=mins, emove=emove, vix=vix, k=emove * np.sqrt(np.pi / 2) / vix_sd, real=abs(np.log(cz / S)) if np.isfinite(cz) else np.nan))
    r = pd.DataFrame(rows); r["hour"] = r.ts.dt.hour
    print("k by hour (median):"); print(r.groupby(["sym", "hour"]).k.median().round(3).unstack(0))
    for sym in ["SPY", "QQQ"]:
        x = r[r.sym == sym]; print(sym, "realized/implied E|move| over the 8 days: %.2f" % (x.real.mean() / x.emove.mean()))
    # smile
    o2 = o[(o.ts.dt.hour * 60 + o.ts.dt.minute <= 15 * 60 + 40) & (o.mid >= 0.03)].copy(); o2["mins"] = (16 * 60) - (o2.ts.dt.hour * 60 + o2.ts.dt.minute)

    def iv(row):
        S, K, Tm, px, call = row.underlying, row.strike, row.mins / MINYR, row.mid, row.type == "call"
        intr = max(S - K, 0) if call else max(K - S, 0)
        if px <= intr + 1e-4:
            return np.nan
        try:
            return brentq(lambda s: float(bs(S, K, Tm, s, call)) - px, 1e-3, 5.0)
        except Exception:
            return np.nan
    o2["iv"] = o2.apply(iv, axis=1); o2 = o2.dropna(subset=["iv"])
    parts = []
    for (ts, sym), g in o2.groupby(["ts", "symbol"]):
        S = g.underlying.iloc[0]; near = g.iloc[(g.strike - S).abs().argsort()[:2]]; atm = near.iv.mean(); sd = atm * np.sqrt(g.mins.iloc[0] / MINYR)
        gg = g.copy(); gg["z"] = np.log(gg.strike / S) / sd; gg["ratio"] = gg.iv / atm; parts.append(gg)
    sm = pd.concat(parts); otm = sm[(((sm.type == "put") & (sm.z < 0)) | ((sm.type == "call") & (sm.z > 0))) & (sm.z.abs() <= 4)]
    for sym in ["SPY", "QQQ"]:
        for side in ["put", "call"]:
            y = otm[(otm.symbol == sym) & (otm.type == side)]; A = np.c_[y.z.abs(), y.z.abs() ** 2]; co = np.linalg.lstsq(A, y.ratio - 1, rcond=None)[0]
            print(f"{sym} {side}: IV(K)/IV(ATM) = 1 + {co[0]:.3f}|z| + {co[1]:.3f} z^2  (n={len(y)})")


if __name__ == "__main__":
    main()
