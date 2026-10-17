#!/usr/bin/env python3
"""Overnight vs intraday returns, and what a long option can capture of them.

1. The classic split: SPY/QQQ close->open (overnight) vs open->close (intraday), 2007-2026, by year and VIX band.
2. A 1-DTE ATM call bought at 15:55 and sold at 09:35 next day (captures the overnight drift; pays one night of theta).
   Pricing: at 15:55 the option has one overnight + one session left. The market prices the overnight at roughly its realized
   variance share (39% of close-to-close variance in 2023-26, from the VIX1D study), so implied sd at 15:55 = VIX1D-style daily sd
   (VIX_close/sqrt(252) * 0.79 * level); at 09:35 the remaining sd is the 0DTE level k(385)*VIX_open*sqrt(385/yr).
   Levels tested: V1D (buyer gets 0.92 of the implied daily move) and VRP (0.80).
3. VIX1D-era check (2023-04 .. 2026-10, n~870): on big-gap days does realized |open->close| / VIX1D(open)-implied rise, i.e. is a
   long straddle at the open cheap on gap days even after the market reprices at 09:30?
4. End-of-day: does the 15:30 -> 16:00 move continue from the 09:30 -> 15:30 move? (sanity re-check of the prior 'dead OOS' result on 1-min data)
"""
import json
import numpy as np, pandas as pd
from common import *


def main():
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    res = {}
    vix = daily("^VIX")
    for sym in ["SPY", "QQQ"]:
        D = sessions(sym); P = D["P"]; dates = D["dates"]; ok = D["ok"]
        df = pd.DataFrame(index=dates)
        df["on"] = D["gap"]; df["oc"] = np.log(P[:, 390] / P[:, 0]); df["last30"] = np.log(P[:, 390] / P[:, T(15, 30)]); df["to1530"] = np.log(P[:, T(15, 30)] / P[:, 0])
        df["vix_p"] = vix.close.shift(1).reindex(dates, method="ffill"); df["vix_c"] = vix.close.reindex(dates); df["vix_o"] = vix.open.reindex(dates)
        df = df[ok & df.on.notna()]
        df["year"] = df.index.year
        by = df.groupby("year")[["on", "oc"]].mean() * 252 * 100
        print(f"\n== {sym}: annualized overnight vs intraday return (%), by year"); print(by.round(1).T.to_string())
        tot = dict(overnight_ann=round(df.on.mean() * 252 * 100, 1), intraday_ann=round(df.oc.mean() * 252 * 100, 1), t_on=round(tstat(df.on), 2), t_oc=round(tstat(df.oc), 2),
                   on_var_share=round(float(df.on.var() / (df.on + df.oc).var()), 3), n=len(df))
        df["period"] = np.where(df.index < "2019-01-01", "IS", "OOS")
        tot["OOS"] = dict(overnight_ann=round(df[df.period == "OOS"].on.mean() * 252 * 100, 1), intraday_ann=round(df[df.period == "OOS"].oc.mean() * 252 * 100, 1), t_on=round(tstat(df[df.period == "OOS"].on), 2))
        print(tot); res[f"{sym}_split"] = tot
        # by VIX band OOS
        df["band"] = pd.cut(df.vix_p, [0, 16, 20, 25, 99], labels=["<16", "16-20", "20-25", "25+"])
        bb = df[df.period == "OOS"].groupby("band", observed=True).agg(n=("on", "size"), on_bp=("on", lambda x: x.mean() * 1e4), on_t=("on", tstat), oc_bp=("oc", lambda x: x.mean() * 1e4))
        print("OOS by VIX band:"); print(bb.round(2).to_string()); res[f"{sym}_oos_by_band"] = bb.round(3).reset_index().to_dict("records")
        # 2. 1-DTE ATM call 15:55 -> 09:35
        S0 = P[:, T(15, 55)]; S1 = P[:, 5]
        # price at 15:55: remaining = overnight + 1 session; implied daily sd (VIX1D style = 0.79 * VIX) in business-day terms, times level
        for level_name, level in [("V1D", 1 / 0.92), ("VRP", 1 / 0.80)]:
            sd_day = 0.79 * df.vix_c / 100 / np.sqrt(252) * level                      # sd of close->close
            T_rem = 1.0                                                                 # one business day (overnight + session) in 'days'
            sig0 = sd_day                                                               # per-day vol; use T in days
            K = S0[ok & D["gap"] is not None] if False else None
            s0 = pd.Series(S0, index=dates).reindex(df.index); s1 = pd.Series(S1, index=dates).reindex(df.index).shift(-1)
            # option at 15:55 on day d, ATM, sold at 09:35 on day d+1
            c0 = pd.Series(bs(s0, s0, 1.0, sig0, True), index=df.index)                 # T=1 day, sig per sqrt(day)
            vo_next = df.vix_o.shift(-1)
            sd_rem = k_spy(385) * vo_next / 100 * np.sqrt(385 / MINYR) * level * (1.376 if sym == "SPY" else 1.223)   # 0DTE level, realized-matched (crossasset fair mult)
            c1 = pd.Series(bs(s1, s0, 1.0, sd_rem, True), index=df.index)               # value at 09:35 with the remaining session's sd (expressed per 'day' with T=1)
            r = (c1 * (1 - 0.01)) / (c0 * (1 + 0.01)) - 1
            r = r.dropna()
            o = summarize(r, f"{sym} 1DTE ATM call 15:55->09:35 {level_name}")
            o["prem_pct"] = round(float((c0 / s0).mean() * 100), 3)
            oo = summarize(r[df.period.reindex(r.index) == "OOS"], "OOS")
            print(o, "| OOS:", oo); res[f"{sym}_1dte_call_{level_name}"] = dict(all=o, oos=oo)
            # always-put version
            p0 = pd.Series(bs(s0, s0, 1.0, sig0, False), index=df.index); p1 = pd.Series(bs(s1, s0, 1.0, sd_rem, False), index=df.index); rp = ((p1 * 0.99) / (p0 * 1.01) - 1).dropna()
            res[f"{sym}_1dte_put_{level_name}"] = summarize(rp, "put"); print("   put:", res[f"{sym}_1dte_put_{level_name}"])
        # 4. end-of-day continuation
        for per in ["IS", "OOS"]:
            d = df[df.period == per]
            q = pd.qcut(d.to1530.rank(method="first"), 5, labels=False)
            sp = d.last30[q == 4].mean() - d.last30[q == 0].mean()
            print(f"   EOD continuation {per}: top-bottom quintile of 09:30->15:30 vs last 30m = {sp*1e4:+.1f} bp, rho {d[['to1530','last30']].corr(method='spearman').iloc[0,1]:+.3f}")
            res[f"{sym}_eod_{per}"] = dict(spread_bp=round(sp * 1e4, 1), rho=round(float(d[["to1530", "last30"]].corr(method="spearman").iloc[0, 1]), 3), n=len(d))
    # 3. VIX1D era: gap days
    v1 = yf_raw("^VIX1D", "1d"); v1.index = v1.index.tz_convert(None).normalize()
    spy = daily("SPY"); hyg = daily("HYG"); tlt = daily("TLT")
    d = pd.DataFrame(index=spy.index)
    d["oc"] = np.log(spy.close / spy.open); d["gap"] = np.log(spy.open / spy.close.shift(1)); d["v1o"] = v1.open.reindex(d.index); d["v1p"] = v1.close.shift(1).reindex(d.index)
    d["hyg_gap"] = np.log(hyg.open / hyg.close.shift(1)).reindex(d.index); d["tlt_gap"] = np.log(tlt.open / tlt.close.shift(1)).reindex(d.index)
    d = d.dropna(subset=["v1o"])
    imp = d.v1o / 100 / np.sqrt(252) * np.sqrt(2 / np.pi) * np.sqrt(0.69)      # intraday share of the VIX1D-implied daily move
    d["ratio"] = d.oc.abs() / imp
    d["dv1"] = np.log(d.v1o / d.v1p)                                             # how much VIX1D repriced at the open
    print("\n== VIX1D era (n=%d): realized |open->close| / VIX1D(open)-implied intraday move, by |gap| quintile" % len(d))
    rows = []
    for f in ["gap", "hyg_gap", "tlt_gap"]:
        q = pd.qcut(d[f].abs().rank(method="first"), 5, labels=False)
        g = d.groupby(q).agg(n=("ratio", "size"), ratio=("ratio", "mean"), dv1=("dv1", "mean"), abs_gap_bp=(f, lambda x: x.abs().mean() * 1e4))
        g["t_vs_1"] = [tstat(d.ratio[q == i] - 1) for i in range(5)]
        print(f); print(g.round(3).to_string()); rows.append(dict(feature=f, q1_ratio=round(g.ratio.iloc[0], 3), q5_ratio=round(g.ratio.iloc[-1], 3), q5_t_vs_1=round(g.t_vs_1.iloc[-1], 2), q5_dv1=round(g.dv1.iloc[-1], 3)))
    res["vix1d_gap_days"] = rows
    res["vix1d_overall_ratio"] = round(float(d.ratio.mean()), 3)
    print("overall intraday ratio:", res["vix1d_overall_ratio"], "(1.0 = fair; the straddle buyer nets ratio - 1 - cost)")
    json.dump(res, open(os.path.join(OUT, "overnight.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
