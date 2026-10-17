#!/usr/bin/env python3
"""Prediction-market odds shocks as a lead signal (the P5 idea, generalized).

Data: market.db pm_prices (Polymarket + Kalshi; 15-minute snapshots since 2025-07, 1-minute for the top-12 markets since 2026-10-08),
      SPY/QQQ/IWM 1h bars since 2023-11, ^VIX 1h, CL=F / GC=F / ZN=F / ES=F / NQ=F 1h (yfinance, 730d), USO/XLE/TLT daily.
Event = a tracked market's probability moves >= X points within a 60-minute window (X = 5, 8, 10), during US RTH or overnight.
Measured: the asset's return in the hour BEFORE the odds move (does the market lead the odds?) and the 1h / to-close / next-day return AFTER.
Mapping (direction of 'risk' per topic): iran/oil 'conflict up' -> crude up, equities down; fed 'cut' -> ZN up; midterms: no sign, use |move|.
Caveat: the sample is short (15 months, few true shocks) and each big headline produces several correlated events (same-event cluster).
"""
import json, re
import numpy as np, pandas as pd
from common import *

ET = "America/New_York"


def load_pm():
    with db() as c:
        m = pd.read_sql("select source, market_id, topic, question, volume from pm_markets", c)
        p = pd.read_sql("select source, market_id, ts, prob from pm_prices", c)
    p["ts"] = pd.to_datetime(p.ts, format="mixed")
    p = p.merge(m, on=["source", "market_id"])
    return p


def hourly(sym):
    """1h close series in ET, from market.db (SPY/QQQ/IWM/^VIX) or the yfinance cache."""
    with db() as c:
        d = pd.read_sql("select ts, open, close from bars where symbol=? and interval='1h' order by ts", c, params=(sym,))
    if len(d):
        d["ts"] = pd.to_datetime(d.ts, format="mixed").dt.tz_localize(ET)
        return d.set_index("ts")
    y = yf_raw(sym, "1h").tz_convert(ET)
    return y[["open", "close"]]


def events(p, pts, window="60min"):
    """probability moves >= pts points within `window` (end-of-window timestamp, direction sign). One event per market per 3 hours."""
    ev = []
    for (src, mid), g in p.groupby(["source", "market_id"]):
        g = g.sort_values("ts").drop_duplicates("ts").set_index("ts").prob
        if len(g) < 50:
            continue
        s = g.resample("15min").last().ffill()
        d = (s - s.shift(4)) * 100       # move over 60 minutes
        hits = d[d.abs() >= pts]
        last = None
        for ts, v in hits.items():
            if last is not None and ts - last < pd.Timedelta(hours=3):
                continue
            last = ts
            ev.append(dict(source=src, market_id=mid, ts=ts, move=v, topic=g.name if False else None))
    e = pd.DataFrame(ev)
    if len(e) == 0:
        return e
    meta = p.drop_duplicates(["source", "market_id"])[["source", "market_id", "topic", "question", "volume"]]
    return e.drop(columns=["topic"]).merge(meta, on=["source", "market_id"])


def asset_ret(h, t0, hours_after, hours_before=1):
    """returns of an hourly close series around t0 (ET-naive timestamp): before = (t0-hb -> t0], after = (t0 -> t0+ha]."""
    c = h.close
    idx = c.index
    i0 = idx.searchsorted(t0, side="right") - 1
    if i0 < 1 or i0 >= len(idx) - 1:
        return np.nan, np.nan
    p0 = c.iloc[i0]
    pb = c.iloc[max(i0 - hours_before, 0)]
    i1 = idx.searchsorted(t0 + pd.Timedelta(hours=hours_after), side="right") - 1
    p1 = c.iloc[min(max(i1, i0 + 1), len(idx) - 1)]
    return np.log(p0 / pb), np.log(p1 / p0)


def main():
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    p = load_pm()
    p["ts"] = p.ts.dt.tz_localize(ET)
    res = {}
    H = {s: hourly(s) for s in ["SPY", "QQQ", "^VIX", "CL=F", "ZN=F", "GC=F", "ES=F", "NQ=F"]}
    sign_map = {   # +1: 'yes' on this question is risk-off / conflict-up; -1 the opposite; 0 unsigned
        "iran": 1, "oil": 1, "ukraine": 0, "china": 1, "fed": 0, "macro": 0, "midterms": 0, "trump": 0,
    }
    def risk_sign(q, topic):
        ql = q.lower()
        if topic == "iran":
            if any(w in ql for w in ["ceasefire", "normal", "peace", "deal", "reopen", "returns to normal"]):
                return -1
            return 1
        if topic == "fed":
            if "decrease" in ql or "cut" in ql:
                return -1          # cut odds up = bond-bullish (ZN up), equity-bullish
            if "increase" in ql or "hike" in ql:
                return 1
            return 0
        if topic == "macro" and "recession" in ql:
            return 1
        return sign_map.get(topic, 0)
    out_rows = []
    for pts in [5, 8, 10]:
        e = events(p, pts)
        if len(e) == 0:
            continue
        e["rs"] = [risk_sign(q, t) for q, t in zip(e.question, e.topic)]
        e["signed"] = np.sign(e.move) * e.rs          # +1 = risk-off impulse
        e["rth"] = (e.ts.dt.hour * 60 + e.ts.dt.minute >= 570) & (e.ts.dt.hour * 60 + e.ts.dt.minute <= 960) & (e.ts.dt.dayofweek < 5)
        for sym in ["SPY", "QQQ", "CL=F", "ZN=F", "^VIX"]:
            h = H[sym]
            b1, a1, a4, a24 = [], [], [], []
            for t in e.ts:
                rb, ra = asset_ret(h, t, 1); _, ra4 = asset_ret(h, t, 4); _, ra24 = asset_ret(h, t, 24)
                b1.append(rb); a1.append(ra); a4.append(ra4); a24.append(ra24)
            e[f"{sym}_b1"] = b1; e[f"{sym}_a1"] = a1; e[f"{sym}_a4"] = a4; e[f"{sym}_a24"] = a24
        res[f"n_events_{pts}"] = int(len(e))
        print(f"\n==== threshold {pts} pts / 60min: {len(e)} events ({e.rth.sum()} in RTH); by topic:", e.topic.value_counts().to_dict())
        # signed analysis: topics with a sign; expected: risk-off impulse -> SPY down, CL up (iran), ZN up (fed cut)
        for sym, expect in [("SPY", -1), ("QQQ", -1), ("CL=F", 1), ("ZN=F", 1), ("^VIX", 1)]:
            for sub, mask in [("all_signed", e.rs != 0), ("iran_only", e.topic == "iran"), ("fed_only", e.topic == "fed"), ("rth_signed", (e.rs != 0) & e.rth)]:
                d = e[mask]
                if len(d) < 8:
                    continue
                for col in ["b1", "a1", "a4", "a24"]:
                    x = (d.signed * expect * d[f"{sym}_{col}"]).dropna()
                    if len(x) < 8:
                        continue
                    out_rows.append(dict(pts=pts, sym=sym, subset=sub, horizon=col, n=len(x), mean_bp=round(x.mean() * 1e4, 1), hit=round((x > 0).mean(), 3), t=round(tstat(x), 2), p=pval(tstat(x), len(x))))
        # unsigned: |odds move| -> |asset move| after vs typical
        for sym in ["SPY", "CL=F"]:
            typ = np.log(H[sym].close / H[sym].close.shift(1)).abs().mean()
            x = e[f"{sym}_a1"].abs().dropna()
            out_rows.append(dict(pts=pts, sym=sym, subset="abs_all", horizon="a1_abs_vs_typical", n=len(x), mean_bp=round(x.mean() * 1e4, 1), hit=round((x > typ).mean(), 3), t=round(tstat(x - typ), 2), p=pval(tstat(x - typ), len(x))))
    R = pd.DataFrame(out_rows)
    print(R.to_string(index=False))
    R["bh"] = bh(R.p.to_numpy(), 0.10)
    print("BH survivors (q=0.10) out of", len(R), ":", R[R.bh][["pts", "sym", "subset", "horizon", "n", "mean_bp", "t"]].to_string(index=False) if R.bh.any() else "none")
    res["tests"] = R.to_dict("records")
    # lead-lag cross-correlation at 1h: does SPY lead the Iran 'invade' / Hormuz odds, or the reverse? (top 6 markets by n)
    print("\n== 1h lead-lag cross-correlation (prob change vs SPY/CL 1h return), lag>0 means asset leads odds")
    top = p.groupby(["source", "market_id"]).size().sort_values(ascending=False).head(12).index
    rows = []
    for src, mid in top:
        g = p[(p.source == src) & (p.market_id == mid)].sort_values("ts").drop_duplicates("ts").set_index("ts").prob.resample("1h").last().ffill()
        dpr = g.diff()
        q = p[(p.source == src) & (p.market_id == mid)].question.iloc[0]; topic = p[(p.source == src) & (p.market_id == mid)].topic.iloc[0]
        for sym in ["SPY", "CL=F", "ZN=F"]:
            r = np.log(H[sym].close / H[sym].close.shift(1)); r.index = r.index.floor("h")
            j = pd.concat([dpr.rename("dp"), r.rename("r")], axis=1).dropna()
            if len(j) < 200:
                continue
            cc = {lag: round(float(j.dp.corr(j.r.shift(lag))), 3) for lag in [-2, -1, 0, 1, 2]}
            rows.append(dict(topic=topic, q=q[:50], sym=sym, n=len(j), **{f"lag{k}": v for k, v in cc.items()}))
    L = pd.DataFrame(rows); print(L.to_string(index=False)); res["leadlag"] = L.to_dict("records")
    json.dump(res, open(os.path.join(OUT, "pm_shocks.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
