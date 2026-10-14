#!/usr/bin/env python3
"""Research: does any index / sector / commodity / single stock hold up to the bot's models better than SPY?

  python3 agents/options-100/bot/research_universe.py fetch     # yfinance daily bars 2007+ (~300 tickers), ^VIX/^VIX3M, earnings dates
  python3 agents/options-100/bot/research_universe.py chains    # live yfinance option chains: real ATM 14-30d call ask + IV/RV20 today
  python3 agents/options-100/bot/research_universe.py run       # all models x tickers, IS 2010-2018 / OOS 2019+, selection test, BH
  python3 agents/options-100/bot/research_universe.py all

Models (signal at close t, entry at close t unless noted; positions per ticker never overlap):
  dip_rsi2   RSI(2)<10                          -> 21d ATM call, hold 5 sessions
  dip_3down  3+ consecutive down closes         -> 21d ATM call, hold 5
  dip_bb     close < 20d lower Bollinger (2sd)   -> 21d ATM call, hold 5
  dip_atr    1-day drop > 2 x ATR(14)            -> 21d ATM call, hold 5
  dip_vix    market VIX > 25                     -> 30d ATM call, hold 10
  dip_vixts  market VIX/VIX3M > 1                -> 30d ATM call, hold 10
  ob_put     RSI(2)>90 (overbought)              -> 21d ATM PUT,  hold 5
  trend_call close>SMA200 and 12-1m momentum>0  -> 30d ATM call, hold 20 (checked every 20 sessions)
  trend_put  close<SMA200 and 12-1m momentum<0  -> 30d ATM put,  hold 20
  gap        |overnight gap| > 1.5 daily sd      -> open->close, direction (fill vs continue) learned IS; 7d ATM option
  pead       earnings reaction |excess|>max(2%,1.5sd) -> 14d ATM call/put in reaction direction, hold 5 (single stocks)
Excess = trade return minus the ticker's UNCONDITIONAL same-structure return over the same period (every day entered),
so a dip-buy on a stock that went up 10x only scores if dips beat random days.
Option pricing: Black-Scholes, IV = k x 20d realized (k=1.2 base; 1.1/1.3 sensitivity), floor 8%, sticky-moneyness skew 3;
round-trip spread by liquidity tier (2% / 5% / 10% of premium).
"""
import socket as _sk
_gai = _sk.getaddrinfo
_sk.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, _sk.AF_INET, *a, **k)   # IPv6 times out on this machine
import sys, json, math, pickle, time, warnings
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "research_universe_cache.pkl"
IS0, IS1 = pd.Timestamp("2010-01-01"), pd.Timestamp("2018-12-31")
OOS0 = pd.Timestamp("2019-01-01")
END = pd.Timestamp("2026-10-13")          # last complete session
KS = (1.1, 1.2, 1.3)                       # IV = k x RV20
K0 = 1.2
SKEW = 3.0
IVFLOOR = 0.08

U = {
    "index": "SPY QQQ IWM DIA MDY RSP",
    "intl": "EFA EEM FXI EWJ EWZ EWW INDA KWEB EWG EWU EWT EWY",
    "sector": "XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY SMH SOXX KRE KBE XBI IBB ITB XHB XRT XOP OIH GDX GDXJ "
              "JETS TAN ARKK IYT XME URA",
    "macro": "GLD SLV USO UNG TLT IEF HYG LQD UUP FXE FXY DBA DBC EMB",
    "vol": "VXX UVXY",
    "mega": "AAPL MSFT NVDA AMZN GOOGL META TSLA AVGO BRK-B JPM V MA UNH XOM JNJ WMT PG HD COST LLY ORCL NFLX ADBE CRM "
            "AMD INTC CSCO QCOM TXN MU AMAT LRCX KLAC IBM",
    "retail": "PLTR COIN MSTR SOFI HOOD RIVN LCID NIO GME AMC RBLX SNAP PINS UBER LYFT DKNG SHOP XYZ PYPL ROKU ZM DOCU "
              "NET CRWD SNOW U AFRM UPST MARA RIOT CLSK SMCI ARM CVNA CHWY PTON BYND OPEN CHPT PLUG FCEL TLRY CGC SNDL "
              "BB NOK SIRI GPRO CHGG",
    "large": "F GM T VZ PFE BAC C WFC GS MS SCHW AXP KO PEP MCD SBUX NKE DIS CMCSA WBD BA CAT DE GE MMM HON LMT RTX "
             "NOC UPS FDX UNP CSX DAL UAL AAL LUV CCL RCL NCLH MAR ABNB BKNG EXPE TGT LOW M KSS GAP BBY DG DLTR CVS "
             "CI HUM ABBV MRK BMY AMGN GILD BIIB MRNA BNTX REGN VRTX ISRG TMO DHR ABT MDT CVX COP OXY SLB HAL DVN "
             "APA EOG FCX NEM CLF AA NUE MOS CF DOW DD LIN SHW NEE DUK SO D AMT O SPG PLD CCI KHC GIS MO PM CL KMB "
             "EL ULTA LULU ETSY EBAY W BABA JD PDD BIDU TSM ASML SONY TM NVO SE MELI VALE PBR ITUB BBD KGC AG PAAS "
             "HL CDE RIG ET KMI WMB EPD LUMN TEVA VFC NWL XRX HPQ HPE DELL WDC STX ON MRVL ADI NXPI SWKS QRVO "
             "WOLF ENPH FSLR RUN SEDG",
}
CLASS = {t: c for c, s in U.items() for t in s.split()}
TICKERS = list(dict.fromkeys(CLASS))
STOCK_CLASSES = ("mega", "retail", "large")


# ---- numerics ------------------------------------------------------------------------------------------------------
def ncdf(x):
    x = np.asarray(x, float); z = np.abs(x) / math.sqrt(2); t = 1 / (1 + 0.3275911 * z)
    y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-z * z)
    return 0.5 * (1 + np.sign(x) * y)


def bs(S, K, T, sig, call=True):
    S, K, T, sig = (np.asarray(a, float) for a in (S, K, T, sig))
    T = np.maximum(T, 0.0); intr = np.maximum(S - K, 0) if call else np.maximum(K - S, 0)
    vs = sig * np.sqrt(T)
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(S / K) + 0.5 * vs ** 2) / vs; d2 = d1 - vs
        px = S * ncdf(d1) - K * ncdf(d2) if call else K * ncdf(-d2) - S * ncdf(-d1)
    return np.where(vs > 1e-9, px, intr)


def opt_ret(S0, S1, v0, v1, T0, dt, call, cost):
    """Long ATM option bought at S0 (tenor T0 yrs), sold dt yrs later at S1. Net of round-trip spread `cost`."""
    K = S0; T1 = np.maximum(T0 - dt, 0)
    sk = lambda v, S_: np.maximum(v * np.clip(1 - SKEW * np.log(K / S_), 0.5, 2.0), IVFLOOR)
    p0 = bs(S0, K, T0, sk(v0, S0), call); p1 = bs(S1, K, T1, sk(v1, S1), call)
    ok = np.isfinite(v0) & np.isfinite(v1) & (p0 > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(ok, p1 * (1 - cost / 2) / (p0 * (1 + cost / 2)) - 1, np.nan)


def tstat(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) < 4 or x.std(ddof=1) == 0: return float("nan")
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def pval(t):
    return math.erfc(abs(t) / math.sqrt(2)) if np.isfinite(t) else 1.0


def bh(p, q):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    thr = q * np.arange(1, n + 1) / n; ok = p[o] <= thr
    k = np.max(np.where(ok)[0]) + 1 if ok.any() else 0
    res = np.zeros(n, bool); res[o[:k]] = True
    return res


def rsi(c, n):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


# ---- data ----------------------------------------------------------------------------------------------------------
def fetch():
    import yfinance as yf
    t0 = time.time()
    px = {}
    allt = TICKERS + ["^VIX", "^VIX3M"]
    for i in range(0, len(allt), 60):
        chunk = allt[i:i + 60]
        d = yf.download(chunk, start="2007-01-01", end="2026-10-14", auto_adjust=False, group_by="ticker",
                        threads=True, progress=False)
        for t in chunk:
            try:
                x = d[t].dropna(subset=["Close"])
                if len(x) > 300: px[t] = x[["Open", "High", "Low", "Close", "Adj Close", "Volume"]].copy()
            except KeyError:
                pass
        print(f"  bars {i + len(chunk)}/{len(allt)}  ({time.time() - t0:.0f}s)")
    earn = {}

    def ge(t):
        for _ in range(3):
            try:
                e = yf.Ticker(t).get_earnings_dates(limit=100)
                if e is None: return t, []
                idx = e.index.tz_convert("America/New_York")
                return t, [(pd.Timestamp(d.date()), d.hour) for d in idx]
            except Exception:
                time.sleep(2)
        return t, []
    stocks = [t for t in TICKERS if CLASS[t] in STOCK_CLASSES and t in px]
    with ThreadPoolExecutor(6) as ex:
        for t, v in ex.map(ge, stocks): earn[t] = v
    print(f"  earnings for {sum(1 for v in earn.values() if v)}/{len(stocks)} stocks; missing bars: "
          f"{sorted(set(TICKERS) - set(px))}")
    CACHE.write_bytes(pickle.dumps({"px": px, "earn": earn, "fetched": str(pd.Timestamp.now())}))


def load():
    return pickle.loads(CACHE.read_bytes())


def save(key, val):
    """Results live in the same gitignored cache pickle (key 'results') so the study writes one data file only."""
    C = load(); C.setdefault("results", {})[key] = val
    CACHE.write_bytes(pickle.dumps(C))


# ---- per-ticker engine ---------------------------------------------------------------------------------------------
MODELS = {   # name: (side, hold sessions, tenor cal days)
    "dip_rsi2": (1, 5, 21), "dip_3down": (1, 5, 21), "dip_bb": (1, 5, 21), "dip_atr": (1, 5, 21),
    "dip_vix": (1, 10, 30), "dip_vixts": (1, 10, 30), "ob_put": (-1, 5, 21),
    "trend_call": (1, 20, 30), "trend_put": (-1, 20, 30), "gap": (0, 0, 7), "pead": (0, 5, 14),
}


def tier(df, t=None):
    dv = (df["Close"] * df["Volume"]).loc["2025-10-01":].mean()
    if t in COSTS: return COSTS[t], float(dv)
    return (0.02 if dv > 1e9 else 0.05 if dv > 1e8 else 0.10), float(dv)


DYNM = None   # dynamic IV multiplier = clip(0.9 x VIX / SPY RV20, 0.8, 2.5): the market's live implied/realized ratio
COSTS = {}    # ticker -> round-trip cost (0.6 x today's quoted ATM spread, floor 2%, cap 30%)


def set_dynm(px):
    global DYNM
    a = px["SPY"]["Adj Close"]; rv = np.log(a).diff().rolling(20).std() * math.sqrt(252)
    DYNM = (0.9 * px["^VIX"]["Close"].reindex(a.index).ffill() / 100 / rv).clip(0.8, 2.5)


def set_costs(C):
    ch = C.get("results", {}).get("chains", {})
    by_cls = {}
    for t, v in ch.items():
        if v.get("spread") is not None and np.isfinite(float(v["spread"])): by_cls.setdefault(CLASS[t], []).append(float(v["spread"]))
    med = {c: float(np.median(v)) for c, v in by_cls.items()}
    for t in TICKERS:
        sp = ch.get(t, {}).get("spread")
        sp = float(sp) if sp is not None and np.isfinite(float(sp)) else med.get(CLASS[t], 0.15)
        COSTS[t] = float(np.clip(0.6 * sp, 0.02, 0.30))


def features(df, vix, vix3m):
    x = pd.DataFrame(index=df.index)
    c = df["Close"]; a = df["Adj Close"]; o = df["Open"]
    x["c"], x["a"], x["o"] = c, a, o
    lr = np.log(a).diff(); x["lr"] = lr
    x["rv20"] = lr.rolling(20).std() * math.sqrt(252)
    x["rsi2"] = rsi(a, 2)
    dn = (a.diff() < 0).astype(int); x["streak"] = dn.groupby((dn == 0).cumsum()).cumsum()
    m, s = a.rolling(20).mean(), a.rolling(20).std(); x["bb"] = a < m - 2 * s
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - c.shift()).abs(), (df["Low"] - c.shift()).abs()], axis=1).max(axis=1)
    x["atr_drop"] = (c.shift() - c) > 2 * tr.rolling(14).mean().shift()
    x["sma200"] = a.rolling(200).mean()
    x["mom"] = a.shift(21) / a.shift(252) - 1
    adjr = a / c                                                   # dividend adjustment factor for the gap
    x["gap"] = (o * adjr) / a.shift() - 1
    x["gapz"] = x["gap"] / (x["rv20"].shift() / math.sqrt(252))
    x["oc"] = c / o - 1
    x["vix"] = vix.reindex(x.index).ffill(); x["ts"] = (vix / vix3m).reindex(x.index).ffill()
    x["dynm"] = DYNM.reindex(x.index).ffill() if DYNM is not None else K0
    return x


def fwd_opt(x, h, T0, call, k, cost):
    """Return for entering a T0-day ATM option at each close and exiting h sessions later."""
    n = len(x); S0 = x["c"].values
    v = (x["rv20"] * x["dynm"]).values if k == "dyn" else x["rv20"].values * k
    S1 = np.full(n, np.nan); v1 = np.full(n, np.nan); dt = np.full(n, np.nan)
    S1[:n - h] = S0[h:]; v1[:n - h] = v[h:]
    dt[:n - h] = (x.index[h:] - x.index[:n - h]).days.values / 365
    return opt_ret(S0, S1, v, v1, T0 / 365, dt, call, cost)


def nonoverlap(mask, h):
    idx = np.where(mask)[0]; keep, last = [], -10 ** 9
    for i in idx:
        if i >= last + h: keep.append(i); last = i
    return np.array(keep, int)


def per_ticker(t, df, vix, vix3m, earn, spy_a):
    x = features(df, vix, vix3m)
    cost, dv = tier(df, t)
    n = len(x); a = x["a"].values; idx = x.index
    period = np.where((idx >= IS0) & (idx <= IS1), "IS", np.where((idx >= OOS0) & (idx <= END), "OOS", ""))
    rows = []

    def fwd_und(h):
        r = np.full(n, np.nan); r[:n - h] = a[h:] / a[:n - h] - 1; return r
    und = {h: fwd_und(h) for h in (5, 10, 20)}
    cache = {}

    def fo(h, T0, call, k):
        key = (h, T0, call, k)
        if key not in cache: cache[key] = fwd_opt(x, h, T0, call, k, cost)
        return cache[key]
    # unconditional baselines per period
    base = {}
    for name, (side, h, T0) in MODELS.items():
        if side == 0: continue
        for p in ("IS", "OOS"):
            m = period == p
            b = dict(und=np.nanmean(side * und[h][m]))
            for k in KS + ("dyn",): b[k] = np.nanmean(fo(h, T0, side > 0, k)[m])
            b["dir"] = np.nanmean((fo(h, T0, side > 0, K0) - 0.5 * (fo(h, T0, True, K0) + fo(h, T0, False, K0)))[m])
            if name.startswith("dip_") and h == 5:
                for T in (14, 30): b[("T", T)] = np.nanmean(fo(h, T, True, "dyn")[m])
            base[(name, p)] = b
    sig = {
        "dip_rsi2": x["rsi2"] < 10, "dip_3down": x["streak"] >= 3, "dip_bb": x["bb"], "dip_atr": x["atr_drop"],
        "dip_vix": x["vix"] > 25, "dip_vixts": x["ts"] > 1, "ob_put": x["rsi2"] > 90,
        "trend_call": (x["a"] > x["sma200"]) & (x["mom"] > 0), "trend_put": (x["a"] < x["sma200"]) & (x["mom"] < 0),
    }
    valid = x["rv20"].notna() & x["sma200"].notna()
    for name, s in sig.items():
        side, h, T0 = MODELS[name]
        mask = (s & valid).values & (period != "")
        if name.startswith("trend"):          # check every 20 sessions (monthly cadence), not on every day
            grid = np.zeros(n, bool); grid[::20] = True; mask &= grid
        ii = nonoverlap(mask, h)
        ii = ii[ii + h < n]
        for i in ii:
            p = period[i]; b = base[(name, p)]
            r = dict(t=t, model=name, d=idx[i], p=p, und=side * und[h][i])
            r["und_x"] = r["und"] - b["und"]
            for k in KS + ("dyn",):
                r[f"o{k}"] = float(fo(h, T0, side > 0, k)[i]); r[f"ox{k}"] = r[f"o{k}"] - b[k]
            r["odx"] = float(fo(h, T0, side > 0, K0)[i] - 0.5 * (fo(h, T0, True, K0)[i] + fo(h, T0, False, K0)[i])) - b["dir"]
            if name.startswith("dip_") and h == 5:
                for T in (14, 30): r[f"oT{T}x"] = float(fo(h, T, True, "dyn")[i]) - b[("T", T)]
            rows.append(r)
    # gap: entry at the open, exit at the close (intraday); sign learned IS, frozen OOS
    gz = x["gapz"].values; oc = x["oc"].values
    gm = np.isfinite(gz) & (np.abs(gz) > 1.5) & (period != "")
    if gm.sum() > 10:
        cont = np.sign(gz) * oc
        is_m = gm & (period == "IS")
        dirn = 1.0 if (is_m.sum() < 10 or np.nanmean(cont[is_m]) >= 0) else -1.0     # +1 continuation, -1 fill
        S0 = x["o"].values; S1 = x["c"].values; v = x["rv20"].shift().values * K0
        for i in np.where(gm)[0]:
            side = dirn * np.sign(gz[i]); p = period[i]
            uncond = np.nanmean(oc[period == p])
            r = dict(t=t, model="gap", d=idx[i], p=p, und=side * oc[i], und_x=side * (oc[i] - uncond), dirn=dirn)
            for k in KS:
                o_ = float(opt_ret(S0[i], S1[i], v[i] / K0 * k, v[i] / K0 * k, 7 / 365, 0.25 / 365, side > 0, cost))
                r[f"o{k}"] = o_; r[f"ox{k}"] = o_          # no unconditional baseline for intraday; see odx
            vd = x["rv20"].shift().values[i] * x["dynm"].values[i]
            r["odyn"] = float(opt_ret(S0[i], S1[i], vd, vd, 7 / 365, 0.25 / 365, side > 0, cost))
            # excess = chosen side minus the same-day straddle average: strips the gamma bias of a calm-day IV on a gap day
            for k in KS + ("dyn",):
                vv = vd if k == "dyn" else v[i] / K0 * k
                st = 0.5 * sum(float(opt_ret(S0[i], S1[i], vv, vv, 7 / 365, 0.25 / 365, cl, cost)) for cl in (True, False))
                r[f"ox{k}"] = r[f"o{k}"] - st
            r["odx"] = r["oxdyn"]
            rows.append(r)
    # PEAD (single stocks): reaction day = report day if before open, else next session
    if earn:
        pos = pd.Series(np.arange(n), index=idx); spy = spy_a.reindex(idx).values
        sd = x["lr"].rolling(60).std().shift().values
        seen = set()
        for d, hr in earn:
            if d not in pos.index: continue
            i = int(pos[d]) if hr < 9 else int(pos[d]) + 1
            if i in seen or i < 61 or i + 5 >= n or period[i] == "": continue
            seen.add(i)
            react = a[i] / a[i - 1] - 1 - (spy[i] / spy[i - 1] - 1)
            if not np.isfinite(react) or abs(react) < max(0.02, 1.5 * sd[i]): continue
            side = 1 if react > 0 else -1
            fwd = a[i + 5] / a[i] - 1 - (spy[i + 5] / spy[i] - 1)
            p = period[i]
            r = dict(t=t, model="pead", d=idx[i], p=p, und=side * fwd, und_x=side * fwd)
            for k in KS:
                o_ = float(fo(5, 14, side > 0, k)[i])
                r[f"o{k}"] = o_
            # proper baseline: unconditional 14d option, hold 5, same side
            r["odyn"] = float(fo(5, 14, side > 0, "dyn")[i])
            for k in KS + ("dyn",):
                bo = np.nanmean(fo(5, 14, side > 0, k)[period == p]); r[f"ox{k}"] = r[f"o{k}"] - bo
            dd = fo(5, 14, side > 0, K0) - 0.5 * (fo(5, 14, True, K0) + fo(5, 14, False, K0))
            r["odx"] = float(dd[i]) - np.nanmean(dd[period == p])
            rows.append(r)
    # character (IS and OOS)
    ch = {}
    for p in ("IS", "OOS"):
        lr = x["lr"][period == p].dropna().values
        if len(lr) < 250: continue
        r5 = pd.Series(lr).rolling(5).sum().values[4::5]
        v1 = lr.var(); ch[p] = dict(
            ac1=float(np.corrcoef(lr[1:], lr[:-1])[0, 1]),
            ac5=float(np.corrcoef(r5[1:], r5[:-1])[0, 1]),
            vr5=float(np.var(pd.Series(lr).rolling(5).sum().dropna().values) / (5 * v1)),
            vr20=float(np.var(pd.Series(lr).rolling(20).sum().dropna().values) / (20 * v1)),
            hurst=float(np.polyfit(np.log([1, 2, 4, 8, 16, 32]),
                                   np.log([np.var(pd.Series(lr).rolling(q).sum().dropna().values) for q in (1, 2, 4, 8, 16, 32)]), 1)[0] / 2),
            bh_cagr=float((a[period == p][-1] / a[period == p][0]) ** (252 / (period == p).sum()) - 1),
            rv=float(lr.std() * math.sqrt(252)))
    info = dict(t=t, cls=CLASS[t], cost=cost, dv=dv, px=float(x["c"].iloc[-1]), rv20=float(x["rv20"].iloc[-1]),
                start=str(idx[0].date()), ch=ch)
    return rows, info


# ---- analysis ------------------------------------------------------------------------------------------------------
def week_t(df, col):
    """t-stat after averaging same-week trades (cross-sectional clustering: many tickers dip together)."""
    g = df.groupby(df["d"].dt.to_period("W"))[col].mean()
    return tstat(g.values), len(g)


def run():
    C = load(); px, earn = C["px"], C["earn"]
    set_dynm(px); set_costs(C)
    vix, vix3m = px["^VIX"]["Close"], px["^VIX3M"]["Close"]
    spy_a = px["SPY"]["Adj Close"]
    rows, infos = [], {}
    t0 = time.time()
    for t in TICKERS:
        if t not in px: continue
        r, info = per_ticker(t, px[t], vix, vix3m, earn.get(t), spy_a)
        rows += r; infos[t] = info
    T = pd.DataFrame(rows); T["d"] = pd.to_datetime(T["d"])
    T["cls"] = T["t"].map(CLASS)
    print(f"{len(infos)} tickers, {len(T)} trades ({time.time() - t0:.0f}s)")
    res = {}
    o, ox = "odyn", "oxdyn"          # primary pricing = dynamic IV (see DYNM); k x RV20 variants are sensitivity

    # 1. per ticker x model summary
    g = T.groupby(["t", "model", "p"])
    S = g.agg(n=("und", "size"), und=("und", "mean"), und_x=("und_x", "mean"), ev=(o, "mean"), evx=(ox, "mean"),
              pop=(o, lambda v: (v > 0).mean())).reset_index()
    S["t_und"] = g["und_x"].apply(tstat).values
    S["t_opt"] = g[ox].apply(tstat).values
    W = S.pivot_table(index=["t", "model"], columns="p", values=["n", "und_x", "ev", "evx", "t_und", "t_opt", "pop"])
    W.columns = [f"{a}_{b}" for a, b in W.columns]; W = W.reset_index()
    W["cls"] = W["t"].map(CLASS)
    # BH on OOS (option-excess t and underlying-excess t), tests with n_OOS >= 8
    Wo = W[W["n_OOS"] >= 8].copy()
    for col in ("t_und_OOS", "t_opt_OOS"):
        pv = Wo[col].apply(pval).values
        Wo[col + "_bh05"] = bh(pv, 0.05); Wo[col + "_bh10"] = bh(pv, 0.10)
        Wo[col + "_nom"] = pv < 0.05
    res["n_tests"] = int(len(Wo))
    res["bh"] = {c: dict(nominal=int(Wo[c + "_nom"].sum()), bh05=int(Wo[c + "_bh05"].sum()), bh10=int(Wo[c + "_bh10"].sum()),
                         expected_by_chance=round(0.05 * len(Wo), 1),
                         survivors=Wo[Wo[c + "_bh10"]][["t", "model", "n_OOS", "und_x_OOS", "ev_OOS", "evx_OOS", c, "t_und_IS"]]
                         .sort_values(c, ascending=False).round(4).to_dict("records"))
                 for c in ("t_und_OOS", "t_opt_OOS")}
    print("\n== BH across ticker x model (OOS 2019+, n>=8) ==")
    for c, v in res["bh"].items():
        print(f"  {c}: tests {len(Wo)}, nominal p<.05 {v['nominal']} (chance {v['expected_by_chance']}), BH q.05 {v['bh05']}, q.10 {v['bh10']}")
        for s in v["survivors"][:25]: print("     ", s)
    # replicated: IS t>=2 and OOS t>=2 in the same direction
    rep = W[(W["t_und_IS"] >= 2) & (W["t_und_OOS"] >= 2)]
    res["replicated"] = rep[["t", "model", "n_IS", "n_OOS", "und_x_IS", "und_x_OOS", "ev_OOS", "evx_OOS", "t_und_IS", "t_und_OOS"]].round(4).to_dict("records")
    print(f"\n== replicated (IS t>=2 & OOS t>=2): {len(rep)} of {len(W)} ==")
    print(rep[["t", "model", "n_IS", "n_OOS", "und_x_OOS", "ev_OOS", "evx_OOS", "t_und_IS", "t_und_OOS"]].round(3).to_string())

    # 2. pooled by model x asset class (OOS), week-clustered t
    print("\n== pooled OOS by model x class (week-clustered t on option excess; raw EV; underlying excess) ==")
    pool = []
    for (m, c), d in T[T.p == "OOS"].groupby(["model", "cls"]):
        tw, nw = week_t(d, ox); tu, _ = week_t(d, "und_x")
        pool.append(dict(model=m, cls=c, n=len(d), tickers=d.t.nunique(), ev=d[o].mean(), evx=d[ox].mean(), pop=(d[o] > 0).mean(),
                         und_x=d.und_x.mean(), t_und_w=tu, t_opt_w=tw, weeks=nw,
                         ev11=d["o1.1"].mean(), ev13=d["o1.3"].mean(), odx=d.odx.mean(), t_dir_w=week_t(d, "odx")[0],
                         evdyn=d["odyn"].mean(), evxdyn=d["oxdyn"].mean(), t_dyn_w=week_t(d, "oxdyn")[0]))
    for (m), d in T[T.p == "OOS"].groupby("model"):
        tw, nw = week_t(d, ox); tu, _ = week_t(d, "und_x")
        pool.append(dict(model=m, cls="ALL", n=len(d), tickers=d.t.nunique(), ev=d[o].mean(), evx=d[ox].mean(), pop=(d[o] > 0).mean(),
                         und_x=d.und_x.mean(), t_und_w=tu, t_opt_w=tw, weeks=nw, ev11=d["o1.1"].mean(), ev13=d["o1.3"].mean(),
                         odx=d.odx.mean(), t_dir_w=week_t(d, "odx")[0],
                         evdyn=d["odyn"].mean(), evxdyn=d["oxdyn"].mean(), t_dyn_w=week_t(d, "oxdyn")[0]))
    P = pd.DataFrame(pool); res["pooled"] = P.round(4).to_dict("records")
    print(P.round(3).to_string())
    # IS pooled for comparison
    Pi = []
    for m, d in T[T.p == "IS"].groupby("model"):
        tu, _ = week_t(d, "und_x"); tw, _ = week_t(d, ox)
        Pi.append(dict(model=m, n=len(d), ev=d[o].mean(), evx=d[ox].mean(), und_x=d.und_x.mean(), t_und_w=tu, t_opt_w=tw,
                       odx=d.odx.mean(), t_dir_w=week_t(d, "odx")[0], evdyn=d["odyn"].mean(), evxdyn=d["oxdyn"].mean()))
    res["pooled_IS"] = pd.DataFrame(Pi).round(4).to_dict("records")
    print("\nIS pooled:\n" + pd.DataFrame(Pi).round(3).to_string())

    # 3. ticker selection out of sample
    print("\n== ticker selection: rank on IS 2010-18, evaluate same list OOS 2019+ ==")
    sel = []
    for m in MODELS:
        d = W[(W.model == m) & (W.n_IS >= 8) & (W.n_OOS >= 3)].copy()
        if len(d) < 20: continue
        for rank_col in ("t_und_IS", "evx_IS"):
            d = d.sort_values(rank_col, ascending=False); q = max(3, len(d) // 10)
            top, bot = d.head(q), d.tail(q)
            Tm = T[(T.model == m) & (T.p == "OOS")]
            def pooled(names):
                x = Tm[Tm.t.isin(names)]
                return dict(n=len(x), ev=x[o].mean(), evx=x[ox].mean(), und_x=x.und_x.mean(), t_w=week_t(x, ox)[0], t_und_w=week_t(x, "und_x")[0])
            from scipy.stats import spearmanr
            rho_u = spearmanr(d["und_x_IS"], d["und_x_OOS"]).correlation
            rho_o = spearmanr(d["evx_IS"], d["evx_OOS"]).correlation
            rho_p = spearmanr(d["und_x_IS"], d["und_x_OOS"]).pvalue
            pt, pb, pa = pooled(top.t), pooled(bot.t), pooled(d.t)
            sel.append(dict(model=m, rank=rank_col, N=len(d), q=q, rho_und=rho_u, rho_und_p=rho_p, rho_opt=rho_o,
                            top_ev=pt["ev"], top_evx=pt["evx"], top_undx=pt["und_x"], top_t=pt["t_w"],
                            all_ev=pa["ev"], all_evx=pa["evx"], all_undx=pa["und_x"],
                            bot_ev=pb["ev"], bot_evx=pb["evx"], bot_undx=pb["und_x"], top_list=" ".join(top.t)))
    SEL = pd.DataFrame(sel); res["selection"] = SEL.round(4).to_dict("records")
    print(SEL.drop(columns=["top_list"]).round(3).to_string())
    for _, r in SEL[SEL["rank"] == "t_und_IS"].iterrows(): print(f"  {r.model:10s} top IS: {r.top_list}")

    # 4. character: does IS mean-reversion/trend character predict OOS model results?
    from scipy.stats import spearmanr
    print("\n== character (IS) -> OOS model excess, Spearman across tickers ==")
    chr_rows = []
    chdf = pd.DataFrame({t: {f"{p}_{k_}": v for p in ("IS", "OOS") for k_, v in i["ch"].get(p, {}).items()} for t, i in infos.items()}).T
    persist = {c: spearmanr(chdf[f"IS_{c}"], chdf[f"OOS_{c}"], nan_policy="omit").correlation for c in ("ac1", "ac5", "vr5", "vr20", "hurst", "rv")}
    print("  persistence of character IS->OOS (rho):", {k_: round(v, 2) for k_, v in persist.items()})
    res["char_persist"] = persist
    for m in MODELS:
        d = W[(W.model == m) & (W.n_OOS >= 5)].set_index("t")
        j = d.join(chdf, how="inner").dropna(subset=["IS_vr5"])
        if len(j) < 20: continue
        for c in ("ac1", "vr5", "vr20", "hurst", "rv"):
            for tgt in ("und_x_OOS", "evx_OOS"):
                rr = spearmanr(j[f"IS_{c}"], j[tgt], nan_policy="omit")
                chr_rows.append(dict(model=m, char=c, target=tgt, rho=rr.correlation, p=rr.pvalue, N=len(j)))
    CH = pd.DataFrame(chr_rows); res["char"] = CH.round(4).to_dict("records")
    print(CH[CH.target == "und_x_OOS"].pivot(index="model", columns="char", values="rho").round(2).to_string())
    print("  p-values:\n" + CH[CH.target == "und_x_OOS"].pivot(index="model", columns="char", values="p").round(3).to_string())
    # mean-reverting vs trending terciles (IS vr5): pooled OOS dip-buy and trend
    terc = pd.qcut(chdf["IS_vr5"].astype(float), 3, labels=["MR (low VR)", "mid", "trend (high VR)"])
    tt = []
    for m in ("dip_rsi2", "dip_3down", "dip_bb", "dip_atr", "dip_vix", "trend_call", "ob_put", "gap"):
        for lab in terc.cat.categories:
            names = terc[terc == lab].index
            x = T[(T.model == m) & (T.p == "OOS") & T.t.isin(names)]
            tt.append(dict(model=m, tercile=lab, n=len(x), evx=x[ox].mean(), und_x=x.und_x.mean(), t_w=week_t(x, "und_x")[0]))
    # selection by CHARACTER instead of past performance: most mean-reverting decile (lowest IS VR5) -> OOS
    cs = []
    vr = chdf["IS_vr5"].astype(float).dropna().sort_values()
    q = len(vr) // 10
    for m in ("dip_rsi2", "dip_3down", "dip_bb", "dip_atr", "dip_vix", "dip_vixts", "ob_put", "trend_call", "gap"):
        Tm = T[(T.model == m) & (T.p == "OOS")]
        for lab, names in (("lowest-VR5 decile", vr.index[:q]), ("highest-VR5 decile", vr.index[-q:]), ("all", vr.index)):
            x = Tm[Tm.t.isin(names)]
            cs.append(dict(model=m, group=lab, n=len(x), ev=x[o].mean(), evx=x[ox].mean(), und_x=x.und_x.mean(),
                           t_und_w=week_t(x, "und_x")[0], t_opt_w=week_t(x, ox)[0]))
    CS = pd.DataFrame(cs); res["char_select"] = CS.round(4).to_dict("records")
    res["mr_decile"] = list(vr.index[:q]); res["trend_decile"] = list(vr.index[-q:])
    print("\n== select by IS character (VR5) -> OOS ==\n" + CS.round(3).to_string())
    print("  lowest-VR5 (mean-reverting) IS decile:", " ".join(vr.index[:q]))
    print("  highest-VR5 (trending) IS decile:", " ".join(vr.index[-q:]))
    TT = pd.DataFrame(tt); res["char_terciles"] = TT.round(4).to_dict("records")
    print(TT.pivot(index="model", columns="tercile", values="und_x").round(4).to_string())
    print(TT.pivot(index="model", columns="tercile", values="evx").round(3).to_string())

    # 5. survivorship: dip-buy on names that FELL OOS vs rose
    surv = []
    for m in ("dip_rsi2", "dip_3down", "dip_bb", "dip_atr", "dip_vix"):
        for lab, cond in (("fell OOS (B&H CAGR<0)", lambda c: c < 0), ("rose 0-15%/yr", lambda c: 0 <= c < .15), ("rose >15%/yr", lambda c: c >= .15)):
            names = [t for t, i in infos.items() if "OOS" in i["ch"] and cond(i["ch"]["OOS"]["bh_cagr"])]
            x = T[(T.model == m) & (T.p == "OOS") & T.t.isin(names)]
            surv.append(dict(model=m, group=lab, tickers=len(names), n=len(x), ev=x[o].mean(), evx=x[ox].mean(), und_x=x.und_x.mean()))
    SV = pd.DataFrame(surv); res["survivorship"] = SV.round(4).to_dict("records")
    print("\n== survivorship split (OOS) ==\n" + SV.round(3).to_string())

    # 6. sensitivity: tenor (dip models) and k
    sens = []
    for m in ("dip_rsi2", "dip_3down", "dip_bb", "dip_atr"):
        x = T[(T.model == m) & (T.p == "OOS")]
        sens.append(dict(model=m, evx_T14=x["oT14x"].mean(), evx_T21=x[ox].mean(), evx_T30=x["oT30x"].mean(),
                         ev_k11=x["o1.1"].mean(), ev_k12=x["o1.2"].mean(), ev_k13=x["o1.3"].mean()))
    res["sens"] = pd.DataFrame(sens).round(4).to_dict("records")
    print("\n== sensitivity (OOS, all tickers) ==\n" + pd.DataFrame(sens).round(3).to_string())

    # 7. SPY benchmark rows + full ranking table
    W["spy_ev_OOS"] = W.model.map(W[W.t == "SPY"].set_index("model")["ev_OOS"])
    W["beats_spy"] = W["ev_OOS"] > W["spy_ev_OOS"]
    res["spy"] = W[W.t == "SPY"].round(4).to_dict("records")
    print("\n== SPY rows ==\n" + W[W.t == "SPY"][["model", "n_IS", "n_OOS", "und_x_IS", "und_x_OOS", "ev_IS", "ev_OOS", "evx_OOS", "t_und_OOS"]].round(3).to_string())
    infos_df = pd.DataFrame(infos.values()).set_index("t")
    W = W.join(infos_df[["px", "rv20", "cost", "dv"]], on="t")
    W["cost21"] = [float(bs(p, p, 21 / 365, max(r * K0, IVFLOOR))) * 100 for p, r in zip(W.px, W.rv20)]
    res["table"] = W.round(4).to_dict("records")
    res["infos"] = {t: {k_: v for k_, v in i.items()} for t, i in infos.items()}
    # 8. affordable universe: real ATM ~21d call ask <= $85 today (yfinance chain), pooled OOS by model
    ch = C.get("results", {}).get("chains", {})
    aff = sorted(t for t, v in ch.items() if float(v["ask_usd"]) <= 85)
    res["affordable"] = aff
    ar = []
    for m in MODELS:
        Tm = T[(T.model == m) & (T.p == "OOS")]
        for lab, names in (("affordable", aff), ("all", list(infos)), ("SPY", ["SPY"])):
            x = Tm[Tm.t.isin(names)]
            if len(x) == 0: continue
            ar.append(dict(model=m, set=lab, tickers=x.t.nunique(), n=len(x), ev=x[o].mean(), evx=x[ox].mean(), pop=(x[o] > 0).mean(),
                           und_x=x.und_x.mean(), t_w=week_t(x, ox)[0], t_und_w=week_t(x, "und_x")[0], ev_k12=x["o1.2"].mean()))
    AR = pd.DataFrame(ar); res["afford_pool"] = AR.round(4).to_dict("records")
    print(f"\n== affordable set ({len(aff)} tickers, ask<=$85) vs all vs SPY, OOS ==\n" + AR.round(3).to_string())
    # 9. candidate table: affordable tickers, dip models, IS and OOS side by side
    cand = W[W.t.isin(aff) & W.model.isin(["dip_rsi2", "dip_3down", "dip_bb", "dip_vix", "dip_vixts", "gap", "ob_put", "trend_call"])].copy()
    cand["ask"] = cand.t.map(lambda t: float(ch[t]["ask_usd"])); cand["spread"] = cand.t.map(lambda t: float(ch[t]["spread"]))
    cand = cand[(cand.n_IS >= 8) & (cand.n_OOS >= 8)]
    cand["both_pos"] = (cand.evx_IS > 0) & (cand.evx_OOS > 0) & (cand.und_x_IS > 0) & (cand.und_x_OOS > 0)
    cols = ["t", "model", "ask", "spread", "n_IS", "n_OOS", "und_x_IS", "und_x_OOS", "t_und_IS", "t_und_OOS", "ev_IS", "ev_OOS", "evx_IS", "evx_OOS", "both_pos"]
    res["candidates"] = cand[cols].sort_values("evx_OOS", ascending=False).round(4).to_dict("records")
    print("\n== affordable candidates with positive IS AND OOS excess (dyn IV) ==")
    print(cand[cand.both_pos][cols].sort_values("t_und_IS", ascending=False).round(3).to_string())
    # 10. lead: crypto-linked names gap FILL (sign fixed a priori = fade the gap; COIN/HOOD/MSTR have no IS period)
    cg = T[(T.model == "gap") & T.t.isin(["MARA", "RIOT", "CLSK", "COIN", "MSTR", "HOOD"])].copy()
    cg["fill"] = cg["und"] * cg["dirn"] * -1          # und is signed by learned dirn; convert to "fade the gap" P&L
    cgo = cg[cg.p == "OOS"]
    yr = cgo.groupby(cgo.d.dt.year)["fill"].agg(["size", "mean"]).round(4)
    res["crypto_gap_fill"] = dict(n=len(cgo), mean=float(cgo.fill.mean()), t_w=week_t(cgo.assign(f=cgo.fill), "f")[0],
                                  hit=float((cgo.fill > 0).mean()), by_year=yr.reset_index().to_dict("records"))
    print("\n== lead: crypto-linked gap fill (OOS, open->close, fade |gap|>1.5sd) ==", {k_: v for k_, v in res["crypto_gap_fill"].items() if k_ != "by_year"})
    print(yr.T.to_string())
    save("run", res); save("trades", T)
    return res


def chains(tickers=None):
    """Real yfinance chains today: ATM call ask for the expiry nearest 21d (14-30d window), IV, and IV / RV20."""
    import yfinance as yf
    C = load(); px = C["px"]
    tickers = tickers or [t for t in TICKERS if t in px]
    today = pd.Timestamp("2026-10-14")

    def one(t):
        try:
            tk = yf.Ticker(t); exps = [pd.Timestamp(e) for e in tk.options]
            cand = [e for e in exps if 14 <= (e - today).days <= 30]
            if not cand: return t, None
            e = min(cand, key=lambda e: abs((e - today).days - 21))
            ch = tk.option_chain(e.strftime("%Y-%m-%d")).calls
            S = float(px[t]["Close"].iloc[-1])
            r = ch.iloc[(ch.strike - S).abs().argsort()[:1]].iloc[0]
            mid = (r.bid + r.ask) / 2
            lr = np.log(px[t]["Adj Close"]).diff().tail(20)
            return t, dict(exp=str(e.date()), dte=(e - today).days, S=S, K=float(r.strike), bid=float(r.bid), ask=float(r.ask),
                           ask_usd=float(r.ask) * 100, spread=float((r.ask - r.bid) / mid) if mid > 0 else None,
                           iv=float(r.impliedVolatility), rv20=float(lr.std() * math.sqrt(252)),
                           oi=int(r.openInterest) if np.isfinite(r.openInterest) else 0)
        except Exception as ex:
            return t, None
    out = {}
    with ThreadPoolExecutor(6) as ex:
        for t, v in ex.map(one, tickers):
            if v: out[t] = v
    df = pd.DataFrame(out).T
    df["iv_rv"] = df.iv.astype(float) / df.rv20.astype(float)
    print(f"chains for {len(df)} tickers; median IV/RV20 {df.iv_rv.median():.2f}; affordable (ask<=$85): {(df.ask_usd <= 85).sum()}")
    print(df.sort_values("ask_usd").head(60).round(3).to_string())
    save("chains", df.round(4).to_dict("index"))
    return df


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "fetch": fetch()
    elif cmd == "run": run()
    elif cmd == "chains": chains()
    elif cmd == "all":
        if not CACHE.exists(): fetch()
        run(); chains()
    else: print(__doc__)
