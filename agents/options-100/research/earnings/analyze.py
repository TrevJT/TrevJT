#!/usr/bin/env python3
"""Earnings-edge study: realized-move panel analysis (no option prices; proxy implied = own-history mean |move|).

  python3 research/earnings/analyze.py        # -> data/research_earnings/analyze_out.json + printed tables

Questions answered here:
  1. Segment table: how big are earnings moves by cap tier / industry / year, and realized vs the own-history proxy.
  2. Is realized/proxy (ratio8) predictable from anything known at the entry close? Quintile spreads IS (<=2018) vs OOS (2019+),
     t-stats clustered by report week, Benjamini-Hochberg across the family; walk-forward HistGB by season.
  3. Does per-ticker / per-industry "moves more than its history" persist IS -> OOS?
  4. Direction: anything predict sign(cc)?
The option-price questions (is the straddle priced above/below realized, after spreads) are in rhanalyze.py on the Robinhood sample.
"""
import json, warnings, itertools
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "research_earnings"
OOS0 = pd.Timestamp("2019-01-01")
N_TESTS = {"count": 0}


def tstat_cluster(y, cl):
    """mean and t of y with clusters cl (report week)."""
    df = pd.DataFrame({"y": y, "c": cl}).dropna()
    if len(df) < 10:
        return np.nan, np.nan, len(df)
    m = df.y.mean()
    g = df.groupby("c").y.agg(["sum", "count"])
    # cluster-robust se of the mean: sqrt(sum_c (sum_c(y-m))^2) / n
    e = (g["sum"] - m * g["count"])
    se = np.sqrt((e ** 2).sum()) / len(df)
    return m, m / se if se > 0 else np.nan, len(df)


def bh(pvals, q=0.10):
    p = np.array(pvals, dtype=float)
    ok = ~np.isnan(p)
    out = np.zeros(len(p), bool)
    if ok.sum() == 0:
        return out
    idx = np.where(ok)[0]
    ps = p[idx]; order = np.argsort(ps); m = len(ps)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = ps[order] <= thresh
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        out[idx[order[:kmax + 1]]] = True
    return out


def quintile_test(df, feat, target, mask_is, mask_oos, clip=(0, 4)):
    res = {}
    for name, m in (("IS", mask_is), ("OOS", mask_oos)):
        d = df[m & df[feat].notna() & df[target].notna()].copy()
        if len(d) < 200:
            res[name] = None; continue
        d["q"] = pd.qcut(d[feat].rank(method="first"), 5, labels=False)
        y = d[target].clip(*clip) if clip else d[target]
        top = y[d.q == 4]; bot = y[d.q == 0]
        spread_y = pd.concat([top, -bot]); spread_c = pd.concat([d.week[d.q == 4], d.week[d.q == 0]])
        # spread = mean(top) - mean(bot); cluster t via combined sample with signs
        mt, _, nt = tstat_cluster(top, d.week[d.q == 4]); mb, _, nb = tstat_cluster(bot, d.week[d.q == 0])
        # cluster se via per-week differences of means (approx): use two-sample with cluster se each
        et = top.groupby(d.week[d.q == 4]).agg(["sum", "count"]); eb = bot.groupby(d.week[d.q == 0]).agg(["sum", "count"])
        se_t = np.sqrt(((et["sum"] - mt * et["count"]) ** 2).sum()) / nt
        se_b = np.sqrt(((eb["sum"] - mb * eb["count"]) ** 2).sum()) / nb
        se = np.sqrt(se_t ** 2 + se_b ** 2)
        t = (mt - mb) / se if se > 0 else np.nan
        qm = [float(y[d.q == k].mean()) for k in range(5)]
        res[name] = dict(spread=float(mt - mb), t=float(t), n=int(len(d)), q=qm, rho=float(stats.spearmanr(d[feat], y).correlation))
    N_TESTS["count"] += 1
    return res


def main():
    P = pd.read_pickle(D / "panel.pkl")
    P = P[P.cc.notna() & (P.C0 > 1)]
    P["week"] = P.R.dt.to_period("W").astype(str)
    P["logcap"] = np.log(P.cap_ev)
    P["amc"] = (P.etiming == "amc") | ((P.etiming == "na") & (P.ytiming == "amc"))
    P["month"] = P.R.dt.month
    P["ratio8c"] = P.ratio8.clip(0, 4)
    P["sgn"] = np.sign(P.cc)
    out = {}
    IS = P.R < OOS0; OOS = P.R >= OOS0
    print("panel", len(P), "IS", IS.sum(), "OOS", OOS.sum(), "tickers", P.t.nunique())

    # 1. segment table
    def seg(d):
        v = d.ratio8.dropna()
        return pd.Series(dict(n=len(d), tickers=d.t.nunique(), mean_abs_cc=d.acc.mean(), med_abs_cc=d.acc.median(),
                              mean_abs_co=d.aco.mean(), p_gt5=(d.acc > .05).mean(), p_gt10=(d.acc > .10).mean(),
                              p_gt20=(d.acc > .20).mean(), gap_share=(d.aco / d.acc.replace(0, np.nan)).clip(0, 2).median(),
                              evol_mult=d.evol_mult.median(), ratio8_mean=v.clip(0, 4).mean(), ratio8_med=v.median(),
                              ratio8_gt1=(v > 1).mean(), n_ratio=len(v)))
    tiers = ["mega", "large", "mid", "small", "micro"]
    out["seg_tier_all"] = P[P.tier.isin(tiers)].groupby("tier").apply(seg).reindex(tiers).round(4).to_dict("index")
    out["seg_tier_oos"] = P[OOS & P.tier.isin(tiers)].groupby("tier").apply(seg).reindex(tiers).round(4).to_dict("index")
    out["seg_ind_oos"] = P[OOS].groupby("ind").apply(seg).sort_values("mean_abs_cc", ascending=False).round(4).to_dict("index")
    out["seg_tier_year"] = P[P.tier.isin(tiers) & (P.year >= 2010)].pivot_table(index="year", columns="tier", values="acc", aggfunc="mean").reindex(columns=tiers).round(4).to_dict("index")
    out["seg_ind_tier_oos"] = P[OOS & P.tier.isin(tiers)].pivot_table(index="ind", columns="tier", values="acc", aggfunc="mean").reindex(columns=tiers).round(4).to_dict("index")
    out["timing_oos"] = P[OOS].groupby("amc").apply(seg).round(4).to_dict("index")
    print("\n== segment table (OOS 2019+) ==")
    print(pd.DataFrame(out["seg_tier_oos"]).T[["n", "tickers", "mean_abs_cc", "med_abs_cc", "mean_abs_co", "p_gt10", "ratio8_mean", "ratio8_med", "ratio8_gt1"]].round(3))
    print(pd.DataFrame(out["seg_ind_oos"]).T[["n", "mean_abs_cc", "med_abs_cc", "p_gt10", "ratio8_mean", "ratio8_gt1"]].round(3))

    # 2. predictability of realized / own-history (ratio8) and of raw |cc| scaled
    feats = ["evol_mult", "hist8", "hist8_sd", "rv20", "run5", "run20", "run60", "dist_hi", "vratio", "last_acc", "ratio_prior",
             "ratio_prior_mean4", "peer_ratio", "n_prior", "logcap", "adv20", "last_surprise", "prevday", "month"]
    P["hist8_cv"] = P.hist8_sd / P.hist8
    feats.append("hist8_cv")
    tests = []
    for f in feats:
        r = quintile_test(P, f, "ratio8c", IS, OOS)
        tests.append(dict(feature=f, target="ratio8", **{k: v for k, v in r.items()}))
    # within-tier for the strongest ones later; record p-values for BH on OOS
    for row in tests:
        o = row.get("OOS")
        row["p_oos"] = float(2 * (1 - stats.norm.cdf(abs(o["t"])))) if o and o["t"] == o["t"] else np.nan
    passed = bh([r["p_oos"] for r in tests])
    for row, pz in zip(tests, passed):
        row["bh_oos"] = bool(pz)
    out["feature_tests"] = tests
    print("\n== features -> realized/own-history ratio (top-bottom quintile spread, cluster t) ==")
    for r in tests:
        i, o = r["IS"], r["OOS"]
        print(f"{r['feature']:18s} IS {i['spread']:+.3f} (t {i['t']:+.1f}, rho {i['rho']:+.3f})   OOS {o['spread']:+.3f} (t {o['t']:+.1f}, rho {o['rho']:+.3f}) n={o['n']} BH={r['bh_oos']}" if i and o else r)

    # 2b. by tier: does the ratio depend on tier (market naive proxy) and within tier on the features that passed
    out["tier_feature"] = {}
    for tr in tiers:
        mt = P.tier == tr
        rr = {}
        for f in ("evol_mult", "run20", "dist_hi", "peer_ratio", "ratio_prior_mean4", "hist8_cv", "vratio"):
            rr[f] = quintile_test(P[mt], f, "ratio8c", IS[mt], OOS[mt])
        out["tier_feature"][tr] = rr

    # 3. persistence: ticker mean ratio8 IS vs OOS
    tk = P.groupby("t").agg(n_is=("ratio8c", lambda s: s[IS.loc[s.index]].notna().sum()), n_oos=("ratio8c", lambda s: s[OOS.loc[s.index]].notna().sum()))
    mis = P[IS].groupby("t").ratio8c.mean(); moos = P[OOS].groupby("t").ratio8c.mean()
    both = pd.concat([mis.rename("is"), moos.rename("oos"), tk], axis=1).dropna()
    both = both[(both.n_is >= 8) & (both.n_oos >= 8)]
    out["ticker_persist"] = dict(n=int(len(both)), spearman=float(stats.spearmanr(both["is"], both["oos"]).correlation),
                                 top_decile_is_oos_mean=float(both.sort_values("is").tail(len(both) // 10).oos.mean()),
                                 bottom_decile_is_oos_mean=float(both.sort_values("is").head(len(both) // 10).oos.mean()),
                                 all_oos_mean=float(both.oos.mean()))
    print("\n== ticker persistence (mean ratio8 IS vs OOS) ==", out["ticker_persist"])
    # also split OOS into 2019-22 vs 2023+ for a second persistence read
    A = P[(P.R >= "2019-01-01") & (P.R < "2023-01-01")].groupby("t").ratio8c.agg(["mean", "count"])
    B = P[P.R >= "2023-01-01"].groupby("t").ratio8c.agg(["mean", "count"])
    ab = A.join(B, lsuffix="_a", rsuffix="_b").dropna(); ab = ab[(ab.count_a >= 8) & (ab.count_b >= 8)]
    out["ticker_persist_2019_22_vs_2023"] = dict(n=int(len(ab)), spearman=float(stats.spearmanr(ab.mean_a, ab.mean_b).correlation),
                                                  top_decile_next=float(ab.sort_values("mean_a").tail(len(ab) // 10).mean_b.mean()), all_next=float(ab.mean_b.mean()))
    print("   2019-22 -> 2023+:", out["ticker_persist_2019_22_vs_2023"])
    # industry persistence
    ind_is = P[IS].groupby("ind").ratio8c.mean(); ind_oos = P[OOS].groupby("ind").ratio8c.agg(["mean", "count"])
    out["industry_persist"] = pd.concat([ind_is.rename("is"), ind_oos], axis=1).round(3).to_dict("index")
    print(pd.DataFrame(out["industry_persist"]).T)

    # ranked tickers: OOS mean ratio8 with n>=12, t vs 1, and 2019-22 / 2023+ halves
    rk = P[OOS].groupby("t").agg(n=("ratio8c", "count"), ratio=("ratio8c", "mean"), sd=("ratio8c", "std"), abs_cc=("acc", "mean"),
                                 tier=("tier", "last"), ind=("ind", "last"), gt1=("ratio8c", lambda s: (s > 1).mean()))
    rk["t_vs_1"] = (rk.ratio - 1) / (rk.sd / np.sqrt(rk.n))
    rk = rk.join(ab[["mean_a", "mean_b"]])
    rk = rk[rk.n >= 12].sort_values("t_vs_1", ascending=False)
    out["ranked_tickers_top40"] = rk.head(40).round(3).reset_index().to_dict("records")
    out["ranked_tickers_n"] = int(len(rk))
    out["ranked_tickers_bh_survivors"] = int(bh([2 * (1 - stats.t.cdf(abs(x), 11)) for x in rk.t_vs_1]).sum())
    print("\n== top tickers by OOS realized/own-history (n>=12) ==")
    print(rk.head(25).round(2))
    print("BH survivors among", len(rk), ":", out["ranked_tickers_bh_survivors"])

    # 4. walk-forward HistGB by season (2019Q1+), target ratio8 > 1
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
        from sklearn.metrics import roc_auc_score
        F = ["evol_mult", "hist8", "hist8_cv", "rv20", "run5", "run20", "run60", "dist_hi", "vratio", "last_acc", "ratio_prior",
             "ratio_prior_mean4", "peer_ratio", "n_prior", "logcap", "adv20", "month"]
        X = P[F].astype(float); X["amc"] = P.amc.astype(float)
        for tr in tiers:
            X[f"tier_{tr}"] = (P.tier == tr).astype(float)
        for ind in P.ind.unique():
            X[f"ind_{ind}"] = (P.ind == ind).astype(float)
        y = (P.ratio8c > 1).astype(int); yr = P.ratio8c
        ok = P.ratio8c.notna() & P.hist8.notna()
        seasons = sorted(P.season[OOS & ok].unique())
        preds = pd.Series(np.nan, index=P.index); predr = pd.Series(np.nan, index=P.index)
        for s in seasons:
            tr_m = ok & (P.season < s) & (P.R >= "2010-01-01"); te_m = ok & (P.season == s)
            if tr_m.sum() < 2000 or te_m.sum() < 50:
                continue
            clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, random_state=0).fit(X[tr_m], y[tr_m])
            preds[te_m] = clf.predict_proba(X[te_m])[:, 1]
            reg = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, random_state=0).fit(X[tr_m], yr[tr_m])
            predr[te_m] = reg.predict(X[te_m])
        m = preds.notna()
        auc = roc_auc_score(y[m], preds[m])
        d = P[m].assign(p=preds[m], pr=predr[m])
        d["dec"] = pd.qcut(d.p.rank(method="first"), 10, labels=False)
        dec = d.groupby("dec").agg(n=("ratio8c", "count"), ratio=("ratio8c", "mean"), gt1=("ratio8c", lambda s: (s > 1).mean()), abs_cc=("acc", "mean"))
        by_year = d[d.dec == 9].groupby("year").ratio8c.agg(["mean", "count"])
        out["walkforward"] = dict(auc=float(auc), n=int(m.sum()), deciles=dec.round(3).to_dict("index"), top_decile_by_year=by_year.round(3).to_dict("index"),
                                  corr_reg=float(stats.spearmanr(d.pr, d.ratio8c).correlation), base_gt1=float(y[m].mean()))
        N_TESTS["count"] += 2
        print("\n== walk-forward HistGB (season-by-season, 2019Q1+) ==", "AUC", round(auc, 3), "spearman(reg)", round(out["walkforward"]["corr_reg"], 3))
        print(dec.round(3)); print(by_year.round(3))
        d.to_pickle(D / "wf_preds.pkl")
    except Exception as e:
        print("walkforward failed", e)

    # 5. direction
    dtests = []
    for f in ("run5", "run20", "run60", "dist_hi", "last_cc", "ratio_prior", "vratio", "peer_ratio", "last_surprise"):
        r = quintile_test(P, f, "cc", IS, OOS, clip=(-0.5, 0.5))
        r2 = quintile_test(P, f, "oc", IS, OOS, clip=(-0.3, 0.3))
        dtests.append(dict(feature=f, cc=r, oc=r2))
    out["direction_tests"] = dtests
    print("\n== direction: feature -> signed cc (top-bottom quintile) ==")
    for r in dtests:
        i, o = r["cc"]["IS"], r["cc"]["OOS"]; o2 = r["oc"]["OOS"]
        if i and o:
            print(f"{r['feature']:14s} cc IS {i['spread']:+.4f} (t {i['t']:+.1f})  OOS {o['spread']:+.4f} (t {o['t']:+.1f})   open->close OOS {o2['spread']:+.4f} (t {o2['t']:+.1f})")
    # PEAD (post-gap drift) by reaction size, OOS, own-drift adjusted (subtract ticker's mean 5d/20d return outside events: approx by median)
    d = P[OOS & P.pead5.notna()].copy()
    d["big"] = pd.qcut(d.cc.rank(method="first"), 10, labels=False)
    pe = d.groupby("big").agg(n=("pead5", "count"), cc=("cc", "mean"), oc=("oc", "mean"), pead5=("pead5", "mean"), pead20=("pead20", "mean"))
    out["pead_oos_by_cc_decile"] = pe.round(4).to_dict("index")
    print("\n== PEAD OOS by reaction decile ==\n", pe.round(4))
    # peer read-through signed: peers' signed mean cc in prior 21d of same industry -> this event's cc
    out["n_tests"] = N_TESTS["count"] + len(feats) * 5 + len(dtests) * 2
    json.dump(out, open(D / "analyze_out.json", "w"), indent=1, default=float)
    print("\ntests run (approx incl. per-tier):", out["n_tests"])


if __name__ == "__main__":
    main()
