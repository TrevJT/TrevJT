#!/usr/bin/env python3
"""Research: does the first part of the session predict the direction of the rest of the day / last hour / last 30 min?

  python3 bot/research_intraday.py fetch_hf      # 1-min bars 2007-01..2026-03 from HuggingFace Rrishab/OHLCV-1m (Finnhub-sourced), RTH only
  python3 bot/research_intraday.py fetch_yf      # yfinance 5m (60d) + 1h (730d) for the same tickers (validation + recent tail)
  python3 bot/research_intraday.py check         # integrity: session alignment, splits, gaps, vs market.db daily/hourly bars
  python3 bot/research_intraday.py build         # per-session feature table -> data/research_intraday_sessions.pkl
  python3 bot/research_intraday.py tests         # H1..H8 out-of-sample + BH correction -> data/research_intraday_results.json
  python3 bot/research_intraday.py options       # 0DTE Black-Scholes economics (brief / FAIR / rich IV) + bankroll $170/$1k/$5k
  python3 bot/research_intraday.py all           # build + tests + options

Downloaded data is untrusted: it is only parsed as parquet/CSV numbers, never executed.
Train = sessions before 2019-01-01; test (OOS) = 2019-01-01 onward. Directions are learned on train and frozen.
Write-up: research/intraday.md. Note: IV = VIX on calendar minutes ("brief") makes every 0DTE buy look +27%, so signals
are ranked under FAIR IV (implied E|move| = realized on the same days) -- the value of the direction call alone.
"""
import socket as _sk
_gai = _sk.getaddrinfo
_sk.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, _sk.AF_INET, *a, **k)   # IPv6 times out here

import os, sys, json, math, sqlite3, time, subprocess, warnings, pickle
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
HF_DIR = DATA / "research_intraday_hf"          # filtered monthly parquet (RTH, our tickers)
YF_DIR = DATA / "research_intraday_yf"
SESS = DATA / "research_intraday_sessions.pkl"
RES = DATA / "research_intraday_results.json"
DB = DATA / "market.db"
HF_URL = "https://huggingface.co/datasets/Rrishab/OHLCV-1m/resolve/main/data/ohlcv_{ym}.parquet"
TICKERS = ["SPY", "QQQ", "QQQQ", "IWM", "DIA", "SMH", "NVDA", "TLT", "UUP", "USO", "GLD", "HYG",
           "XLK", "XLF", "XLE", "XLY", "XLV", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AMD",
           "MARA", "RIOT", "CLSK", "COIN", "MSTR", "HOOD"]
SPLIT = os.environ.get("RI_SPLIT", "2019-01-01")


def db():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)


# ------------------------------------------------------------------ fetch
def _hf_month(ym):
    out = HF_DIR / f"{ym}.parquet"
    if out.exists():
        return ym, "cached"
    import pyarrow.parquet as pq, pyarrow as pa, pyarrow.compute as pc
    tmp = HF_DIR / "tmp" / f"ohlcv_{ym}.parquet"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        r = subprocess.run(["curl", "-4", "-sfL", "--max-time", "1200", "-o", str(tmp), HF_URL.format(ym=ym)])
        if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 1000:
            break
        time.sleep(5 * (attempt + 1))
    else:
        return ym, "download failed"
    try:
        pf = pq.ParquetFile(tmp)
        keep = pa.array(TICKERS)
        parts = []
        for b in pf.iter_batches(batch_size=1 << 20, columns=["timestamp", "open", "high", "low", "close", "volume", "ticker"]):
            m = pc.is_in(b.column("ticker"), value_set=keep)
            if pc.any(m).as_py():
                parts.append(b.filter(m))
        df = pa.Table.from_batches(parts).to_pandas() if parts else pd.DataFrame()
        if len(df):
            et = df["timestamp"].dt.tz_convert("America/New_York")
            hm = et.dt.hour * 60 + et.dt.minute
            df = df[(hm >= 9 * 60 + 25) & (hm <= 16 * 60 + 5)].copy()
            df["timestamp"] = df["timestamp"].dt.tz_convert("America/New_York").dt.tz_localize(None)
            df.to_parquet(out, index=False)
        else:
            pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "ticker"]).to_parquet(out, index=False)
    finally:
        tmp.unlink(missing_ok=True)
    return ym, f"{len(df)} rows"


def fetch_hf():
    HF_DIR.mkdir(parents=True, exist_ok=True)
    yms = [f"{y}-{m:02d}" for y in range(2007, 2027) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-03"]
    with ThreadPoolExecutor(3) as ex:
        for ym, msg in ex.map(_hf_month, yms):
            print(ym, msg, flush=True)


def fetch_yf():
    import yfinance as yf
    YF_DIR.mkdir(parents=True, exist_ok=True)
    for t in TICKERS + ["^VIX"]:
        for iv, per in (("5m", "60d"), ("1h", "730d"), ("1d", "max")):
            try:
                df = yf.download(t, period=per, interval=iv, progress=False, auto_adjust=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.index = df.index.tz_convert("America/New_York").tz_localize(None)
                df.to_csv(YF_DIR / f"{t.replace('^', '')}_{iv}.csv")
                print(t, iv, len(df), df.index[0], df.index[-1], flush=True)
            except Exception as e:
                print(t, iv, "ERR", e)


# ------------------------------------------------------------------ session matrices
N = 390                                   # 1-min bars 09:30..15:59 (bar labelled by its START; verified in check())
INDEX = ["SPY", "QQQ", "IWM"]
LEADS = ["DIA", "SMH", "NVDA", "TLT", "UUP", "USO", "HYG", "GLD"]
CRYPTO = ["MARA", "RIOT", "CLSK", "COIN", "MSTR", "HOOD"]


def T(h, m):
    """minute index: P[:, T(10, 0)] is the price at 10:00 (close of the 09:59 bar)."""
    return (h - 9) * 60 + m - 30


def db_daily(sym):
    with db() as c:
        d = pd.read_sql("SELECT ts, open, high, low, close, adj_close, volume FROM bars WHERE symbol=? AND interval='1d' ORDER BY ts",
                        c, params=(sym,), parse_dates=["ts"])
    if len(d) == 0 and (YF_DIR / f"{sym}_1d.csv").exists():      # not in market.db: yfinance daily cache
        y = pd.read_csv(YF_DIR / f"{sym}_1d.csv", parse_dates=[0])
        d = pd.DataFrame(dict(ts=y.iloc[:, 0], open=y.Open, high=y.High, low=y.Low, close=y.Close, adj_close=y["Adj Close"], volume=y.Volume))
    return d.set_index("ts")


# ticker reuse / relevance: crypto-linked only from these dates (COIN and HOOD were other companies' symbols before listing)
START = {"MARA": "2018-01-01", "RIOT": "2017-10-04", "CLSK": "2020-01-24", "COIN": "2021-04-14", "MSTR": "2020-08-11", "HOOD": "2021-07-29"}


def load_sym(sym, full=False):
    names = [sym] + (["QQQQ"] if sym == "QQQ" else [])
    parts = []
    for f in sorted(HF_DIR.glob("20*.parquet")):
        x = pd.read_parquet(f, filters=[("ticker", "in", names)])
        if len(x):
            parts.append(x)
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    if sym in START:
        df = df[df.timestamp >= START[sym]]
        if len(df) == 0:
            return None
    df = df.sort_values(["timestamp", "volume"]).drop_duplicates("timestamp", keep="last")
    mi = (df.timestamp.dt.hour * 60 + df.timestamp.dt.minute - 570).to_numpy()
    k = (mi >= 0) & (mi < N)
    df, mi = df[k], mi[k]
    days, di = np.unique(df.timestamp.dt.normalize().to_numpy(), return_inverse=True)
    n = len(days)
    O, H, L, C, V = (np.full((n, N), np.nan) for _ in range(5))
    for A, col in ((O, "open"), (H, "high"), (L, "low"), (C, "close"), (V, "volume")):
        A[di, mi] = df[col].to_numpy()
    fin = np.isfinite(C)
    nbar = fin.sum(1)
    first = np.argmax(fin, 1)
    last = N - 1 - np.argmax(fin[:, ::-1], 1)
    open0 = O[np.arange(n), first]
    Cf = pd.DataFrame(C).ffill(axis=1).to_numpy()
    Cf = np.where(np.isnan(Cf), open0[:, None], Cf)
    P = np.column_stack([open0, Cf])
    dates = pd.DatetimeIndex(days)
    # overnight gap, corrected for splits and dividends using market.db daily bars (HF minute data is unadjusted)
    gap = np.full(n, np.nan)
    try:
        dd = db_daily(sym)
        trading = dd.index
        pos = pd.Series(np.arange(len(trading)), index=trading)
        f = (dd.adj_close / dd.close).to_numpy()
        dcl = dd.close.to_numpy()
        for i in range(1, n):
            a, b = dates[i - 1], dates[i]
            if a not in pos.index or b not in pos.index or pos[b] - pos[a] != 1:
                continue
            ia, ib = pos[a], pos[b]
            g = math.log(P[i, 0] / P[i - 1, N]) + math.log(f[ib] / f[ia])
            fix = math.log((dcl[ib] / dcl[ia]) / (P[i, N] / P[i - 1, N]))
            if abs(fix) > 0.03:          # split (or bad print) between sessions
                g += fix
            gap[i] = g
    except Exception as e:
        print("  gap correction failed", sym, e)
    if not np.isfinite(gap).any():
        # no daily bars to correct against: raw gap between consecutive sessions (<=4 calendar days apart);
        # drop gaps that look like a split ratio (x2, x3, x4, x5, x10, x20 either way)
        raw = np.r_[np.nan, np.log(P[1:, 0] / P[:-1, N])]
        dt = np.r_[99, np.diff(dates.values).astype("timedelta64[D]").astype(int)]
        splitlike = np.zeros(n, bool)
        for rr in (2, 3, 4, 5, 8, 10, 15, 20, 25, 30):
            splitlike |= np.abs(np.abs(raw) - math.log(rr)) < 0.12
        gap = np.where((dt <= 4) & ~splitlike, raw, np.nan)
        print(f"  {sym}: no daily bars; raw gaps used, {int(splitlike.sum())} split-like gaps dropped")
    ok = (nbar >= 0.9 * N) & (last >= N - 3) & (first <= 2) if sym in INDEX + ["DIA"] else (nbar >= 0.5 * N) & (last >= N - 15)
    if sym in INDEX + CRYPTO:
        ok &= np.isfinite(gap)
    D = dict(sym=sym, dates=dates, P=P, nbar=nbar, first=first, last=last, gap=gap, ok=ok)
    if full:
        Hf = np.where(np.isnan(H), Cf, H); Lf = np.where(np.isnan(L), Cf, L)
        D.update(H=Hf.astype(np.float32), L=Lf.astype(np.float32), V=np.nan_to_num(V).astype(np.float32))
    return D


def check():
    """Integrity: bars per session, half days, missing sessions, splits, HF close vs market.db daily, bar-label alignment vs 1h bars."""
    out = {}
    for sym in INDEX + ["NVDA", "TSLA", "COIN"]:
        try:
            D = load_sym(sym)
        except Exception as e:
            print(sym, "load failed", e); continue
        if D is None:
            continue
        dd = db_daily(sym)
        dates = D["dates"]
        inrange = dd.index[(dd.index >= dates[0]) & (dd.index <= dates[-1])]
        missing = len(set(inrange) - set(dates))
        m = dd.reindex(dates)
        cl_err = np.abs(D["P"][:, N] / m.close.to_numpy() - 1)
        op_err = np.abs(D["P"][:, 0] / m.open.to_numpy() - 1)
        P = D["P"]
        splits = int(np.sum(np.abs(np.diff(np.log(P[:, N]))) > 0.25))
        r = dict(sessions=len(dates), first=str(dates[0].date()), last=str(dates[-1].date()), full_ok=int(D["ok"].sum()),
                 half_or_short=int(np.sum(D["last"] < N - 3)), missing_vs_db=missing,
                 close_vs_db_median_bp=round(float(np.nanmedian(cl_err)) * 1e4, 2),
                 close_vs_db_gt20bp=round(float(np.nanmean(cl_err > 0.002)), 4),
                 open_vs_db_median_bp=round(float(np.nanmedian(op_err)) * 1e4, 2),
                 raw_jumps_gt25pct=splits, gap_abs_gt10pct_after_fix=int(np.nansum(np.abs(D["gap"]) > 0.10)))
        # bar-label alignment: market.db 1h bar labelled 09:30 closes at 10:30; compare with P[:, 60] and P[:, 59]
        with db() as c:
            h = pd.read_sql("SELECT ts, close FROM bars WHERE symbol=? AND interval='1h' AND ts LIKE '%09:30'", c, params=(sym,))
        if len(h):
            h["d"] = pd.to_datetime(h.ts.str[:10]); h = h.set_index("d").close.reindex(dates)
            for lag in (59, 60, 61):
                e = np.abs(P[:, lag] / h.to_numpy() - 1)
                r[f"1h_close_vs_P[{lag}]_median_bp"] = round(float(np.nanmedian(e)) * 1e4, 2) if np.isfinite(e).any() else None
        out[sym] = r
        print(sym, r, flush=True)
    save("integrity", out)


def save(key, val):
    res = json.loads(RES.read_text()) if RES.exists() else {}
    res[key] = val
    RES.write_text(json.dumps(res, indent=1, default=str))


def build():
    S = {}
    for sym in INDEX + LEADS + CRYPTO:
        t0 = time.time()
        D = load_sym(sym, full=sym in INDEX)
        if D is None:
            print("  no data", sym); continue
        S[sym] = D
        print(f"  {sym}: {len(S[sym]['dates'])} sessions, ok {S[sym]['ok'].sum()}  ({time.time()-t0:.0f}s)", flush=True)
    with open(SESS, "wb") as f:
        pickle.dump(S, f, protocol=4)


# ------------------------------------------------------------------ stats helpers
from scipy.stats import norm, t as tdist


def tstat(r, groups=None):
    """mean, t; cluster-robust by day when several obs share a day."""
    r = np.asarray(r, float); n = len(r)
    if n < 3:
        return float(np.mean(r)) if n else np.nan, np.nan
    mu = r.mean()
    if groups is None:
        se = r.std(ddof=1) / math.sqrt(n)
    else:
        e = pd.Series(r - mu).groupby(np.asarray(groups)).sum().to_numpy()
        se = math.sqrt(np.sum(e ** 2)) / n * math.sqrt(len(e) / max(len(e) - 1, 1))
    return float(mu), float(mu / se) if se > 0 else np.nan


def pval(t, n):
    return float(2 * tdist.sf(abs(t), max(n - 1, 1))) if np.isfinite(t) else 1.0


TESTS = []


def add(h, name, O, learn=True, fixed=None, tradable=True, note=""):
    """O: dict of equal-length arrays: date, sym, i0, i1, s (+1/-1), y (log return of the underlying from i0 to i1), sig (ann. vol base).
    Direction d is learned on train (<SPLIT) as sign(mean(s*y)) unless fixed is given; OOS uses d frozen."""
    if O is None or len(O["y"]) == 0:
        return
    k = np.isfinite(O["y"]) & (O["s"] != 0)
    O = {a: np.asarray(b)[k] for a, b in O.items()}
    date = pd.DatetimeIndex(O["date"])
    tr, te = date < SPLIT, date >= SPLIT
    sy = O["s"] * O["y"]
    if fixed is not None:
        d = fixed
    else:
        d = 1 if tr.sum() == 0 or np.mean(sy[tr]) >= 0 else -1
    r = d * sy
    def st(m):
        if m.sum() < 3:
            return dict(n=int(m.sum()))
        mu, t = tstat(r[m], date[m].normalize() if len(np.unique(date[m].normalize())) < m.sum() else None)
        return dict(n=int(m.sum()), hit=round(float(np.mean(r[m] > 0) / max(np.mean(r[m] != 0), 1e-9)) * 100, 1), mean_pct=round(mu * 100, 4),
                    t=round(t, 2), p=pval(t, m.sum()))
    last3 = date >= pd.Timestamp("2023-04-01")
    rec = dict(h=h, name=name, dir="as-is" if d == 1 else "faded", fixed=fixed is not None, tradable=tradable, note=note,
               train=st(tr), test=st(te), last3y=st(last3 & te))
    rec["_oos"] = {a: b[te] for a, b in O.items()}
    rec["_oos"]["dir"] = d * O["s"][te]
    TESTS.append(rec)


def obs(D, rows, s, i0, i1, sig):
    rows = np.asarray(rows)
    if len(rows) == 0:
        return None
    i0 = np.broadcast_to(np.asarray(i0), rows.shape) if np.ndim(i0) == 0 else np.asarray(i0)
    i1 = np.broadcast_to(np.asarray(i1), rows.shape) if np.ndim(i1) == 0 else np.asarray(i1)
    P = D["P"]
    y = np.log(P[rows, i1] / P[rows, i0])
    return dict(date=D["dates"][rows].to_numpy(), sym=np.array([D["sym"]] * len(rows)), i0=i0.astype(int), i1=i1.astype(int),
                s=np.asarray(s, float), y=y, sig=np.asarray(sig, float), S0=P[rows, i0])


def cat(*Os):
    Os = [o for o in Os if o is not None]
    return {k: np.concatenate([o[k] for o in Os]) for k in Os[0]} if Os else None


def sel(D, mask, s, i0, i1, sig):
    """session-level observation set: rows where mask & ok & s != 0."""
    m = mask & D["ok"] & (np.asarray(s) != 0)
    rows = np.where(m)[0]
    pick = lambda a: a[rows] if np.ndim(a) else a
    return obs(D, rows, np.asarray(s)[rows], pick(i0), pick(i1), np.asarray(sig)[rows])


def train_q(D, x, q):
    tr = (D["dates"] < SPLIT) & D["ok"] & np.isfinite(x)
    return np.nanquantile(x[tr], q)


# ------------------------------------------------------------------ context: VIX, trend, events, shocks, volume
def context(S):
    spy = S["SPY"]; dates = spy["dates"]
    vix = db_daily("^VIX").close
    spyd = db_daily("SPY").close
    ma50 = spyd.rolling(50).mean()
    prev = lambda s: s.shift(1).reindex(dates, method="ffill").to_numpy()
    ctx = dict(vix=prev(vix), trend=np.sign(prev(spyd) - prev(ma50)))
    sys.path.insert(0, str(ROOT / "bot"))
    from research_direction import FOMC_OLD, _brainstorm_lists
    ev = _brainstorm_lists()
    fomc = set(pd.Timestamp(x) for x in FOMC_OLD.split()) | set(ev["FOMC"])
    nfp = set(ev["NFP"])
    for y in range(2007, 2015):
        for m in range(1, 13):
            d0 = pd.Timestamp(y, m, 1); nfp.add(d0 + pd.Timedelta(days=(4 - d0.weekday()) % 7))
    cpi = set(ev["CPI"])
    ctx["fomc"] = np.array([d in fomc for d in dates]); ctx["cpi"] = np.array([d in cpi for d in dates])
    ctx["nfp"] = np.array([d in nfp for d in dates])
    ctx["event"] = ctx["fomc"] | ctx["cpi"] | ctx["nfp"]
    ctx["dow"] = dates.dayofweek.to_numpy()
    return ctx


def per_sym_ctx(D, ctx_dates, ctx):
    """align SPY-calendar context to another symbol's sessions."""
    idx = pd.Series(np.arange(len(ctx_dates)), index=ctx_dates).reindex(D["dates"]).to_numpy()
    out = {}
    for k, v in ctx.items():
        a = np.full(len(idx), np.nan if v.dtype.kind == "f" else 0, dtype=float if v.dtype.kind == "f" else v.dtype)
        good = np.isfinite(idx)
        a[good] = v[idx[good].astype(int)]
        out[k] = a
    return out


def shocks(D):
    """4-sigma 5-minute moves; sigma = sd of all 5-min returns over the previous 20 ok sessions."""
    P = D["P"]
    r5 = np.diff(np.log(P[:, ::5]), axis=1)                       # 78 blocks
    sd_day = np.nanstd(r5, axis=1)
    sig = pd.Series(np.where(D["ok"], sd_day, np.nan)).rolling(20, min_periods=10).apply(lambda x: np.sqrt(np.nanmean(x ** 2))).shift(1).to_numpy()
    sh = np.abs(r5) > 4 * sig[:, None]
    return sh                                                     # [n, 78], block j covers minutes 5j..5j+5


def ann_sig(D, ctx_v, sym):
    """base annualised vol for option pricing at multiplier 1.0: VIX for SPY/DIA, 1.2 VIX for QQQ, 1.3 VIX for IWM, else 20d RV."""
    if sym in ("SPY", "DIA"):
        return ctx_v / 100
    if sym == "QQQ":
        return 1.2 * ctx_v / 100
    if sym == "IWM":
        return 1.3 * ctx_v / 100
    cc = D["gap"] + np.log(D["P"][:, N] / D["P"][:, 0])          # split/dividend-corrected close->close
    rv = pd.Series(cc).rolling(20, min_periods=10).std().shift(1).to_numpy() * math.sqrt(252)
    return rv

# ------------------------------------------------------------------ hypotheses
def first_cross(above, start, stop, hold=30):
    """per row: first index j in [start, stop) where the boolean series flips after `hold` minutes on the other side; -1 if none."""
    n = above.shape[0]; out = np.full(n, -1); side = np.zeros(n)
    for i in range(n):
        a = above[i]
        flips = np.where(a[start:stop] != a[start - 1:stop - 1])[0] + start
        for j in flips:
            if j >= hold and (a[j - hold:j] == a[j - 1]).all():
                out[i] = j; side[i] = 1 if a[j] else -1; break
    return out, side


def orb(D, m, cutoff):
    """first CLOSE outside the m-minute opening range, between minute m and cutoff. Entry at that bar's close (index j+1)."""
    H, L, P = D["H"], D["L"], D["P"]
    hi, lo = H[:, :m].max(1), L[:, :m].min(1)
    C = P[:, 1:]
    up = (C[:, m:cutoff] > hi[:, None]); dn = (C[:, m:cutoff] < lo[:, None])
    ju = np.where(up.any(1), up.argmax(1), 10 ** 6); jd = np.where(dn.any(1), dn.argmax(1), 10 ** 6)
    s = np.where((ju < jd), 1, np.where(jd < ju, -1, 0))
    entry = m + np.minimum(ju, jd) + 1
    return s, np.where(s != 0, entry, 0), (hi - lo) / P[:, 0]


def tests():
    with open(SESS, "rb") as f:
        S = pickle.load(f)
    TESTS.clear()
    spy = S["SPY"]
    ctx0 = context(S)
    C = {sym: per_sym_ctx(S[sym], spy["dates"], ctx0) for sym in S}
    sg = lambda x: np.sign(np.nan_to_num(x))
    for sym in INDEX:
        D = S[sym]; P = D["P"]; n = len(P); c = C[sym]
        sig = ann_sig(D, c["vix"], sym)
        pc = P[:, 0] / np.exp(D["gap"])
        ret = lambda a, b: np.log(P[:, b] / P[:, a])
        ALL = np.ones(n, bool)
        sh = shocks(D)
        shock_after = lambda i: sh[:, i // 5:].any(1)
        shock_before = lambda i: sh[:, :i // 5].any(1)
        V = D["V"]
        v30 = V[:, :30].sum(1)
        vratio = v30 / pd.Series(np.where(D["ok"], v30, np.nan)).rolling(20, min_periods=10).mean().shift(1).to_numpy()
        vix_hi = c["vix"] >= train_q(D, c["vix"], 2 / 3); vix_lo = c["vix"] <= train_q(D, c["vix"], 1 / 3)
        ev = c["event"].astype(bool)
        g = D["gap"] * 100
        # ---- H1 market intraday momentum (Gao-Han-Li-Zhou)
        x1 = np.log(P[:, 30] / pc); x12 = ret(330, 360)
        big1 = np.abs(x1) >= train_q(D, np.abs(x1), 2 / 3)
        add("H1", f"{sym} first half-hour (prev close->10:00) => last 30m", sel(D, ALL, sg(x1), 360, N, sig))
        add("H1", f"{sym} first half-hour => last hour", sel(D, ALL, sg(x1), 330, N, sig))
        add("H1", f"{sym} 12th half-hour (15:00-15:30) => last 30m", sel(D, ALL, sg(x12), 360, N, sig))
        add("H1", f"{sym} first & 12th half-hour agree => last 30m", sel(D, sg(x1) == sg(x12), sg(x1), 360, N, sig))
        add("H1", f"{sym} first half-hour, high-volume open (top tercile vol ratio) => last 30m",
            sel(D, vratio >= train_q(D, vratio, 2 / 3), sg(x1), 360, N, sig))
        add("H1", f"{sym} first half-hour, high VIX tercile => last 30m", sel(D, vix_hi, sg(x1), 360, N, sig))
        add("H1", f"{sym} first half-hour, |x| top tercile => last 30m", sel(D, big1, sg(x1), 360, N, sig))
        add("H1", f"{sym} first half-hour, event day (FOMC/CPI/NFP) => last 30m", sel(D, ev, sg(x1), 360, N, sig))
        add("H1", f"{sym} first half-hour, shock day (4sd 5-min move before 15:30) => last 30m", sel(D, shock_before(360), sg(x1), 360, N, sig))
        # ---- H2 opening range breakout and gaps
        for m in (5, 15, 30):
            s, ent, orw = orb(D, m, T(12, 0))
            add("H2", f"{sym} ORB-{m} (first close outside range by 12:00) => close", sel(D, ALL, s, ent, N, sig))
            add("H2", f"{sym} ORB-{m} breakout agrees with gap => close", sel(D, s == sg(g), s, ent, N, sig))
            add("H2", f"{sym} ORB-{m} breakout against gap => close", sel(D, s == -sg(g), s, ent, N, sig))
            add("H2", f"{sym} ORB-{m}, high VIX tercile => close", sel(D, vix_hi, s, ent, N, sig))
        for lo_, hi_ in ((0.1, 0.3), (0.3, 0.6), (0.6, 1.0), (1.0, 99)):
            b = (np.abs(g) >= lo_) & (np.abs(g) < hi_)
            add("H2", f"{sym} gap {lo_}-{hi_}% : open => close (go vs fill)", sel(D, b, sg(g), 0, N, sig))
            conf = b & (sg(ret(0, 30)) == sg(g))
            add("H2", f"{sym} gap {lo_}-{hi_}% confirmed by 10:00 => 10:00-close", sel(D, conf, sg(g), 30, N, sig))
            notfilled = b & np.where(g > 0, D["L"][:, :30].min(1) > pc, D["H"][:, :30].max(1) < pc)
            add("H2", f"{sym} gap {lo_}-{hi_}% unfilled by 10:00 => 10:00-close", sel(D, notfilled, sg(g), 30, N, sig))
        # ---- H3 first hour => rest of day, conditioned
        xo = ret(0, 60); xc = np.log(P[:, 60] / pc)
        add("H3", f"{sym} first hour open->10:30 => 10:30-close", sel(D, ALL, sg(xo), 60, N, sig))
        add("H3", f"{sym} prev close->10:30 => 10:30-close", sel(D, ALL, sg(xc), 60, N, sig))
        add("H3", f"{sym} first hour agrees with gap => 10:30-close", sel(D, sg(xo) == sg(g), sg(xo), 60, N, sig))
        add("H3", f"{sym} first hour against gap => 10:30-close", sel(D, sg(xo) == -sg(g), sg(xo), 60, N, sig))
        rng = (D["H"][:, :60].max(1) - D["L"][:, :60].min(1)) / P[:, 0]
        trng = np.maximum(D["H"].max(1), pc) - np.minimum(D["L"].min(1), pc)
        atr = pd.Series(np.where(D["ok"], trng / pc, np.nan)).rolling(14, min_periods=10).mean().shift(1).to_numpy()
        ra = rng / atr
        add("H3", f"{sym} first hour, range/ATR top tercile => 10:30-close", sel(D, ra >= train_q(D, ra, 2 / 3), sg(xo), 60, N, sig))
        add("H3", f"{sym} first hour, range/ATR bottom tercile => 10:30-close", sel(D, ra <= train_q(D, ra, 1 / 3), sg(xo), 60, N, sig))
        add("H3", f"{sym} first hour, high VIX tercile => 10:30-close", sel(D, vix_hi, sg(xo), 60, N, sig))
        add("H3", f"{sym} first hour, low VIX tercile => 10:30-close", sel(D, vix_lo, sg(xo), 60, N, sig))
        for dw, nm in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri")):
            add("H3", f"{sym} first hour, {nm} => 10:30-close", sel(D, c["dow"] == dw, sg(xo), 60, N, sig))
        add("H3", f"{sym} first hour, SPY above 50dMA => 10:30-close", sel(D, c["trend"] > 0, sg(xo), 60, N, sig))
        add("H3", f"{sym} first hour, SPY below 50dMA => 10:30-close", sel(D, c["trend"] < 0, sg(xo), 60, N, sig))
        add("H3", f"{sym} first hour agrees with 50dMA trend => 10:30-close", sel(D, sg(xo) == c["trend"], sg(xo), 60, N, sig))
        for m in (5, 15, 30, 90, 120):
            add("H3", f"{sym} first {m} min open->{m} => rest of day", sel(D, ALL, sg(ret(0, m)), m, N, sig))
        # ---- H4 VWAP
        typ = (D["H"] + D["L"] + P[:, 1:]) / 3
        cv = np.cumsum(D["V"], 1); vw = np.cumsum(typ * D["V"], 1) / np.where(cv > 0, cv, np.nan)
        vwap = np.column_stack([P[:, 0], vw])                     # vwap[:, i] = VWAP of bars before minute i
        for i, nm in ((60, "10:30"), (120, "11:30"), (210, "13:00")):
            s = sg(P[:, i] - vwap[:, i])
            add("H4", f"{sym} price vs VWAP at {nm} => rest of day", sel(D, ALL, s, i, N, sig))
            dist = np.abs(np.log(P[:, i] / vwap[:, i]))
            add("H4", f"{sym} price vs VWAP at {nm}, distance top tercile => rest of day",
                sel(D, dist >= train_q(D, dist, 2 / 3), s, i, N, sig))
        above = P[:, 1:] > vwap[:, 1:]
        j, side = first_cross(above, 60, 210)
        add("H4", f"{sym} first VWAP reclaim/loss 10:30-13:00 (after 30m on other side) => close",
            sel(D, j > 0, side, np.where(j > 0, j + 1, 0), N, sig))
        # ---- H5 lunch reversal / power hour (conditioned)
        add("H5", f"{sym} open->11:30 => 11:30-13:30 (lunch)", sel(D, ALL, sg(ret(0, 120)), 120, 240, sig))
        add("H5", f"{sym} open->12:00 => 12:00-14:00", sel(D, ALL, sg(ret(0, 150)), 150, 270, sig))
        add("H5", f"{sym} 11:30-13:30 lunch move => 13:30-close", sel(D, ALL, sg(ret(120, 240)), 240, N, sig))
        x15 = ret(0, 330); s15 = sg(x15)
        add("H5", f"{sym} open->15:00 => power hour (15:00-close)", sel(D, ALL, s15, 330, N, sig))
        add("H5", f"{sym} 14:00-15:00 => power hour", sel(D, ALL, sg(ret(270, 330)), 330, N, sig))
        add("H5", f"{sym} open->15:00, |x| top tercile => power hour", sel(D, np.abs(x15) >= train_q(D, np.abs(x15), 2 / 3), s15, 330, N, sig))
        add("H5", f"{sym} open->15:00, high VIX => power hour", sel(D, vix_hi, s15, 330, N, sig))
        add("H5", f"{sym} open->15:00, low VIX => power hour", sel(D, vix_lo, s15, 330, N, sig))
        add("H5", f"{sym} open->15:00, uptrend => power hour", sel(D, c["trend"] > 0, s15, 330, N, sig))
        add("H5", f"{sym} open->15:00, downtrend => power hour", sel(D, c["trend"] < 0, s15, 330, N, sig))
        add("H5", f"{sym} open->15:00, quiet (no event, no shock before 15:00) => power hour",
            sel(D, ~ev & ~shock_before(330), s15, 330, N, sig))
        add("H5", f"{sym} open->15:00, gap agrees => power hour", sel(D, s15 == sg(g), s15, 330, N, sig))
        # ---- H6 quiet vs eventful, for the core morning signals
        for nm, s, i in (("first hour", sg(xo), 60), ("VWAP 10:30", sg(P[:, 60] - vwap[:, 60]), 60), ("first half-hour", sg(x1), 30)):
            add("H6", f"{sym} {nm} => close, non-event days (ex-ante)", sel(D, ~ev, s, i, N, sig))
            add("H6", f"{sym} {nm} => close, event days", sel(D, ev, s, i, N, sig))
            add("H6", f"{sym} {nm} => close, no 4sd shock after signal (EX-POST, not tradable)", sel(D, ~shock_after(i), s, i, N, sig),
                tradable=False)
            add("H6", f"{sym} {nm} => close, shock after signal (EX-POST)", sel(D, shock_after(i), s, i, N, sig), tradable=False)
            blk = sh[:, i // 5:]
            ex = np.where(blk.any(1), (i // 5 + blk.argmax(1)) * 5 + 5, N)
            add("H6", f"{sym} {nm} => close, non-event, exit on first 4sd shock (tradable)", sel(D, ~ev, s, i, np.minimum(ex, N), sig))
    # ---- H7 cross-asset leads (non-overlapping k-minute windows 10:00-15:30)
    D = spy; c = C["SPY"]; sig = ann_sig(D, c["vix"], "SPY")
    for k in (5, 15, 30):
        grid = np.arange(30 + k, 360 - k + 1, k)
        for lead in ["SPY", "QQQ", "IWM", "SMH", "NVDA", "TLT", "UUP", "USO", "HYG", "GLD", "QQQ-SPY", "SMH-SPY", "NVDA-SPY"]:
            nm = lead.split("-")[0]
            if nm not in S:
                continue
            L_ = S[nm]
            rows_l = pd.Series(np.arange(len(L_["dates"])), index=L_["dates"]).reindex(D["dates"]).to_numpy()
            okr = np.isfinite(rows_l) & D["ok"]
            okr[okr] &= L_["ok"][rows_l[okr].astype(int)]
            rs = np.where(okr)[0]; rl = rows_l[rs].astype(int)
            parts = []
            for t0 in grid:
                xl = np.log(L_["P"][rl, t0] / L_["P"][rl, t0 - k])
                if "-" in lead:
                    xl = xl - np.log(D["P"][rs, t0] / D["P"][rs, t0 - k])
                parts.append(obs(D, rs, sg(xl), t0, t0 + k, sig[rs]))
            add("H7", f"{lead} last {k}m => SPY next {k}m", cat(*parts))
    # ---- H8 relative strength QQQ vs IWM first hour
    Q, I = S["QQQ"], S["IWM"]
    ri = pd.Series(np.arange(len(I["dates"])), index=I["dates"]).reindex(Q["dates"]).to_numpy()
    okq = np.isfinite(ri) & Q["ok"]; okq[okq] &= I["ok"][ri[okq].astype(int)]
    rq = np.where(okq)[0]; rI = ri[rq].astype(int)
    rel = np.log(Q["P"][rq, 60] / Q["P"][rq, 0]) - np.log(I["P"][rI, 60] / I["P"][rI, 0])
    yrel = np.log(Q["P"][rq, N] / Q["P"][rq, 60]) - np.log(I["P"][rI, N] / I["P"][rI, 60])
    O = dict(date=Q["dates"][rq].to_numpy(), sym=np.array(["QQQ-IWM"] * len(rq)), i0=np.full(len(rq), 60), i1=np.full(len(rq), N),
             s=sg(rel), y=yrel, sig=np.full(len(rq), np.nan), S0=np.full(len(rq), np.nan))
    add("H8", "QQQ-IWM first hour => QQQ-IWM 10:30-close (spread)", O, tradable=False)
    big = np.abs(rel) >= np.nanquantile(np.abs(rel[Q["dates"][rq] < SPLIT]), 2 / 3)
    add("H8", "QQQ-IWM first hour, top tercile => spread 10:30-close", {k: v[big] for k, v in O.items()}, tradable=False)
    for sym in ("QQQ", "SPY", "IWM"):
        Dm = S[sym]; rr = pd.Series(np.arange(len(Dm["dates"])), index=Dm["dates"]).reindex(Q["dates"][rq]).to_numpy()
        g_ = np.isfinite(rr); rr2 = rr[g_].astype(int)
        add("H8", f"QQQ-IWM first hour => {sym} 10:30-close",
            obs(Dm, rr2, sg(rel[g_]), 60, N, ann_sig(Dm, C[sym]["vix"], sym)[rr2]))
    # ---- extra: walk-forward ridge at 10:30 combining morning features (SPY)
    D = spy; P = D["P"]; c = C["SPY"]
    typ = (D["H"] + D["L"] + P[:, 1:]) / 3; cv = np.cumsum(D["V"], 1)
    vw60 = (np.cumsum(typ * D["V"], 1) / np.where(cv > 0, cv, np.nan))[:, 59]
    X = np.column_stack([np.ones(len(P)), D["gap"], np.log(P[:, 60] / P[:, 0]), np.log(P[:, 30] / P[:, 0]), np.log(P[:, 60] / P[:, 45]),
                         np.log(P[:, 60] / vw60), (D["H"][:, :60].max(1) - P[:, 60]) / P[:, 0], (P[:, 60] - D["L"][:, :60].min(1)) / P[:, 0],
                         c["trend"], np.nan_to_num(c["vix"]) / 100, c["event"].astype(float)])
    y = np.log(P[:, N] / P[:, 60])
    good = D["ok"] & np.isfinite(X).all(1) & np.isfinite(y)
    pred = np.full(len(P), np.nan)
    years = D["dates"].year
    for yr in range(int(SPLIT[:4]), years.max() + 1):
        trn = good & (years < yr); tst = good & (years == yr)
        if trn.sum() < 500 or tst.sum() == 0:
            continue
        Xt = X[trn]; mu, sd = Xt[:, 1:].mean(0), Xt[:, 1:].std(0) + 1e-12
        Z = lambda A: np.column_stack([A[:, :1], (A[:, 1:] - mu) / sd])
        A = Z(Xt)
        beta = np.linalg.solve(A.T @ A + 50.0 * np.eye(A.shape[1]), A.T @ y[trn])
        pred[tst] = Z(X[tst]) @ beta
    add("H3", "SPY walk-forward ridge (10 morning features) at 10:30 => close",
        sel(D, np.isfinite(pred), sg(pred), 60, N, ann_sig(D, c["vix"], "SPY")), fixed=1)
    # ---- owner lead: crypto-linked names fade their opening gap (daily-bar finding); replay intraday, fixed fade direction
    for thr in (0.03, 0.05):
        for ent, nm in ((0, "open print"), (5, "09:35"), (30, "10:00"), (60, "10:30")):
            parts = []
            for sym in [x for x in CRYPTO if x in S]:
                Dc = S[sym]; gg = Dc["gap"]
                parts.append(sel(Dc, np.abs(gg) >= thr, -sg(gg), ent, N, ann_sig(Dc, None, sym)))
            add("CRYPTO", f"crypto names gap >= {thr:.0%}: fade from {nm} => close", cat(*parts), fixed=1)
            for sym in [x for x in CRYPTO if x in S] if (thr == 0.03 and ent == 5) else []:
                Dc = S[sym]; gg = Dc["gap"]
                add("CRYPTO", f"{sym} gap >= 3%: fade from 09:35 => close", sel(Dc, np.abs(gg) >= thr, -sg(gg), ent, N, ann_sig(Dc, None, sym)), fixed=1)
    # ---- BH across all tests
    ps = np.array([t["test"].get("p", 1.0) for t in TESTS])
    order = np.argsort(ps); m_ = len(ps)
    for q in (0.05, 0.10):
        ok_i = [i for i, j in enumerate(order) if ps[j] <= (i + 1) / m_ * q]
        cut = ps[order[max(ok_i)]] if ok_i else -1
        for t, p in zip(TESTS, ps):
            t[f"bh{int(q * 100)}"] = bool(p <= cut)
    for t, p in zip(TESTS, ps):
        t["bonf"] = bool(p <= 0.05 / m_)
    save("tests", [{k: v for k, v in t.items() if k != "_oos"} for t in TESTS])
    with open(DATA / "research_intraday_trades.pkl", "wb") as f:
        pickle.dump([(t["name"], t["tradable"], t["bh10"], t["_oos"]) for t in TESTS], f, protocol=4)
    print(f"{len(TESTS)} tests; BH q=0.05 pass {sum(t['bh5'] for t in TESTS)}, q=0.10 pass {sum(t['bh10'] for t in TESTS)}, "
          f"Bonferroni pass {sum(t['bonf'] for t in TESTS)}; nominal OOS p<0.05: {int(np.sum(ps < 0.05))} (expected by chance {0.05 * m_:.0f})")
    for t in sorted(TESTS, key=lambda t: t["test"].get("p", 1))[:45]:
        a, b, l3 = t["train"], t["test"], t["last3y"]
        print(f"  {t['h']:6s} {t['name'][:72]:72s} {t['dir']:6s} OOS n={b.get('n')} hit={b.get('hit')} mean={b.get('mean_pct')}% "
              f"t={b.get('t')} | IS t={a.get('t')} | 3y t={l3.get('t')} {'BH10' if t['bh10'] else ''}{' BONF' if t['bonf'] else ''}")

# ------------------------------------------------------------------ option economics
MINYR = 365 * 24 * 60          # 0DTE: calendar-minute time to expiry. With IV = VIX this gives E|move| ~0.30% at VIX 15 from 10:00,
                               # matching the repo's observed 0DTE implied move (vol_obs).


def bs_px(S, K, Tm, sig, call):
    sT = sig * np.sqrt(Tm)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * Tm) / sT; d2 = d1 - sT
    return np.where(call, S * norm.cdf(d1) - K * norm.cdf(d2), K * norm.cdf(-d2) - S * norm.cdf(-d1))


def opt_returns(O, delta=0.40, m=1.0, cost=0.03, days_extra=0.0):
    """buy a delta-`delta` call (dir>0) or put (dir<0) at i0 with IV = sig*m; exit at i1 (intrinsic if i1 == close and no extra days).
    cost = round-trip spread as a fraction of premium (all paid on entry when held to expiry)."""
    S0 = O["S0"]; S1 = S0 * np.exp(O["y"]); call = O["dir"] > 0
    sig = O["sig"] * m
    T0 = (N - O["i0"]) / MINYR + days_extra / 365; T1 = (N - O["i1"]) / MINYR + days_extra / 365
    z = norm.ppf(delta)
    K = np.where(call, S0 * np.exp(-z * sig * np.sqrt(T0) + 0.5 * sig ** 2 * T0), S0 * np.exp(z * sig * np.sqrt(T0) + 0.5 * sig ** 2 * T0))
    prem = bs_px(S0, K, T0, sig, call)
    expiry = T1 <= 1e-12
    intrinsic = np.where(call, np.maximum(S1 - K, 0), np.maximum(K - S1, 0))
    val = np.where(expiry, intrinsic, bs_px(S1, K, np.maximum(T1, 1e-9), sig, call))
    r = np.where(expiry, val / (prem * (1 + cost)) - 1, val * (1 - cost / 2) / (prem * (1 + cost / 2)) - 1)
    return r, prem / S0


def bankroll(r, pfrac, per_year, start, f, px_now, cost=0.03, n=20000, seed=11, whole=True):
    """one year of trades drawn with replacement from OOS returns. whole=True buys whole contracts with f*equity and skips
    the trade when even one contract is unaffordable; whole=False is ideal fractional sizing."""
    rng = np.random.default_rng(seed)
    k = max(int(round(per_year)), 1)
    idx = rng.integers(0, len(r), size=(n, k))
    E = np.full(n, float(start)); traded = np.zeros(n)
    for j in range(k):
        rr = r[idx[:, j]]
        if whole:
            c1 = pfrac[idx[:, j]] * np.broadcast_to(px_now, r.shape)[idx[:, j]] * 100 * (1 + cost)
            nc = np.floor(f * E / c1)
            E = E + nc * c1 * rr; traded += nc > 0
        else:
            E = E * (1 + f * rr); traded += 1
    E = np.minimum(E, 1e6)                       # report cap: liquidity/position limits make >$1M meaningless
    return dict(median=round(float(np.median(E)), 0), p_grow=round(float(np.mean(E > start)), 3),
                p_double=round(float(np.mean(E >= 2 * start)), 3), p_lose90=round(float(np.mean(E < 0.1 * start)), 3),
                p25=round(float(np.percentile(E, 25)), 0), p75=round(float(np.percentile(E, 75)), 0),
                trades_done=round(float(traded.mean()), 1))


def px_now(sym):
    try:
        with db() as c:
            v = c.execute("SELECT close FROM bars WHERE symbol=? AND interval='1d' ORDER BY ts DESC LIMIT 1", (sym,)).fetchone()
        if v:
            return float(v[0])
    except Exception:
        pass
    f = YF_DIR / f"{sym}_1h.csv"
    return float(pd.read_csv(f).iloc[-1]["Close"]) if f.exists() else np.nan


def options():
    with open(DATA / "research_intraday_trades.pkl", "rb") as f:
        trades = pickle.load(f)
    tests_ = {t["name"]: t for t in json.loads(RES.read_text())["tests"]}
    oos_years = None
    out = {}
    # calibration: realized |SPY move| from 10:00 to close vs BS-implied E|move| with IV = VIX (m=1.0)
    for name, tradable, bh, O in trades:
        if name.startswith("SPY first half-hour (prev close->10:00) => last 30m"):
            pass
    with open(SESS, "rb") as f:
        S = pickle.load(f)
    spy = S["SPY"]; ctx = context(S)
    te = (spy["dates"] >= SPLIT) & spy["ok"] & np.isfinite(ctx["vix"])
    for i0, nm in ((30, "10:00"), (60, "10:30"), (330, "15:00"), (360, "15:30")):
        real = np.abs(np.log(spy["P"][te, N] / spy["P"][te, i0]))
        imp = ctx["vix"][te] / 100 * np.sqrt((N - i0) / MINYR) * 0.798
        out[f"calib_{nm}"] = dict(realized_mean_abs_pct=round(float(real.mean()) * 100, 3), implied_mean_abs_pct=round(float(imp.mean()) * 100, 3),
                                  ratio=round(float(real.mean() / imp.mean()), 3),
                                  ratio_vix_lt16=round(float(real[ctx["vix"][te] < 16].mean() / imp[ctx["vix"][te] < 16].mean()), 3))
        print("calibration", nm, out[f"calib_{nm}"])
    span = (pd.Timestamp(max(spy["dates"])) - pd.Timestamp(SPLIT)).days / 365.25
    # which tests to price: BH survivors + top tradable by OOS t + baselines + every crypto test
    ranked = sorted([t for t in trades if t[1]], key=lambda t: -(tests_[t[0]]["test"].get("t") or -99))
    pick = [t for t in trades if t[2] and t[1]] + ranked[:12] + [t for t in trades if t[0].startswith("crypto") or tests_[t[0]]["h"] == "CRYPTO"]
    seen = set(); pick = [t for t in pick if not (t[0] in seen or seen.add(t[0]))]
    # baselines: always-call / always-put at 10:30 from the first-hour test universe
    base = next(t for t in trades if t[0] == "SPY first hour open->10:30 => 10:30-close")
    for nm, d in (("BASELINE SPY always call 10:30 => close", 1), ("BASELINE SPY always put 10:30 => close", -1)):
        O = dict(base[3]); O["dir"] = np.full(len(O["y"]), d)
        pick.append((nm, True, False, O))
    rows = []
    for name, tradable, bh, O in pick:
        O = {k: np.asarray(v) for k, v in O.items()}
        good = np.isfinite(O["sig"]) & (O["sig"] > 0) & np.isfinite(O["S0"])
        O = {k: v[good] for k, v in O.items()}
        if len(O["y"]) < 10:
            continue
        sym = str(O["sym"][0])
        single = sym in CRYPTO or "crypto" in name
        costs = (0.04, 0.08) if single else (0.02, 0.04)
        grid = {}
        for dl in (0.3, 0.4, 0.5):
            for m in (1.0, 1.2):
                for c in costs:
                    for wk in ((0.0, 2.5) if single else (0.0,)):
                        r, pf = opt_returns(O, dl, m, c, wk)
                        grid[(dl, m, c, wk)] = (r, pf)
        c0 = sum(costs) / 2
        r_brief, pf_brief = opt_returns(O, 0.4, 1.0, c0)
        # FAIR pricing: IV multiplier set so implied E|move| over [i0, i1] equals the realized mean |move| on these same days
        # (direction-free, so no look-ahead on the signal). EV under fair pricing = value of the DIRECTION call alone.
        # RICH = fair / 0.8 (repo's 33y evidence: realized ~0.8x implied).
        imp = O["sig"] * np.sqrt((O["i1"] - O["i0"]) / MINYR) * 0.798
        k_fair = float(np.mean(np.abs(O["y"])) / np.mean(imp))
        r, pf = opt_returns(O, 0.4, k_fair, c0)
        r_rich, _ = opt_returns(O, 0.4, k_fair / 0.8, c0)
        mu, t = tstat(r)
        ev_all = [float(np.mean(v[0])) for v in grid.values()]
        per_year = len(r) / span
        prices = {s: px_now(s) for s in set(O["sym"])}
        pnow = np.array([prices[s] for s in O["sym"]])
        cost1 = float(np.median(pf * pnow * 100 * (1 + c0)))
        rec = dict(name=name, n=len(r), k_fair=round(k_fair, 2),
                   ev_brief=round(float(np.mean(r_brief)) * 100, 1), pop_brief=round(float(np.mean(r_brief > 0)) * 100, 1),
                   ev_rich=round(float(np.mean(r_rich)) * 100, 1), per_year=round(per_year, 1), underlying_mean_pct=round(float(np.mean(O["dir"] * O["y"])) * 100, 4),
                   hit=round(float(np.mean(O["dir"] * O["y"] > 0)) * 100, 1),
                   ev_base=round(mu * 100, 1), t_ev=round(t, 2), pop=round(float(np.mean(r > 0)) * 100, 1),
                   ev_min=round(min(ev_all) * 100, 1), ev_max=round(max(ev_all) * 100, 1),
                   ev_delta50=round(float(np.mean(grid[(0.5, 1.0, costs[0], 0.0)][0])) * 100, 1),
                   ev_iv12_c4=round(float(np.mean(grid[(0.4, 1.2, costs[1], 0.0)][0])) * 100, 1),
                   ev_mkt_calib=round(float(np.mean(opt_returns(O, 0.4, 0.8, c0)[0])) * 100, 1),
                   contract_cost=round(cost1, 0), min_capital_15=round(cost1 / 0.15, 0), min_capital_25=round(cost1 / 0.25, 0),
                   bh10=bool(tests_.get(name, {}).get("bh10", False)), last3y_ev=None)
        ev_all = [float(np.mean(opt_returns(O, dl, k_fair * mm, cc)[0])) for dl in (0.3, 0.4, 0.5) for mm in (1.0, 1.2) for cc in costs]
        rec["ev_min"] = round(min(ev_all) * 100, 1); rec["ev_max"] = round(max(ev_all) * 100, 1)
        rec["ev_delta50"] = round(float(np.mean(opt_returns(O, 0.5, k_fair, c0)[0])) * 100, 1)
        if single:
            rw, _ = opt_returns(O, 0.4, k_fair, costs[1], 2.5)
            rec["ev_weekly_fair_c8"] = round(float(np.mean(rw)) * 100, 1)
            rec["pop_weekly"] = round(float(np.mean(rw > 0)) * 100, 1)
        l3 = pd.DatetimeIndex(O["date"]) >= pd.Timestamp("2023-04-01")
        if l3.sum() > 5:
            rec["last3y_ev"] = round(float(np.mean(r[l3])) * 100, 1)
        # bankroll: fractional sizing and whole-contract sizing at $170 / $1k / $5k
        bk = {}
        for st in (170, 1000, 5000):
            for f in (0.15, 0.25):
                key = f"${st}@{int(f*100)}%"
                bk[key] = bankroll(r, pf, per_year, st, f, pnow, c0, whole=True, n=5000) | dict(
                    frac_median=bankroll(r, pf, per_year, st, f, pnow, c0, whole=False, n=5000)["median"])
        rec["bankroll"] = bk
        rows.append(rec)
        print(f"{name[:70]:70s} n={rec['n']:5d} /yr={rec['per_year']:6.1f} und={rec['underlying_mean_pct']:+.3f}% k={k_fair:.2f} "
              f"EVbrief={rec['ev_brief']:+.1f}% EVfair={rec['ev_base']:+.1f}% EVrich={rec['ev_rich']:+.1f}% wk={rec.get('ev_weekly_fair_c8')} "
              f"(t {rec['t_ev']:+.1f}) PoP={rec['pop']}% range[{rec['ev_min']:+.1f},{rec['ev_max']:+.1f}] 3y={rec['last3y_ev']} "
              f"cost=${rec['contract_cost']:.0f} | $170@25% med {bk['$170@25%']['median']} | $5k@25% med {bk['$5000@25%']['median']} "
              f"P(grow) {bk['$5000@25%']['p_grow']}", flush=True)
    out["options"] = rows
    save("options", out)


def all():
    tests(); options()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    globals()[cmd]()
