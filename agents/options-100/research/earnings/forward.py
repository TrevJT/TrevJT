#!/usr/bin/env python3
"""Earnings-edge study: forward paper watchlist for the 2026-10-19..11-14 season.

  python3 research/earnings/forward.py score     # panel features + model score for every calendar name -> fwd_scores.pkl
  python3 research/earnings/forward.py chains    # yfinance chains (after-hours, delayed is fine) for the top candidates -> fwd_chains.pkl
  python3 research/earnings/forward.py report    # ranked watchlist table (implied move vs model expectation, cost, capital fit)

Model: the same HistGB regressor family as analyze.py (target = realized |cc| / own-history mean, features known at entry),
trained on every event through 2026Q3; the expected move = predicted ratio x hist8. EV uses the RH-sample calibration
(rhanalyze.py: straddle net return vs realized/implied) when available.
"""
import sys, json, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "research_earnings"
SCRATCH = Path("/private/tmp/claude-501/-Users-trevorthompson-Desktop-stocks/74e8f7e2-d921-494b-8820-b6e65ac5b3fa/scratchpad/earn")
sys.path.insert(0, str(ROOT / "bot"))
F = ["evol_mult", "hist8", "hist8_cv", "rv20", "run5", "run20", "run60", "dist_hi", "vratio", "last_acc", "ratio_prior",
     "ratio_prior_mean4", "peer_ratio", "n_prior", "logcap", "adv20", "month"]


def score():
    from sklearn.ensemble import HistGradientBoostingRegressor
    P = pd.read_pickle(D / "panel.pkl")
    P = P[P.cc.notna() & (P.C0 > 1)]
    P["logcap"] = np.log(P.cap_ev); P["amc"] = (P.etiming == "amc") | ((P.etiming == "na") & (P.ytiming == "amc"))
    P["month"] = P.R.dt.month; P["hist8_cv"] = P.hist8_sd / P.hist8; P["ratio8c"] = P.ratio8.clip(0, 4)
    cal = pd.read_csv(SCRATCH / "rh_calendar.csv")
    prices = pd.read_pickle(D / "prices.pkl")
    ok = P.ratio8c.notna() & P.hist8.notna() & (P.R >= "2010-01-01")
    X = P.loc[ok, F].astype(float); X["amc"] = P.loc[ok, "amc"].astype(float)
    tiers = ["mega", "large", "mid", "small", "micro"]
    for tr in tiers:
        X[f"tier_{tr}"] = (P.loc[ok, "tier"] == tr).astype(float)
    inds = sorted(P.ind.unique())
    for ind in inds:
        X[f"ind_{ind}"] = (P.loc[ok, "ind"] == ind).astype(float)
    reg = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, random_state=0).fit(X, P.loc[ok, "ratio8c"])
    # feature rows for upcoming events: last panel row per ticker gives the history; recompute price features as of 2026-10-16
    rows = []
    last = P.sort_values("R").groupby("t").last()
    for r in cal.itertuples():
        t = r.symbol
        if t not in last.index or t not in prices:
            continue
        px = prices[t]; c = px.Close.astype(float); o = px.Open.astype(float); v = px.Volume.astype(float)
        if len(c) < 70:
            continue
        L = last.loc[t]
        lr = np.log(c).diff(); C0 = float(c.iloc[-1])
        hist8 = P[P.t == t].acc.tail(8).mean() if (P.t == t).sum() >= 4 else np.nan
        hist8_sd = P[P.t == t].acc.tail(8).std()
        hist_all = P[P.t == t].acc.mean()
        rec = dict(t=t, rdate=r.date, timing=r.timing, verified=r.verified, C0=C0, n_prior=int((P.t == t).sum()), hist8=hist8, hist8_sd=hist8_sd, hist_all=hist_all,
                   hist8_cv=hist8_sd / hist8 if hist8 else np.nan, rv20=float(lr.tail(20).std() * np.sqrt(252)), run5=C0 / float(c.iloc[-6]) - 1,
                   run20=C0 / float(c.iloc[-21]) - 1, run60=C0 / float(c.iloc[-61]) - 1, dist_hi=C0 / float(c.tail(252).max()) - 1,
                   vratio=float(v.tail(5).mean() / v.iloc[-65:-5].mean()) if v.iloc[-65:-5].mean() > 0 else np.nan,
                   last_acc=float(P[P.t == t].acc.iloc[-1]), ratio_prior=float(P[P.t == t].ratio8.iloc[-1]) if pd.notna(P[P.t == t].ratio8.iloc[-1]) else np.nan,
                   ratio_prior_mean4=float(P[P.t == t].ratio8.tail(4).mean()), peer_ratio=np.nan, logcap=np.log(L.cap_ev * C0 / L.C0) if L.cap_ev == L.cap_ev else np.nan,
                   adv20=float((v * c).tail(20).mean()), month=pd.Timestamp(r.date).month, amc=float(r.timing == "pm"), tier=L.tier, ind=L.ind, gics=L.gics,
                   last_ratio8=float(P[P.t == t].ratio8.iloc[-1]) if pd.notna(P[P.t == t].ratio8.iloc[-1]) else np.nan)
        rec["daily_e"] = rec["rv20"] / np.sqrt(252) * np.sqrt(2 / np.pi)
        rec["evol_mult"] = hist8 / rec["daily_e"] if hist8 and rec["daily_e"] else np.nan
        rows.append(rec)
    W = pd.DataFrame(rows)
    # peer read-through as of today: same industry, reports since 2026-09-25 in the panel (few so far; filled nightly during the season)
    recent = P[P.R >= "2026-09-25"]
    pr = recent.groupby("ind").ratio8.agg(lambda s: s.clip(0, 4).mean() if s.notna().sum() >= 3 else np.nan)
    W["peer_ratio"] = W.ind.map(pr)
    Xw = W[F].astype(float); Xw["amc"] = W.amc
    for tr in tiers:
        Xw[f"tier_{tr}"] = (W.tier == tr).astype(float)
    for ind in inds:
        Xw[f"ind_{ind}"] = (W.ind == ind).astype(float)
    W["pred_ratio"] = reg.predict(Xw[X.columns])
    W["exp_move"] = W.pred_ratio * W.hist8
    W = W[W.hist8.notna()]
    W.to_pickle(D / "fwd_scores.pkl")
    print("scored", len(W)); print(W.sort_values("pred_ratio", ascending=False).head(20)[["t", "rdate", "timing", "tier", "ind", "hist8", "pred_ratio", "exp_move", "rv20", "run20"]].round(3))


def chains():
    import yfinance as yf
    W = pd.read_pickle(D / "fwd_scores.pkl")
    f = D / "fwd_chains.pkl"
    out = pd.read_pickle(f) if f.exists() else {}
    cand = W[(W.tier.isin(["mega", "large", "mid", "small"])) & (W.n_prior >= 8)]
    cand = cand.sort_values("hist8", ascending=False) if "movers" in sys.argv else cand.sort_values("pred_ratio", ascending=False)
    if "mega" in sys.argv:
        cand = W[(W.tier == "mega") | W.t.isin(["TSLA", "NFLX", "META", "MSFT", "GOOGL", "AMZN", "AAPL", "AVGO", "AMD", "COST", "LLY", "ORCL", "CRM", "NVDA", "JPM", "IBM", "INTC", "NOW", "SNAP", "COIN", "HOOD", "PLTR", "SOFI", "RBLX", "UBER", "SHOP", "SPOT", "ARM", "SMCI", "MSTR"])]
    todo = [t for t in cand.t if t not in out][: int(sys.argv[2]) if len(sys.argv) > 2 else 120]
    print("chains todo", len(todo))
    for i, t in enumerate(todo):
        row = W[W.t == t].iloc[0]
        R = pd.Timestamp(row.rdate) + (pd.Timedelta(days=1) if row.timing == "pm" else pd.Timedelta(0))
        try:
            tk = yf.Ticker(t)
            exps = [e for e in tk.options if pd.Timestamp(e) >= R]
            if not exps:
                out[t] = None; continue
            res = {}
            for e in exps[:2]:
                ch = tk.option_chain(e)
                spot = row.C0
                calls = ch.calls.assign(d=(ch.calls.strike - spot).abs()).sort_values("d")
                puts = ch.puts.assign(d=(ch.puts.strike - spot).abs()).sort_values("d")
                if not len(calls) or not len(puts):
                    continue
                k = calls.strike.iloc[0]
                c = calls.iloc[0]; p = puts[puts.strike == k]
                p = p.iloc[0] if len(p) else puts.iloc[0]
                res[e] = dict(strike=float(k), c_bid=float(c.bid), c_ask=float(c.ask), p_bid=float(p.bid), p_ask=float(p.ask), c_oi=float(c.openInterest or 0), p_oi=float(p.openInterest or 0),
                              c_vol=float(c.volume or 0), p_vol=float(p.volume or 0), n_strikes=int(len(calls)))
            out[t] = res
        except Exception as ex:
            out[t] = {"error": str(ex)[:80]}
        if i % 10 == 0:
            pd.to_pickle(out, f); print("  chains", i, t, flush=True)
        time.sleep(0.6)
    pd.to_pickle(out, f)
    print("chains", len(out))


def report():
    W = pd.read_pickle(D / "fwd_scores.pkl")
    ch = pd.read_pickle(D / "fwd_chains.pkl")
    calib = json.load(open(D / "rh_out.json")) if (D / "rh_out.json").exists() else {}
    rows = []
    for t, res in ch.items():
        if not res or "error" in res:
            continue
        row = W[W.t == t].iloc[0]
        for e, q in res.items():
            mid = (q["c_bid"] + q["c_ask"]) / 2 + (q["p_bid"] + q["p_ask"]) / 2
            ask = q["c_ask"] + q["p_ask"]
            if mid <= 0 or q["c_bid"] <= 0 or q["p_bid"] <= 0:
                continue                      # stale / one-sided weekend quotes
            spread = (ask - mid) * 2 / mid
            implied = mid / row.C0
            Rday = pd.Timestamp(row.rdate) + (pd.Timedelta(days=1) if row.timing == "pm" else pd.Timedelta(0))
            dte_post = (pd.Timestamp(e) - Rday).days
            tv = 0.8 * row.rv20 * np.sqrt(max(dte_post, 0) / 252)
            implied_ev = max(np.sqrt(max(implied ** 2 - tv ** 2, 0)), 0.5 * implied)   # variances add
            rows.append(dict(implied_ev=implied_ev, dte_post=dte_post,t=t, rdate=row.rdate, timing=row.timing, verified=row.verified, tier=row.tier, ind=row.ind, expiry=e, strike=q["strike"], spot=row.C0,
                             straddle_mid=mid, straddle_ask=ask, spread_pct=spread, implied=implied, hist8=row.hist8, hist_all=row.hist_all, pred_ratio=row.pred_ratio,
                             exp_move=row.exp_move, exp_over_impl=row.exp_move / implied_ev, oi=q["c_oi"] + q["p_oi"], n_prior=row.n_prior,
                             cost_mid=mid * 100, cost_ask=ask * 100, fits_170=ask * 100 <= 170, rv20=row.rv20, run20=row.run20, dist_hi=row.dist_hi))
    T = pd.DataFrame(rows)
    T = T[T.spread_pct < 0.5]
    # EV at the close exit: straddle return = a + b x (realized/event-implied) from the Robinhood sample (rhanalyze.py), model's
    # realized/implied forecast = pred_ratio x hist8 / implied_ev, minus the live round-trip spread (half the quoted spread each way)
    cr = calib.get("calib_ret", {"a": -0.6, "b": 0.6, "by_tier": {}})
    def ev(r):
        c = cr.get("by_tier", {}).get(r.tier, cr)
        return c["a"] + c["b"] * min(r.exp_over_impl, 3) - r.spread_pct / 2
    T["ev_close"] = T.apply(ev, axis=1)
    T["tier_hist_ret"] = T.tier.map({k: v["ret_close"]["mean"] for k, v in calib.get("by_tier", {}).items()})
    T.to_pickle(D / "fwd_table.pkl")
    pd.set_option("display.width", 250)
    first = T.sort_values(["t", "expiry"]).groupby("t").first().reset_index()
    print(first.sort_values("exp_over_impl", ascending=False).head(40)[["t", "rdate", "timing", "tier", "ind", "expiry", "spot", "straddle_mid", "spread_pct", "implied", "implied_ev", "hist8", "pred_ratio", "exp_move", "exp_over_impl", "ev_close", "oi", "cost_ask", "fits_170"]].round(3).to_string())
    print("\nfits $170 (ask):"); print(first[first.fits_170].sort_values("exp_over_impl", ascending=False).head(25)[["t", "rdate", "timing", "tier", "ind", "expiry", "spot", "straddle_mid", "spread_pct", "implied_ev", "hist8", "exp_move", "exp_over_impl", "ev_close", "oi", "cost_ask"]].round(3).to_string())


if __name__ == "__main__":
    globals()[sys.argv[1]]()
