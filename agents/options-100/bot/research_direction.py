#!/usr/bin/env python3
"""Research: can any indicator (trend, vol state, rates/credit, commodities/FX, macro, calendar/events, breadth)
predict SPY/QQQ DIRECTION well enough to pay for long options?  And which long-only-options strategy fits a ~$170 account?

  python3 agents/options-100/bot/research_direction.py fetch       # FRED macro + mega-cap earnings dates -> data/research_direction_cache.pkl
  python3 agents/options-100/bot/research_direction.py signals     # ~300 single-signal OOS tests (train <2015, test 2015+), BH/Bonferroni
  python3 agents/options-100/bot/research_direction.py model       # walk-forward ridge-logistic combo (all features / survivors), confidence deciles
  python3 agents/options-100/bot/research_direction.py options     # option economics (BS, IV = VIX x ratio, 3% round trip) for survivors + baselines
  python3 agents/options-100/bot/research_direction.py strategies  # strategies (a)-(f): OOS EV on premium, freq, $170 bootstrap
  python3 agents/options-100/bot/research_direction.py all

Conventions (no look-ahead):
  * features are known at the close of day t (VIX close 16:15 treated as known). Late-stamped series (CL=F/GC=F/DXY settle
    after 16:00, BTC daily bar ends 20:00 ET) are lagged one day for close->close targets; used unlagged only for the
    next-day open->close target (known by 09:30).
  * FRED series are aligned on availability date = observation date + publication lag (see FRED_LAG).
  * targets: oc1 = next-day open->close (the 0DTE trade; also gets the next-day gap as a feature),
             cc1/cc5/cc20 = close t -> close t+h (adj close).
  * direction of each signal is learned on train (<2015; or first 3y of a short series) and frozen for test.
Results are written to data/research_direction_results.json (gitignored) for the write-up in research/direction.md.
"""
import socket as _sk
_gai = _sk.getaddrinfo
_sk.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, _sk.AF_INET, *a, **k)   # IPv6 times out on this machine
import sys, json, math, pickle, sqlite3, urllib.request, io
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "market.db"
CACHE = ROOT / "data" / "research_direction_cache.pkl"
OUT = ROOT / "data" / "research_direction_results.json"
SPLIT = pd.Timestamp("2015-01-01")
LAST3 = pd.Timestamp("2023-10-14")
END = pd.Timestamp("2026-10-13")      # last complete session in the DB at time of writing (10-14 bar is intraday)
COST = 0.03                           # round-trip cost as a fraction of premium (1.5% each side)
IVR = 0.90                            # SPY ATM IV ~= 0.9 x VIX for 2-6 week tenors
QQQ_VOL = 1.20                        # QQQ IV ~= 1.2 x SPY IV (VXN/VIX proxy)
SKEW = 5.0                            # IV(K) = IV_atm * (1 - SKEW * ln(K/S)): +3% OTM call ~ -15% IV, -3% OTM put ~ +15% IV

FRED = ["UNRATE", "ICSA", "PAYEMS", "CPIAUCSL", "T10Y2Y", "T10Y3M", "BAA10Y", "BAMLH0A0HYM2", "NFCI",
        "SAHMREALTIME", "DFF", "USREC"]
# publication lag in calendar days from FRED observation date to first availability
FRED_LAG = {"UNRATE": 40, "PAYEMS": 40, "SAHMREALTIME": 40, "CPIAUCSL": 46, "ICSA": 6, "NFCI": 6,
            "T10Y2Y": 1, "T10Y3M": 1, "BAA10Y": 1, "BAMLH0A0HYM2": 1, "DFF": 1, "USREC": 365}
MEGA = ["AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA", "AVGO"]

# ---- event calendars -------------------------------------------------------------------------------------------
# FOMC scheduled decision days. 1994-2014 hard-coded from the Fed's historical meeting calendar (federalreserve.gov
# /monetarypolicy/fomc_historical.htm); 2015-2026 from research/brainstorm/macro_events.py. Unscheduled moves excluded.
FOMC_OLD = """1994-02-04 1994-03-22 1994-05-17 1994-07-06 1994-08-16 1994-09-27 1994-11-15 1994-12-20 1995-02-01 1995-03-28
1995-05-23 1995-07-06 1995-08-22 1995-09-26 1995-11-15 1995-12-19 1996-01-31 1996-03-26 1996-05-21 1996-07-03 1996-08-20
1996-09-24 1996-11-13 1996-12-17 1997-02-05 1997-03-25 1997-05-20 1997-07-02 1997-08-19 1997-09-30 1997-11-12 1997-12-16
1998-02-04 1998-03-31 1998-05-19 1998-07-01 1998-08-18 1998-09-29 1998-11-17 1998-12-22 1999-02-03 1999-03-30 1999-05-18
1999-06-30 1999-08-24 1999-10-05 1999-11-16 1999-12-21 2000-02-02 2000-03-21 2000-05-16 2000-06-28 2000-08-22 2000-10-03
2000-11-15 2000-12-19 2001-01-31 2001-03-20 2001-05-15 2001-06-27 2001-08-21 2001-10-02 2001-11-06 2001-12-11 2002-01-30
2002-03-19 2002-05-07 2002-06-26 2002-08-13 2002-09-24 2002-11-06 2002-12-10 2003-01-29 2003-03-18 2003-05-06 2003-06-25
2003-08-12 2003-09-16 2003-10-28 2003-12-09 2004-01-28 2004-03-16 2004-05-04 2004-06-30 2004-08-10 2004-09-21 2004-11-10
2004-12-14 2005-02-02 2005-03-22 2005-05-03 2005-06-30 2005-08-09 2005-09-20 2005-11-01 2005-12-13 2006-01-31 2006-03-28
2006-05-10 2006-06-29 2006-08-08 2006-09-20 2006-10-25 2006-12-12 2007-01-31 2007-03-21 2007-05-09 2007-06-28 2007-08-07
2007-09-18 2007-10-31 2007-12-11 2008-01-30 2008-03-18 2008-04-30 2008-06-25 2008-08-05 2008-09-16 2008-10-29 2008-12-16
2009-01-28 2009-03-18 2009-04-29 2009-06-24 2009-08-12 2009-09-23 2009-11-04 2009-12-16 2010-01-27 2010-03-16 2010-04-28
2010-06-23 2010-08-10 2010-09-21 2010-11-03 2010-12-14 2011-01-26 2011-03-15 2011-04-27 2011-06-22 2011-08-09 2011-09-21
2011-11-02 2011-12-13 2012-01-25 2012-03-13 2012-04-25 2012-06-20 2012-08-01 2012-09-13 2012-10-24 2012-12-12 2013-01-30
2013-03-20 2013-05-01 2013-06-19 2013-07-31 2013-09-18 2013-10-30 2013-12-18 2014-01-29 2014-03-19 2014-04-30 2014-06-18
2014-07-30 2014-09-17 2014-10-29 2014-12-17"""


def _brainstorm_lists():
    src = (ROOT / "research" / "brainstorm" / "macro_events.py").read_text()
    out = {}
    for name in ("CPI", "NFP", "FOMC"):
        s = src.split(f'{name}="""')[1].split('"""')[0]
        out[name] = [pd.Timestamp(x.strip()) for x in s.split(",") if x.strip()]
    return out


# ---- small numerics ------------------------------------------------------------------------------------------------
def ncdf(x):
    x = np.asarray(x, float)
    z = np.abs(x) / math.sqrt(2)
    t = 1 / (1 + 0.3275911 * z)
    y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-z * z)
    return 0.5 * (1 + np.sign(x) * y)


def bs(S, K, T, sig, call=True):
    S, K, T, sig = (np.asarray(a, float) for a in (S, K, T, sig))
    T = np.maximum(T, 0.0)
    intr = np.maximum(S - K, 0) if call else np.maximum(K - S, 0)
    vs = sig * np.sqrt(T)
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(S / K) + 0.5 * vs ** 2) / vs
        d2 = d1 - vs
        px = S * ncdf(d1) - K * ncdf(d2) if call else K * ncdf(-d2) - S * ncdf(-d1)
    return np.where(vs > 1e-9, px, intr)


def nw_t(y, x, L=1):
    """OLS slope t-stat of y on x with Newey-West(L) errors."""
    y = np.asarray(y, float); x = np.asarray(x, float)
    X = np.column_stack([np.ones_like(x), x])
    XtX = X.T @ X
    if np.linalg.matrix_rank(XtX) < 2: return 0.0, 0.0
    b = np.linalg.solve(XtX, X.T @ y)
    u = (X * (y - X @ b)[:, None])
    S = u.T @ u
    for l in range(1, L + 1):
        w = 1 - l / (L + 1)
        G = u[l:].T @ u[:-l]
        S += w * (G + G.T)
    Xi = np.linalg.inv(XtX)
    V = Xi @ S @ Xi
    return b[1], b[1] / math.sqrt(V[1, 1]) if V[1, 1] > 0 else 0.0


def pval(t):
    return math.erfc(abs(t) / math.sqrt(2))


def mean_t(r, L=1):
    r = np.asarray(r, float)
    if len(r) < 3: return float("nan")
    # NW(L) t-stat of the mean
    u = r - r.mean(); S = (u @ u)
    for l in range(1, L + 1):
        S += 2 * (1 - l / (L + 1)) * (u[l:] @ u[:-l])
    return r.mean() / math.sqrt(S / len(r) ** 2) if S > 0 else float("nan")


# ---- data ----------------------------------------------------------------------------------------------------------
def db():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)


def load_daily(c, sym):
    d = pd.read_sql("SELECT ts, open, high, low, close, adj_close FROM bars WHERE symbol=? AND interval='1d' ORDER BY ts",
                    c, params=(sym,), parse_dates=["ts"]).set_index("ts")
    d = d[~d.index.duplicated(keep="last")]
    d = d[d.index <= END]
    d["adj_close"] = d["adj_close"].fillna(d["close"])
    return d


def fetch():
    cache = pickle.load(open(CACHE, "rb")) if CACHE.exists() else {}
    fred = cache.get("fred", {})
    for s in FRED:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}"
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
            df = pd.read_csv(io.BytesIO(raw))
            df.columns = ["date", "v"]
            df["date"] = pd.to_datetime(df["date"]); df["v"] = pd.to_numeric(df["v"], errors="coerce")
            fred[s] = df.dropna().set_index("date")["v"]
            print(f"FRED {s:14s} {len(fred[s]):6d} obs {fred[s].index[0].date()}..{fred[s].index[-1].date()}")
        except Exception as e:
            print(f"FRED {s} failed: {e}")
    cache["fred"] = fred
    earn = cache.get("earn", {})
    try:
        import yfinance as yf
        for s in MEGA:
            try:
                idx = yf.Ticker(s).get_earnings_dates(limit=60).index
                earn[s] = sorted({(t.strftime("%Y-%m-%d"), t.hour) for t in idx if t.tz_localize(None) <= pd.Timestamp.now()})
                print(f"earnings {s}: {len(earn[s])} dates {earn[s][0][0]}..{earn[s][-1][0]}")
            except Exception as e:
                print(f"earnings {s} failed: {e}")
    except ImportError:
        pass
    old = ROOT / "data" / "research_news_cache.pkl"
    if old.exists():          # fall back / merge with the news-research cache (2020-10..2026)
        oe = pickle.load(open(old, "rb")).get("earn", {})
        for s in MEGA:
            if oe.get(s):
                earn[s] = sorted(set(map(tuple, earn.get(s) or [])) | set(map(tuple, oe[s])))
    cache["earn"] = earn
    pickle.dump(cache, open(CACHE, "wb"))
    print(f"-> {CACHE}")


def fred_aligned(fred, s, idx):
    """FRED series value known as of each trading date (observation date + publication lag)."""
    if s not in fred: return pd.Series(np.nan, index=idx)
    x = fred[s].copy()
    x.index = x.index + pd.Timedelta(days=FRED_LAG[s])
    x = x[~x.index.duplicated(keep="last")].sort_index()
    return x.reindex(idx.union(x.index)).ffill().reindex(idx)


def fred_transform_then_align(fred, s, fn, idx):
    if s not in fred: return pd.Series(np.nan, index=idx)
    x = fn(fred[s].copy())
    x.index = x.index + pd.Timedelta(days=FRED_LAG[s])
    x = x.dropna(); x = x[~x.index.duplicated(keep="last")].sort_index()
    return x.reindex(idx.union(x.index)).ffill().reindex(idx)


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def streak(r):
    s = np.sign(r.fillna(0).values); out = np.zeros(len(s))
    for i in range(1, len(s)):
        out[i] = out[i - 1] + s[i] if s[i] == np.sign(out[i - 1]) or out[i - 1] == 0 else s[i]
    return pd.Series(out, index=r.index)


_PANEL = None


def panel():
    """Returns (P, feats) where P has per-symbol prices/targets and feats is {name: (Series, kind, late, group, cal)}."""
    global _PANEL
    if _PANEL is not None: return _PANEL
    c = db()
    syms = [r[0] for r in c.execute("SELECT DISTINCT symbol FROM bars WHERE interval='1d'")]
    D = {s: load_daily(c, s) for s in syms}
    idx = D["SPY"].index[D["SPY"].index >= "1993-02-01"]
    cache = pickle.load(open(CACHE, "rb")) if CACHE.exists() else {"fred": {}, "earn": {}}
    fred = cache["fred"]

    def cl(s, col="close"):
        d = D[s][col]
        return d.reindex(idx.union(d.index)).ffill(limit=5).reindex(idx) if s in ("BTC-USD",) else d.reindex(idx)

    P = {"idx": idx, "D": D, "fred": fred, "earn": cache.get("earn", {})}
    for s in ("SPY", "QQQ"):
        o, cc, a = D[s]["open"].reindex(idx), D[s]["close"].reindex(idx), D[s]["adj_close"].reindex(idx)
        P[s] = dict(open=o, close=cc, adj=a,
                    oc1=(cc.shift(-1) / o.shift(-1) - 1), cc1=a.shift(-1) / a - 1,
                    cc5=a.shift(-5) / a - 1, cc20=a.shift(-20) / a - 1,
                    gap1=o.shift(-1) / cc - 1)
    spy = P["SPY"]["adj"]; spyc = P["SPY"]["close"]
    vix, vix9, vix3m = cl("^VIX"), cl("^VIX9D"), cl("^VIX3M")
    vvix, skew = cl("^VVIX"), cl("^SKEW")
    tnx, irx = cl("^TNX"), cl("^IRX")
    oil, gold, dxy = cl("CL=F"), cl("GC=F"), cl("DX-Y.NYB")
    btc = cl("BTC-USD")
    r1 = spy.pct_change()
    F = {}

    def add(name, s, kind="c", late=False, group="", cal=False):
        F[name] = (s.astype(float).replace([np.inf, -np.inf], np.nan), kind, late, group, cal)

    # 1. trend / momentum
    for n in (20, 60, 120, 252): add(f"mom{n}", spy / spy.shift(n) - 1, group="trend")
    add("above200", (spyc > spyc.rolling(200).mean()).astype(float).where(spyc.rolling(200).count() == 200), "b", group="trend")
    add("ret1", r1, group="trend"); add("ret3", spy / spy.shift(3) - 1, group="trend"); add("ret5", spy / spy.shift(5) - 1, group="trend")
    R = rsi(spyc)
    add("rsi14_lt30", (R < 30).astype(float), "b", group="trend"); add("rsi14_gt70", (R > 70).astype(float), "b", group="trend")
    R2 = rsi(spyc, 2)
    add("rsi2_lt10", (R2 < 10).astype(float), "b", group="trend"); add("rsi2_gt90", (R2 > 90).astype(float), "b", group="trend")
    st = streak(r1)
    add("down3plus", (st <= -3).astype(float), "b", group="trend"); add("up3plus", (st >= 3).astype(float), "b", group="trend")
    add("dist_ma50", spyc / spyc.rolling(50).mean() - 1, group="trend")
    # 2. volatility state
    add("vix", vix, group="vol"); add("vix_chg1", np.log(vix / vix.shift(1)), group="vol")
    add("vix_spike3", (vix / vix.shift(3) > 1.2).astype(float).where(vix.notna()), "b", group="vol")
    add("vix_vs_ma20", vix / vix.rolling(20).mean() - 1, group="vol")
    add("vix9d_vix", vix9 / vix, group="vol"); add("vix_vix3m", vix / vix3m, group="vol")
    add("ts_inverted", (vix / vix3m > 1).astype(float).where(vix3m.notna()), "b", group="vol")
    add("vvix", vvix, group="vol"); add("skew", skew, group="vol")
    rv20 = r1.rolling(20).std() * math.sqrt(252) * 100
    add("vrp", vix - rv20, group="vol"); add("vix_lt15", (vix < 15).astype(float).where(vix.notna()), "b", group="vol")
    add("vix_gt25", (vix > 25).astype(float).where(vix.notna()), "b", group="vol")
    # 3. rates and credit
    add("tnx_chg5", tnx - tnx.shift(5), group="rates"); add("tnx_chg20", tnx - tnx.shift(20), group="rates")
    add("curve_tnx_irx", tnx - irx, group="rates"); add("curve_chg20", (tnx - irx) - (tnx - irx).shift(20), group="rates")
    add("t10y3m", fred_aligned(fred, "T10Y3M", idx), group="rates")
    add("t10y2y", fred_aligned(fred, "T10Y2Y", idx), group="rates")
    add("curve_inverted", (fred_aligned(fred, "T10Y3M", idx) < 0).astype(float).where(fred_aligned(fred, "T10Y3M", idx).notna()), "b", group="rates")
    baa = fred_aligned(fred, "BAA10Y", idx)
    add("baa10y", baa, group="credit"); add("baa10y_chg20", baa - baa.shift(20), group="credit")
    hy = fred_aligned(fred, "BAMLH0A0HYM2", idx)
    add("hy_chg20", hy - hy.shift(20), group="credit")
    nfci = fred_aligned(fred, "NFCI", idx)
    add("nfci", nfci, group="credit"); add("nfci_chg4w", nfci - nfci.shift(20), group="credit")
    dff = fred_aligned(fred, "DFF", idx)
    add("fed_chg6m", dff - dff.shift(126), group="rates")
    # 4. commodities and FX (late-stamped: lagged for close->close targets)
    for nm, s in (("oil", oil), ("gold", gold), ("dxy", dxy)):
        add(f"{nm}_ret1", s / s.shift(1) - 1, late=True, group="cmdty")
        add(f"{nm}_ret5", s / s.shift(5) - 1, late=True, group="cmdty")
        add(f"{nm}_ret20", s / s.shift(20) - 1, late=True, group="cmdty")
    add("btc_ret1", btc / btc.shift(1) - 1, late=True, group="cmdty")
    add("btc_ret5", btc / btc.shift(5) - 1, late=True, group="cmdty")
    # 5. macro (FRED, availability-lagged)
    un3 = lambda x: x.rolling(3).mean()
    add("sahm_custom", fred_transform_then_align(fred, "UNRATE", lambda x: un3(x) - un3(x).rolling(12).min(), idx), group="macro")
    add("sahm_rt", fred_aligned(fred, "SAHMREALTIME", idx), group="macro")
    add("sahm_trig", (fred_aligned(fred, "SAHMREALTIME", idx) >= 0.5).astype(float).where(fred_aligned(fred, "SAHMREALTIME", idx).notna()), "b", group="macro")
    add("unrate_chg6m", fred_transform_then_align(fred, "UNRATE", lambda x: x - x.shift(6), idx), group="macro")
    add("claims_yoy", fred_transform_then_align(fred, "ICSA", lambda x: x.rolling(4).mean() / x.rolling(4).mean().shift(52) - 1, idx), group="macro")
    add("claims_4v26", fred_transform_then_align(fred, "ICSA", lambda x: x.rolling(4).mean() / x.rolling(26).mean() - 1, idx), group="macro")
    add("payems_3m", fred_transform_then_align(fred, "PAYEMS", lambda x: x - x.shift(3), idx), group="macro")
    add("cpi_surprise", fred_transform_then_align(fred, "CPIAUCSL", lambda x: x.pct_change() - x.pct_change().shift(1).rolling(12).mean(), idx), group="macro")
    add("cpi_yoy", fred_transform_then_align(fred, "CPIAUCSL", lambda x: x / x.shift(12) - 1, idx), group="macro")
    add("usrec_lag12m", fred_aligned(fred, "USREC", idx), "b", group="macro")
    # 7. breadth / cross-section
    sect = [s for s in ("XLE", "XLF", "XLK", "XLI", "XLY", "XLV", "XLU", "XLRE", "XLC") if s in D]
    above = pd.DataFrame({s: (cl(s) > cl(s).rolling(50).mean()).astype(float).where(cl(s).rolling(50).count() == 50) for s in sect})
    add("breadth50", above.mean(axis=1).where(above.count(axis=1) >= 6), group="breadth")
    rel = lambda a, b, n: (cl(a, "adj_close") / cl(a, "adj_close").shift(n)) / (cl(b, "adj_close") / cl(b, "adj_close").shift(n)) - 1
    add("iwm_spy20", rel("IWM", "SPY", 20), group="breadth"); add("xly_xlu20", rel("XLY", "XLU", 20), group="breadth")
    add("smh_spy20", rel("SMH", "SPY", 20), group="breadth"); add("kre_spy20", rel("KRE", "SPY", 20), group="breadth")
    add("tlt_ret20", cl("TLT", "adj_close") / cl("TLT", "adj_close").shift(20) - 1, group="breadth")
    # 6. calendar / events -- flags describe the TARGET day (t+1); cal=True
    ev = _brainstorm_lists()
    fomc = set(pd.Timestamp(x) for x in FOMC_OLD.split()) | set(ev["FOMC"])
    cpi = set(ev["CPI"])
    nfp = set(ev["NFP"])
    for y in range(1994, 2015):     # NFP pre-2015 approximated as first Friday of the month (BLS rule exceptions ignored)
        for m in range(1, 13):
            d0 = pd.Timestamp(y, m, 1); nfp.add(d0 + pd.Timedelta(days=(4 - d0.weekday()) % 7))
    dates = pd.Series(idx, index=idx)
    nxt = dates.shift(-1)
    pos = pd.Series(np.arange(len(idx)), index=idx)
    mon = idx.to_period("M")
    first_k = pd.Series(pos.groupby(mon).rank(method="first").values, index=idx)
    last_k = pd.Series(pos.groupby(mon).rank(method="first", ascending=False).values, index=idx)
    tom = ((first_k <= 3) | (last_k == 1)).astype(float)
    fomc_f = pd.Series(idx.isin(list(fomc)).astype(float), index=idx)
    pre_fomc = fomc_f.shift(-1).fillna(0)
    cpi_f = pd.Series(idx.isin(list(cpi)).astype(float), index=idx).where(idx >= "2015-01-01")
    nfp_f = pd.Series(idx.isin(list(nfp)).astype(float), index=idx)
    third_fri = {}
    for p in mon.unique():
        d0 = p.to_timestamp(); f1 = d0 + pd.Timedelta(days=(4 - d0.weekday()) % 7); third_fri[p] = f1 + pd.Timedelta(days=14)
    tf = pd.Series([third_fri[p] for p in mon], index=idx)
    opex_wk = ((idx >= tf - pd.Timedelta(days=4)) & (idx <= tf)).astype(float)
    bd_to_next = pd.Series(np.r_[np.busday_count(idx.values[:-1].astype("datetime64[D]"), idx.values[1:].astype("datetime64[D]")), 1], index=idx)
    pre_hol = (bd_to_next > 1).astype(float)
    dow = pd.Series(idx.dayofweek, index=idx)
    for nm, s in (("cal_tom", tom), ("cal_fomc", fomc_f.where(idx >= "1994-02-01")), ("cal_pre_fomc", pre_fomc.where(idx >= "1994-02-01")),
                  ("cal_cpi", cpi_f), ("cal_nfp", nfp_f), ("cal_opex_week", pd.Series(opex_wk, index=idx)),
                  ("cal_pre_holiday", pre_hol), ("cal_monday", (dow == 0).astype(float)), ("cal_friday", (dow == 4).astype(float))):
        add(nm, s.shift(-1), "b", group="calendar", cal=True)       # row t describes day t+1
    # mega-cap earnings day for QQQ (reaction day = date if pre-market else next session)
    earn = P["earn"]; eday = set()
    for s in MEGA:
        for d, h in (earn.get(s) or []):
            d = pd.Timestamp(d)
            if d not in pos.index: continue
            eday.add(d if h < 9 else (nxt.get(d) if pd.notna(nxt.get(d)) else d))
    e = pd.Series(idx.isin(list(eday)).astype(float), index=idx).where(idx >= "2020-10-01")
    add("cal_mega_earn", e.shift(-1), "b", group="calendar", cal=True)
    P["fomc"], P["cpi"], P["nfp"] = sorted(fomc), sorted(cpi), sorted(nfp)
    P["vix"], P["vix3m"], P["vix9"], P["tom"], P["rv20"] = vix, vix3m, vix9, tom, rv20
    _PANEL = (P, F)
    return _PANEL


HORIZONS = {"oc1": 1, "cc1": 1, "cc5": 5, "cc20": 20}


def feature_for(F, name, h):
    s, kind, late, group, cal = F[name]
    return s.shift(1) if (late and h != "oc1") else s


def eval_signal(x, y, kind, idx, L, yall=None):
    """Learn direction on train, return OOS stats. x, y aligned Series."""
    ok = x.notna() & y.notna()
    x, y = x[ok], y[ok]
    if len(x) < 300: return None
    tr = x.index < SPLIT
    if tr.sum() < 750:              # short series: first ~3y = train
        cut = x.index[min(755, len(x) - 1)]
        tr = x.index < cut
    tr = np.asarray(tr)
    te = ~tr
    if te.sum() < 200 or tr.sum() < 200: return None
    xv, yv = x.values, y.values
    if kind == "c":
        q1, q2 = np.nanpercentile(xv[tr], [33.3, 66.7])
        raw = np.where(xv > q2, 1.0, np.where(xv < q1, -1.0, 0.0))
        if (raw[tr] == 1).sum() < 30 or (raw[tr] == -1).sum() < 30: return None
        d = np.sign(yv[tr][raw[tr] == 1].mean() - yv[tr][raw[tr] == -1].mean()) or 1.0
        sig = d * raw
    else:
        raw = xv
        if raw[tr].sum() < 15 or raw[te].sum() < 15: return None
        d = np.sign(yv[tr][raw[tr] == 1].mean() - yv[tr][raw[tr] == 0].mean()) or 1.0
        sig = d * raw
    dates = x.index

    def stats(m):
        s_, y_ = sig[m], yv[m]
        if kind == "c":
            b, t = nw_t(y_, s_, L)
        else:
            b, t = nw_t(y_, (s_ != 0).astype(float), L); b, t = b * d, t * d
        on = s_ != 0
        hit = float(np.mean(np.sign(y_[on]) == s_[on])) if on.any() else float("nan")
        return dict(n=int(m.sum()), n_on=int(on.sum()), b=float(b), t=float(t), hit=hit,
                    base_up=float(np.mean(y_ > 0)),
                    m_long=float(y_[s_ > 0].mean()) if (s_ > 0).any() else None,
                    m_short=float(y_[s_ < 0].mean()) if (s_ < 0).any() else None,
                    m_off=float(y_[s_ == 0].mean()) if (s_ == 0).any() else None)
    ins = stats(tr)
    oos = stats(te)
    ex20 = stats(te & np.asarray(dates.year != 2020))
    l3 = stats(np.asarray(dates >= LAST3))
    return dict(dir=float(d), train_end=str(dates[tr][-1].date()), ins=ins, oos=oos, ex2020=ex20, last3=l3,
                sig=pd.Series(sig, index=dates))


def signals(verbose=True):
    P, F = panel()
    rows = []
    for sym in ("SPY", "QQQ"):
        extra = {"gap_next": (P[sym]["gap1"], "c", False, "gap", False)}
        for h, L in HORIZONS.items():
            y = P[sym][h]
            names = list(F) + (["gap_next"] if h == "oc1" else [])
            for nm in names:
                if nm in F:
                    s, kind, late, group, cal = F[nm]
                    if cal and h in ("cc5", "cc20"): continue
                    if nm == "cal_mega_earn" and sym != "QQQ": continue
                    x = feature_for(F, nm, h)
                else:
                    s, kind, late, group, cal = extra[nm]; x = s
                r = eval_signal(x, y, kind, P["idx"], L)
                if r is None: continue
                r.pop("sig")
                rows.append(dict(sym=sym, h=h, feat=nm, group=group, kind=kind, **r))
    # multiple testing on OOS p-values
    m = len(rows)
    ps = np.array([pval(r["oos"]["t"]) for r in rows])
    order = np.argsort(ps)
    bh = np.zeros(m, bool)
    thr = 0.05 * np.arange(1, m + 1) / m
    passed = np.where(ps[order] <= thr)[0]
    if len(passed): bh[order[:passed.max() + 1]] = True
    bh10 = np.zeros(m, bool); p10 = np.where(ps[order] <= 2 * thr)[0]
    if len(p10): bh10[order[:p10.max() + 1]] = True
    for i, r in enumerate(rows):
        r["p"] = float(ps[i]); r["bh"] = bool(bh[i]); r["bh10"] = bool(bh10[i]); r["bonf"] = bool(ps[i] < 0.05 / m)
        r["replicated"] = bool(r["ins"]["t"] >= 2 and r["oos"]["t"] >= 2)   # learned dir => ins t>0 by construction
        r["robust"] = bool(r["bh"] and np.sign(r["ex2020"]["t"]) == np.sign(r["oos"]["t"]) and np.sign(r["last3"]["b"]) == np.sign(r["oos"]["b"]))
    if verbose:
        print(f"{m} OOS tests (train <2015 / first 3y; test 2015-01..2026-10).  Bonferroni p<{0.05/m:.1e} (|t|>{_tcrit(0.05/m):.2f});"
              f" BH q=0.05 passes {bh.sum()}, Bonferroni {sum(r['bonf'] for r in rows)}, nominal p<0.05 {int((ps<0.05).sum())}"
              f" (expected by chance {0.05*m:.0f}); BH q=0.10 passes {bh10.sum()}; in-sample t>=2 AND OOS t>=2: {sum(r['replicated'] for r in rows)}")
        print(f"{'sym':4s} {'h':4s} {'feature':16s} {'dir':>3s} {'n_on':>5s} {'hit':>5s} {'base':>5s} {'mL/on%':>7s} {'mShort/off%':>11s}"
              f" {'t_oos':>6s} {'t_ins':>6s} {'t_ex20':>6s} {'t_l3y':>6s} BH  Bonf")
        for r in sorted(rows, key=lambda r: r["p"])[:40]:
            o = r["oos"]; ms = o["m_short"] if r["kind"] == "c" else o["m_off"]
            ml = o["m_long"] if r["kind"] == "c" else (o["m_long"] if r["dir"] > 0 else o["m_short"])
            print(f"{r['sym']:4s} {r['h']:4s} {r['feat']:16s} {int(r['dir']):+3d} {o['n_on']:5d} {o['hit']*100:5.1f} {o['base_up']*100:5.1f}"
                  f" {(ml or 0)*100:7.3f} {(ms or 0)*100:11.3f} {o['t']:6.2f} {r['ins']['t']:6.2f} {r['ex2020']['t']:6.2f}"
                  f" {r['last3']['t']:6.2f} {'*' if r['bh'] else ' ':3s} {'*' if r['bonf'] else ''}")
    save("signals", rows)
    return rows


def _tcrit(p):
    lo, hi = 0.0, 10.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if pval(mid) > p: lo = mid
        else: hi = mid
    return hi


def save(key, val):
    cur = json.loads(OUT.read_text()) if OUT.exists() else {}
    cur[key] = val
    OUT.write_text(json.dumps(cur, indent=1, default=float))


# ---- combined model ------------------------------------------------------------------------------------------------
def ridge_logit(X, y, lam=5.0, it=25):
    w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (p - y) + lam * np.r_[0, w[1:]]
        Hm = (X * (p * (1 - p))[:, None]).T @ X + lam * np.diag(np.r_[0, np.ones(len(w) - 1)])
        w -= np.linalg.solve(Hm + 1e-9 * np.eye(len(w)), g)
    return w


def model(rows=None, verbose=True):
    P, F = panel()
    if rows is None:
        rows = json.loads(OUT.read_text())["signals"] if OUT.exists() else signals(False)
    out = {}
    for sym in ("SPY", "QQQ"):
        for h, L in HORIZONS.items():
            y = P[sym][h]
            names = [n for n in F if not (F[n][4] and h in ("cc5", "cc20")) and n != "cal_mega_earn"]
            X = pd.DataFrame({n: feature_for(F, n, h) for n in names})
            if h == "oc1": X["gap_next"] = P[sym]["gap1"]
            surv = [r["feat"] for r in rows if r["sym"] == sym and r["h"] == h and r["bh"]]
            ins_sel = [r["feat"] for r in rows if r["sym"] == sym and r["h"] == h and abs(r["ins"]["t"]) >= 2.5 and r["feat"] != "gap_next"]
            repl = [r["feat"] for r in rows if r["sym"] == sym and r["h"] == h and r["replicated"] and r["feat"] != "gap_next"]
            ok = y.notna() & (X.index >= "1999-06-01")
            X, yy = X[ok], y[ok]
            res = {}
            for variant, cols in (("all", list(X.columns)), ("bh_survivors", surv), ("ins_selected", ins_sel),
                                  ("replicated(biased)", repl)):
                if not cols: res[variant] = None; continue
                preds = pd.Series(np.nan, index=X.index); trp = {}
                for yr in range(2015, END.year + 1):
                    te = (X.index.year == yr)
                    tr_end = X.index[te][0] if te.any() else None
                    if tr_end is None: continue
                    tr = X.index < tr_end
                    tr[np.where(tr)[0][-HORIZONS[h]:]] = False        # purge overlap
                    Xa = X.loc[:, cols]
                    mu, sd = Xa[tr].mean(), Xa[tr].std().replace(0, 1)
                    Z = ((Xa - mu) / sd).clip(-5, 5).fillna(0.0)
                    A = np.column_stack([np.ones(len(Z)), Z.values])
                    w = ridge_logit(A[tr], (yy.values[tr] > 0).astype(float), lam=max(5.0, 0.002 * tr.sum()))
                    p = 1 / (1 + np.exp(-(A @ w)))
                    preds[te] = p[te]
                    trp[yr] = np.percentile(p[tr], [10, 90])
                pr = preds.dropna(); yt = yy.reindex(pr.index)
                up = (yt > 0).values
                call = pr.values > np.median(pr.values)        # rank-based: long top half, short bottom half
                hit_sign = float(np.mean((pr.values > 0.5) == up))
                hit_rank = float(np.mean(call == up))
                dec = pd.qcut(pr.rank(method="first"), 10, labels=False)
                dec_up = [float(up[dec.values == k].mean()) for k in range(10)]
                dec_ret = [float(yt.values[dec.values == k].mean()) for k in range(10)]
                l3 = pr.index >= LAST3
                res[variant] = dict(n=int(len(pr)), base_up=float(up.mean()), hit_p50=hit_sign, hit_rank=hit_rank,
                                    top_dec_up=dec_up[9], bot_dec_down=1 - dec_up[0], dec_up=dec_up, dec_ret=dec_ret,
                                    l3_hit_p50=float(np.mean((pr.values[l3] > 0.5) == up[l3])), l3_base=float(up[l3].mean()),
                                    l3_top_dec_up=float(up[l3 & (dec.values == 9)].mean()) if (l3 & (dec.values == 9)).any() else None,
                                    ls_t=float(nw_t(yt.values, np.where(call, 1.0, -1.0), L)[1]),
                                    corr=float(np.corrcoef(pr.values, yt.values)[0, 1]), cols=cols)
            out[f"{sym}_{h}"] = res
            if verbose:
                for v, r in res.items():
                    if r is None: print(f"{sym} {h:4s} {v:18s}: no survivors"); continue
                    print(f"{sym} {h:4s} {v:18s} n={r['n']:5d} base_up={r['base_up']*100:5.1f}% hit(p>.5)={r['hit_p50']*100:5.1f}%"
                          f" hit(rank)={r['hit_rank']*100:5.1f}% top-dec P(up)={r['top_dec_up']*100:5.1f}% bot-dec P(down)={r['bot_dec_down']*100:5.1f}%"
                          f" corr={r['corr']:+.3f} t_LS={r['ls_t']:+.2f} | last3y hit={r['l3_hit_p50']*100:5.1f}% (base {r['l3_base']*100:4.1f}%)"
                          f" top-dec {(r['l3_top_dec_up'] or 0)*100:4.1f}%")
                    if v == "all":
                        print("      decile mean ret %: " + " ".join(f"{x*100:+.3f}" for x in r["dec_ret"]))
    save("model", out)
    return out


# ---- option economics ----------------------------------------------------------------------------------------------
def opt_trade(S0, S1, v0, v1, T0, dt, call, width=None, cost=COST):
    """Long ATM option (or ATM/+width debit spread) bought at S0 with tenor T0 (yrs), sold after dt yrs at S1.
    v0/v1 = IV at entry/exit. Returns net return on premium incl. round-trip cost (applied to each leg)."""
    K = S0
    T1 = np.maximum(T0 - dt, 0)
    sk = lambda v, K_, S_: v * np.clip(1 - SKEW * np.log(K_ / S_), 0.5, 2.0)   # sticky-moneyness skew
    p0 = bs(S0, K, T0, sk(v0, K, S0), call); p1 = bs(S1, K, T1, sk(v1, K, S1), call)
    if width is None:
        return (p1 * (1 - cost / 2)) / (p0 * (1 + cost / 2)) - 1
    K2 = S0 * (1 + width) if call else S0 * (1 - width)
    q0 = bs(S0, K2, T0, sk(v0, K2, S0), call); q1 = bs(S1, K2, T1, sk(v1, K2, S1), call)
    debit = p0 - q0 + cost / 2 * (p0 + q0)
    credit = p1 - q1 - cost / 2 * (p1 + q1)
    return credit / debit - 1


STRUCT = {   # horizon -> list of (label, T0 days (calendar), hold days (calendar approx), width)
    "oc1": [("0DTE ATM", None, None, None), ("0DTE ATM/+0.5%", None, None, 0.005)],
    "cc1": [("7d ATM, hold 1d", 7, 1.4, None)],
    "cc5": [("14d ATM, hold 5d", 14, 7, None), ("30d ATM, hold 5d", 30, 7, None), ("14d ATM/+2%", 14, 7, 0.02)],
    "cc20": [("30d ATM to expiry", 28, 28, None), ("45d ATM, hold 20d", 45, 28, None), ("30d ATM/+3% to exp", 28, 28, 0.03)],
}


def option_returns(P, sym, h, sig, label, T0, hold, width, ivr=IVR):
    """sig: Series of +1/-1 at entry rows. Returns Series of net returns on premium."""
    s = sig[sig != 0].dropna()
    vix = P["vix"]; mult = QQQ_VOL if sym == "QQQ" else 1.0
    if h == "oc1":
        # entry next-day open, exit next-day close. 0DTE: sd over the session = VIX/sqrt(252) * 0.8 * ivr0
        o = P[sym]["open"].shift(-1).reindex(s.index); c = P[sym]["close"].shift(-1).reindex(s.index)
        v = vix.reindex(s.index) / 100 * mult
        T0y = 1 / 252; sig0 = v * 0.80 * 1.0
        out = []
        for side in (1, -1):
            m = (s == side).values
            if not m.any(): continue
            r = opt_trade(o.values[m], c.values[m], sig0.values[m], sig0.values[m], T0y, T0y, side > 0, width)
            out.append(pd.Series(r, index=s.index[m]))
        return pd.concat(out).sort_index() if out else pd.Series(dtype=float)
    hd = HORIZONS[h]
    a = P[sym]["close"]
    S0 = a.reindex(s.index); S1 = a.shift(-hd).reindex(s.index)
    v0 = vix.reindex(s.index) / 100 * ivr * mult; v1 = vix.shift(-hd).reindex(s.index) / 100 * ivr * mult
    out = []
    for side in (1, -1):
        m = (s == side).values
        if not m.any(): continue
        r = opt_trade(S0.values[m], S1.values[m], v0.values[m], v1.values[m], T0 / 365, hold / 365, side > 0, width)
        out.append(pd.Series(r, index=s.index[m]))
    return pd.concat(out).sort_index().dropna() if out else pd.Series(dtype=float)


def summarize(r, L=1):
    r = r.dropna()
    if len(r) == 0: return None
    te = r[r.index >= SPLIT]; l3 = r[r.index >= LAST3]; ex = te[te.index.year != 2020]
    f = lambda x: dict(n=int(len(x)), ev=float(x.mean()) if len(x) else None, pop=float((x > 0).mean()) if len(x) else None,
                       med=float(x.median()) if len(x) else None, t=float(mean_t(x.values, L)) if len(x) > 5 else None)
    return dict(full=f(r), oos=f(te), ex2020=f(ex), last3=f(l3))


def options(rows=None, verbose=True):
    P, F = panel()
    if rows is None:
        rows = json.loads(OUT.read_text())["signals"]
    res = []
    for sym in ("SPY", "QQQ"):
        for h, L in HORIZONS.items():
            y = P[sym][h]
            base_long = pd.Series(1.0, index=y.dropna().index)
            cands = [("ALWAYS CALL", base_long), ("ALWAYS PUT", -base_long)]
            for r in rows:
                if r["sym"] == sym and r["h"] == h and (r["bh"] or r["replicated"]):
                    x = feature_for(F, r["feat"], h) if r["feat"] in F else P[sym]["gap1"]
                    ev = eval_signal(x, y, r["kind"], P["idx"], L)
                    cands.append((r["feat"] + (" [BH]" if r["bh"] else " [repl]"), ev["sig"]))
            for name, sig in cands:
                for label, T0, hold, width in STRUCT[h]:
                    rr = option_returns(P, sym, h, sig, label, T0, hold, width)
                    sm = summarize(rr, L)
                    if sm is None: continue
                    # side split
                    res.append(dict(sym=sym, h=h, signal=name, struct=label, **sm))
                    if verbose:
                        o, l3, ex = sm["oos"], sm["last3"], sm["ex2020"]
                        print(f"{sym} {h:4s} {name:28s} {label:20s} OOS n={o['n']:5d} EV={o['ev']*100:+6.1f}% PoP={o['pop']*100:4.1f}%"
                              f" t={o['t'] or 0:+5.2f} | ex2020 EV={ex['ev']*100:+6.1f}% | last3y n={l3['n']:4d} EV={(l3['ev'] or 0)*100:+6.1f}%")
    save("options", res)
    # sensitivity of baselines to the IV ratio
    sens = []
    for ivr in (0.8, 0.9, 1.0):
        y = P["SPY"]["cc20"]; sig = pd.Series(1.0, index=y.dropna().index)
        rr = option_returns(P, "SPY", "cc20", sig, "", 45, 28, None, ivr=ivr)
        sens.append((ivr, float(rr[rr.index >= SPLIT].mean())))
    if verbose: print("SPY always-call 45d hold 20d OOS EV vs IV/VIX ratio: " + ", ".join(f"{a}:{b*100:+.1f}%" for a, b in sens))
    save("iv_sensitivity", sens)
    return res


# ---- strategies ----------------------------------------------------------------------------------------------------
def nonoverlap(entries, hold):
    """Keep entries so that positions don't overlap (hold in trading days)."""
    keep, last = [], -10 ** 9
    pos = {d: i for i, d in enumerate(_PANEL[0]["idx"])}
    for d in entries:
        i = pos[d]
        if i >= last + hold: keep.append(d); last = i
    return keep


def swing(P, sym, entries, side, T0, hold_td, width=None, ivr=IVR):
    idx = P["idx"]; pos = pd.Series(np.arange(len(idx)), index=idx)
    a = P[sym]["close"]; vix = P["vix"]; mult = QQQ_VOL if sym == "QQQ" else 1.0
    e = [d for d in entries if pos[d] + hold_td < len(idx)]
    if not e: return pd.Series(dtype=float)
    ix = pos[e].values
    S0, S1 = a.values[ix], a.values[ix + hold_td]
    v0, v1 = vix.values[ix] / 100 * ivr * mult, vix.values[ix + hold_td] / 100 * ivr * mult
    dt = (idx[ix + hold_td] - idx[ix]).days.values / 365
    r = opt_trade(S0, S1, v0, v1, T0 / 365, dt, side > 0, width)
    return pd.Series(r, index=pd.DatetimeIndex(e)).dropna()


def bootstrap(r, per_year, fracs=(0.15, 0.25, 0.35, 0.6), start=170.0, ruin=20.0, n=20000, seed=7):
    rng = np.random.default_rng(seed)
    r = np.asarray(r, float)
    k = max(1, int(round(per_year)))
    out = {}
    for f in fracs:
        eq = np.full(n, start)
        draws = r[rng.integers(0, len(r), size=(n, k))]
        dead = np.zeros(n, bool)
        for j in range(k):
            eq = np.where(dead, eq, eq * (1 + f * draws[:, j]))
            dead |= eq < ruin
        out[f] = dict(p_grow=float((eq > start).mean()), p_double=float((eq > 2 * start).mean()),
                      p_ruin=float(dead.mean()), median=float(np.median(eq)), p_half=float((eq < start / 2).mean()))
    return out


def strategies(verbose=True):
    P, F = panel()
    idx = P["idx"]; pos = pd.Series(np.arange(len(idx)), index=idx)
    spy = P["SPY"]["close"]; vix = P["vix"]; vix3m = P["vix3m"]
    ma200 = spy.rolling(200).mean(); mom252 = spy / spy.shift(252) - 1
    S = {}
    valid = idx[(idx >= "1994-01-01") & (pos < len(idx) - 25)]
    # (a) swing trend: monthly (every 20 sessions) entries
    monthly = [d for i, d in enumerate(valid) if i % 20 == 0]
    trend_on = [d for d in monthly if spy[d] > ma200[d] and mom252[d] > 0]
    trend_off = [d for d in monthly if spy[d] < ma200[d] and mom252[d] < 0]
    S["a1 trend-on: 45d ATM call, hold 20d (monthly)"] = swing(P, "SPY", trend_on, 1, 45, 20)
    S["a2 trend-on: 30d ATM/+3% call spread to exp"] = swing(P, "SPY", trend_on, 1, 28, 20, 0.03)
    S["a3 trend-off: 45d ATM put, hold 20d"] = swing(P, "SPY", trend_off, -1, 45, 20)
    S["a0 baseline: 45d ATM call every month"] = swing(P, "SPY", monthly, 1, 45, 20)
    # (b) VIX spike mean reversion / term-structure inversion
    spike = [d for d in valid if vix[d] / vix.shift(3)[d] > 1.2 and vix[d] >= 18]
    spike = nonoverlap(spike, 10)
    S["b1 VIX +20%/3d (>=18): 30d ATM call, hold 10d"] = swing(P, "SPY", spike, 1, 30, 10)
    S["b2 VIX +20%/3d: 30d ATM/+3% call spread, hold 10d"] = swing(P, "SPY", spike, 1, 30, 10, 0.03)
    inv = [d for d in valid if pd.notna(vix3m[d]) and vix[d] / vix3m[d] > 1.0]
    inv = nonoverlap(inv, 10)
    S["b3 VIX/VIX3M>1: 30d ATM put, hold 10d"] = swing(P, "SPY", inv, -1, 30, 10)
    S["b4 VIX/VIX3M>1: 30d ATM call, hold 10d (contrarian)"] = swing(P, "SPY", inv, 1, 30, 10)
    # (c) pre-FOMC: buy at close t-1, sell at close t (daily) ; hourly version below
    fomc = [d for d in P["fomc"] if d in pos.index and pos[d] > 0]
    pre = [idx[pos[d] - 1] for d in fomc]
    S["c1 pre-FOMC: 14d ATM call, close t-1 -> close t"] = swing(P, "SPY", pre, 1, 14, 1)
    pre2 = [idx[pos[d] - 2] for d in fomc if pos[d] > 1]
    S["c2 pre-FOMC: 14d ATM call, close t-2 -> close t-1"] = swing(P, "SPY", pre2, 1, 14, 1)
    # (d) turn of month: enter close of 2nd-to-last session, exit close of 3rd session of new month (4 sessions)
    mon = idx.to_period("M")
    lastk = pd.Series(pos.groupby(mon).rank(method="first", ascending=False).values, index=idx)
    tom_e = [d for d in idx[(lastk == 2).values] if d >= pd.Timestamp("1994-01-01") and pos[d] + 4 < len(idx)]
    S["d1 TOM: 14d ATM call, hold 4 sessions"] = swing(P, "SPY", tom_e, 1, 14, 4)
    S["d2 TOM: 30d ATM call, hold 4 sessions"] = swing(P, "SPY", tom_e, 1, 30, 4)
    # (f) existing engine proxies: 0DTE ATM straddle open->close when prior VIX>=20 / >=16, and coin-flip 0DTE call
    o1, c1 = P["SPY"]["open"].shift(-1), P["SPY"]["close"].shift(-1)
    def zdte(mask, kind):
        d = idx[mask.reindex(idx).fillna(False).values & o1.notna().values & (idx >= "1994-01-01")]
        sd = (vix[d] / 100 * 0.80).values; T = 1 / 252
        if kind == "straddle":
            p0 = bs(o1[d].values, o1[d].values, T, sd, True) + bs(o1[d].values, o1[d].values, T, sd, False)
            pay = np.abs(c1[d].values - o1[d].values)
            r = pay * (1 - COST / 2) / (p0 * (1 + COST / 2)) - 1
        else:
            rng = np.random.default_rng(1); side = rng.choice([1, -1], len(d))
            r = np.array([opt_trade(o1[x], c1[x], s_, s_, T, T, sd_ > 0) for x, s_, sd_ in zip(d, sd, side)], float)
        return pd.Series(r, index=d)
    S["f1 0DTE ATM straddle when prior VIX>=20"] = zdte(vix >= 20, "straddle")
    S["f2 0DTE ATM straddle when prior VIX>=16 (current gate)"] = zdte(vix >= 16, "straddle")
    S["f3 0DTE ATM call/put coin-flip when VIX>=16"] = zdte(vix >= 16, "flip")
    # (g) the one replicated family: buy short-term oversold (RSI2<10) -- note: picked after seeing OOS, but pre-published (Connors 2008)
    R2 = rsi(spy, 2)
    for sym in ("SPY", "QQQ"):
        R2s = rsi(P[sym]["close"], 2)
        os_ = nonoverlap([d for d in valid if R2s[d] < 10], 5)
        S[f"g1 {sym} RSI2<10: 14d ATM call, hold 5d"] = swing(P, sym, os_, 1, 14, 5)
        S[f"g2 {sym} RSI2<10: 30d ATM call, hold 5d"] = swing(P, sym, os_, 1, 30, 5)
        S[f"g3 {sym} RSI2<10: 14d ATM/+2% call spread, hold 5d"] = swing(P, sym, os_, 1, 14, 5, 0.02)
    # (e) PEAD on mega-caps
    pe, pe_raw = pead(P)
    S["e1 PEAD mega-caps: 7d ATM option in reaction direction, hold 5d (IV=1.2xRV20)"] = pe
    for k_ in (1.0, 1.5):
        S[f"e1 PEAD sensitivity IV={k_}xRV20"] = pead(P, k_)[0]
    meta = {}
    for k, r in S.items():
        r = r.dropna()
        te = r[r.index >= SPLIT]
        yrs = max(1.0, (te.index[-1] - te.index[0]).days / 365.25) if len(te) else 1
        per_year = len(te) / yrs
        sm = summarize(r)
        bt = bootstrap(te.values, per_year) if len(te) >= 10 else None
        meta[k] = dict(per_year=per_year, **sm, boot=bt)
    meta["e1_underlying"] = pe_raw
    hr = prefomc_hourly(P)
    meta["c3 pre-FOMC hourly (2023-11+): 14d call, close t-1 -> 13:30 t"] = hr
    if verbose:
        print(f"{'strategy':62s} {'trd/yr':>6s} {'OOS n':>5s} {'OOS EV':>7s} {'PoP':>5s} {'t':>5s} {'exCovid':>7s} {'last3y':>7s} {'full EV':>7s} |"
              f" P(grow) @15/25/35/60%   P(ruin<$20) @15/25/35/60%   median$ @25%")
        for k, m in meta.items():
            if k.startswith("e1_") or k.startswith("c3"): continue
            o, l3, ex, fu = m["oos"], m["last3"], m["ex2020"], m["full"]
            b = m["boot"]
            bs_ = " ".join(f"{b[f]['p_grow']*100:4.0f}" for f in (0.15, 0.25, 0.35, 0.6)) if b else "  -"
            br_ = " ".join(f"{b[f]['p_ruin']*100:4.0f}" for f in (0.15, 0.25, 0.35, 0.6)) if b else "  -"
            br_ += f"   {b[0.25]['median']:6.0f}" if b else ""
            print(f"{k[:62]:62s} {m['per_year']:6.1f} {o['n']:5d} {(o['ev'] or 0)*100:+6.1f}% {(o['pop'] or 0)*100:4.0f}% {o['t'] or 0:+5.2f}"
                  f" {(ex['ev'] or 0)*100:+6.1f}% {(l3['ev'] or 0)*100:+6.1f}% {(fu['ev'] or 0)*100:+6.1f}% |   {bs_}     {br_}")
        print("PEAD underlying (signed 5d excess return after reaction day):", pe_raw)
        print("pre-FOMC hourly:", hr)
    save("strategies", meta)
    afford(P)
    return meta


def pead(P, ivk=1.2):
    D, earn = P["D"], P["earn"]
    spy = P["SPY"]["adj"]
    rets, raw = [], []
    for s in MEGA:
        if not earn.get(s) or s not in D: continue
        a = D[s]["adj_close"]; idx = a.index; pos = pd.Series(np.arange(len(idx)), index=idx)
        lr = np.log(a).diff(); rv = lr.rolling(20).std() * math.sqrt(252)
        for d, h in earn[s]:
            d = pd.Timestamp(d)
            if d not in pos.index: continue
            i = pos[d] if h < 9 else pos[d] + 1          # reaction day
            if i + 5 >= len(idx) or i < 25: continue
            R = idx[i]
            react = a.iloc[i] / a.iloc[i - 1] - 1 - (spy.get(R, np.nan) / spy.get(idx[i - 1], np.nan) - 1)
            if not np.isfinite(react) or abs(react) < 0.02: continue
            side = 1 if react > 0 else -1
            fwd = a.iloc[i + 5] / a.iloc[i] - 1 - (spy.get(idx[i + 5], np.nan) / spy.get(R, np.nan) - 1)
            raw.append((R, side * fwd))
            iv = float(rv.iloc[i - 1]) * ivk               # post-event IV proxy: ivk x pre-event 20d realized
            r = opt_trade(a.iloc[i], a.iloc[i + 5], iv, iv, 7 / 365, (idx[i + 5] - R).days / 365, side > 0)
            rets.append((R, float(r)))
    sr = pd.Series([x[1] for x in rets], index=pd.DatetimeIndex([x[0] for x in rets])).sort_index()
    rs = pd.Series([x[1] for x in raw], index=pd.DatetimeIndex([x[0] for x in raw])).sort_index()
    f = lambda x: dict(n=int(len(x)), mean=float(x.mean()), t=float(mean_t(x.values)), hit=float((x > 0).mean()))
    return sr, {"all": f(rs), "pre2015": f(rs[rs.index < SPLIT]), "2015+": f(rs[rs.index >= SPLIT]),
                "last3y": f(rs[rs.index >= LAST3])}


def prefomc_hourly(P):
    c = db()
    h = pd.read_sql("SELECT ts, open, close FROM bars WHERE symbol='SPY' AND interval='1h' ORDER BY ts", c)
    v = pd.read_sql("SELECT ts, close FROM bars WHERE symbol='^VIX' AND interval='1h' ORDER BY ts", c)
    h["d"] = h.ts.str[:10]; v["d"] = v.ts.str[:10]
    out = []
    idx = P["idx"]; pos = pd.Series(np.arange(len(idx)), index=idx)
    for d in P["fomc"]:
        ds = d.strftime("%Y-%m-%d")
        x = h[(h.d == ds) & (h.ts.str[11:] == "13:30")]
        vv = v[(v.d == ds) & (v.ts.str[11:] == "12:00")]
        if x.empty or d not in pos.index: continue
        p = idx[pos[d] - 1]
        S0 = P["SPY"]["close"][p]; S1 = float(x.open.iloc[0]); v0 = P["vix"][p] / 100 * IVR
        v1 = float(vv.close.iloc[0]) / 100 * IVR if not vv.empty else v0
        r = opt_trade(S0, S1, v0, v1, 14 / 365, (d - p).days / 365, True)
        out.append((ds, S1 / S0 - 1, float(r)))
    if not out: return None
    u = np.array([o[1] for o in out]); r = np.array([o[2] for o in out])
    return dict(n=len(out), mean_underlying=float(u.mean()), hit=float((u > 0).mean()), t_underlying=float(mean_t(u)),
                ev_option=float(r.mean()), pop=float((r > 0).mean()))


def afford(P):
    """Cost of ONE contract today for each structure (for the $170 account)."""
    S, v = float(P["SPY"]["close"].iloc[-1]), float(P["vix"].iloc[-1]) / 100
    q = float(P["QQQ"]["close"].iloc[-1])
    rows = []
    for und, px, mult in (("SPY", S, 1.0), ("QQQ", q, QQQ_VOL), ("XSP (=SPX/10)", S * 0.1006, 1.0)):   # SPX ~ 10.06 x SPY
        for label, T, w in (("0DTE ATM", 1 / 252, None), ("14d ATM", 14 / 365, None), ("30d ATM", 30 / 365, None), ("45d ATM", 45 / 365, None),
                            ("30d ATM/+3% spread", 30 / 365, 0.03)):
            sig = v * mult * (0.8 if T < 0.01 else IVR)
            p = bs(px, px, T, sig, True)
            if w: p = p - bs(px, px * (1 + w), T, sig * (1 - SKEW * math.log(1 + w)), True)
            rows.append((und, label, float(p) * 100))
    print(f"\nCost of ONE contract today (SPY {S:.0f}, QQQ {q:.0f}, VIX {v*100:.1f}); 15-35% of $170 = $25-60:")
    for u, l, c_ in rows: print(f"  {u:16s} {l:20s} ${c_:8.0f}")
    save("afford", rows)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "fetch": fetch()
    elif cmd == "signals": signals()
    elif cmd == "model": model()
    elif cmd == "options": options()
    elif cmd == "strategies": strategies()
    elif cmd == "all":
        if not CACHE.exists(): fetch()
        rows = signals(); model(rows); options(rows); strategies()
    else: print(__doc__)
