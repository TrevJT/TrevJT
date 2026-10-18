#!/usr/bin/env python3
"""Earnings-edge study: analyse the Robinhood expired-option sample (real ATM straddle prices around reports).

  python3 research/earnings/rhanalyze.py        # reads data/research_earnings/rh_out_*.jsonl -> rh_events.pkl, rh_out.json

Per event: straddle at the entry close (S0 = call close + put close on the session before R) = the market's implied move
(implied = S0 / C0, the break-even move for a straddle buyer at expiry; for a weekly expiry the premium ~ E|move| + a little time value).
Exits: open of R (sell into the gap), close of R, close of R+1. Straddle return = S1/S0 - 1 at marks; a fill model then charges
half the quoted spread each way, by cap tier (spread_tier below comes from live chains measured 2026-10-14, research_fills.py: trades
print at mid, ~37% of the half-spread paid; we charge 50% to be safe).

Caveats: Robinhood bars are TRADE-based for thin contracts (open 0.01 = no trade yet; close = last trade, possibly stale) and
close-only before ~2023. We require both legs to have a close on the entry day and on R, and drop entries where a leg's close is
<= 0.01 or where the straddle implies a move > 60% or < 0.5%.
"""
import json, glob, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "research_earnings"
# round-trip cost as a fraction of the straddle premium (half-spread each way, quoted-spread share 50%)
SPREAD_TIER = {"mega": 0.03, "large": 0.05, "mid": 0.10, "small": 0.18, "micro": 0.30}


def load():
    rows = []
    for f in sorted(glob.glob(str(D / "rh2_out_*.jsonl"))):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    spec = pd.read_pickle(D / "rh_spec_all.pkl").set_index("eid")
    P = pd.read_pickle(D / "panel.pkl")
    P["eid"] = P.t + "_" + P.R.dt.strftime("%Y-%m-%d")
    P["hist8_cv"] = P.hist8_sd / P.hist8
    P = P.set_index("eid")
    out = []
    for r in rows:
        eid = r.get("eid")
        if eid not in spec.index or eid not in P.index:
            continue
        s = spec.loc[eid]; p = P.loc[eid]
        rec = dict(eid=eid, t=r["t"], R=pd.Timestamp(r["R"]), tier=s.tier, found=not r.get("not_found", False) and "bars" in r, err=r.get("error"))
        if rec["found"]:
            b = r["bars"]
            dates = sorted(b)
            entry = s.entry
            # entry close: last available bar <= entry date
            ent = [d for d in dates if d <= entry]
            Rd = r["R"]
            def leg(d, i):
                v = b.get(d)
                if v is None or len(v) < 4 or v[i] is None:
                    return np.nan
                return float(v[i])
            if ent:
                e = ent[-1]
                rec.update(entry_used=e, S0=leg(e, 1) + leg(e, 3), c0=leg(e, 1), p0=leg(e, 3))
                # 5-session earlier straddle (IV ramp)
                early = [d for d in dates if d <= e][0]
                ce_, pe_ = leg(early, 1), leg(early, 3)
                rec.update(early=early, S_early=(ce_ + pe_) if (ce_ > 0.011 and pe_ > 0.011 and early < e) else np.nan)
            if Rd in b:
                co_, po_ = leg(Rd, 0), leg(Rd, 2)
                rec.update(S_open=(co_ + po_) if (co_ > 0.011 and po_ > 0.011) else np.nan,   # 0.01 open = no trade yet (trade-based bars)
                           S_close=leg(Rd, 1) + leg(Rd, 3), c_close=leg(Rd, 1), p_close=leg(Rd, 3), c_open=co_, p_open=po_)
            nxt = [d for d in dates if d > Rd]
            if nxt:
                rec.update(S_next=leg(nxt[0], 1) + leg(nxt[0], 3))
            rec.update(expiry=r.get("expiry"), strike=r.get("strike"), C0=float(s.C0), dte=(pd.Timestamp(r["expiry"]) - pd.Timestamp(Rd)).days if r.get("expiry") else np.nan)
        for k in ("cc", "co", "c2", "oc", "acc", "aco", "hist8", "ratio8", "evol_mult", "rv20", "run5", "run20", "run60", "dist_hi",
                  "vratio", "peer_ratio", "peer_n", "hist8_cv", "last_acc", "ratio_prior", "n_prior", "ind", "gics", "cap_ev", "etiming", "ytiming", "pead5", "season", "year"):
            rec[k] = p[k]
        out.append(rec)
    E = pd.DataFrame(out)
    return E, spec


def tc(y, cl):
    df = pd.DataFrame({"y": y, "c": cl}).dropna()
    if len(df) < 8:
        return np.nan, np.nan, len(df)
    m = df.y.mean(); g = df.groupby("c").y.agg(["sum", "count"]); e = g["sum"] - m * g["count"]
    se = np.sqrt((e ** 2).sum()) / len(df)
    return float(m), float(m / se) if se > 0 else np.nan, int(len(df))


def main():
    E, spec = load()
    print("rows", len(E), "found", E.found.sum(), "of spec", len(spec))
    out = {"n_rows": int(len(E)), "n_found": int(E.found.sum()), "n_spec": int(len(spec)), "by_tier_found": E.groupby("tier").found.mean().round(3).to_dict()}
    V = E[E.found & E.S0.notna() & (E.S0 > 0.02) & E.S_close.notna() & (E.c0 > 0.01) & (E.p0 > 0.01)].copy()
    V["implied"] = V.S0 / V.C0
    V = V[(V.implied > 0.005) & (V.implied < 0.6)]
    # event-implied move: strip the post-event time value an ATM straddle keeps (0.8 x RV20 x sqrt(DTE after R / 252))
    V["tv_post"] = 0.8 * V.rv20 * np.sqrt(V.dte.clip(lower=0) / 252)
    V["implied_ev"] = np.sqrt((V.implied ** 2 - V.tv_post ** 2).clip(lower=0)).clip(lower=0.5 * V.implied)   # variances add
    V["ratio_mkt"] = V.acc / V.implied_ev         # realized close-to-close / event-implied move
    V["ratio_mkt_raw"] = V.acc / V.implied
    V["ratio_mkt_co"] = V.aco / V.implied_ev
    V["ret_close"] = V.S_close / V.S0 - 1
    V["ret_open"] = V.S_open / V.S0 - 1
    V["ret_next"] = V.S_next / V.S0 - 1
    V["week"] = V.R.dt.to_period("W").astype(str)
    V["cost"] = V.tier.map(SPREAD_TIER)
    V["ret_close_net"] = V.ret_close - V.cost
    V["ret_open_net"] = V.ret_open - V.cost
    V["ret_next_net"] = V.ret_next - V.cost
    V["impl_vs_hist8"] = V.implied / V.hist8
    V["iv_ramp"] = (V.S0 / V.S_early - 1).clip(-0.8, 3)
    V["moneyness"] = V.strike / V.C0 - 1
    V = V[V.moneyness.abs() < 0.06]
    V["oos"] = V.R >= "2025-01-01"
    V.to_pickle(D / "rh_events.pkl")
    print("valid", len(V), V.tier.value_counts().to_dict(), "dte", V.dte.describe()[["min", "50%", "max"]].to_dict())
    tiers = ["mega", "large", "mid", "small"]

    def block(d):
        r = {}
        for k in ("implied", "implied_ev", "acc", "ratio_mkt", "ratio_mkt_raw", "ratio_mkt_co", "impl_vs_hist8", "iv_ramp", "ret_open", "ret_close", "ret_next", "ret_open_net", "ret_close_net", "ret_next_net"):
            m, t, n = tc(d[k], d.week)
            r[k] = dict(mean=m, t=t, n=n, med=float(d[k].median()))
        r["p_win_close_net"] = float((d.ret_close_net > 0).mean())
        r["p_win_open_net"] = float((d.ret_open_net > 0).mean())
        r["n"] = int(len(d)); r["tickers"] = int(d.t.nunique())
        return r
    out["all"] = block(V)
    out["by_tier"] = {tr: block(V[V.tier == tr]) for tr in tiers if (V.tier == tr).sum() >= 20}
    out["by_year"] = {int(y): block(V[V.year == y]) for y in sorted(V.year.unique()) if (V.year == y).sum() >= 20}
    out["by_ind"] = {i: block(V[V.ind == i]) for i in V.ind.unique() if (V.ind == i).sum() >= 25}
    out["by_dte"] = {str(b): block(V[(V.dte >= lo) & (V.dte <= hi)]) for b, (lo, hi) in {"0-3": (0, 3), "4-10": (4, 10), "11-40": (11, 40)}.items() if ((V.dte >= lo) & (V.dte <= hi)).sum() >= 20}
    out["by_timing"] = {k: block(V[V.etiming == k]) for k in ("amc", "bmo") if (V.etiming == k).sum() >= 20}
    pd.set_option("display.width", 250)

    def show(name, dd):
        print(f"\n== {name} ==")
        rows = []
        if not dd:
            print("(none)"); return
        for k, r in dd.items():
            rows.append(dict(seg=k, n=r["n"], implied=r["implied"]["mean"], impl_ev=r["implied_ev"]["mean"], realized=r["acc"]["mean"], ratio=r["ratio_mkt"]["mean"], ratio_med=r["ratio_mkt"]["med"],
                             impl_hist8=r["impl_vs_hist8"]["mean"], ivramp=r["iv_ramp"]["mean"],
                             ret_open=r["ret_open"]["mean"], ret_close=r["ret_close"]["mean"], ret_next=r["ret_next"]["mean"],
                             net_open=r["ret_open_net"]["mean"], t_open=r["ret_open_net"]["t"], net_close=r["ret_close_net"]["mean"], t_close=r["ret_close_net"]["t"], pwin=r["p_win_close_net"]))
        print(pd.DataFrame(rows).set_index("seg").round(3).to_string())
    show("all", {"all": out["all"]}); show("by tier", out["by_tier"]); show("by year", out["by_year"]); show("by industry", out["by_ind"]); show("by dte", out["by_dte"]); show("by timing", out["by_timing"])

    # features -> straddle net return (close exit), tercile spreads with cluster t; IS = <2025, OOS = 2025+
    feats = ["evol_mult", "impl_vs_hist8", "hist8_cv", "rv20", "run5", "run20", "run60", "dist_hi", "vratio", "peer_ratio", "ratio_prior", "last_acc", "iv_ramp", "implied", "n_prior", "dte"]
    ft = []
    for f in feats:
        rec = {"feature": f}
        for name, m in (("IS", ~V.oos), ("OOS", V.oos), ("ALL", V.oos | ~V.oos)):
            d = V[m & V[f].notna()]
            if len(d) < 60:
                rec[name] = None; continue
            q = pd.qcut(d[f].rank(method="first"), 3, labels=False)
            top, bot = d[q == 2], d[q == 0]
            mt, tt, nt = tc(top.ret_close_net, top.week); mb, tb, nb = tc(bot.ret_close_net, bot.week)
            se_t = (mt / tt) if tt == tt and tt != 0 else np.nan; se_b = (mb / tb) if tb == tb and tb != 0 else np.nan
            se = np.sqrt(se_t ** 2 + se_b ** 2) if se_t == se_t and se_b == se_b else np.nan
            rec[name] = dict(top=mt, bot=mb, spread=mt - mb, t=(mt - mb) / se if se and se == se else np.nan, n=int(len(d)),
                             rho=float(stats.spearmanr(d[f], d.ret_close_net).correlation),
                             top_ratio=float(top.ratio_mkt.mean()), bot_ratio=float(bot.ratio_mkt.mean()))
        ft.append(rec)
    out["feature_tests"] = ft
    print("\n== features -> straddle net return (close exit), top-bottom tercile ==")
    for r in ft:
        i, o, a = r["IS"], r["OOS"], r["ALL"]
        if a:
            print(f"{r['feature']:14s} ALL {a['spread']:+.3f} (t {a['t']:+.1f}, rho {a['rho']:+.3f}; top {a['top']:+.3f} bot {a['bot']:+.3f}) "
                  + (f"IS {i['spread']:+.3f} (t {i['t']:+.1f}) " if i else "") + (f"OOS {o['spread']:+.3f} (t {o['t']:+.1f})" if o else ""))

    # calibration: implied vs hist8 by tier (how the market prices relative to the naive proxy), regression of ratio_mkt on panel-model inputs
    out["calib"] = {tr: dict(impl_over_hist8_med=float(V[V.tier == tr].impl_vs_hist8.median()), impl_over_rv20daily=float((V[V.tier == tr].implied / (V[V.tier == tr].rv20 / np.sqrt(252))).median()))
                    for tr in tiers if (V.tier == tr).sum() >= 20}
    print("\ncalibration implied/hist8 by tier:", out["calib"])
    X1 = V.ratio_mkt.clip(0, 4); y1 = V.ret_close.clip(-1, 4)
    b, a = np.polyfit(X1, y1, 1)
    out["calib_ret"] = dict(a=float(a), b=float(b), n=int(len(V)), r=float(np.corrcoef(X1, y1)[0, 1]),
                            by_tier={tr: dict(a=float(np.polyfit(V[V.tier == tr].ratio_mkt.clip(0, 4), V[V.tier == tr].ret_close.clip(-1, 4), 1)[1]),
                                              b=float(np.polyfit(V[V.tier == tr].ratio_mkt.clip(0, 4), V[V.tier == tr].ret_close.clip(-1, 4), 1)[0]))
                                     for tr in tiers if (V.tier == tr).sum() >= 20})
    print("straddle close-exit return = a + b x (realized/event-implied):", out["calib_ret"])
    # walk-forward model inside the sample: predict ret_close_net > 0 from features, train on R < season, test on season (2024Q1+)
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
        F = ["evol_mult", "impl_vs_hist8", "hist8_cv", "rv20", "run5", "run20", "run60", "dist_hi", "vratio", "peer_ratio", "ratio_prior", "last_acc", "iv_ramp", "implied", "n_prior", "dte"]
        X = V[F].astype(float); y = V.ret_close_net.clip(-1, 3)
        seasons = sorted(V.season.unique())
        pred = pd.Series(np.nan, index=V.index)
        for s in seasons:
            trm = V.season < s; tem = V.season == s
            if trm.sum() < 120 or tem.sum() < 10:
                continue
            m = HistGradientBoostingRegressor(max_depth=2, learning_rate=0.05, max_iter=100, random_state=0).fit(X[trm], y[trm])
            pred[tem] = m.predict(X[tem])
        ok = pred.notna()
        d = V[ok].assign(p=pred[ok])
        d["q"] = pd.qcut(d.p.rank(method="first"), 4, labels=False)
        wf = d.groupby("q").agg(n=("ret_close_net", "count"), net=("ret_close_net", "mean"), ratio=("ratio_mkt", "mean"), pwin=("ret_close_net", lambda s: (s > 0).mean()))
        top = d[d.q == 3]; mt, tt, nt = tc(top.ret_close_net, top.week)
        out["walkforward"] = dict(n=int(ok.sum()), spearman=float(stats.spearmanr(d.p, d.ret_close_net).correlation), quartiles=wf.round(3).to_dict("index"), top_t=tt,
                                  top_by_year=top.groupby("year").ret_close_net.agg(["mean", "count"]).round(3).to_dict("index"))
        print("\n== walk-forward (season) model -> straddle net return quartiles ==", "spearman", round(out["walkforward"]["spearman"], 3), "top t", round(tt, 2))
        print(wf.round(3)); print(out["walkforward"]["top_by_year"])
    except Exception as e:
        print("wf failed", e)
    # ticker-level: realized/implied persistence within the sample (first half vs second half of each ticker's events)
    V = V.sort_values(["t", "R"])
    halves = []
    for t, g in V.groupby("t"):
        if len(g) >= 8:
            h = len(g) // 2
            halves.append((t, g.ratio_mkt.iloc[:h].mean(), g.ratio_mkt.iloc[h:].mean(), g.ret_close_net.iloc[:h].mean(), g.ret_close_net.iloc[h:].mean(), len(g), g.tier.iloc[0]))
    H = pd.DataFrame(halves, columns=["t", "ratio_a", "ratio_b", "net_a", "net_b", "n", "tier"])
    if len(H) > 10:
        out["ticker_persist"] = dict(n=int(len(H)), spearman_ratio=float(stats.spearmanr(H.ratio_a, H.ratio_b).correlation), spearman_net=float(stats.spearmanr(H.net_a, H.net_b).correlation),
                                     top_third_next=float(H.sort_values("ratio_a").tail(len(H) // 3).ratio_b.mean()), all_next=float(H.ratio_b.mean()))
        print("\nticker persistence (first half -> second half):", out["ticker_persist"])
    tk = V.groupby("t").agg(n=("ratio_mkt", "count"), tier=("tier", "first"), ind=("ind", "first"), implied=("implied", "mean"), realized=("acc", "mean"), ratio=("ratio_mkt", "mean"),
                            net_close=("ret_close_net", "mean"), net_open=("ret_open_net", "mean"), pwin=("ret_close_net", lambda s: (s > 0).mean()))
    tk["t_net"] = tk.net_close / (V.groupby("t").ret_close_net.std() / np.sqrt(tk.n))
    out["tickers"] = tk[tk.n >= 6].sort_values("net_close", ascending=False).round(3).reset_index().to_dict("records")
    print("\n== tickers (n>=6) by mean net straddle return (close exit) ==")
    print(tk[tk.n >= 6].sort_values("net_close", ascending=False).round(3).head(25))
    print(tk[tk.n >= 6].sort_values("net_close").round(3).head(10))
    json.dump(out, open(D / "rh_out.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
