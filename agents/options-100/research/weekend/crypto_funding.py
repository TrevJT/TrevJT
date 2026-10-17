#!/usr/bin/env python3
"""Crypto perpetual funding, basis and weekend gaps as signals (Trevor: "maybe it's not the options... futures that don't expire").

Hard rule: perps/futures/spot-on-margin are NOT tradeable. Tradeable proxies: long calls/puts on IBIT (BTC ETF, options since Nov 2024),
COIN, MSTR, MARA, RIOT, HOOD. So each signal is tested on (a) BTC itself [RESEARCH-ONLY / with-more-capital], (b) the equity proxies.

Signals (all known at the decision time; times in ET):
  F1  Deribit BTC-PERPETUAL funding, 8h rate, 1-day and 7-day sums; z-score vs trailing 90 days. Hypothesis: extreme positive funding
      (crowded longs) -> next 1-3 day BTC return negative; extreme negative -> positive (classic crowded-trade reversal).
  F2  Weekend move: BTC Fri 16:00 -> Mon 09:30 return. Hypothesis: Monday US crypto equities gap and either continue or fade.
  F3  Overnight BTC 16:00 -> 09:00 return -> COIN/MSTR/MARA open->close (beyond the gap). Tests continuation vs fade.
      (hourly bars are labelled by START time: the 08:00 bar's close is the 09:00 price; a first version used the 09:00 bar and leaked 09:30-10:00)
  F4  Weekend realized BTC range -> Monday IBIT/COIN straddle (is weekend vol priced?).  [only descriptive here: no IBIT option history]
Data: Deribit funding 2019-04+, Coinbase 1h 2022-09+, yfinance BTC-USD 1h (730d) and daily, 1-min sessions of the crypto names 2017-2026.
Splits: IS = before 2023-07, OOS = 2023-07+ (funding) ; BH over all tests.
"""
import json
import numpy as np, pandas as pd
from common import *

ET = "America/New_York"


def btc_hourly():
    c = pd.read_csv(os.path.join(RAW, "coinbase_btc_1h.csv"))
    c["ts"] = pd.to_datetime(c.t, unit="s", utc=True).dt.tz_convert(ET)
    c = c.set_index("ts").sort_index()
    y = yf_raw("BTC-USD", "1h").tz_convert(ET)
    s = pd.concat([c.close, y.close[y.index < c.index.min()]]).sort_index()
    s = s[~s.index.duplicated()]
    return s


def funding():
    f = pd.read_csv(os.path.join(RAW, "deribit_btc_funding.csv"))
    f["ts"] = pd.to_datetime(f.timestamp, unit="ms", utc=True).dt.tz_convert(ET)
    f = f.set_index("ts").sort_index()
    # interest_8h is the 8h funding rate observed at that hour (Deribit publishes hourly); daily sum of interest_1h = daily funding paid
    d = f.interest_1h.resample("1D").sum()
    d.index = d.index.tz_localize(None)            # keep ET calendar dates (midnight) so it aligns with daily bars
    return d


def btc_daily_close(s):
    """BTC price at 16:00 ET each calendar day."""
    at16 = s[(s.index.hour == 15)]                   # 15:00 bar closes at 16:00 ET
    at16 = at16.groupby(at16.index.normalize()).last()
    at16.index = at16.index.tz_localize(None)
    return at16


def main():
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    res = {}
    s = btc_hourly()
    p16 = btc_daily_close(s)
    btc_d = daily("BTC-USD")
    fund = funding()
    # ---------- F1 funding -> next BTC returns (daily UTC closes from yfinance, long history 2019+)
    r = np.log(btc_d.close / btc_d.close.shift(1))
    df = pd.DataFrame({"r": r})
    df["f1"] = fund.reindex(df.index); df["f7"] = fund.rolling(7).sum().reindex(df.index)
    df["f1z"] = (df.f1 - df.f1.rolling(90).mean()) / df.f1.rolling(90).std(); df["f7z"] = (df.f7 - df.f7.rolling(90).mean()) / df.f7.rolling(90).std()
    for h in [1, 3, 7]:
        df[f"fwd{h}"] = np.log(btc_d.close.shift(-h) / btc_d.close)
    df = df.dropna(subset=["f1", "f7"])
    df["period"] = np.where(df.index < "2023-07-01", "IS", "OOS")
    rows = []
    for feat in ["f1", "f7", "f1z", "f7z"]:
        for h in [1, 3, 7]:
            for per in ["IS", "OOS"]:
                d = df[(df.period == per)].dropna(subset=[feat, f"fwd{h}"])
                q = pd.qcut(d[feat].rank(method="first"), 5, labels=False)
                top = d.loc[q == 4, f"fwd{h}"]; bot = d.loc[q == 0, f"fwd{h}"]
                sp = bot.mean() - top.mean()          # contrarian: low funding minus high funding
                wk = d.index.isocalendar().week.to_numpy() + 100 * d.index.year.to_numpy()
                x = np.where(q == 0, d[f"fwd{h}"], np.where(q == 4, -d[f"fwd{h}"], np.nan))
                t = tstat_cluster(x, wk)
                rho = d[[feat, f"fwd{h}"]].corr(method="spearman").iloc[0, 1]
                rows.append(dict(test="F1_funding_contrarian", feat=feat, h=h, period=per, n=len(d), spread_bp=round(sp * 1e4, 1), t=round(t, 2), p=pval(t, (q == 0).sum() + (q == 4).sum()), rho=round(rho, 3),
                                 top_mean_bp=round(top.mean() * 1e4, 1), bot_mean_bp=round(bot.mean() * 1e4, 1)))
    F1 = pd.DataFrame(rows); print("== F1 funding -> BTC forward returns (contrarian spread = low-funding quintile minus high)"); print(F1.to_string(index=False))
    res["F1"] = F1.to_dict("records")
    # ---------- F2/F3: BTC overnight & weekend -> crypto equities open->close
    names = ["COIN", "MSTR", "MARA", "RIOT", "HOOD", "CLSK"]
    rows = []
    for nm in names:
        D = sessions(nm)
        dates = D["dates"]; P = D["P"]; ok = D["ok"]
        oc = np.log(P[:, 390] / P[:, 0]); oc_935 = np.log(P[:, 390] / P[:, 5]); first5 = np.log(P[:, 5] / P[:, 0])
        gap = D["gap"]
        # BTC: 16:00 ET prior trading day -> 09:30 ET today (use 09:00 hourly bar close, i.e. price at 10:00? use the bar labelled 09:00 = open of 09:00 hour)
        at9 = s[s.index.hour == 8]; at9 = at9.groupby(at9.index.normalize()).last(); at9.index = at9.index.tz_localize(None)   # 08:00 bar closes ~09:00 ET (bars are labelled by START; the 09:00 bar would leak 09:30-10:00)
        prev16 = p16.reindex(dates - pd.Timedelta(days=0)).to_numpy()  # placeholder
        # previous trading day's 16:00 price: map each session date to the prior session date
        prev_dates = pd.Series(dates).shift(1)
        p_prev16 = p16.reindex(prev_dates).to_numpy()
        p_9 = at9.reindex(dates).to_numpy()
        btc_on = np.log(p_9 / p_prev16)
        df = pd.DataFrame(dict(date=dates, oc=oc, oc_935=oc_935, first5=first5, gap=gap, btc_on=btc_on, ok=ok)).dropna(subset=["btc_on", "oc", "gap"])
        df = df[df.ok]
        df["dow"] = df.date.dt.dayofweek
        df["period"] = np.where(df.date < "2024-07-01", "IS", "OOS")
        df["resid_gap"] = df.gap - 1.5 * df.btc_on                     # stock gap beyond its BTC beta (beta ~1.5 for miners/MSTR; COIN ~1.2)
        for per in ["IS", "OOS"]:
            d = df[df.period == per]
            if len(d) < 60:
                continue
            for feat, tgt, label in [("btc_on", "oc", "F3_btc_overnight->oc"), ("btc_on", "oc_935", "F3_btc_overnight->935c"), ("gap", "oc_935", "gap->935c (fade?)"), ("resid_gap", "oc_935", "resid_gap->935c")]:
                rho = d[[feat, tgt]].corr(method="spearman").iloc[0, 1]
                q = pd.qcut(d[feat].rank(method="first"), 3, labels=False)
                sp = d.loc[q == 2, tgt].mean() - d.loc[q == 0, tgt].mean()
                se = np.sqrt(d.loc[q == 2, tgt].var() / (q == 2).sum() + d.loc[q == 0, tgt].var() / (q == 0).sum())
                rows.append(dict(name=nm, test=label, period=per, n=len(d), rho=round(rho, 3), tercile_spread_bp=round(sp * 1e4, 1), t=round(sp / se, 2), p=pval(sp / se, len(d))))
            # weekend: Monday sessions, BTC Fri 16:00 -> Mon 09:30
            mon = d[d.dow == 0]
            if len(mon) >= 40:
                rho = mon[["btc_on", "oc_935"]].corr(method="spearman").iloc[0, 1]
                q = pd.qcut(mon.btc_on.rank(method="first"), 3, labels=False)
                sp = mon.loc[q == 2, "oc_935"].mean() - mon.loc[q == 0, "oc_935"].mean(); se = np.sqrt(mon.loc[q == 2, "oc_935"].var() / (q == 2).sum() + mon.loc[q == 0, "oc_935"].var() / (q == 0).sum())
                rows.append(dict(name=nm, test="F2_weekend_btc->Mon_935c", period=per, n=len(mon), rho=round(rho, 3), tercile_spread_bp=round(sp * 1e4, 1), t=round(sp / se, 2), p=pval(sp / se, len(mon))))
                # Monday |move| vs other days (straddle angle)
                rows.append(dict(name=nm, test="Mon_abs_oc_vs_other", period=per, n=len(mon), rho=np.nan, tercile_spread_bp=round((mon.oc.abs().mean() - d[d.dow != 0].oc.abs().mean()) * 1e4, 1),
                                 t=round(tstat(mon.oc.abs().to_numpy() - d[d.dow != 0].oc.abs().mean()), 2), p=np.nan))
    F3 = pd.DataFrame(rows); print("\n== F2/F3 BTC overnight/weekend -> crypto equities"); print(F3.to_string(index=False)); res["F2F3"] = F3.to_dict("records")
    # ---------- BTC itself: weekend return vs Monday-Tuesday continuation (RESEARCH-ONLY on BTC; IBIT proxy)
    b = p16.copy(); bd = pd.DataFrame({"p": b}); bd["dow"] = bd.index.dayofweek
    bd["r_wkend"] = np.log(bd.p / bd.p.shift(2)); bd["fwd1"] = np.log(bd.p.shift(-1) / bd.p); bd["fwd2"] = np.log(bd.p.shift(-2) / bd.p)
    mon = bd[(bd.dow == 0)].dropna()
    rho1 = mon[["r_wkend", "fwd1"]].corr(method="spearman").iloc[0, 1]; rho2 = mon[["r_wkend", "fwd2"]].corr(method="spearman").iloc[0, 1]
    res["btc_weekend"] = dict(n=len(mon), rho_fwd1=round(rho1, 3), rho_fwd2=round(rho2, 3), mean_abs_wkend_bp=round(mon.r_wkend.abs().mean() * 1e4, 1), mean_abs_wkday_bp=round(bd[bd.dow.isin([1, 2, 3, 4])].fwd1.abs().mean() * 1e4, 1))
    print("\n== BTC weekend (Fri16->Mon16) vs Mon->Tue/Wed continuation:", res["btc_weekend"])
    # IBIT option economics sketch: IBIT ~ BTC/1750; 1-week ATM call at IV 50% costs ~0.5*sqrt(7/365)*0.8 = 5.5% of spot
    ibit = daily("IBIT"); px = float(ibit.close.iloc[-1])
    res["ibit"] = dict(price=round(px, 2), one_week_atm_call_est=round(px * 0.5 * np.sqrt(7 / 365) * 0.8 * 100, 0), note="cost per contract at IV 50%; min capital at 35% sizing = ~3x that")
    print("IBIT", res["ibit"])
    # multiple testing
    allp = pd.concat([F1[["p"]], F3[["p"]]]).p.dropna().to_numpy()
    res["n_tests"] = int(len(allp)); res["bh_survivors"] = int(bh(allp, 0.10).sum())
    oosp = pd.concat([F1[F1.period == "OOS"][["p"]], F3[F3.period == "OOS"][["p"]]]).p.dropna().to_numpy()
    res["n_tests_oos"] = int(len(oosp)); res["bh_survivors_oos"] = int(bh(oosp, 0.10).sum())
    print("tests:", res["n_tests"], "BH survivors:", res["bh_survivors"], "| OOS tests:", res["n_tests_oos"], "OOS BH survivors:", res["bh_survivors_oos"])
    json.dump(res, open(os.path.join(OUT, "crypto_funding.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
