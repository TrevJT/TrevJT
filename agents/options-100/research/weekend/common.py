#!/usr/bin/env python3
"""Shared loaders and option-pricing helpers for the 2026-10-17 weekend edge hunt.

Data (all local; see fetch_yf.py / fetch_crypto.py for how the raw files were pulled):
  data/market.db                     daily bars 1993+, SPY/QQQ 1m (Sep 29 2026+), 5m (Jul 15 2026+), 1h (Nov 2023+), real 0DTE option snapshots (8 days)
  data/research_intraday_sessions.pkl 1-minute session matrices 2007-01 .. 2026-03 (SPY, QQQ, IWM, DIA, SMH, NVDA, TLT, UUP, USO, HYG, GLD, crypto names)
  data/weekend_raw/yf_*.csv          yfinance daily (and 1h, 730d) for foreign indices, FX, futures, proxy ETFs, vol indices
  data/weekend_raw/deribit_btc_funding.csv  BTC-PERPETUAL funding (hourly interest) 2019-04 .. now
  data/weekend_raw/coinbase_btc_1h.csv      BTC-USD hourly candles 2022-09 .. now

0DTE pricing convention (calibrated 2026-10-17 on 8 days / 400 real SPY+QQQ ATM straddle quotes, see zdte_calibration.py):
  implied sd of the move from now to the close  =  K(mins_left) * VIX/100 * sqrt(mins_left / 525600)
  K_SPY(mins_left) = interpolation of hourly medians: 1.00 at the open, 0.92 at 10:00, 0.88 at 11:00, 1.14 at 13:00, 1.37 at 14:00, 1.52 at 15:00
  QQQ: same shape times VXN/VIX (measured QQQ/SPY ratio 1.5 in Oct 2026, VXN/VIX 1.4-1.5).
  Realized/implied E|move| over the 8 calibration days: SPY 0.82, QQQ 1.01 (Oct 16 was a 2.5% QQQ day).
  33-year daily VRP (research_vol.py): realized close->close |move| = 0.80 x VIX-implied.
"""
import os, sqlite3, math
import numpy as np, pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.abspath(os.path.join(HERE, "..", ".."))
DATA = os.path.join(AGENT, "data")
RAW = os.path.join(DATA, "weekend_raw")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
DB = os.path.join(DATA, "market.db")
N = 390
MINYR = 365 * 24 * 60


def T(h, m):
    """minute index into the (n, 391) price matrix: P[:, T(10, 0)] = price at 10:00."""
    return (h - 9) * 60 + m - 30


def db():
    return sqlite3.connect(DB)


def daily(sym):
    """daily OHLC from market.db, else from the yfinance raw cache. Index = date (naive)."""
    with db() as c:
        d = pd.read_sql("SELECT ts, open, high, low, close, adj_close, volume FROM bars WHERE symbol=? AND interval='1d' ORDER BY ts", c, params=(sym,))
    if len(d):
        d["ts"] = pd.to_datetime(d.ts, format="mixed")
        return d.set_index("ts")
    f = os.path.join(RAW, f"yf_{sym.replace('^', '_').replace('=', '_')}_1d.csv")
    if not os.path.exists(f):
        raise FileNotFoundError(sym)
    y = pd.read_csv(f, index_col=0, parse_dates=True)
    y = y.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Adj Close": "adj_close", "Volume": "volume"})
    y.index = pd.to_datetime(y.index, utc=True).tz_convert(None).normalize() if getattr(y.index, "tz", None) is not None else pd.to_datetime(y.index).normalize()
    return y[["open", "high", "low", "close", "adj_close", "volume"]].astype(float)


def yf_raw(sym, interval="1d"):
    f = os.path.join(RAW, f"yf_{sym.replace('^', '_').replace('=', '_')}_{interval}.csv")
    y = pd.read_csv(f, index_col=0)
    y.index = pd.to_datetime(y.index, utc=True)
    return y.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Adj Close": "adj_close", "Volume": "volume"}).astype(float)


def sessions(sym):
    """1-minute session matrices from research_intraday_sessions.pkl (P: open + 390 closes; H/L/V 390)."""
    s = pd.read_pickle(os.path.join(DATA, "research_intraday_sessions.pkl"))
    return s[sym]


def vix_daily():
    v = daily("^VIX")
    return v


_K_MINS = np.array([5, 15, 45, 105, 165, 225, 285, 345, 390], float)
_K_VAL = np.array([1.65, 1.60, 1.52, 1.37, 1.14, 0.94, 0.88, 0.92, 1.00], float)   # hourly medians of real-quote k (SPY, 8 days, Oct 2026)


def k_spy(mins_left):
    """0DTE implied-sd multiplier on VIX (calendar-minute convention), interpolated from hourly medians of real quotes."""
    m = np.asarray(mins_left, dtype=float)
    return np.interp(m, _K_MINS, _K_VAL)


def bs(S, K, Tm, sig, call):
    """Black-Scholes, zero rates. Tm in years (calendar-minute convention for 0DTE). Vectorized."""
    S = np.asarray(S, float); K = np.asarray(K, float); Tm = np.maximum(np.asarray(Tm, float), 1e-9); sig = np.maximum(np.asarray(sig, float), 1e-6)
    sT = sig * np.sqrt(Tm)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * Tm) / sT
    d2 = d1 - sT
    c = S * norm.cdf(d1) - K * norm.cdf(d2)
    p = K * norm.cdf(-d2) - S * norm.cdf(-d1)
    return np.where(call, c, p)


def bs_delta(S, K, Tm, sig, call):
    S = np.asarray(S, float); K = np.asarray(K, float); Tm = np.maximum(np.asarray(Tm, float), 1e-9); sig = np.maximum(np.asarray(sig, float), 1e-6)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * Tm) / (sig * np.sqrt(Tm))
    return np.where(call, norm.cdf(d1), norm.cdf(d1) - 1)


def tstat(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) < 3:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def tstat_cluster(x, groups):
    """t-stat with clustering by group (e.g. week) for overlapping/ correlated observations."""
    x = np.asarray(x, float); g = np.asarray(groups)
    ok = np.isfinite(x); x, g = x[ok], g[ok]
    if len(x) < 3:
        return float("nan")
    m = x.mean()
    s = pd.Series(x - m).groupby(g).sum()
    var = (s ** 2).sum() / len(x) ** 2
    return float(m / math.sqrt(var)) if var > 0 else float("nan")


def bh(pvals, q=0.10):
    """Benjamini-Hochberg: returns boolean array of discoveries."""
    p = np.asarray(pvals, float); n = len(p); o = np.argsort(p); r = np.empty(n, int); r[o] = np.arange(1, n + 1)
    thr = q * r / n
    ok = p <= thr
    if not ok.any():
        return np.zeros(n, bool)
    kmax = r[ok].max()
    return r <= kmax


def pval(t, n):
    from scipy.stats import t as tdist
    if not np.isfinite(t):
        return 1.0
    return float(2 * tdist.sf(abs(t), max(n - 1, 1)))


def summarize(r, name=""):
    r = np.asarray(r, float); r = r[np.isfinite(r)]
    if len(r) == 0:
        return dict(name=name, n=0)
    return dict(name=name, n=int(len(r)), mean=round(float(r.mean()), 4), median=round(float(np.median(r)), 4), win=round(float((r > 0).mean()), 3),
                t=round(tstat(r), 2), p_double=round(float((r >= 1.0).mean()), 3), p_lose_half=round(float((r <= -0.5).mean()), 3))
