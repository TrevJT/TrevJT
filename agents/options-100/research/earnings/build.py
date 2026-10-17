#!/usr/bin/env python3
"""Earnings-edge study (2026-10): build the event panel.

  python3 research/earnings/build.py            # -> data/research_earnings/panel.pkl (+ prints coverage)

One row per (ticker, reaction day R). R = the first session whose OPEN can trade on the report:
  EDGAR 8-K item 2.02 accepted before 09:30 ET on D -> R = D; accepted at/after 16:00 ET on D -> R = next session;
  accepted 09:30-16:00 ('mid': late 8-K or intraday release) -> resolved with Yahoo's timing, else dropped.
Every EDGAR event must have a Yahoo earnings date within 2 days (drops non-earnings 2.02 filings such as TSLA delivery reports).
Yahoo-only events (no 8-K match) are kept with Yahoo's timing when it is explicit (16:00 = AMC, <= 09:00 = BMO).

Moves are measured from the close before R (the entry close, C0): co = open(R)/C0-1, cc = close(R)/C0-1, c2 = close(R+1)/C0-1.
All "known at entry" features use bars up to and including R-1. Post-event features (pead5/pead20, Yahoo surprise) are
for the drift study only and are never used as entry inputs.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "research_earnings"
SCRATCH = Path("/private/tmp/claude-501/-Users-trevorthompson-Desktop-stocks/74e8f7e2-d921-494b-8820-b6e65ac5b3fa/scratchpad/earn")

TIERS = [(2e11, "mega"), (1e10, "large"), (2e9, "mid"), (3e8, "small"), (0, "micro")]


def tier(cap):
    if cap != cap or cap is None:
        return "na"
    for lo, name in TIERS:
        if cap >= lo:
            return name
    return "micro"


def sic_group(s):
    try:
        s = int(s)
    except Exception:
        return "unknown"
    if s in (2834, 2835, 2836, 8731):
        return "biotech_pharma"
    if s in (3841, 3842, 3843, 3844, 3845, 3851, 5047) or 8000 <= s <= 8099:
        return "medtech_health_svc"
    if s in (3674,):
        return "semis"
    if s in (7370, 7371, 7372, 7373, 7374, 7375, 7379):
        return "software_internet"
    if 3570 <= s <= 3579 or 3600 <= s <= 3699 or s in (3576, 3577, 3661, 3663, 3669):
        return "hardware_electronics"
    if 5200 <= s <= 5999:
        return "retail"
    if 6000 <= s <= 6299:
        return "banks_finance"
    if 6300 <= s <= 6499:
        return "insurance"
    if 6500 <= s <= 6799:
        return "reit_realestate"
    if 1300 <= s <= 1399 or 2900 <= s <= 2999:
        return "energy"
    if 4000 <= s <= 4999:
        return "transport_utilities_telecom"
    if 2000 <= s <= 2399 or s in (2840, 2844) or 3900 <= s <= 3999:
        return "consumer_goods"
    if 1000 <= s <= 1299 or 1400 <= s <= 1999 or 2400 <= s <= 3999:
        return "industrial_materials"
    if 7000 <= s <= 8999:
        return "services_media"
    return "other"


def main():
    E = pd.read_pickle(D / "edgar_events.pkl")
    Y = pd.read_pickle(D / "yfdates.pkl")
    P = pd.read_pickle(D / "prices.pkl")
    caps = pd.read_pickle(D / "caps.pkl") if (D / "caps.pkl").exists() else {}
    meta = pd.read_pickle(D / "edgar_meta.pkl")
    gics = {}
    for n in ("sp500.csv", "sp400.csv"):
        p = SCRATCH / n
        if p.exists():
            df = pd.read_csv(p)
            for r in df.itertuples():
                gics[str(r.Symbol).replace(".", "-")] = (r._3, r._4, "sp500" if n == "sp500.csv" else "sp400")
    print("edgar", len(E), "yf", len(Y), "prices", len(P), "caps", len(caps))

    # Yahoo dates -> (date, timing)
    yrows = []
    for t, df in Y.items():
        if df is None or len(df) == 0:
            continue
        for ts, r in df.iterrows():
            try:
                ts = pd.Timestamp(ts).tz_convert("America/New_York")
            except Exception:
                ts = pd.Timestamp(ts)
            h = ts.hour
            tm = "amc" if h >= 15 else ("bmo" if h <= 9 else "unk")
            yrows.append((t, ts.strftime("%Y-%m-%d"), tm, r.get("EPS Estimate"), r.get("Reported EPS"), r.get("Surprise(%)")))
    YD = pd.DataFrame(yrows, columns=["t", "ydate", "ytiming", "eps_est", "eps_act", "surprise"]).drop_duplicates(["t", "ydate"])
    YD["yd"] = pd.to_datetime(YD.ydate)
    ymap = {t: g.sort_values("yd") for t, g in YD.groupby("t")}
    print("yahoo dates", len(YD), "tickers", len(ymap))

    rows = []
    for t, g in E.groupby("t"):
        if t not in P:
            continue
        px = P[t]
        idx = px.index
        yg = ymap.get(t)
        last = None
        for r in g.itertuples():
            d = pd.Timestamp(r.rdate)
            tm = r.timing
            ymatch = None
            if yg is not None:
                near = yg[(yg.yd >= d - pd.Timedelta(days=2)) & (yg.yd <= d + pd.Timedelta(days=2))]
                if len(near):
                    near = near.assign(dd=(near.yd - d).abs()).sort_values("dd")
                    ymatch = near.iloc[0]
            if ymatch is None:
                continue                      # not corroborated as an earnings report
            if tm == "mid":
                yd, yt = ymatch.yd, ymatch.ytiming
                if (yd == d - pd.Timedelta(days=1) and yt == "amc") or (yd == d and yt == "bmo") or (yd < d):
                    R0 = d
                elif yd == d and yt == "amc":
                    R0 = d + pd.Timedelta(days=1)
                else:
                    continue
                src = "edgar_mid+yf"
            elif tm == "bmo":
                R0 = d; src = "edgar"
            else:
                R0 = d + pd.Timedelta(days=1); src = "edgar"
            pos = idx.searchsorted(R0)
            if pos >= len(idx) or pos < 30:
                continue
            R = idx[pos]
            if last is not None and (R - last).days < 6:
                continue
            last = R
            rows.append((t, R, src, tm, ymatch.ytiming, ymatch.eps_est, ymatch.eps_act, ymatch.surprise))
    # Yahoo-only events with explicit timing
    have = {(t, R) for t, R, *_ in rows}
    for t, yg in ymap.items():
        if t not in P:
            continue
        px = P[t]; idx = px.index
        for r in yg.itertuples():
            if r.ytiming == "unk":
                continue
            R0 = r.yd if r.ytiming == "bmo" else r.yd + pd.Timedelta(days=1)
            pos = idx.searchsorted(R0)
            if pos >= len(idx) or pos < 30:
                continue
            R = idx[pos]
            if any((t, R2) in have for R2 in idx[max(0, pos - 4):pos + 5]):
                continue
            have.add((t, R))
            rows.append((t, R, "yf", "na", r.ytiming, r.eps_est, r.eps_act, r.surprise))
    EV = pd.DataFrame(rows, columns=["t", "R", "src", "etiming", "ytiming", "eps_est", "eps_act", "surprise"])
    EV = EV.sort_values(["t", "R"]).reset_index(drop=True)
    EV = EV[EV.R <= pd.Timestamp("2026-10-14")]
    print("events", len(EV), EV.src.value_counts().to_dict())

    # price features
    out = []
    for t, g in EV.groupby("t"):
        px = P[t]
        c = px.Close.astype(float); o = px.Open.astype(float); v = px.Volume.astype(float)
        h = px.High.astype(float); lo = px.Low.astype(float)
        lr = np.log(c).diff()
        rv20 = lr.rolling(20).std() * np.sqrt(252)
        rv60 = lr.rolling(60).std() * np.sqrt(252)
        adv20 = (v * c).rolling(20).mean()
        hi252 = c.rolling(252).max()
        idx = c.index
        n = len(idx)
        cap_now = (caps.get(t) or {}).get("mcap")
        ctoday = float(c.iloc[-1])
        for r in g.itertuples():
            i = idx.get_loc(r.R)
            if i < 25 or i + 1 >= n:
                continue
            C0 = c.iloc[i - 1]
            if not (C0 > 0):
                continue
            co = o.iloc[i] / C0 - 1
            cc = c.iloc[i] / C0 - 1
            c2 = c.iloc[i + 1] / C0 - 1 if i + 1 < n else np.nan
            oc = c.iloc[i] / o.iloc[i] - 1              # open -> close of R (post-gap drift)
            rng = (h.iloc[i] - lo.iloc[i]) / C0
            pead5 = c.iloc[i + 5] / c.iloc[i] - 1 if i + 5 < n else np.nan
            pead20 = c.iloc[i + 20] / c.iloc[i] - 1 if i + 20 < n else np.nan
            prev = c.iloc[i - 2] / c.iloc[i - 3] - 1    # a non-event day move for scale
            # known at entry (bars <= R-1)
            run5 = C0 / c.iloc[i - 6] - 1
            run20 = C0 / c.iloc[i - 21] - 1
            run60 = C0 / c.iloc[i - 61] - 1 if i >= 61 else np.nan
            dist_hi = C0 / hi252.iloc[i - 1] - 1 if hi252.iloc[i - 1] == hi252.iloc[i - 1] else np.nan
            vratio = v.iloc[i - 5:i].mean() / v.iloc[i - 65:i - 5].mean() if i >= 65 and v.iloc[i - 65:i - 5].mean() > 0 else np.nan
            cap_ev = cap_now * C0 / ctoday if cap_now else np.nan
            out.append(dict(t=t, R=r.R, src=r.src, etiming=r.etiming, ytiming=r.ytiming, eps_est=r.eps_est, eps_act=r.eps_act,
                            surprise=r.surprise, C0=C0, co=co, cc=cc, c2=c2, oc=oc, rng=rng, pead5=pead5, pead20=pead20,
                            prevday=prev, rv20=rv20.iloc[i - 1], rv60=rv60.iloc[i - 1], adv20=adv20.iloc[i - 1],
                            run5=run5, run20=run20, run60=run60, dist_hi=dist_hi, vratio=vratio, cap_ev=cap_ev))
    PNL = pd.DataFrame(out)
    PNL["tier"] = PNL.cap_ev.map(tier)
    PNL["sic"] = PNL.t.map(lambda t: meta.sic.get(t) if t in meta.index else None)
    PNL["ind"] = PNL.sic.map(sic_group)
    PNL["gics"] = PNL.t.map(lambda t: gics.get(t, (None, None, None))[0])
    PNL["gics_sub"] = PNL.t.map(lambda t: gics.get(t, (None, None, None))[1])
    PNL["year"] = PNL.R.dt.year
    PNL["season"] = PNL.R.dt.year.astype(str) + "Q" + PNL.R.dt.quarter.astype(str)
    PNL["acc"] = PNL.cc.abs()
    PNL["aco"] = PNL.co.abs()

    # own-history features (strictly prior events)
    PNL = PNL.sort_values(["t", "R"]).reset_index(drop=True)
    g = PNL.groupby("t")
    PNL["n_prior"] = g.cumcount()
    for k in (4, 8, 12):
        PNL[f"hist{k}"] = g.acc.transform(lambda s: s.shift(1).rolling(k, min_periods=min(4, k)).mean())
        PNL[f"histco{k}"] = g.aco.transform(lambda s: s.shift(1).rolling(k, min_periods=min(4, k)).mean())
    PNL["hist8_med"] = g.acc.transform(lambda s: s.shift(1).rolling(8, min_periods=4).median())
    PNL["hist8_sd"] = g.acc.transform(lambda s: s.shift(1).rolling(8, min_periods=4).std())
    PNL["hist_all"] = g.acc.transform(lambda s: s.shift(1).expanding(min_periods=4).mean())
    PNL["last_acc"] = g.acc.shift(1)
    PNL["last_cc"] = g.cc.shift(1)
    PNL["last_surprise"] = g.surprise.shift(1)
    # realized / own-history proxy (the market's naive forecast)
    PNL["ratio8"] = PNL.acc / PNL.hist8
    PNL["ratio_prior"] = g.ratio8.shift(1)
    PNL["ratio_prior_mean4"] = g.ratio8.transform(lambda s: s.shift(1).rolling(4, min_periods=2).mean())
    # daily-vol proxy: expected |move| from RV20 for a normal day = rv20/sqrt(252)*sqrt(2/pi)
    PNL["daily_e"] = PNL.rv20 / np.sqrt(252) * np.sqrt(2 / np.pi)
    PNL["evol_mult"] = PNL.hist8 / PNL.daily_e

    # peer read-through: same industry bucket, events in [R-21d, R-1d] of the same season, their ratio8
    PNL["peer_ratio"] = np.nan; PNL["peer_n"] = 0
    PNL = PNL.sort_values("R").reset_index(drop=True)
    for ind, gi in PNL.groupby("ind"):
        if ind in ("unknown", "other"):
            continue
        arr_R = gi.R.values; arr_ratio = gi.ratio8.values; arr_t = gi.t.values
        idxs = gi.index.values
        for k in range(len(gi)):
            R = arr_R[k]
            lo = np.searchsorted(arr_R, R - np.timedelta64(21, "D")); hi = np.searchsorted(arr_R, R - np.timedelta64(1, "D"), side="right")
            m = arr_ratio[lo:hi]; m = m[(arr_t[lo:hi] != arr_t[k]) & ~np.isnan(m)]
            if len(m) >= 3:
                PNL.at[idxs[k], "peer_ratio"] = float(np.mean(np.clip(m, 0, 4))); PNL.at[idxs[k], "peer_n"] = len(m)
    PNL = PNL.sort_values(["t", "R"]).reset_index(drop=True)
    PNL.to_pickle(D / "panel.pkl")
    print("panel", len(PNL), "tickers", PNL.t.nunique())
    print(PNL.groupby("tier").size().to_dict())
    print(PNL.groupby("ind").size().to_dict())
    print(PNL.groupby("year").size().to_dict())


if __name__ == "__main__":
    main()
