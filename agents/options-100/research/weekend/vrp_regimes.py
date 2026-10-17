#!/usr/bin/env python3
"""Volatility risk premium timing: WHEN is a long option (straddle) actually cheap?

Instruments modelled (both long-premium, defined risk):
  0DTE ATM straddle bought at the open, held to the close (SPY; XSP for the real account).
  5-session ATM straddle bought at the open, held to expiry (implied from VIX9D).
Return of a straddle held to expiry = |move| / implied E|move| - 1 - cost. Implied E|move|:
  0DTE: k(390) * VIX_open * sqrt(390/525600) * sqrt(2/pi)  (MKT, Oct-2026 live-quote calibration), realized-matched x 1/0.92 (V1D, central:
        CBOE VIX1D vs realized 2023-26 gives buyers 0.90-0.92 of the implied move) and realized-matched x 1/0.8 (VRP, conservative).
  5d:   VIX9D_open/100 * sqrt(5/252) * sqrt(2/pi) (MKT ~ business-day convention), realized-matched x 1/0.92 (V1D) and x 1/0.8 (VRP).
Features known at the open: VIX level, VIX9D/VIX, VIX/VIX3M, VVIX/VIX, 1d and 5d VIX change, RV5/VIX, RV20/VIX, SKEW, MOVE, OVX,
  gap, |prior-day return|, day-of-week, OPEX (3rd Friday), month-end, pre-holiday.
Tests: (a) realized/implied and straddle return by VIX band, term structure, weekday, OPEX (IS 2007-2018 / OOS 2019+; BH over all subgroup tests);
       (b) walk-forward HistGradientBoosting classifier (yearly refit, expanding window from 2013) on 'straddle return > 0', P&L on p>0.5 / p>0.6 days;
       (c) per-feature quintile long-vol P&L OOS.
"""
import json
import numpy as np, pandas as pd
from common import *
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score

COST0 = 0.02       # 0DTE ATM straddle round trip (4% spread, half paid, both legs)
COST5 = 0.03


def third_friday(d):
    f = pd.Timestamp(d.year, d.month, 1)
    first_fri = f + pd.Timedelta(days=(4 - f.weekday()) % 7)
    return d == first_fri + pd.Timedelta(days=14)


def build():
    spy = daily("SPY"); vix = daily("^VIX"); v9 = daily("^VIX9D"); v3 = daily("^VIX3M"); vv = daily("^VVIX"); sk = daily("^SKEW"); mv = daily("^MOVE"); ovx = daily("^OVX")
    df = pd.DataFrame(index=spy.index)
    df["oc"] = np.log(spy.close / spy.open)
    df["cc"] = np.log(spy.close / spy.close.shift(1))
    df["gap"] = np.log(spy.open / spy.close.shift(1))
    df["r5f"] = np.log(spy.close.shift(-5) / spy.open)            # forward 5-session move from today's open
    df["vix_o"] = vix.open.reindex(df.index); df["vix_c"] = vix.close.reindex(df.index)
    df["vix_p"] = df.vix_c.shift(1)
    df["v9"] = v9.open.reindex(df.index); df["v3"] = v3.open.reindex(df.index); df["vvix"] = vv.close.shift(1).reindex(df.index)
    df["skew"] = sk.close.shift(1).reindex(df.index); df["move"] = mv.close.shift(1).reindex(df.index); df["ovx"] = ovx.close.shift(1).reindex(df.index)
    df["rv5"] = df.cc.rolling(5).std().shift(1) * np.sqrt(252) * 100; df["rv20"] = df.cc.rolling(20).std().shift(1) * np.sqrt(252) * 100
    df["ts9"] = df.v9 / df.vix_o; df["ts3"] = df.vix_o / df.v3; df["vv_ratio"] = df.vvix / df.vix_p
    df["dvix1"] = np.log(df.vix_p / df.vix_p.shift(1)); df["dvix5"] = np.log(df.vix_p / df.vix_p.shift(5))
    df["rv5r"] = df.rv5 / df.vix_p; df["rv20r"] = df.rv20 / df.vix_p
    df["absr1"] = df.cc.shift(1).abs(); df["r1"] = df.cc.shift(1); df["r5"] = np.log(spy.close.shift(1) / spy.close.shift(6))
    df["dow"] = df.index.dayofweek
    df["opex"] = [third_friday(d) for d in df.index]
    df["month_end"] = (df.index.month != pd.Series(df.index).shift(-1).dt.month.to_numpy())
    nxt = pd.Series(df.index).shift(-1).to_numpy(); gapdays = (nxt - df.index.to_numpy()) / np.timedelta64(1, "D")
    df["pre_holiday"] = (gapdays > 3) | ((gapdays > 1) & (df.dow != 4))
    df["year"] = df.index.year
    # 0DTE straddle (open -> close)
    imp0_mkt = k_spy(390) * df.vix_o / 100 * np.sqrt(390 / MINYR) * np.sqrt(2 / np.pi)
    sel = (df.index >= "2007-01-01") & np.isfinite(df.oc) & np.isfinite(imp0_mkt)
    fair0 = df.oc[sel].abs().mean() / imp0_mkt[sel].mean()
    imp0_vrp = imp0_mkt * fair0 / 0.8
    df["ratio0_mkt"] = df.oc.abs() / imp0_mkt
    df["st0_mkt"] = df.ratio0_mkt - 1 - COST0
    df["st0_vrp"] = df.oc.abs() / imp0_vrp - 1 - COST0
    df["st0_v1d"] = df.oc.abs() / (imp0_mkt * fair0 / 0.92) - 1 - COST0
    # 5-session straddle (open -> close 5 sessions later), implied from VIX9D
    imp5_mkt = df.v9 / 100 * np.sqrt(5 / 252) * np.sqrt(2 / np.pi)
    sel5 = np.isfinite(df.r5f) & np.isfinite(imp5_mkt)
    fair5 = df.r5f[sel5].abs().mean() / imp5_mkt[sel5].mean()
    df["ratio5_mkt"] = df.r5f.abs() / imp5_mkt
    df["st5_mkt"] = df.ratio5_mkt - 1 - COST5
    df["st5_vrp"] = df.r5f.abs() / (imp5_mkt * fair5 / 0.8) - 1 - COST5
    df["st5_v1d"] = df.r5f.abs() / (imp5_mkt * fair5 / 0.92) - 1 - COST5
    meta = dict(fair0=round(float(fair0), 3), fair5=round(float(fair5), 3), note="fairX = realized mean |move| / implied E|move| under the MKT convention; VRP pricing = fair/0.8")
    return df[df.index >= "2007-01-01"], meta


FEATS = ["vix_p", "ts9", "ts3", "vv_ratio", "dvix1", "dvix5", "rv5r", "rv20r", "skew", "move", "ovx", "gap", "absr1", "r1", "r5", "dow", "opex", "month_end", "pre_holiday"]


def subgroup_tests(df, target, period_col="period"):
    rows = []
    groups = {
        "vix_band": pd.cut(df.vix_p, [0, 13, 16, 18, 20, 25, 30, 999], labels=["<13", "13-16", "16-18", "18-20", "20-25", "25-30", "30+"]),
        "ts9_tercile": pd.qcut(df.ts9, 3, labels=["low", "mid", "high"]) if df.ts9.notna().sum() > 100 else None,
        "ts3_tercile": pd.qcut(df.ts3, 3, labels=["low", "mid", "high"]),
        "vvix_tercile": pd.qcut(df.vv_ratio, 3, labels=["low", "mid", "high"]),
        "rv5r_tercile": pd.qcut(df.rv5r, 3, labels=["low", "mid", "high"]),
        "dvix5_tercile": pd.qcut(df.dvix5, 3, labels=["low", "mid", "high"]),
        "dow": df.dow.map({0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}),
        "opex": df.opex.map({True: "opex", False: "other"}),
        "pre_holiday": df.pre_holiday.map({True: "pre_hol", False: "other"}),
        "gap_abs_tercile": pd.qcut(df.gap.abs(), 3, labels=["low", "mid", "high"]),
        "absr1_tercile": pd.qcut(df.absr1, 3, labels=["low", "mid", "high"]),
    }
    for gname, g in groups.items():
        if g is None:
            continue
        for lvl in pd.unique(g.dropna()):
            for per in ["IS", "OOS"]:
                m = (g == lvl) & (df.period == per) & df[target].notna()
                x = df.loc[m, target]
                if len(x) < 30:
                    continue
                t = tstat(x) if "st5" not in target else tstat_cluster(x, df.index[m].isocalendar().week.to_numpy() + 100 * df.index[m].year.to_numpy())
                rows.append(dict(group=gname, level=str(lvl), period=per, n=int(len(x)), mean=round(float(x.mean()), 4), win=round(float((x > 0).mean()), 3), t=round(t, 2), p=pval(t, len(x))))
    r = pd.DataFrame(rows)
    oos = r[r.period == "OOS"].copy()
    oos["bh"] = bh(oos.p.to_numpy(), 0.10) if len(oos) else []
    return r, oos


def walk_forward(df, target, feats, start=2013, thr=0.5):
    d = df.dropna(subset=feats + [target]).copy()
    y = (d[target] > 0).astype(int)
    years = sorted(d.year.unique())
    preds = pd.Series(np.nan, index=d.index)
    for yr in years:
        if yr < start:
            continue
        tr = d.year < yr
        te = d.year == yr
        if tr.sum() < 500 or te.sum() == 0:
            continue
        clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=40, l2_regularization=1.0)
        clf.fit(d.loc[tr, feats], y[tr])
        preds[te] = clf.predict_proba(d.loc[te, feats])[:, 1]
    ok = preds.notna()
    out = {}
    if ok.sum() < 50:
        return out
    r = d.loc[ok, target]; p = preds[ok]
    out["n_oos"] = int(ok.sum()); out["auc"] = round(float(roc_auc_score(y[ok], p)), 3) if y[ok].nunique() > 1 else None
    out["always"] = summarize(r, "always")
    for q in [0.5, 0.55, 0.6]:
        m = p > q
        out[f"p>{q}"] = summarize(r[m], f"p>{q}") if m.sum() > 10 else dict(n=int(m.sum()))
    # per-year of the p>0.5 rule
    out["by_year_p>0.5"] = {int(k): round(float(v), 3) for k, v in r[p > 0.5].groupby(d.loc[ok & (p > 0.5), "year"]).mean().items()}
    return out


def main():
    df, meta = build()
    df["period"] = np.where(df.index < "2019-01-01", "IS", "OOS")
    res = {"meta": meta}
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    print("meta", meta)
    for target in ["st0_mkt", "st0_v1d", "st0_vrp", "st5_mkt", "st5_v1d", "st5_vrp"]:
        print(f"\n==== {target}: always-long straddle by period")
        for per in ["IS", "OOS"]:
            print(per, summarize(df.loc[df.period == per, target].dropna()))
        r, oos = subgroup_tests(df, target)
        res[f"{target}_subgroups"] = r.to_dict("records")
        res[f"{target}_oos_bh"] = oos[oos.bh].to_dict("records") if len(oos) else []
        print(r.pivot_table(index=["group", "level"], columns="period", values=["n", "mean", "t"]).round(3).to_string())
        print("OOS BH survivors:", oos[oos.bh][["group", "level", "n", "mean", "t"]].to_string(index=False) if oos.bh.any() else "none", f"(of {len(oos)} OOS subgroup tests)")
        wf = walk_forward(df, target, FEATS)
        res[f"{target}_walkforward"] = wf
        print("walk-forward HistGB:", json.dumps(wf, default=str)[:1500])
    # multiple testing count
    res["meta"]["n_subgroup_tests_oos"] = sum(len(v) for k, v in res.items() if k.endswith("_subgroups"))
    json.dump(res, open(os.path.join(OUT, "vrp_regimes.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
