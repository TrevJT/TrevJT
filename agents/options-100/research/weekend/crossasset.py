#!/usr/bin/env python3
"""Cross-asset overnight lead-lag: do Asia/Europe closes, futures overnight, FX, crude, gold, rates, credit and BTC predict
the US open->close move of SPY/QQQ (direction and size), well enough to pay for a 0DTE ATM option at 09:35?

Two panels
  A. Daily, 2007/2010 .. 2026-03 (1-minute sessions for the target): features known before 09:30 ET
     - gaps (prior close -> today's open) of SPY, QQQ, TLT, GLD, USO, HYG, UUP (from the 1-minute sessions)
     - Asia closes on the same calendar day: Nikkei, Hang Seng, Shanghai, KOSPI, ASX (all closed before the US open)
     - lagged-day returns of DAX, STOXX50, FTSE, EURUSD, USDJPY, DXY, CL, GC (daily closes are AFTER the prior US close but
       BEFORE today's open, so they are legal, just mostly overlapping yesterday's US session)
     - BTC UTC-day return (closes 20:00 ET the prior evening) and BTC 7-day return
     - VIX prior close, VIX9D/VIX, VIX/VIX3M, SPY prior 1d/5d returns, RV20
  B. Hourly, last 730 days (yfinance 1h): true overnight moves 17:00 ET prior day -> 09:00 ET today of ES, NQ, CL, GC, ZN, 6E, 6J, BTC
     (bars are labelled by START time, so the 08:00 bar's close is the 09:00 price; the first version used the 09:00 bar = 10:00 price and leaked).
Targets: SPY and QQQ log(open->close) and log(09:35->close), sign and |size|.
Tests: per-feature OOS quintile spread (2019+), BH over all; walk-forward logistic + HistGB (yearly refit from 2013) with the
0DTE ATM call/put P&L under MKT and VRP pricing when the model is confident.
"""
import json
import numpy as np, pandas as pd
from common import *
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score


def ret(d, lag=0):
    r = np.log(d.close / d.close.shift(1))
    return r.shift(lag)


def panel_daily():
    S = sessions("SPY"); Q = sessions("QQQ")
    idx = S["dates"]
    df = pd.DataFrame(index=idx)
    df["spy_oc"] = np.log(S["P"][:, 390] / S["P"][:, 0]); df["spy_935c"] = np.log(S["P"][:, 390] / S["P"][:, 5])
    qi = pd.Series(np.arange(len(Q["dates"])), index=Q["dates"]).reindex(idx)
    qok = qi.notna().to_numpy(); qii = qi.fillna(0).astype(int).to_numpy()
    df["qqq_oc"] = np.where(qok, np.log(Q["P"][qii, 390] / Q["P"][qii, 0]), np.nan); df["qqq_935c"] = np.where(qok, np.log(Q["P"][qii, 390] / Q["P"][qii, 5]), np.nan)
    df["spy_gap"] = S["gap"]; df["qqq_gap"] = np.where(qok, Q["gap"][qii], np.nan)
    df["ok"] = S["ok"] & qok
    for sym in ["TLT", "GLD", "USO", "HYG", "UUP"]:
        D = sessions(sym); g = pd.Series(D["gap"], index=D["dates"]).reindex(idx)
        df[f"{sym.lower()}_gap"] = g.to_numpy()
    # Asia same-day closes
    for sym, name in [("^N225", "nikkei"), ("^HSI", "hsi"), ("000001.SS", "shanghai"), ("^KS11", "kospi"), ("^AXJO", "asx")]:
        d = daily(sym); df[name] = ret(d).reindex(idx).to_numpy()
    # lagged-day (prior session) returns of Europe, FX, commodities
    for sym, name in [("^GDAXI", "dax_l1"), ("^STOXX50E", "stoxx_l1"), ("^FTSE", "ftse_l1"), ("EURUSD=X", "eurusd_l1"), ("JPY=X", "usdjpy_l1"), ("DX-Y.NYB", "dxy_l1"), ("CL=F", "cl_l1"), ("GC=F", "gc_l1")]:
        d = daily(sym); df[name] = ret(d, 1).reindex(idx, method="ffill").to_numpy()
    btc = daily("BTC-USD"); rb = np.log(btc.close / btc.close.shift(1)); rb7 = np.log(btc.close / btc.close.shift(7))
    # BTC UTC day d-1 closes 00:00 UTC day d = 19/20:00 ET day d-1 -> known at the US open of day d; index by the UTC date d-1 -> shift to d
    df["btc_l1"] = rb.shift(1).reindex(idx, method="ffill").to_numpy(); df["btc_7d_l1"] = rb7.shift(1).reindex(idx, method="ffill").to_numpy()
    vix = daily("^VIX"); v9 = daily("^VIX9D"); v3 = daily("^VIX3M")
    df["vix_p"] = vix.close.shift(1).reindex(idx, method="ffill").to_numpy(); df["vix_o"] = vix.open.reindex(idx).to_numpy()
    df["ts9"] = (v9.close / vix.close).shift(1).reindex(idx, method="ffill").to_numpy(); df["ts3"] = (vix.close / v3.close).shift(1).reindex(idx, method="ffill").to_numpy()
    spyd = daily("SPY"); df["spy_r1"] = ret(spyd, 1).reindex(idx).to_numpy(); df["spy_r5"] = np.log(spyd.close.shift(1) / spyd.close.shift(6)).reindex(idx).to_numpy()
    df["rv20"] = ret(spyd).rolling(20).std().shift(1).reindex(idx).to_numpy()
    df["year"] = df.index.year
    return df


def panel_hourly():
    """true overnight 16:00 ET (prior day) -> 09:00 ET moves from 1h bars; target = SPY/QQQ 09:30 open -> close from market.db 1h/1d."""
    out = {}
    for sym, name in [("ES=F", "es"), ("NQ=F", "nq"), ("CL=F", "cl"), ("GC=F", "gc"), ("ZN=F", "zn"), ("6E=F", "eur"), ("6J=F", "jpy"), ("BTC-USD", "btc")]:
        try:
            h = yf_raw(sym, "1h")
        except Exception:
            continue
        h = h.tz_convert("America/New_York")
        hh = h.index.hour; d = h.index.normalize()
        c = h.close
        # last bar at/after 16:00 prior day and the 09:00 bar today
        p16 = c[(hh == 16) | (hh == 15)].groupby(d[(hh == 16) | (hh == 15)]).last()
        p9 = c[hh == 8].groupby(d[hh == 8]).last()            # bar labelled 08:00 closes at 09:00 ET: no overlap with the 09:30 open (yfinance labels by bar START)
        p16 = p16.tz_localize(None); p9 = p9.tz_localize(None)
        ov = pd.Series(np.nan, index=p9.index)
        prev = p16.reindex(p9.index, method="ffill")       # ffill gives the prior day's 16:00 when today's doesn't exist yet at 09:00... use shift of calendar day
        # align explicitly: for each date in p9, prior p16 date strictly before
        pv = p16.copy(); pv.index = pv.index + pd.Timedelta(days=1)
        prev = pv.reindex(p9.index, method="ffill")
        out[f"{name}_on"] = np.log(p9 / prev)
    spy = daily("SPY"); qqq = daily("QQQ")
    df = pd.DataFrame(out)
    df["spy_oc"] = np.log(spy.close / spy.open).reindex(df.index); df["qqq_oc"] = np.log(qqq.close / qqq.open).reindex(df.index)
    df["spy_gap"] = np.log(spy.open / spy.close.shift(1)).reindex(df.index)
    return df.dropna(subset=["spy_oc"])


def quintile_tests(df, feats, target, period):
    rows = []
    d = df[(df.period == period) & df[target].notna()]
    for f in feats:
        x = d[f]; m = x.notna()
        if m.sum() < 200:
            continue
        q = pd.qcut(x[m].rank(method="first"), 5, labels=False)
        r = d.loc[m, target]
        top = r[q == 4]; bot = r[q == 0]
        spread = top.mean() - bot.mean()
        se = np.sqrt(top.var(ddof=1) / len(top) + bot.var(ddof=1) / len(bot))
        t = spread / se if se > 0 else np.nan
        rho = d.loc[m, [f, target]].corr(method="spearman").iloc[0, 1]
        rows.append(dict(feature=f, target=target, period=period, n=int(m.sum()), spread_bp=round(spread * 1e4, 1), t=round(float(t), 2), p=pval(t, len(top) + len(bot)), rho=round(float(rho), 3),
                         hit_top=round(float((top > 0).mean()), 3), hit_bot=round(float((bot > 0).mean()), 3)))
    return pd.DataFrame(rows)


def option_pnl(df, pred_sign, target_col, sym, pricing_mult):
    """0DTE ATM option bought at 09:35 in the predicted direction, held to close. Return on premium (held to expiry: intrinsic / premium - 1 - cost)."""
    kq = 1.0 if sym == "SPY" else 1.45
    sd = k_spy(385) * kq * df.vix_o / 100 * np.sqrt(385 / MINYR) * pricing_mult
    prem = sd * 0.3989                        # ATM option = 0.3989 * S * sd (BS at the money, zero rates)
    move = df[target_col] * pred_sign
    payoff = np.maximum(move, 0)
    return payoff / prem - 1 - 0.02


def walk_forward_dir(df, feats, target, sym, start=2013):
    d = df.dropna(subset=feats + [target, "vix_o"]).copy()
    y = (d[target] > 0).astype(int)
    pl = pd.Series(np.nan, index=d.index); ph = pd.Series(np.nan, index=d.index)
    for yr in sorted(d.year.unique()):
        if yr < start:
            continue
        tr = d.year < yr; te = d.year == yr
        if tr.sum() < 500 or te.sum() == 0:
            continue
        lr = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500)); lr.fit(d.loc[tr, feats], y[tr]); pl[te] = lr.predict_proba(d.loc[te, feats])[:, 1]
        gb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=50, l2_regularization=1.0); gb.fit(d.loc[tr, feats], y[tr]); ph[te] = gb.predict_proba(d.loc[te, feats])[:, 1]
    out = {}
    fair = {"SPY": FAIR["SPY"], "QQQ": FAIR["QQQ"]}
    for name, p in [("logit", pl), ("histgb", ph)]:
        ok = p.notna()
        if ok.sum() < 100:
            continue
        r = d.loc[ok, target]; pp = p[ok]; yy = y[ok]
        o = dict(n=int(ok.sum()), auc=round(float(roc_auc_score(yy, pp)), 3), acc=round(float(((pp > 0.5) == yy).mean()), 3), base_up=round(float(yy.mean()), 3))
        for conf in [0.0, 0.05, 0.10]:
            m = (pp - 0.5).abs() > conf
            if m.sum() < 30:
                continue
            sign = np.where(pp[m] > 0.5, 1, -1)
            o[f"conf>{conf}"] = dict(n=int(m.sum()), acc=round(float((sign == np.where(yy[m] == 1, 1, -1)).mean()), 3), move_bp=round(float((r[m] * sign).mean() * 1e4), 1), t=round(tstat(r[m] * sign), 2),
                                     opt_mkt=summarize(option_pnl(d.loc[ok][m], sign, target, sym, 1.0)), opt_vrp=summarize(option_pnl(d.loc[ok][m], sign, target, sym, fair[sym] / 0.8)))
        out[name] = o
    return out


FAIR = {}


def main():
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    res = {}
    df = panel_daily()
    df = df[df.ok & (df.index >= "2010-01-01")]
    df["period"] = np.where(df.index < "2019-01-01", "IS", "OOS")
    # fair multipliers for 09:35->close pricing
    for sym, col, kq in [("SPY", "spy_935c", 1.0), ("QQQ", "qqq_935c", 1.45)]:
        imp = k_spy(385) * kq * df.vix_o / 100 * np.sqrt(385 / MINYR) * np.sqrt(2 / np.pi)
        m = df[col].notna() & imp.notna()
        FAIR[sym] = float(df.loc[m, col].abs().mean() / imp[m].mean())
    res["fair_mult"] = {k: round(v, 3) for k, v in FAIR.items()}
    print("fair multipliers:", res["fair_mult"])
    feats = ["spy_gap", "qqq_gap", "tlt_gap", "gld_gap", "uso_gap", "hyg_gap", "uup_gap", "nikkei", "hsi", "shanghai", "kospi", "asx", "dax_l1", "stoxx_l1", "ftse_l1", "eurusd_l1", "usdjpy_l1", "dxy_l1", "cl_l1", "gc_l1", "btc_l1", "btc_7d_l1", "vix_p", "ts9", "ts3", "spy_r1", "spy_r5", "rv20"]
    allq = []
    for target in ["spy_935c", "qqq_935c"]:
        for per in ["IS", "OOS"]:
            q = quintile_tests(df, feats, target, per); allq.append(q)
    Q = pd.concat(allq, ignore_index=True)
    oos = Q[Q.period == "OOS"].copy(); oos["bh"] = bh(oos.p.to_numpy(), 0.10)
    print("\n== per-feature quintile spread (top-bottom, bp, 09:35->close)")
    piv = Q.pivot_table(index=["target", "feature"], columns="period", values=["spread_bp", "t", "rho"]).round(2)
    print(piv.to_string())
    print("OOS BH survivors:", oos[oos.bh][["target", "feature", "spread_bp", "t"]].to_string(index=False) if oos.bh.any() else "none", f"of {len(oos)} OOS tests")
    res["quintiles"] = Q.to_dict("records"); res["oos_bh"] = oos[oos.bh].to_dict("records"); res["n_oos_tests"] = int(len(oos))
    # |move| prediction: does cross-asset overnight activity predict a big US day (for straddles)? quintile of |feature| vs |target|/implied
    print("\n== |feature| vs realized/implied (0DTE straddle MKT ratio), OOS")
    rows = []
    for sym, col, kq in [("SPY", "spy_935c", 1.0), ("QQQ", "qqq_935c", 1.45)]:
        imp = k_spy(385) * kq * df.vix_o / 100 * np.sqrt(385 / MINYR) * np.sqrt(2 / np.pi)
        ratio = df[col].abs() / imp
        d = df[df.period == "OOS"]
        for f in ["nikkei", "hsi", "kospi", "dax_l1", "cl_l1", "btc_l1", "spy_gap", "qqq_gap", "tlt_gap", "hyg_gap", "gld_gap", "uso_gap"]:
            x = d[f].abs(); m = x.notna() & ratio[d.index].notna()
            q = pd.qcut(x[m].rank(method="first"), 5, labels=False); r = ratio[d.index][m]
            rows.append(dict(sym=sym, feature=f, n=int(m.sum()), ratio_q1=round(float(r[q == 0].mean()), 3), ratio_q5=round(float(r[q == 4].mean()), 3), t=round(float(tstat(r[q == 4].to_numpy()) - 0), 2),
                             straddle_q5_mkt=round(float(r[q == 4].mean() - 1 - 0.02), 3), straddle_q5_vrp=round(float(r[q == 4].mean() / (FAIR[sym] / 0.8) - 1 - 0.02), 3)))
    big = pd.DataFrame(rows); print(big.to_string(index=False)); res["abs_feature_vs_ratio"] = big.to_dict("records")
    # walk-forward direction models
    print("\n== walk-forward direction models (yearly refit, OOS from 2013)")
    for sym, target in [("SPY", "spy_935c"), ("QQQ", "qqq_935c")]:
        wf = walk_forward_dir(df, feats, target, sym)
        res[f"wf_{sym}"] = wf
        print(sym, json.dumps(wf, default=str)[:2500])
    # hourly true-overnight panel (2 years)
    try:
        h = panel_hourly()
        h["year"] = h.index.year
        print("\n== hourly true-overnight panel", h.shape, h.index.min().date(), h.index.max().date())
        rows = []
        for f in [c for c in h.columns if c.endswith("_on")]:
            for target in ["spy_oc", "qqq_oc"]:
                m = h[f].notna() & h[target].notna()
                if m.sum() < 100:
                    continue
                rho = h.loc[m, [f, target]].corr(method="spearman").iloc[0, 1]
                q = pd.qcut(h.loc[m, f].rank(method="first"), 3, labels=False); r = h.loc[m, target]
                spread = r[q == 2].mean() - r[q == 0].mean(); se = np.sqrt(r[q == 2].var() / (q == 2).sum() + r[q == 0].var() / (q == 0).sum())
                rows.append(dict(feature=f, target=target, n=int(m.sum()), rho=round(float(rho), 3), tercile_spread_bp=round(spread * 1e4, 1), t=round(float(spread / se), 2)))
        hh = pd.DataFrame(rows); print(hh.to_string(index=False)); res["hourly_overnight"] = hh.to_dict("records")
    except Exception as e:
        print("hourly panel failed", e); res["hourly_overnight_error"] = str(e)
    json.dump(res, open(os.path.join(OUT, "crossasset.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
