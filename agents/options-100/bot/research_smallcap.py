#!/usr/bin/env python3
"""Research: do simple option-buying edges survive in $1B-$5B small caps (owner's "less crowded" thesis)?

  python3 agents/options-100/bot/research_smallcap.py holdings   # parse ETF holdings (SPDR SPSM/MDY live, iShares IWM/IJR via Wayback)
  python3 agents/options-100/bot/research_smallcap.py caps       # yfinance fast_info market cap -> $1-5B candidates
  python3 agents/options-100/bot/research_smallcap.py chains     # live option chains: ATM OI, volume, spread, IV, contract cost
  python3 agents/options-100/bot/research_smallcap.py prices     # daily bars (max history) for liquid names + survivorship cohorts
  python3 agents/options-100/bot/research_smallcap.py earnings   # yfinance earnings dates (Yahoo serves ~2020+ only)
  python3 agents/options-100/bot/research_smallcap.py run        # all strategies, IS 2012-2019 / OOS 2020+, BH, quiet vs crowded, bankroll
  python3 agents/options-100/bot/research_smallcap.py bank       # bankroll for IS-selected T1/T2 cells at $170/$1k/$5k
  python3 agents/options-100/bot/research_smallcap.py all

Downloads live in data/research_smallcap_raw/ (untrusted, parsed only). Caches: data/research_smallcap_cache.pkl,
results: data/research_smallcap_results.json. data/ is gitignored.
"""
import socket as _sk
_gai = _sk.getaddrinfo
_sk.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, _sk.AF_INET, *a, **k)   # IPv6 times out on this machine
import sys, json, math, pickle, time, sqlite3, csv, io, warnings, datetime as dt
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "research_smallcap_raw"
CACHE = ROOT / "data" / "research_smallcap_cache.pkl"
OUT = ROOT / "data" / "research_smallcap_results.json"
DB = ROOT / "data" / "market.db"
IS0, IS1 = pd.Timestamp("2012-01-01"), pd.Timestamp("2019-12-31")
OOS0 = pd.Timestamp("2020-01-01")
END = pd.Timestamp("2026-10-13")          # last complete session
CAP_LO, CAP_HI = 1e9, 5e9
SKEW = 3.0
ACCOUNT = 170.0


# ---------------------------------------------------------------- cache helpers
def load():
    if CACHE.exists():
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    return {}


def store(c):
    tmp = CACHE.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(c, f)
    tmp.replace(CACHE)


def yf():
    import yfinance
    return yfinance


# ---------------------------------------------------------------- 1. holdings
def _ishares_csv(path):
    txt = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    hdr = next(i for i, l in enumerate(txt) if l.startswith("Ticker,"))
    asof = next((l for l in txt[:hdr] if "Holdings as of" in l), "")
    rows = list(csv.DictReader(io.StringIO("\n".join(txt[hdr:]))))
    out = [(r.get("Ticker") or "").strip() for r in rows if (r.get("Asset Class") or "").strip() == "Equity" and r.get("Ticker")]
    return out, asof


def _spdr_xlsx(path):
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    hdr = next(i for i, r in enumerate(rows) if r and r[0] == "Name" and r[1] == "Ticker")
    asof = rows[2][1] if len(rows) > 2 else ""
    out = [str(r[1]).strip() for r in rows[hdr + 1:] if r and r[1] and str(r[1]).strip() and not str(r[1]).startswith("CASH")
           and str(r[1]).strip() != "-"]
    return out, asof


def _clean(t):
    t = t.replace(".", "-").replace("/", "-").strip().upper()
    return t if t and t.replace("-", "").isalnum() and len(t) <= 6 else None


def holdings():
    c = load()
    src = {}
    for name, fn, parser in [("SPSM_live(S&P600)", "spsm.xlsx", _spdr_xlsx), ("MDY_live(S&P400)", "mdy.xlsx", _spdr_xlsx),
                             ("IWM_wayback(R2000)", "iwm_2025.csv", _ishares_csv),
                             ("IWM_2018_wayback", "iwm_2018.csv", _ishares_csv), ("IJR_2021_wayback", "ijr_2021.csv", _ishares_csv)]:
        p = RAW / fn
        if not p.exists():
            print("missing", p); continue
        tk, asof = parser(p)
        tk = sorted({x for x in map(_clean, tk) if x})
        src[name] = dict(asof=str(asof), tickers=tk)
        print(f"{name:22s} {asof!s:30s} {len(tk)} equities")
    cur = sorted(set().union(*[set(v["tickers"]) for k, v in src.items() if "2018" not in k and "2021" not in k]))
    old = sorted(set(src.get("IWM_2018_wayback", {}).get("tickers", [])) | set(src.get("IJR_2021_wayback", {}).get("tickers", [])))
    gone = sorted(set(old) - set(cur))
    print(f"current union {len(cur)}; historical cohort names no longer in any current list: {len(gone)}")
    c["holdings"] = dict(src=src, current=cur, gone=gone)
    store(c)


# ---------------------------------------------------------------- 2. market caps
def _cap(t):
    for k in range(3):
        try:
            fi = yf().Ticker(t).fast_info
            mc, px = fi["marketCap"], fi["lastPrice"]
            try:
                v10 = fi["tenDayAverageVolume"]
            except Exception:
                v10 = None
            time.sleep(0.15)
            return t, dict(mcap=float(mc) if mc else None, price=float(px) if px else None, vol10=float(v10) if v10 else None)
        except Exception as e:
            err = str(e)[:80]
            time.sleep(1.0 + 2 * k)
    return t, dict(mcap=None, price=None, vol10=None, err=err)


def caps():
    c = load()
    have = c.setdefault("caps", {})
    todo = [t for t in c["holdings"]["current"] if t not in have or have[t].get("mcap") is None and "err" not in have[t]]
    print("caps to fetch", len(todo))
    with ThreadPoolExecutor(6) as ex:
        for i, (t, r) in enumerate(ex.map(_cap, todo)):
            have[t] = r
            if i % 200 == 199:
                store(c); print(i + 1, "done")
    store(c)
    cand = [t for t, r in have.items() if r.get("mcap") and CAP_LO <= r["mcap"] <= CAP_HI]
    print(f"{sum(1 for r in have.values() if r.get('mcap'))} with cap; {len(cand)} in $1-5B")


# ---------------------------------------------------------------- 3. option chains
def _session_frac():
    now = pd.Timestamp.now(tz="America/New_York")
    o = now.normalize() + pd.Timedelta(hours=9, minutes=30)
    f = (now - o) / pd.Timedelta(hours=6.5)
    return float(min(max(f, 0.15), 1.0))


def _chain(t):
    out = dict(t=t, ts=pd.Timestamp.now(tz="America/New_York").isoformat())
    try:
        tk = yf().Ticker(t)
        exps = list(tk.options)
        time.sleep(0.25)
        if not exps:
            out["err"] = "no options"; return out
        today = pd.Timestamp.now(tz="America/New_York").normalize().tz_localize(None)
        days = [(pd.Timestamp(e) - today).days for e in exps]
        cands = [(abs(d - 30), e, d) for e, d in zip(exps, days) if 14 <= d <= 40]
        if not cands:
            cands = [(abs(d - 30), e, d) for e, d in zip(exps, days) if d >= 7]
        _, tgt, tdays = min(cands)
        spot = yf().Ticker(t).fast_info["lastPrice"]
        ch = tk.option_chain(tgt)
        time.sleep(0.25)
        calls, puts = ch.calls, ch.puts
        k = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]]["strike"].iloc[0]
        cr = calls[calls.strike == k].iloc[0]
        pr = puts[puts.strike == k]
        pr = pr.iloc[0] if len(pr) else None
        def sp(r):
            if r is None: return None
            b, a = float(r["bid"] or 0), float(r["ask"] or 0)
            if a <= 0 or b <= 0: return None
            return (a - b) / ((a + b) / 2)
        vol_t = float(calls["volume"].fillna(0).sum() + puts["volume"].fillna(0).sum())
        vol_n = 0.0
        near = exps[0]
        if near != tgt:
            try:
                ch2 = tk.option_chain(near); time.sleep(0.25)
                vol_n = float(ch2.calls["volume"].fillna(0).sum() + ch2.puts["volume"].fillna(0).sum())
            except Exception:
                pass
        out.update(spot=float(spot), exp=tgt, dte=int(tdays), strike=float(k), n_exp=len(exps),
                   weeklies=sum(1 for d in days if d <= 45) >= 4,
                   call_bid=float(cr["bid"] or 0), call_ask=float(cr["ask"] or 0),
                   put_bid=float(pr["bid"] or 0) if pr is not None else None, put_ask=float(pr["ask"] or 0) if pr is not None else None,
                   spread_call=sp(cr), spread_put=sp(pr),
                   atm_oi=float((cr["openInterest"] or 0) + ((pr["openInterest"] or 0) if pr is not None else 0)),
                   oi_tgt=float(calls["openInterest"].fillna(0).sum() + puts["openInterest"].fillna(0).sum()),
                   vol_tgt=vol_t, vol_near=vol_n,
                   iv_call=float(cr["impliedVolatility"] or 0), iv_put=float(pr["impliedVolatility"] or 0) if pr is not None else None)
    except Exception as e:
        out["err"] = str(e)[:100]
    return out


def chains():
    c = load()
    caps_ = c["caps"]
    cand = sorted(t for t, r in caps_.items() if r.get("mcap") and CAP_LO <= r["mcap"] <= CAP_HI)
    have = c.setdefault("chains", {})
    todo = [t for t in cand if t not in have]
    print("chains to fetch", len(todo), "session frac", round(_session_frac(), 2))
    with ThreadPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(_chain, todo)):
            r["frac"] = _session_frac()
            have[r["t"]] = r
            if i % 100 == 99:
                store(c); print(i + 1, "done")
    store(c)
    summarize_chains(c)


def chain_table(c):
    rows = []
    for t, r in c["chains"].items():
        if "err" in r or "spot" not in r: continue
        cap = c["caps"][t]
        sps = [x for x in (r["spread_call"], r["spread_put"]) if x is not None]
        spread = float(np.mean(sps)) if sps else np.nan
        dvol = (r["vol_tgt"] + r["vol_near"]) / r.get("frac", 1.0)
        ivs = [x for x in (r["iv_call"], r["iv_put"]) if x and x > 0.01]
        cost = r["call_ask"] * 100 if r["call_ask"] else np.nan
        # normalise cost to a 21-day tenor (sqrt-time) so names whose chosen expiry is 37d are comparable
        cost21 = cost * math.sqrt(21 / max(r["dte"], 7)) if cost == cost else np.nan
        rows.append(dict(t=t, mcap=cap["mcap"], price=r["spot"], dvol_stock=(cap.get("vol10") or 0) * r["spot"],
                         exp=r["exp"], dte=r["dte"], atm_oi=r["atm_oi"], opt_vol=dvol, spread=spread,
                         iv=float(np.mean(ivs)) if ivs else np.nan, cost=cost, cost21=cost21, weeklies=r["weeklies"]))
    d = pd.DataFrame(rows).set_index("t")
    d["liquid"] = (d.atm_oi >= 500) & (d.opt_vol >= 200) & (d.spread <= 0.10)
    d["liquid_loose"] = (d.atm_oi >= 250) & (d.opt_vol >= 100) & (d.spread <= 0.20)
    # research tier: real option activity but any spread up to 50% (option EV is charged the measured spread)
    d["research"] = ((d.atm_oi >= 250) | (d.opt_vol >= 200)) & (d.spread <= 0.50)
    d["tier"] = np.where(d.liquid, "T1 strict", np.where(d.liquid_loose, "T2 loose", np.where(d.research, "T3 wide", "none")))
    # crowding: daily option notional turnover and stock turnover relative to market cap
    d["opt_turn"] = d.opt_vol * 100 * d.price / d.mcap
    d["stk_turn"] = d.dvol_stock / d.mcap
    return d


def summarize_chains(c):
    d = chain_table(c)
    print(f"chains ok {len(d)}; liquid (OI>=500, vol>=200, spread<=10%): {int(d.liquid.sum())}; loose: {int(d.liquid_loose.sum())}")
    L = d[d.liquid]
    print(L[["mcap", "price", "atm_oi", "opt_vol", "spread", "iv", "cost"]].describe().round(3).to_string())


# ---------------------------------------------------------------- 4. prices
def _dl(tks):
    for k in range(3):
        try:
            df = yf().download(tks, period="max", interval="1d", auto_adjust=True, group_by="ticker", progress=False, threads=False)
            return df
        except Exception as e:
            time.sleep(3 + 5 * k)
    return None


def universe(c):
    d = chain_table(c)
    return sorted(d[d.research | d.liquid | d.liquid_loose].index)


def prices():
    c = load()
    px = c.setdefault("px", {})
    liq = universe(c)
    d = chain_table(c)
    loose = sorted(set(d[d.liquid_loose].index) - set(liq))
    gone = c["holdings"]["gone"]
    extra = ["IWM", "IJR", "SPY", "VB", "IJH", "SPSM", "MDY"]
    want = [t for t in liq + loose + extra + gone if t not in px]
    print("price series to fetch", len(want), f"(liquid {len(liq)}, loose {len(loose)}, survivorship cohort {len(gone)})")
    B = 40
    for i in range(0, len(want), B):
        tks = want[i:i + B]
        df = _dl(tks)
        for t in tks:
            try:
                s = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                s = s.dropna(subset=["Close"])
                px[t] = s[["Open", "High", "Low", "Close", "Volume"]].astype(float) if len(s) else None
            except Exception:
                px[t] = None
        time.sleep(1.0)
        if (i // B) % 5 == 4:
            store(c); print(i + B, "fetched")
    store(c)
    print("have", sum(1 for v in px.values() if v is not None), "/", len(px))


def cohort():
    """Survivorship: fetch every ticker of the 2018 IWM and 2021 IJR snapshots (yfinance drops most delisted names)."""
    c = load(); px = c["px"]
    src = c["holdings"]["src"]
    want = sorted((set(src["IWM_2018_wayback"]["tickers"]) | set(src["IJR_2021_wayback"]["tickers"])) - set(px))
    print("cohort tickers to fetch", len(want))
    B = 50
    for i in range(0, len(want), B):
        tks = want[i:i + B]
        df = _dl(tks)
        for t in tks:
            try:
                s_ = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                s_ = s_.dropna(subset=["Close"])
                px[t] = s_[["Open", "High", "Low", "Close", "Volume"]].astype(float) if len(s_) else None
            except Exception:
                px[t] = None
        time.sleep(1.0)
    store(c)


# ---------------------------------------------------------------- 5. earnings dates
def _earn(t):
    for k in range(2):
        try:
            e = yf().Ticker(t).get_earnings_dates(limit=60)
            time.sleep(0.3)
            return t, e
        except Exception:
            time.sleep(2)
    return t, None


def earnings():
    c = load()
    ed = c.setdefault("earn", {})
    d = chain_table(c)
    tk = [t for t in universe(c) if t not in ed]
    print("earnings to fetch", len(tk))
    with ThreadPoolExecutor(4) as ex:
        for i, (t, e) in enumerate(ex.map(_earn, tk)):
            ed[t] = e
            if i % 100 == 99:
                store(c); print(i + 1)
    store(c)


# ---------------------------------------------------------------- math
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


def opt_ret(S0, S1, v0, v1, T0, dtt, call, spread):
    """Long ATM option bought at ask (mid*(1+s/2)), sold at bid (mid*(1-s/2)) after dtt yrs. Sticky-moneyness skew."""
    K = S0
    sk = lambda v, S_: v * np.clip(1 - SKEW * np.log(K / S_), 0.5, 2.0)
    p0 = bs(S0, K, T0, v0, call)
    p1 = bs(S1, K, np.maximum(T0 - dtt, 0), sk(v1, S1), call)
    return (p1 * (1 - spread / 2)) / (p0 * (1 + spread / 2)) - 1


def mean_t(r, L=1):
    r = np.asarray(r, float)
    if len(r) < 4: return float("nan")
    u = r - r.mean(); S = u @ u
    for l in range(1, L + 1):
        S += 2 * (1 - l / (L + 1)) * (u[l:] @ u[:-l])
    return float(r.mean() / math.sqrt(S / len(r) ** 2)) if S > 0 else float("nan")


def week_t(s):
    """t-stat of the trade mean with standard errors clustered by entry week (dip signals cluster on market selloffs)."""
    s = s.dropna()
    if len(s) < 6: return float("nan")
    u = s - s.mean()
    g = u.groupby(s.index.to_period("W")).sum()
    if len(g) < 3: return float("nan")
    se = math.sqrt((g ** 2).sum() * len(g) / (len(g) - 1)) / len(s)
    return float(s.mean() / se) if se > 0 else float("nan")


def pval(t):
    return math.erfc(abs(t) / math.sqrt(2)) if t == t else 1.0


def bh(ps, q=0.05):
    ps = np.asarray(ps, float); n = len(ps)
    o = np.argsort(ps); passed = np.zeros(n, bool)
    th = q * np.arange(1, n + 1) / n
    ok = np.where(ps[o] <= th)[0]
    if len(ok): passed[o[:ok.max() + 1]] = True
    return passed


def rsi(close, n):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


# ---------------------------------------------------------------- panel
def market():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)
    out = {}
    for s in ("SPY", "IWM", "^VIX"):
        d = pd.read_sql("SELECT ts, close, adj_close FROM bars WHERE symbol=? AND interval='1d' ORDER BY ts", con, params=(s,),
                        parse_dates=["ts"]).set_index("ts")
        d = d[~d.index.duplicated(keep="last")]
        d.index = d.index.normalize()
        out[s] = d["adj_close"].fillna(d["close"])
    con.close()
    m = pd.DataFrame(out).loc[:END].dropna(subset=["SPY"])
    m["spy200"] = m.SPY > m.SPY.rolling(200).mean()
    m.rename(columns={"^VIX": "VIX"}, inplace=True)
    # market implied/realized ratio (universe.md lesson: it rises on dip days, 1.35 vs 1.18 for SPY)
    rvs = np.log(m.SPY).diff().rolling(20).std() * math.sqrt(252)
    mr = (0.9 * m.VIX / 100 / rvs).clip(0.8, 2.5)
    m["mr"] = mr / mr.loc["2012":].median()
    return m


def prep(df, m):
    d = df.loc[:END].copy()
    d.index = pd.DatetimeIndex(d.index).tz_localize(None).normalize()
    d = d[~d.index.duplicated(keep="last")]
    d = d[d.Close > 0]
    c = d.Close
    r = np.log(c).diff()
    d["r"] = c.pct_change()
    d["rv20"] = r.rolling(20).std() * math.sqrt(252)
    d["rv60"] = r.rolling(60).std() * math.sqrt(252)
    d["rsi2"] = rsi(c, 2)
    dn = (d.r < 0).astype(int)
    d["streak"] = dn.groupby((dn != dn.shift()).cumsum()).cumsum() * dn
    tr = pd.concat([d.High - d.Low, (d.High - c.shift()).abs(), (d.Low - c.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(14).mean()
    d["drop_atr"] = (c.shift() - c) / d.atr.shift()
    d["drop3_atr"] = (c.shift(3) - c) / d.atr.shift(3)
    ma, sd = c.rolling(20).mean(), c.rolling(20).std()
    d["bbl"] = c < ma - 2 * sd
    d["hi252"] = c.rolling(252).max()
    d["at52"] = (c >= d.hi252) & (d.index.to_series().diff().notna())
    d["fresh52"] = d.at52 & ~(d.at52.shift(1).rolling(20).max().fillna(0).astype(bool))
    d["vavg50"] = d.Volume.rolling(50).mean().shift()
    d["vshock"] = (d.Volume > 3 * d.vavg50) & (d.r > 0.04)
    mm = m.reindex(d.index).ffill()
    d["spy_r"] = mm.SPY.pct_change(); d["iwm_r"] = mm.IWM.pct_change()
    d["spy200"] = mm.spy200; d["vix"] = mm.VIX
    d["IWM"] = mm.IWM; d["SPYc"] = mm.SPY; d["mr"] = mm.mr.fillna(1.0)
    # residual vs SPY (rolling beta 120d) for lead-lag / catch-up
    cov = d.r.rolling(120).cov(d.spy_r); var = d.spy_r.rolling(120).var()
    d["beta"] = (cov / var).shift()
    d["resid"] = d.r - d.beta * d.spy_r
    d["resid_sd"] = d.resid.rolling(60).std().shift()
    return d


# ---------------------------------------------------------------- strategy engine
STRATS = {
    # name: (side, tenor_days, hold_sessions, description)
    "dip_rsi2":     (1, 21, 5, "RSI(2)<10 -> 21d ATM call, hold 5"),
    "dip_3down":    (1, 21, 5, "3+ down closes -> 21d ATM call, hold 5"),
    "dip_atr2":     (1, 21, 5, "1-day drop > 2xATR(14) -> 21d ATM call, hold 5"),
    "dip_atr3x3":   (1, 21, 5, "3-day drop > 3xATR -> 21d ATM call, hold 5"),
    "dip_bb":       (1, 21, 5, "close < lower Bollinger(20,2) -> 21d ATM call, hold 5"),
    "dip_rsi2_bb":  (1, 21, 5, "RSI2<10 AND below lower BB -> 21d call, hold 5"),
    "dip_rsi2_h10": (1, 30, 10, "RSI2<10 -> 30d ATM call, hold 10"),
    "dip_rsi2_up":  (1, 21, 5, "RSI2<10 and SPY>200dMA -> 21d call, hold 5"),
    "dip_rsi2_dn":  (1, 21, 5, "RSI2<10 and SPY<200dMA -> 21d call, hold 5"),
    "dip_rsi2_vix": (1, 21, 5, "RSI2<10 and VIX>20 -> 21d call, hold 5"),
    "brk_52w":      (1, 30, 10, "fresh 52-week-high close -> 30d call, hold 10"),
    "brk_vol":      (1, 30, 10, "volume>3x 50d avg and +4% day -> 30d call, hold 10"),
    "brk_vol_put":  (-1, 30, 10, "volume>3x and +4% day -> 30d PUT (fade), hold 10"),
    "catchup":      (1, 21, 3, "SPY>+1.5% day, stock lagged (resid<-1.5sd) -> 21d call, hold 3"),
    "catchup_h5":   (1, 21, 5, "same, hold 5"),
    "ob_put":       (-1, 21, 5, "RSI(2)>95 -> 21d ATM PUT, hold 5"),
}


def signal(d, name):
    if name in ("dip_rsi2", "dip_rsi2_h10"): return d.rsi2 < 10
    if name == "dip_3down": return d.streak >= 3
    if name == "dip_atr2": return d.drop_atr > 2
    if name == "dip_atr3x3": return d.drop3_atr > 3
    if name == "dip_bb": return d.bbl
    if name == "dip_rsi2_bb": return (d.rsi2 < 10) & d.bbl
    if name == "dip_rsi2_up": return (d.rsi2 < 10) & (d.spy200 == True)
    if name == "dip_rsi2_dn": return (d.rsi2 < 10) & (d.spy200 == False)
    if name == "dip_rsi2_vix": return (d.rsi2 < 10) & (d.vix > 20)
    if name == "brk_52w": return d.fresh52 & (d.index >= d.index[0] + pd.Timedelta(days=400))
    if name in ("brk_vol", "brk_vol_put"): return d.vshock
    if name in ("catchup", "catchup_h5"): return (d.spy_r > 0.015) & (d.resid < -1.5 * d.resid_sd)
    if name == "ob_put": return d.rsi2 > 95
    raise KeyError(name)


DIP_BUMP = {"none": 1.0}


def trades(d, entries_mask, side, tenor, hold, ivr, spread, nonoverlap=True, ivmode="ratio", k=1.2, bump=1.0):
    """Entries at close t (mask), exit close t+hold. Returns DataFrame indexed by entry date."""
    idx = np.where(entries_mask.fillna(False).values)[0]
    n = len(d)
    keep, last = [], -10 ** 9
    for i in idx:
        if i + hold >= n or i < 60: continue
        if nonoverlap and i < last + hold: continue
        keep.append(i); last = i
    if not keep:
        return pd.DataFrame(columns=["ret", "und", "und_x"], index=pd.DatetimeIndex([]), dtype=float)
    ix = np.array(keep)
    C = d.Close.values; rv = d.rv20.values; iw = d.IWM.values; mr = d.mr.values
    S0, S1 = C[ix], C[ix + hold]
    if ivmode == "ratio":
        # dynamic: ticker's current IV/RV ratio x market implied/realized regime at that date (dip days priced richer)
        v0 = np.clip(rv[ix] * ivr * mr[ix] * bump, 0.15, 3.0); v1 = np.clip(rv[ix + hold] * ivr * mr[ix + hold], 0.15, 3.0)
    else:
        v0 = np.clip(rv[ix] * k * bump, 0.15, 3.0); v1 = np.clip(rv[ix + hold] * k, 0.15, 3.0)
    dtt = (d.index[ix + hold] - d.index[ix]).days.values / 365
    r = opt_ret(S0, S1, v0, v1, tenor / 365, dtt, side > 0, spread)
    und = S1 / S0 - 1
    ux = und - (iw[ix + hold] / iw[ix] - 1)
    return pd.DataFrame(dict(ret=r, und=und * side, und_x=ux * side), index=d.index[ix]).replace([np.inf, -np.inf], np.nan).dropna()


def period(df, a, b):
    return df[(df.index >= a) & (df.index <= b)]


def stats(s):
    s = s.dropna()
    return dict(n=int(len(s)), ev=float(s.mean()) if len(s) else None, pop=float((s > 0).mean()) if len(s) else None,
                t=week_t(s) if len(s) > 5 else None)


# ---------------------------------------------------------------- run
def run():
    c = load()
    m = market()
    ct = chain_table(c)
    liq = [t for t in universe(c) if c["px"].get(t) is not None]
    print(f"liquid universe with prices: {len(liq)}")
    R = dict(meta=dict(n_liquid=len(liq), session_frac=None))
    # ivr per ticker: current ATM IV / current RV20
    P = {}
    for t in liq:
        d = prep(c["px"][t], m)
        if len(d) < 300: continue
        P[t] = d
    rv_now = {t: float(P[t].rv20.iloc[-1]) for t in P}
    mr_now = float(m.mr.iloc[-1])
    # ticker IV premium = today's ATM IV / (RV20 today x today's market regime factor); historical IV = RV20_t x ivr x regime_t
    ivr = {t: float(np.clip(ct.loc[t, "iv"] / (rv_now[t] * mr_now), 0.7, 2.5)) if rv_now[t] > 0 and ct.loc[t, "iv"] == ct.loc[t, "iv"] else 1.2
           for t in P}
    R["meta"]["mr_now"] = mr_now
    spread = {t: float(min(ct.loc[t, "spread"], 0.5)) for t in P}
    # crowded vs quiet
    sc = ct.loc[list(P)][["opt_turn", "stk_turn"]].rank(pct=True).mean(axis=1)
    crowd = pd.Series(np.where(sc >= sc.quantile(2 / 3), "crowded", np.where(sc <= sc.quantile(1 / 3), "quiet", "mid")), index=sc.index)
    R["crowd"] = crowd.to_dict()
    R["ivr"] = ivr; R["spread"] = spread
    print("ivr median", np.median(list(ivr.values())), "spread median", np.median(list(spread.values())))

    # ---- per-strategy, per-ticker trades + unconditional baselines
    rows, T, BASE = [], {}, {}
    for s, (side, ten, hold, desc) in STRATS.items():
        for t, d in P.items():
            tr = trades(d, signal(d, s), side, ten, hold, ivr[t], spread[t])
            # excess vs unconditional same-structure return over the same period (IS or OOS)
            bkey = (side, ten, hold, t)
            if bkey not in BASE:
                base = trades(d, pd.Series(True, index=d.index), side, ten, hold, ivr[t], spread[t], nonoverlap=False)
                BASE[bkey] = [(a, b, period(base, a, b).ret.mean(), period(base, a, b).und.mean()) for a, b in ((IS0, IS1), (OOS0, END))]
            bv = np.full(len(tr), np.nan); bu = np.full(len(tr), np.nan)
            for a, b, mu, muu in BASE[bkey]:
                inp = (tr.index >= a) & (tr.index <= b)
                bv = np.where(inp, mu, bv); bu = np.where(inp, muu, bu)
            tr = tr.assign(base=bv, und_xu=tr.und - bu)
            tr["x"] = tr.ret - tr.base
            T[(s, t)] = tr
    c_T = T
    # pooled strategy table
    strat_rows = []
    for s in STRATS:
        allt = pd.concat([T[(s, t)].assign(t=t) for t in P if len(T[(s, t)])])
        for lab, a, b in (("IS", IS0, IS1), ("OOS", OOS0, END)):
            q = period(allt, a, b)
            row = dict(strat=s, per=lab, **{f"{k}": v for k, v in stats(q.ret).items()},
                       x_ev=float(q.x.mean()), x_t=week_t(q.x), und_x=float(q.und_x.mean()), und_x_t=week_t(q.und_x),
                       und_xu=float(q.und_xu.mean()), und_xu_t=week_t(q.und_xu),
                       tpy=len(q) / max((min(b, END) - a).days / 365.25, 0.1))
            for g in ("quiet", "crowded"):
                qq = q[q.t.map(crowd) == g]
                row[f"{g}_ev"] = float(qq.ret.mean()) if len(qq) else None
                row[f"{g}_x"] = float(qq.x.mean()) if len(qq) else None
                row[f"{g}_xt"] = week_t(qq.x) if len(qq) > 5 else None
                row[f"{g}_n"] = int(len(qq))
                row[f"{g}_uxu"] = float(qq.und_xu.mean()) if len(qq) else None
                row[f"{g}_uxu_t"] = week_t(qq.und_xu) if len(qq) > 5 else None
                row[f"{g}_ev"] = float(qq.ret.mean()) if len(qq) else None
            for tier in ("T1 strict", "T2 loose", "T3 wide"):
                qq = q[q.t.map(ct.tier) == tier]
                row[f"{tier[:2]}_ev"] = float(qq.ret.mean()) if len(qq) else None
                row[f"{tier[:2]}_n"] = int(len(qq))
            strat_rows.append(row)
    S = pd.DataFrame(strat_rows)
    oos = S[S.per == "OOS"].copy()
    oos["p"] = oos.x_t.map(pval)
    oos["bh05"] = bh(oos.p.values, 0.05); oos["bh10"] = bh(oos.p.values, 0.10)
    R["strategies"] = S.to_dict("records"); R["strat_oos_bh"] = oos[["strat", "p", "bh05", "bh10"]].to_dict("records")
    pd.set_option("display.width", 250)
    print("\n== pooled strategies (ret = option return on premium net of measured spread; x = minus same-ticker unconditional; und_x = underlying vs IWM)")
    print(S[["strat", "per", "n", "ev", "pop", "t", "x_ev", "x_t", "und_x", "und_xu", "und_xu_t", "tpy"]].round(4).to_string())
    print("quiet vs crowded / tiers")
    print(S[["strat", "per", "quiet_n", "quiet_ev", "quiet_x", "quiet_xt", "quiet_uxu", "quiet_uxu_t", "crowded_n", "crowded_ev", "crowded_x",
             "crowded_xt", "crowded_uxu", "crowded_uxu_t", "T1_ev", "T1_n", "T2_ev", "T2_n", "T3_ev"]].round(4).to_string())
    grp = ct.loc[list(P)].assign(crowd=crowd)
    R["crowd_liquidity"] = grp.groupby("crowd")[["mcap", "price", "spread", "atm_oi", "opt_vol", "iv", "cost21"]].median().to_dict("index")
    R["tier_liquidity"] = grp.groupby("tier")[["mcap", "price", "spread", "atm_oi", "opt_vol", "iv", "cost21"]].median().to_dict("index")
    R["tier_counts"] = grp.tier.value_counts().to_dict()
    print(pd.DataFrame(R["crowd_liquidity"]).T.round(3).to_string()); print(pd.DataFrame(R["tier_liquidity"]).T.round(3).to_string())
    print(oos[["strat", "p", "bh05", "bh10"]].to_string())

    # ---- ticker selection: rank (strategy, ticker) on IS excess, test top picks OOS
    sel_rows, cells = [], []
    for (s, t), tr in T.items():
        a = period(tr, IS0, IS1); b = period(tr, OOS0, END)
        if len(a) < 8: continue
        cells.append(dict(strat=s, t=t, n_is=len(a), x_is=float(a.x.mean()), t_is=mean_t(a.x.values),
                          n_oos=len(b), x_oos=float(b.x.mean()) if len(b) else np.nan, ev_oos=float(b.ret.mean()) if len(b) else np.nan,
                          t_oos=mean_t(b.x.values) if len(b) > 3 else np.nan, und_x_oos=float(b.und_x.mean()) if len(b) else np.nan,
                          crowd=crowd.get(t)))
    Cdf = pd.DataFrame(cells)
    sel = []
    for s, g in Cdf.groupby("strat"):
        g = g.dropna(subset=["x_oos"])
        top = g[(g.t_is >= 1.5)]
        rest = g[(g.t_is < 1.5)]
        rho = g[["x_is", "x_oos"]].corr(method="spearman").iloc[0, 1] if len(g) > 10 else np.nan
        sel.append(dict(strat=s, n_cells=len(g), n_top=len(top), top_x_oos=float(top.x_oos.mean()) if len(top) else None,
                        top_ev_oos=float(top.ev_oos.mean()) if len(top) else None,
                        rest_x_oos=float(rest.x_oos.mean()) if len(rest) else None, rank_corr=float(rho)))
    SEL = pd.DataFrame(sel)
    print("\n== IS-selected tickers (IS excess t>=1.5) vs the rest, OOS excess")
    print(SEL.round(3).to_string())
    # ticker-level OOS BH among the IS-selected cells
    top_cells = Cdf[(Cdf.t_is >= 1.5) & (Cdf.n_oos >= 5)].copy()
    top_cells["p"] = top_cells.t_oos.map(lambda x: pval(x) if x == x else 1.0)
    top_cells["bh10"] = bh(top_cells.p.values, 0.10) if len(top_cells) else []
    R["selection"] = SEL.to_dict("records")
    R["top_cells"] = top_cells.sort_values("p").head(60).to_dict("records")
    print("top IS-selected cells by OOS p (BH q=0.10 passes:", int(top_cells.bh10.sum()) if len(top_cells) else 0, ")")
    print(top_cells.sort_values("p").head(20).round(3).to_string())

    # ---- (d) character: variance ratio / autocorrelation persistence, and does it predict dip-buy edge?
    ch_rows = []
    for t, d in P.items():
        def vr_ac(x):
            r1 = x.r.dropna()
            if len(r1) < 250: return np.nan, np.nan
            r5 = np.log(x.Close).diff(5).dropna()
            return float(r5.var() / (5 * np.log(x.Close).diff().var())), float(r1.autocorr(1))
        a = vr_ac(period(d, IS0, IS1)); b = vr_ac(period(d, OOS0, END))
        dr = T[("dip_rsi2", t)]
        ch_rows.append(dict(t=t, vr_is=a[0], ac_is=a[1], vr_oos=b[0], ac_oos=b[1],
                            dip_x_oos=float(period(dr, OOS0, END).x.mean()) if len(period(dr, OOS0, END)) else np.nan,
                            mom_x_oos=float(period(T[("brk_52w", t)], OOS0, END).x.mean()) if len(period(T[("brk_52w", t)], OOS0, END)) else np.nan))
    CH = pd.DataFrame(ch_rows).set_index("t")
    chres = dict(vr_persist=float(CH[["vr_is", "vr_oos"]].corr(method="spearman").iloc[0, 1]),
                 ac_persist=float(CH[["ac_is", "ac_oos"]].corr(method="spearman").iloc[0, 1]),
                 vr_is_median=float(CH.vr_is.median()), vr_oos_median=float(CH.vr_oos.median()),
                 share_vr_lt1_is=float((CH.vr_is < 1).mean()), share_vr_lt1_oos=float((CH.vr_oos < 1).mean()))
    CH["vr_t"] = pd.qcut(CH.vr_is, 3, labels=["meanrev", "mid", "trendy"])
    chres["dip_x_oos_by_IS_VR"] = CH.groupby("vr_t").dip_x_oos.mean().to_dict()
    chres["brk_x_oos_by_IS_VR"] = CH.groupby("vr_t").mom_x_oos.mean().to_dict()
    R["character"] = {k: (v if not isinstance(v, dict) else {str(a): b for a, b in v.items()}) for k, v in chres.items()}
    print("\n== character", json.dumps(R["character"], default=float, indent=1))

    # ---- (f) lead-lag: equal-weight small-cap portfolio vs SPY
    ew = pd.DataFrame({t: P[t].r for t in P}).loc["2010":]
    ewr = ew.mean(axis=1, skipna=True)
    L = pd.DataFrame(dict(ew=ewr, spy=m.SPY.pct_change().reindex(ewr.index), iwm=m.IWM.pct_change().reindex(ewr.index))).dropna()
    ll = {}
    for lab, a, b in (("IS", IS0, IS1), ("OOS", OOS0, END)):
        q = L.loc[a:b]
        y = q.ew.shift(-1) - q.spy.shift(-1)
        X = np.column_stack([np.ones(len(q)), q.spy, q.ew - q.spy])
        ok = ~np.isnan(y.values)
        beta, *_ = np.linalg.lstsq(X[ok], y.values[ok], rcond=None)
        res = y.values[ok] - X[ok] @ beta
        cov = np.linalg.inv(X[ok].T @ X[ok]) * (res @ res) / (ok.sum() - 3)
        big = q[q.spy > 0.015]
        nxt = (L.ew.shift(-1) - L.spy.shift(-1)).reindex(big.index)
        nxt3 = sum((L.ew.shift(-k) - L.spy.shift(-k)) for k in (1, 2, 3)).reindex(big.index)
        lag = big[big.ew - big.spy < -0.005]
        ll[lab] = dict(b_spy=float(beta[1]), t_spy=float(beta[1] / math.sqrt(cov[1, 1])), b_gap=float(beta[2]),
                       t_gap=float(beta[2] / math.sqrt(cov[2, 2])),
                       n_bigup=int(len(big)), next1_ew_minus_spy=float(nxt.mean()), next3=float(nxt3.mean()),
                       t_next3=mean_t(nxt3.dropna().values, 3),
                       n_lagged=int(len(lag)), lagged_next3=float(nxt3.reindex(lag.index).mean()) if len(lag) else None)
    R["leadlag"] = ll
    print("\n== lead-lag (next-day EW smallcap minus SPY on SPY_t and gap_t)", json.dumps(ll, indent=1))

    # ---- (b) PEAD and (e) pre-earnings run-up (earnings dates 2020+ only)
    pe = pead(c, P, ivr, spread, crowd)
    R.update(pe)

    # ---- IV sensitivity on the leading strategies
    sens = {}
    for s in ("dip_rsi2", "dip_rsi2_bb", "dip_3down", "dip_atr2", "brk_52w", "catchup"):
        side, ten, hold, _ = STRATS[s]
        out = {}
        for lab, mode, k in (("ratio", "ratio", None), ("1.0xRV", "k", 1.0), ("1.2xRV", "k", 1.2), ("1.5xRV", "k", 1.5)):
            xs = []
            for t, d in P.items():
                tr = trades(d, signal(d, s), side, ten, hold, ivr[t], spread[t], ivmode=mode, k=k or 1.2)
                xs.append(period(tr, OOS0, END).ret)
            out[lab] = float(pd.concat(xs).mean())
        xs = [period(trades(d, signal(d, s), side, ten, hold, ivr[t], spread[t], bump=1.14), OOS0, END).ret for t, d in P.items()]
        out["ratio+entry IV x1.14"] = float(pd.concat(xs).mean())
        # spread sensitivity: zero vs 2x measured
        for lab, mult in (("spread0", 0.0), ("spread0.5x", 0.5), ("spread2x", 2.0)):
            xs = [period(trades(d, signal(d, s), side, ten, hold, ivr[t], spread[t] * mult), OOS0, END).ret for t, d in P.items()]
            out[lab] = float(pd.concat(xs).mean())
        sens[s] = out
    R["iv_sensitivity"] = sens
    print("\n== OOS EV sensitivity", json.dumps(sens, indent=1))

    # ---- survivorship
    R["survivorship"] = survivorship(c, m, list(P))
    print("\n== survivorship", json.dumps(R["survivorship"], indent=1, default=float))

    # ---- shortlist + bankroll
    R["shortlist"], R["bankroll"] = shortlist(c, P, T, ct, crowd, Cdf, ivr, spread)
    OUT.write_text(json.dumps(R, default=lambda o: None if (isinstance(o, float) and o != o) else (float(o) if isinstance(o, (np.floating, np.integer)) else str(o)), indent=1))
    print("wrote", OUT)


def _earn_events(c, t, d):
    e = c.get("earn", {}).get(t)
    if e is None or len(e) == 0: return []
    ev = []
    for ts, row in e.iterrows():
        ts = pd.Timestamp(ts)
        if pd.isna(row.get("Reported EPS")): continue
        day = ts.tz_localize(None).normalize() if ts.tzinfo else ts.normalize()
        amc = ts.hour >= 12
        pos = d.index.searchsorted(day)
        if pos >= len(d): continue
        # reaction day: same day if BMO (index day == announce day), next session if AMC
        if d.index[pos] != day: amc = False   # announce on non-trading day -> first session after is reaction
        rpos = pos + 1 if amc else pos
        if rpos >= len(d) or rpos < 61: continue
        ev.append(dict(rpos=rpos, apos=pos, surprise=row.get("Surprise(%)"), amc=amc))
    return ev


def pead(c, P, ivr, spread, crowd):
    rows, pre = [], []
    for t, d in P.items():
        C = d.Close.values; iw = d.IWM.values; rv = d.rv20.values; n = len(d)
        xr = (d.r - d.iwm_r)
        xsd = xr.rolling(60).std().shift().values
        cc = d.Close.loc["2020":]
        mu = {h: float((cc.shift(-h) / cc - 1).mean()) for h in (5, 20)}   # ticker's unconditional h-day drift (survivorship-neutral)
        for e in _earn_events(c, t, d):
            i = e["rpos"]
            react = C[i] / C[i - 1] - 1 - (iw[i] / iw[i - 1] - 1)
            big = abs(react) >= max(0.04, 1.5 * (xsd[i] if xsd[i] == xsd[i] else 0.03))
            v_pre = rv[i - 2] * ivr[t] * d.mr.values[i]       # post-crush IV ~ normal (pre-event) level x market regime
            for hold, ten in ((5, 21), (20, 45)):
                if i + hold >= n: continue
                sgn = 1 if react > 0 else -1
                S0, S1 = C[i], C[i + hold]
                dtt = (d.index[i + hold] - d.index[i]).days / 365
                v1 = rv[i + hold] * ivr[t] * d.mr.values[i + hold] if hold >= 20 else v_pre
                r = float(opt_ret(S0, S1, max(v_pre, .15), max(v1, .15), ten / 365, dtt, sgn > 0, spread[t]))
                dr = (S1 / S0 - 1 - (iw[i + hold] / iw[i] - 1)) * sgn
                sur = e["surprise"]
                du = ((S1 / S0 - 1) - mu[hold]) * sgn
                rows.append(dict(t=t, date=d.index[i], hold=hold, react=react, big=big, sgn=sgn, ret=r, drift_x=dr, drift_u=du,
                                 sur=float(sur) if sur == sur and sur is not None else np.nan,
                                 agree=(np.sign(sur) == sgn) if sur == sur and sur is not None else np.nan, crowd=crowd.get(t)))
            # (e) pre-earnings run-up: enter close 5 sessions before the last pre-announcement close, exit at that close
            ex = i - 1                              # last close before the reaction
            en = ex - 5
            if en > 60:
                S0, S1 = C[en], C[ex]
                dtt = (d.index[ex] - d.index[en]).days / 365
                v0 = max(rv[en] * ivr[t] * d.mr.values[en], .15)
                for lab, bump in (("flat", 1.0), ("iv+15%", 1.15)):
                    r = float(opt_ret(S0, S1, v0, v0 * bump, 21 / 365, dtt, True, spread[t]))
                    pre.append(dict(t=t, date=d.index[en], var=lab, ret=r, und_x=S1 / S0 - 1 - (iw[ex] / iw[en] - 1),
                                    und_u=S1 / S0 - 1 - mu[5], crowd=crowd.get(t)))
    D = pd.DataFrame(rows); Q = pd.DataFrame(pre)
    out = {}
    if len(D):
        D = D.set_index("date").sort_index()
        res = {}
        for hold in (5, 20):
            for lab, q in (("all big reactions", D[(D.hold == hold) & D.big]),
                           ("big & surprise agrees", D[(D.hold == hold) & D.big & (D.agree == True)]),
                           ("big up", D[(D.hold == hold) & D.big & (D.sgn > 0)]), ("big down", D[(D.hold == hold) & D.big & (D.sgn < 0)]),
                           ("quiet big", D[(D.hold == hold) & D.big & (D.crowd == "quiet")]),
                           ("crowded big", D[(D.hold == hold) & D.big & (D.crowd == "crowded")])):
                for per, a, b in (("2020-22", pd.Timestamp("2020-01-01"), pd.Timestamp("2022-12-31")), ("2023+", pd.Timestamp("2023-01-01"), END)):
                    qq = q.loc[a:b]
                    res[f"h{hold} | {lab} | {per}"] = dict(n=len(qq), drift_x=float(qq.drift_x.mean()) if len(qq) else None,
                                                           drift_t=week_t(qq.drift_x) if len(qq) > 5 else None,
                                                           drift_u=float(qq.drift_u.mean()) if len(qq) else None,
                                                           drift_u_t=week_t(qq.drift_u) if len(qq) > 5 else None,
                                                           opt_ev=float(qq.ret.mean()) if len(qq) else None,
                                                           pop=float((qq.ret > 0).mean()) if len(qq) else None)
        out["pead"] = res
        print("\n== PEAD (enter close of reaction day, direction of reaction; drift_x = underlying vs IWM, signed)")
        for k, v in res.items():
            print(f"{k:45s} n={v['n']:5d} drift={100*(v['drift_x'] or 0):+6.2f}% t={v['drift_t'] or 0:+5.2f} "
                  f"vs-own={100*(v['drift_u'] or 0):+6.2f}% t={v['drift_u_t'] or 0:+5.2f} optEV={100*(v['opt_ev'] or 0):+6.1f}%")
        out["pead_trades"] = D[D.big].reset_index()[["date", "t", "hold", "react", "sgn", "ret", "drift_x", "crowd"]].assign(
            date=lambda x: x.date.astype(str)).to_dict("records")
    if len(Q):
        Q = Q.set_index("date").sort_index()
        r2 = {}
        for v in ("flat", "iv+15%"):
            for per, a, b in (("2020-22", pd.Timestamp("2020-01-01"), pd.Timestamp("2022-12-31")), ("2023+", pd.Timestamp("2023-01-01"), END)):
                qq = Q[Q["var"] == v].loc[a:b]
                r2[f"{v} | {per}"] = dict(n=len(qq), und_x=float(qq.und_x.mean()), und_t=week_t(qq.und_x), opt_ev=float(qq.ret.mean()),
                                          und_u=float(qq.und_u.mean()), und_u_t=week_t(qq.und_u),
                                          quiet_und_x=float(qq[qq.crowd == "quiet"].und_x.mean()),
                                          crowded_und_x=float(qq[qq.crowd == "crowded"].und_x.mean()))
        out["prerun"] = r2
        print("\n== pre-earnings run-up (5 sessions into the print, 21d call)", json.dumps(r2, indent=1))
    return out


def survivorship(c, m, live):
    px = c["px"]
    out = {}
    gone = c["holdings"]["gone"]
    have = [t for t in gone if px.get(t) is not None and len(px[t]) > 50]
    out["historical_cohort_not_in_current_lists"] = len(gone)
    out["of_which_yfinance_has_history"] = len(have)
    # how many of those stopped trading (last bar well before END) -> delisted/acquired names yfinance still serves
    last = {t: pd.Timestamp(px[t].index[-1]).tz_localize(None) if pd.Timestamp(px[t].index[-1]).tzinfo else pd.Timestamp(px[t].index[-1]) for t in have}
    dead = [t for t, l in last.items() if l < END - pd.Timedelta(days=30)]
    out["of_which_stopped_trading"] = len(dead)
    # 2018 IWM cohort: equal-weight buy-and-hold from 2018-03-15 using names yfinance still has vs IWM
    src = c["holdings"]["src"]
    for lab, key, start in (("IWM 2018-03 cohort", "IWM_2018_wayback", "2018-03-15"), ("IJR 2021-01 cohort", "IJR_2021_wayback", "2021-01-14")):
        tk = src[key]["tickers"]
        avail = [t for t in tk if px.get(t) is not None]
        rets = []
        for t in avail:
            s = px[t].Close
            s.index = pd.DatetimeIndex(s.index).tz_localize(None)
            s = s.loc[start:END]
            if len(s) < 2 or s.index[0] > pd.Timestamp(start) + pd.Timedelta(days=10): continue
            rets.append(s.iloc[-1] / s.iloc[0] - 1)
        etf = "IWM" if "IWM" in key else "IJR"
        e = px[etf].Close; e.index = pd.DatetimeIndex(e.index).tz_localize(None); e = e.loc[start:END]
        out[lab] = dict(n_holdings=len(tk), n_in_cache=len(avail), n_priced_from_start=len(rets),
                        ew_return_survivors=float(np.mean(rets)) if rets else None, median=float(np.median(rets)) if rets else None,
                        etf_total_return=float(e.iloc[-1] / e.iloc[0] - 1))
    # current liquid universe EW vs IWM/IJR since 2012 (annualised)
    ew = pd.DataFrame({t: pd.Series(px[t].Close.values, index=pd.DatetimeIndex(px[t].index).tz_localize(None)).pct_change() for t in live}).loc["2012":END]
    ewr = ew.mean(axis=1).fillna(0)
    yrs = (ewr.index[-1] - ewr.index[0]).days / 365.25
    res = dict(ew_universe_cagr=float((1 + ewr).prod() ** (1 / yrs) - 1))
    for etf in ("IWM", "IJR"):
        e = px[etf].Close; e.index = pd.DatetimeIndex(e.index).tz_localize(None); e = e.loc[ewr.index[0]:END]
        res[f"{etf}_cagr"] = float((e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1)
    for per, a, b in (("IS", IS0, IS1), ("OOS", OOS0, END)):
        q = ewr.loc[a:b]; yy = (q.index[-1] - q.index[0]).days / 365.25
        e = px["IWM"].Close; e.index = pd.DatetimeIndex(e.index).tz_localize(None); e = e.loc[a:b]
        res[f"{per}_ew_cagr"] = float((1 + q).prod() ** (1 / yy) - 1); res[f"{per}_IWM_cagr"] = float((e.iloc[-1] / e.iloc[0]) ** (1 / yy) - 1)
    out["current_list_backfill"] = res
    return out


LONG_STRATS = ("dip_rsi2", "dip_rsi2_bb", "dip_3down", "dip_atr2", "dip_atr3x3", "dip_bb", "dip_rsi2_h10", "dip_rsi2_up",
               "dip_rsi2_dn", "dip_rsi2_vix", "brk_52w", "brk_vol", "catchup", "catchup_h5")


def shortlist(c, P, T, ct, crowd, Cdf, ivr, spread):
    """Edge + liquid, ranked by OOS return on premium. Cost is NOT a filter (owner 2026-10-14): min_capital = one 21d ATM call."""
    yrs = (END - OOS0).days / 365.25
    out = []
    for s in LONG_STRATS:
        for t in P:
            tr = T[(s, t)]
            a, b = period(tr, IS0, IS1), period(tr, OOS0, END)
            out.append(dict(strat=s, t=t, min_capital=float(ct.loc[t, "cost21"]), price=float(ct.loc[t, "price"]),
                            spread=float(ct.loc[t, "spread"]), atm_oi=float(ct.loc[t, "atm_oi"]), opt_vol=float(ct.loc[t, "opt_vol"]),
                            crowd=crowd.get(t), n_is=len(a), ev_is=float(a.ret.mean()) if len(a) else np.nan,
                            x_is=float(a.x.mean()) if len(a) else np.nan, t_is=mean_t(a.x.values) if len(a) > 3 else np.nan,
                            n_oos=len(b), ev_oos=float(b.ret.mean()) if len(b) else np.nan, x_oos=float(b.x.mean()) if len(b) else np.nan,
                            pop_oos=float((b.ret > 0).mean()) if len(b) else np.nan,
                            tpy_oos=len(b) / yrs, und_x_oos=float(b.und_x.mean()) if len(b) else np.nan,
                            und_xu_oos=float(b.und_xu.mean()) if len(b) else np.nan, tier=ct.loc[t, "tier"],
                            ev_oos_mid=float(period(trades(P[t], signal(P[t], s), *STRATS[s][:3], ivr[t], 0.0), OOS0, END).ret.mean()) if len(b) else np.nan))
    D = pd.DataFrame(out)
    D["affordable"] = D.min_capital <= 85
    def agg(g):
        w = g.n_oos.clip(lower=0)
        return pd.Series(dict(cells=len(g), trades=int(w.sum()),
                              ev_oos=np.average(g.ev_oos.fillna(0), weights=w) if w.sum() else np.nan,
                              x_oos=np.average(g.x_oos.fillna(0), weights=w) if w.sum() else np.nan, tpy=g.tpy_oos.sum()))
    pooled = D.groupby("strat").apply(agg).reset_index()
    pooled_aff = D[D.affordable].groupby("strat").apply(agg).reset_index()
    pooled_tier = D.groupby(["strat", "tier"]).apply(agg).reset_index()
    print("\n== by liquidity tier\n", pooled_tier[pooled_tier.strat.isin(["dip_rsi2", "dip_rsi2_bb", "dip_rsi2_vix", "dip_rsi2_dn", "brk_52w"])].round(3).to_string())
    # IS-selected cells (n_is>=8, IS excess t>=1, IS EV>0) -> OOS; no OOS information used to pick
    pick = D[(D.n_is >= 8) & (D.t_is >= 1.0) & (D.ev_is > 0)]
    pick_stats = pick.groupby("strat").apply(agg).reset_index()
    print("\n== all liquid names, pooled OOS per strategy\n", pooled.round(3).to_string())
    print("affordable (<=$85) subset\n", pooled_aff.round(3).to_string())
    print("IS-selected cells (t_is>=1, ev_is>0) -> OOS\n", pick_stats.round(3).to_string())
    # bankroll: one position at a time over a trade pool (OOS trades), whole contracts at the ticker's measured cost
    bank = {}
    pools = {}
    for s in ("dip_rsi2", "dip_rsi2_bb", "dip_3down", "dip_atr2", "dip_atr3x3", "dip_rsi2_vix", "brk_52w", "catchup"):
        for lab, names in (("all liquid", list(P)), ("IS-selected", list(pick[pick.strat == s].t))):
            names = [t for t in names if len(T[(s, t)]) and ct.loc[t, "cost21"] == ct.loc[t, "cost21"]]
            if not names: continue
            allt = pd.concat([period(T[(s, t)], OOS0, END).assign(t=t) for t in names]).sort_index()
            if len(allt) < 10: continue
            hold = STRATS[s][2]
            rng = np.random.default_rng(1); seqs = []
            for rep in range(100):
                busy = pd.Timestamp("1900-01-01"); seq = []
                for day, g in allt.groupby(level=0):
                    if day <= busy: continue
                    r = g.iloc[rng.integers(len(g))]
                    seq.append((r.ret, ct.loc[r.t, "cost21"]))
                    busy = day + pd.Timedelta(days=int(hold * 1.45))
                seqs.append(seq)
            tpy = np.mean([len(q) for q in seqs]) / yrs
            pool = np.array([x for q in seqs for x in q], float)
            res = dict(trades_per_year=float(tpy), ev_per_trade=float(pool[:, 0].mean()), pop=float((pool[:, 0] > 0).mean()),
                       median_contract=float(np.median(pool[:, 1])))
            for start in (170.0, 1000.0, 5000.0):
                for f, v in boot_contracts(pool, tpy, start).items():
                    res[f"${int(start)} f{int(f*100)}"] = v
            bank[f"{s} | {lab}"] = res
    print("\n== bankroll (1y, one position at a time, whole contracts at measured cost; skip if 1 contract > 60% of equity)")
    for k, v in bank.items():
        print(k, " ".join(f"{a}={b:.3g}" for a, b in v.items() if not isinstance(b, dict)))
        for a, b in v.items():
            if isinstance(b, dict): print("   ", a, " ".join(f"{x}={y:.3g}" for x, y in b.items()))
    return dict(cells=D.to_dict("records"), pooled=pooled.to_dict("records"), pooled_affordable=pooled_aff.to_dict("records"),
                pooled_tier=pooled_tier.to_dict("records"),
                picked=pick_stats.to_dict("records"), picked_cells=pick.sort_values("ev_oos", ascending=False).to_dict("records")), bank


def boot_contracts(pool, per_year, start, fracs=(0.2, 0.25, 0.35), ruin_frac=0.12, n=20000, seed=7):
    """pool: rows (return on premium, contract cost). Position = floor(f*equity/cost) contracts, min 1 if cost <= 60% of equity,
    else the trade is skipped. Ruin = equity < 12% of start."""
    rng = np.random.default_rng(seed)
    k = max(1, int(round(per_year)))
    out = {}
    for f in fracs:
        eq = np.full(n, start); dead = np.zeros(n, bool); skipped = 0
        draws = rng.integers(0, len(pool), size=(n, k))
        for j in range(k):
            r = pool[draws[:, j], 0]; cost = pool[draws[:, j], 1]
            nc = np.floor(f * eq / cost)
            nc = np.where((nc == 0) & (cost <= 0.6 * eq), 1, nc)
            skipped += int((nc == 0).sum())
            eq = np.where(dead, eq, eq + nc * cost * r)
            dead |= eq < ruin_frac * start
        out[f] = dict(p_grow=float((eq > start).mean()), p_double=float((eq > 2 * start).mean()), p_ruin=float(dead.mean()),
                      median=float(np.median(eq)), skip_rate=skipped / (n * k))
    return out


def bank():
    """Bankroll for IS-selected cells in tiers T1/T2 (selection uses IS only), $170/$1k/$5k, whole contracts."""
    c = load(); m = market(); ct = chain_table(c)
    res = json.loads(OUT.read_text())
    D = pd.DataFrame(res["shortlist"]["cells"])
    L = D[D.tier.isin(["T1 strict", "T2 loose"])]
    sel = L[(L.n_is >= 5) & (L.ev_is > 0) & (L.x_is > 0)]
    P = {}
    for t in set(sel.t):
        P[t] = prep(c["px"][t], m)
    yrs = (END - OOS0).days / 365.25
    out = {}
    for s in ("dip_rsi2", "dip_rsi2_vix", "dip_rsi2_dn", "dip_rsi2_h10", "brk_52w", "brk_vol"):
        side, ten, hold, _ = STRATS[s]
        names = list(sel[sel.strat == s].t)
        rows = []
        for t in names:
            d = P[t]; iv = res["ivr"][t]; sp = res["spread"][t]
            tr = period(trades(d, signal(d, s), side, ten, hold, iv, sp), OOS0, END)
            for dte, r in tr.ret.items(): rows.append((dte, r, ct.loc[t, "cost21"], t))
        A = pd.DataFrame(rows, columns=["d", "ret", "cost", "t"]).dropna().set_index("d").sort_index()
        rng = np.random.default_rng(1); seqs = []
        for rep in range(100):
            busy = pd.Timestamp("1900-01-01"); seq = []
            for day, g in A.groupby(level=0):
                if day <= busy: continue
                r = g.iloc[rng.integers(len(g))]; seq.append((r.ret, r.cost)); busy = day + pd.Timedelta(days=int(hold * 1.45))
            seqs.append(seq)
        tpy = np.mean([len(q) for q in seqs]) / yrs
        pool = np.array([x for q in seqs for x in q], float)
        o = dict(names=names, tpy=tpy, ev=float(pool[:, 0].mean()), pop=float((pool[:, 0] > 0).mean()), med_cost=float(np.median(pool[:, 1])))
        for st in (170.0, 1000.0, 5000.0):
            for f, v in boot_contracts(pool, tpy, st, fracs=(0.2, 0.35)).items():
                o[f"${int(st)} f{int(f*100)}"] = {k: round(x, 3) for k, x in v.items()}
        out[s] = o
        print(s, len(names), f"tpy={tpy:.1f} ev={o['ev']:+.3f} pop={o['pop']:.2f} cost={o['med_cost']:.0f}")
        for k, v in o.items():
            if k.startswith("$"): print("   ", k, v)
    json.dump(out, open(str(ROOT / "data" / "research_smallcap_bank_t12.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = dict(holdings=holdings, caps=caps, chains=chains, prices=prices, cohort=cohort, earnings=earnings, run=run, bank=bank)
    if cmd == "all":
        for k in ("holdings", "caps", "chains", "prices", "cohort", "earnings", "run", "bank"):
            print(f"===== {k}"); steps[k]()
    elif cmd == "summary":
        summarize_chains(load())
    else:
        steps[cmd]()
