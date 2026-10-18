#!/usr/bin/env python3
"""Earnings-edge study: build the Robinhood expired-option pull spec (stratified sample of events).

  python3 research/earnings/rhspec.py            # -> data/research_earnings/rh_spec_<k>.json (one file per agent) + rh_spec_all.pkl

Why: Robinhood's get_option_historicals returns DAILY bars for EXPIRED contracts (tested 2026-10-16: MSFT back to Jan 2019,
close-only marks before ~2023, full OHLC after). Pulling the ATM call+put around every report gives the real straddle price
(= the implied move) and the real straddle P&L, which no free source has. The pull goes through MCP calls made by agents,
so the sample is stratified and capped (~1,700 events).
"""
import json, pickle
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "research_earnings"
SC = ROOT / "data" / "research_smallcap_cache.pkl"
SEED = 11

MEGA = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "NFLX", "COST", "JPM", "LLY", "AMD", "ORCL", "CRM"]


def third_friday(y, m):
    d = pd.Timestamp(year=y, month=m, day=15)
    while d.dayofweek != 4:
        d += pd.Timedelta(days=1)
    return d


def expiries(R):
    R = pd.Timestamp(R)
    fri = R + pd.Timedelta(days=(4 - R.dayofweek) % 7)
    m = third_friday(R.year, R.month)
    if m < R:
        y, mo = (R.year + 1, 1) if R.month == 12 else (R.year, R.month + 1)
        m = third_friday(y, mo)
    out = [fri.strftime("%Y-%m-%d")]
    if m.strftime("%Y-%m-%d") not in out:
        out.append(m.strftime("%Y-%m-%d"))
    return out


def strike_grid(px):
    if px < 5:
        steps = [0.5, 1.0, 2.5]
    elif px < 25:
        steps = [0.5, 1.0, 2.5]
    elif px < 100:
        steps = [1.0, 2.5, 5.0, 0.5]
    elif px < 250:
        steps = [2.5, 5.0, 1.0]
    else:
        steps = [5.0, 2.5, 10.0]
    cands = []
    for s in steps:
        k = round(px / s) * s
        for kk in (k, k + s, k - s):
            if kk > 0 and f"{kk:.4f}" not in cands:
                cands.append(f"{kk:.4f}")
    # order by distance to spot
    cands.sort(key=lambda x: abs(float(x) - px))
    return cands[:6]


def main():
    PNL = pd.read_pickle(D / "panel.pkl")
    raw = pd.read_pickle(D / "raw_close.pkl") if (D / "raw_close.pkl").exists() else {}   # UNADJUSTED closes (strikes live in raw prices)
    sc = pickle.load(open(SC, "rb"))
    chains = sc.get("chains", {})
    liq = {}
    for t, c in chains.items():
        if not c:
            continue
        sp = c.get("spread_call") or c.get("spread_put")
        liq[t] = dict(spread=sp, oi=c.get("atm_oi"), vol=c.get("vol_tgt"), weeklies=c.get("weeklies"))
    recent = PNL[(PNL.R >= "2023-01-01")]
    last_tier = recent.groupby("t").tier.last()
    rng = np.random.default_rng(SEED)

    def pick(names, n):
        names = [x for x in names if x in PNL.t.values]
        if len(names) <= n:
            return names
        return list(rng.choice(names, n, replace=False))
    mega = [t for t in MEGA if t in last_tier.index]
    large = pick([t for t, v in last_tier.items() if v == "large" and t not in mega and PNL[PNL.t == t].gics.notna().any()], 30)
    mid_liq = [t for t, v in last_tier.items() if v == "mid" and (t not in liq or (liq[t]["spread"] or 1) <= 0.25)]
    mid = pick(mid_liq, 45)
    small_liq = [t for t, v in last_tier.items() if v == "small" and t in liq and (liq[t]["spread"] or 1) <= 0.30 and (liq[t]["oi"] or 0) >= 50]
    small = pick(small_liq, 35)
    micro_liq = [t for t, v in last_tier.items() if v == "micro" and t in liq and (liq[t]["spread"] or 1) <= 0.40]
    micro = pick(micro_liq, 8)
    sel = {"mega": mega, "large": large, "mid": mid, "small": small, "micro": micro}
    print({k: len(v) for k, v in sel.items()})
    rows = []
    for tr, names in sel.items():
        for t in names:
            g = PNL[(PNL.t == t) & (PNL.R >= ("2022-01-01" if tr in ("mega",) else "2024-07-01"))]
            for r in g.itertuples():
                entry = (r.R - pd.tseries.offsets.BDay(1))
                c0 = float(raw[t].asof(entry)) if t in raw and raw[t].index[0] <= entry else float(r.C0)
                if not (c0 > 0):
                    continue
                rows.append(dict(t=t, tier=tr, R=r.R.strftime("%Y-%m-%d"), entry=entry.strftime("%Y-%m-%d"),
                                 C0=round(c0, 2), C0adj=round(float(r.C0), 2), expiries=(expiries(r.R) if tr == "mega" else expiries(r.R)[::-1]), strikes=strike_grid(c0),
                                 window=[(r.R - pd.Timedelta(days=8)).strftime("%Y-%m-%d"), (r.R + pd.Timedelta(days=2)).strftime("%Y-%m-%d")]))
    S = pd.DataFrame(rows).sort_values(["R", "t"]).reset_index(drop=True)
    S["eid"] = S.t + "_" + S.R
    S.to_pickle(D / "rh_spec_all.pkl")
    print("events", len(S), S.tier.value_counts().to_dict())
    # split into agent files: chunk by R so each agent's batches share windows
    k = 6
    parts = np.array_split(S.index.values, k)
    for i, idx in enumerate(parts):
        part = S.loc[idx]
        batches, cur = [], []
        for r in part.itertuples():
            if cur and (len(cur) >= 5 or (pd.Timestamp(r.R) - pd.Timestamp(cur[0]["R"])).days > 6):
                batches.append(cur); cur = []
            cur.append(dict(eid=r.eid, t=r.t, R=r.R, entry=r.entry, C0=r.C0, expiries=r.expiries, strikes=r.strikes, window=r.window))
        if cur:
            batches.append(cur)
        json.dump(batches, open(D / f"rh2_spec_{i}.json", "w"))
        print("agent", i, "events", len(part), "batches", len(batches))


if __name__ == "__main__":
    main()
