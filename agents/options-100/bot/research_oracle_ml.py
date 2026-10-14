#!/usr/bin/env python3
"""Research: (1) ORACLE / break-even map -- if we could call direction with accuracy p, what would each option structure earn?
             (2) a serious pooled ML direction model (many assets, strict walk-forward) -- what accuracy does it actually reach?

  python3 bot/research_oracle_ml.py calib    # 0DTE implied-move calibration (option_snaps + VIX1D) and realized/implied by VIX bucket
  python3 bot/research_oracle_ml.py oracle   # PART 1: EV vs accuracy, break-even accuracy, $170 bankroll sim, VIX buckets
  python3 bot/research_oracle_ml.py fetch    # yfinance daily max-history for ~100 liquid optionable names -> data/research_ml_cache.pkl
  python3 bot/research_oracle_ml.py ml       # PART 2: pooled walk-forward LR + HistGradientBoosting, 4 targets
  python3 bot/research_oracle_ml.py map      # map ML confident buckets onto PART 1 and simulate option P&L vs buy-and-hold / always-calls
  python3 bot/research_oracle_ml.py oracle_sens   # 0DTE pricing live/rich + term IV/VIX 0.6/1.0 sensitivities
  python3 bot/research_oracle_ml.py all

Results -> $ORACLE_ML_OUT/research_oracle_ml_results.json (+ research_ml_preds.pkl); default = system temp dir. Write-up: research/oracle_ml.md.
Read-only on data/market.db. Never places orders.
"""
import socket as _sk
_gai = _sk.getaddrinfo
_sk.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, _sk.AF_INET, *a, **k)   # IPv6 times out on this machine
import os, sys, json, math, pickle, sqlite3, tempfile, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "market.db"
DIR_CACHE = ROOT / "data" / "research_direction_cache.pkl"
ML_CACHE = ROOT / "data" / "research_ml_cache.pkl"
_OUTDIR = Path(os.environ.get("ORACLE_ML_OUT", tempfile.gettempdir()))   # results/preds kept OUT of the repo (set ORACLE_ML_OUT to keep)
PREDS = _OUTDIR / "research_ml_preds.pkl"
OUT = _OUTDIR / "research_oracle_ml_results.json"
END = pd.Timestamp("2026-10-13")          # last complete session (10-14 bar is intraday)
START = pd.Timestamp("2007-01-01")        # oracle sample start (VIX-era, IWM/QQQ post-split, pre-GFC included)
ACC = [0.50, 0.52, 0.55, 0.58, 0.60, 0.65, 0.70, 0.80, 1.00]

# ---------- pricing assumptions (stated in research/oracle_ml.md) ----------
IVR_TERM = 0.85      # SPY ATM IV / VIX for 1-4 week tenors (long-run norm ~0.85; Oct-2026 snapshots show ~0.6 -> sensitivity)
SKEW = 5.0           # term options: IV(K) = IV_atm * (1 - SKEW*ln(K/S))  (same as research_direction.py)
SKEW0_PUT, SKEW0_CALL = 1.10, 0.95    # 0DTE 0.30-delta wing IV vs ATM (put wing rich, call wing cheap)
# full bid-ask width as a fraction of mid; we pay HALF on entry and half on exit (exit cost only on remaining value)
SPREAD = {  # (0DTE ATM, 0DTE 0.30d, 1-4wk ATM) -- SPY/QQQ/IWM from option_snaps medians (Oct 2026); XSP assumed wider
    "SPY": (0.014, 0.03, 0.006), "QQQ": (0.011, 0.025, 0.006), "IWM": (0.03, 0.06, 0.016), "XSP": (0.04, 0.08, 0.03)}
FEE = 0.03           # $/contract/side regulatory+clearing; per-share = FEE/100. Matters only for XSP (premium ~$24)
VIX_M = [(12, 1.05), (14.5, 1.00), (18, 1.02), (22.5, 1.11), (27.5, 1.15), (35, 1.25), (60, 1.35)]  # 0DTE IV/VIX shape from VIX1D


def db():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)


def load_daily(c, sym):
    d = pd.read_sql("SELECT ts, open, high, low, close, adj_close, volume FROM bars WHERE symbol=? AND interval='1d' ORDER BY ts",
                    c, params=(sym,), parse_dates=["ts"]).set_index("ts")
    d = d[~d.index.duplicated(keep="last")]
    d = d[d.index <= END]
    d["adj_close"] = d["adj_close"].fillna(d["close"])
    return d


def save(key, val):
    J = json.load(open(OUT)) if OUT.exists() else {}
    J[key] = val
    json.dump(J, open(OUT, "w"), indent=1, default=float)


def ncdf(x):
    from scipy.special import ndtr
    return ndtr(np.asarray(x, float))


def bs(S, K, sd, call=True):
    """Black-Scholes (r=0) with total sd = sigma*sqrt(T) as a fraction. Vectorised."""
    S, K, sd = (np.asarray(a, float) for a in (S, K, sd))
    intr = np.maximum(S - K, 0) if call else np.maximum(K - S, 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(S / K) + 0.5 * sd ** 2) / sd
        d2 = d1 - sd
        px = S * ncdf(d1) - K * ncdf(d2) if call else K * ncdf(-d2) - S * ncdf(-d1)
    return np.where(sd > 1e-9, px, intr)


# =====================================================================================================================
# 0DTE calibration
# =====================================================================================================================
def var_profile(c):
    """Share of the session's variance remaining at each hourly bar start (U-shape), from SPY 1h bars 2023-11+."""
    h = pd.read_sql("SELECT ts, open, close FROM bars WHERE symbol='SPY' AND interval='1h' ORDER BY ts", c)
    h["t"] = h.ts.str[11:16]
    h["r2"] = np.log(h.close / h.open) ** 2
    v = h.groupby("t").r2.mean()
    v = v[[t for t in v.index if "09:30" <= t <= "15:30"]]
    rem = v[::-1].cumsum()[::-1] / v.sum()
    return rem  # index '09:30','10:30',...


def f_at(rem, hhmm):
    """remaining-variance fraction at clock time hh:mm (linear within the hour bar)."""
    keys = list(rem.index); mins = [int(k[:2]) * 60 + int(k[3:]) for k in keys] + [960]
    vals = list(rem.values) + [0.0]
    m = int(hhmm[:2]) * 60 + int(hhmm[3:])
    return float(np.interp(m, mins, vals))


def vix_mult(v):
    xs, ys = zip(*VIX_M)
    return np.interp(v, xs, ys)


def calib(verbose=True):
    c = db()
    rem = var_profile(c)
    vix = load_daily(c, "^VIX")["close"]
    d = pd.read_sql("SELECT ts,symbol,expiry,type,strike,bid,ask,underlying FROM option_snaps "
                    "WHERE length(ts)=16 AND substr(ts,1,10)=expiry AND bid>0 AND ask>0", c)
    d["mid"] = (d.bid + d.ask) / 2
    p = d.pivot_table(index=["ts", "symbol", "strike"], columns="type", values="mid").dropna().reset_index()
    p = p.merge(d.groupby(["ts", "symbol"]).underlying.first().reset_index())
    p["ad"] = (p.strike - p.underlying).abs()
    p = p.loc[p.groupby(["ts", "symbol"]).ad.idxmin()]
    p["hhmm"] = p.ts.str[11:16]
    p = p[(p.hhmm >= "09:40") & (p.hhmm <= "15:15")]
    p["f"] = p.hhmm.map(lambda t: f_at(rem, t))
    p["vprev"] = p.ts.str[:10].map(lambda x: float(vix[vix.index < x].iloc[-1]))
    p["em"] = (p["call"] + p["put"]) / p.underlying      # ATM straddle = risk-neutral E|move| to close
    p["k"] = p.em / (p.vprev / 100 / math.sqrt(252) * np.sqrt(p.f) * vix_mult(p.vprev))
    p["early"] = p.hhmm <= "11:00"
    K = p.groupby("symbol").k.median().to_dict()
    Ke = p[p.early].groupby("symbol").k.median().to_dict()
    res = {"var_remaining": rem.round(4).to_dict(), "k_all": K, "k_early": Ke, "n": p.groupby("symbol").size().to_dict(),
           "snap_days": sorted(p.ts.str[:10].unique().tolist())}
    # realized / implied E|move| open->close by VIX bucket, using k_SPY and relative-RV scaling for QQQ/IWM
    spy = load_daily(c, "SPY")
    kfall = {}
    for sym in ("SPY", "QQQ", "IWM"):      # per-symbol fair k so realized/implied = 1 in every VIX bucket (2007-2026)
        D = build_oracle_frame(c, sym, K["SPY"], spy=spy, vix=vix)
        D = D[(D.index >= START) & (D.index <= END)]
        D["b"] = pd.cut(D.vix, [0, 13, 16, 20, 30, 100])
        kfall[sym] = [(float(x.vix.mean()), float(x.oc.abs().mean() / (x.relvol * x.vix / 100 / math.sqrt(252)).mean()))
                      for b, x in D.groupby("b", observed=True)]
    res["kfair"] = kfall
    rr = {}
    for sym, zm in (("SPY", "live"), ("QQQ", "live"), ("IWM", "live"), ("SPY", "fair"), ("QQQ", "fair"), ("IWM", "fair"),
                    ("SPY", "rich")):
        D = build_oracle_frame(c, sym, K["SPY"], spy=spy, vix=vix, zmode=zm, kfair=kfall[sym])
        D = D[D.index >= START]
        D["rr"] = D.oc.abs() / D.em0
        D["b"] = pd.cut(D.vix, [0, 13, 16, 20, 30, 100])
        g = D.groupby("b", observed=True)
        sym_ = sym; sym = f"{sym_}|{zm}"
        rr[sym] = {str(b): dict(n=int(len(x)), real=float(x.oc.abs().mean() * 100), impl=float(x.em0.mean() * 100),
                                ratio=float(x.oc.abs().mean() / x.em0.mean()),
                                ratio_2023=float(x[x.index >= "2023-11-01"].oc.abs().mean() / x[x.index >= "2023-11-01"].em0.mean())
                                if (x.index >= "2023-11-01").sum() > 10 else None) for b, x in g}
        rr[sym]["ALL"] = dict(n=len(D), ratio=float(D.oc.abs().mean() / D.em0.mean()))
        if sym_ != "SPY":
            res[f"relvol_now_{sym_}"] = float(D.relvol.iloc[-1])
    res["realized_over_implied"] = rr
    save("calib", res)
    if verbose:
        print("remaining-variance profile:", {k: round(v, 3) for k, v in rem.items()})
        for s_, kf in kfall.items(): print("kfair", s_, "(VIX, k):", [(round(a, 1), round(b, 3)) for a, b in kf])
        print("k (0DTE E|move| / [VIX/sqrt252*sqrt(f)*m(VIX)]): all", {k: round(v, 3) for k, v in K.items()},
              " early", {k: round(v, 3) for k, v in Ke.items()}, " n", res["n"])
        print("relative-vol scaling now: QQQ", round(res["relvol_now_QQQ"], 2), " IWM", round(res["relvol_now_IWM"], 2),
              " vs snapshot k ratio QQQ", round(K["QQQ"] / K["SPY"], 2), " IWM", round(K["IWM"] / K["SPY"], 2))
        for s, t in rr.items():
            print(s, "realized/implied E|open->close| by VIX:", {b: (round(x["ratio"], 2), x["n"]) for b, x in t.items() if b != "ALL"},
                  "ALL", round(t["ALL"]["ratio"], 2))
    return res


# =====================================================================================================================
# PART 1: oracle
# =====================================================================================================================
def build_oracle_frame(c, sym, k_spy, spy=None, vix=None, zmode="live", kfair=None):
    """Per-day frame: open/close, multi-day closes, VIX (prev close), relative vol vs SPY, implied 0DTE E|move| at the open."""
    d = load_daily(c, sym)
    spy = load_daily(c, "SPY") if spy is None else spy
    vix = load_daily(c, "^VIX")["close"] if vix is None else vix
    D = pd.DataFrame(index=d.index)
    D["open"], D["close"] = d.open, d.close
    a = d.adj_close
    D["oc"] = d.close / d.open - 1
    D["vix"] = vix.shift(1).reindex(D.index).ffill()          # previous close: known at the open
    D["vix_c"] = vix.reindex(D.index).ffill()                 # today's close: known at the close (term trades enter at close)
    lr = np.log(a).diff(); ls = np.log(spy.adj_close).diff().reindex(D.index)
    rel = (lr.rolling(60).std() / ls.rolling(60).std()).shift(1)
    D["relvol"] = 1.0 if sym == "SPY" else rel.clip(0.6, 3.0)
    base = D.relvol * D.vix / 100 / math.sqrt(252)
    if zmode == "live":      # repo evidence: live/Yahoo 0DTE straddles at VIX~15 (Oct 2026), VIX1D-shaped across VIX levels
        D["em0"] = k_spy * vix_mult(D.vix) * base
    elif zmode == "fair":    # E|move| implied = SPY realized mean |open->close| in that VIX bucket (2007-2026), x relvol
        xs, ys = zip(*kfair)
        D["em0"] = np.interp(D.vix, xs, ys) * base
    else:                    # "rich": research_direction.py convention, session sd = 0.8 x VIX/sqrt(252)
        D["em0"] = 0.8 * 0.7979 * base                                                   # implied E|move| open->close
    for n in (5, 10, 20):
        D[f"cc{n}"] = a.shift(-n) / a - 1
    return D.dropna(subset=["vix", "relvol"])


def leg_returns(S0, S1, K, sd, call, half_in, half_out, fee_ps=0.0):
    """Net return on premium of a long option bought at mid*(1+half_in) and settled at intrinsic(S1) less half_out."""
    p0 = bs(S0, K, sd, call)
    pay = np.maximum(S1 - K, 0) if call else np.maximum(K - S1, 0)
    cost0 = p0 * (1 + half_in) + fee_ps
    val1 = np.maximum(pay * (1 - half_out) - np.where(pay > 0, fee_ps, 0), 0)
    return val1 / cost0 - 1, p0


def spread_returns(S0, S1, K1, K2, sd1, sd2, call, half_in, half_out, fee_ps=0.0):
    p1, q1 = bs(S0, K1, sd1, call), bs(S0, K2, sd2, call)
    pay = (np.clip(S1 - K1, 0, K2 - K1) if call else np.clip(K1 - S1, 0, K1 - K2))
    debit = (p1 - q1) + half_in * (p1 + q1) + 2 * fee_ps
    credit = np.maximum(pay * (1 - half_out) - np.where(pay > 0, 2 * fee_ps, 0), 0)
    return credit / debit - 1


def structure_returns(D, sym, venue, k_spy, rem, hourly=None, ivr=IVR_TERM, zero_mult=1.0):
    """Returns dict name -> DataFrame(index=date, rc, rp, up, mv (signed underlying move), vix).
    venue = cost table key (SPY/QQQ/IWM/XSP). XSP = SPY pricing (/10) with XSP spreads, fees and cash settlement."""
    sp0, spd, spt = SPREAD[venue]
    xsp = venue == "XSP"
    scale = 0.1 if xsp else 1.0
    fee_ps = FEE / 100
    out = {}
    S0 = D.open.values * scale; S1 = D.close.values * scale
    sd0 = D.em0.values / 0.7979 * zero_mult                     # session sd at the open
    ex = 0.0 if xsp else 0.005                                  # exit: XSP cash-settles; ETF ITM sold near close at ~0.5% haircut
    up = (D.oc.values >= 0)

    def pack(name, rc, rp, upv, mv, idx, vixv, prem=None):
        out[name] = pd.DataFrame({"rc": rc, "rp": rp, "up": upv, "mv": mv, "vix": vixv, **({"prem": prem} if prem is not None else {})},
                                 index=idx).replace([np.inf, -np.inf], np.nan).dropna(subset=["rc", "rp", "mv"])

    # 0DTE ATM at the open, hold to close
    rc, pc = leg_returns(S0, S1, S0, sd0, True, sp0 / 2, ex, fee_ps)
    rp, _ = leg_returns(S0, S1, S0, sd0, False, sp0 / 2, ex, fee_ps)
    pack("0DTE ATM @open", rc, rp, up, D.oc.values, D.index, D.vix.values, pc * (1 + sp0 / 2) / S0)
    # 0DTE 0.30 delta (strike from ATM sd; wing IV skew)
    zc = 0.5244   # N(d1)=0.30 -> d1=-0.5244
    sdc, sdp = sd0 * SKEW0_CALL, sd0 * SKEW0_PUT
    Kc = S0 * np.exp(zc * sdc + 0.5 * sdc ** 2); Kp = S0 * np.exp(-zc * sdp + 0.5 * sdp ** 2)
    rc, pc = leg_returns(S0, S1, Kc, sdc, True, spd / 2, ex, fee_ps)
    rp, _ = leg_returns(S0, S1, Kp, sdp, False, spd / 2, ex, fee_ps)
    pack("0DTE 0.30d @open", rc, rp, up, D.oc.values, D.index, D.vix.values, pc * (1 + spd / 2) / S0)
    # 0DTE debit spread ATM/+-1%
    K2c, K2p = S0 * 1.01, S0 * 0.99
    rc = spread_returns(S0, S1, S0, K2c, sd0, sd0 * SKEW0_CALL, True, sp0 / 2, ex, fee_ps)
    rp = spread_returns(S0, S1, S0, K2p, sd0, sd0 * SKEW0_PUT, False, sp0 / 2, ex, fee_ps)
    pack("0DTE ATM/1% spread", rc, rp, up, D.oc.values, D.index, D.vix.values,
         (bs(S0, S0, sd0, True) - bs(S0, K2c, sd0 * SKEW0_CALL, True)) / S0)
    # intraday entries (hourly bars, 2023-11+): 10:30 / 12:30 / 14:30 bar opens -> close
    if hourly is not None:
        for hh in ("10:30", "12:30", "14:30"):
            h = hourly[hourly.t == hh].set_index("d")
            idx = D.index[D.index.isin(h.index)]
            if not len(idx): continue
            s0 = h.loc[idx, "open"].values * scale; s1 = D.loc[idx, "close"].values * scale
            sd = D.loc[idx, "em0"].values / 0.7979 * math.sqrt(f_at(rem, hh)) * zero_mult
            sw = sp0 * (1 + {"10:30": 0.2, "12:30": 0.6, "14:30": 1.5}[hh])     # spreads widen (as % of mid) as premium decays
            rc, pc = leg_returns(s0, s1, s0, sd, True, sw / 2, ex, fee_ps)
            rp, _ = leg_returns(s0, s1, s0, sd, False, sw / 2, ex, fee_ps)
            mv = s1 / s0 - 1
            pack(f"0DTE ATM @{hh}", rc, rp, mv >= 0, mv, idx, D.loc[idx, "vix"].values, pc / s0)
    # term structures: bought at the close, held to expiry (horizon = tenor). IV = ivr * VIX(close) * relvol
    Sc = D.close.values * scale
    for name, n, cal, width in (("1wk ATM", 5, 7, None), ("2wk ATM", 10, 14, None), ("4wk ATM", 20, 28, None),
                                ("1wk ATM/1% spread", 5, 7, 0.01), ("2wk ATM/1% spread", 10, 14, 0.01)):
        mv = D[f"cc{n}"].values
        S1t = Sc * (1 + mv)
        iv = ivr * D.vix_c.values / 100 * D.relvol.values
        sd = iv * math.sqrt(cal / 365)
        if width is None:
            rc, prem = leg_returns(Sc, S1t, Sc, sd, True, spt / 2, ex / 2, fee_ps)
            rp, _ = leg_returns(Sc, S1t, Sc, sd, False, spt / 2, ex / 2, fee_ps)
        else:
            rc = spread_returns(Sc, S1t, Sc, Sc * (1 + width), sd, sd * (1 - SKEW * math.log(1 + width)), True, spt / 2, ex / 2, fee_ps)
            rp = spread_returns(Sc, S1t, Sc, Sc * (1 - width), sd, sd * (1 - SKEW * math.log(1 - width)), False, spt / 2, ex / 2, fee_ps)
            prem = bs(Sc, Sc, sd, True) - bs(Sc, Sc * (1 + width), sd * (1 - SKEW * math.log(1 + width)), True)
        pack(name, rc, rp, mv >= 0, mv, D.index, D.vix_c.values, prem / Sc)
    return out


def acc_profile(mv, p, mode, rng=None):
    """per-trade probability of being right. 'random': p everywhere. 'bigger': accuracy rises with |move|, mean = p."""
    n = len(mv)
    if mode == "random" or p in (0.5, 1.0):
        return np.full(n, p)
    a = np.abs(mv); w = a / a.mean()
    lo, hi = 0.0, 50.0
    for _ in range(60):                       # find c so mean(clip(0.5 + c*(p-0.5)*w, 0, 1)) = p
        cc = (lo + hi) / 2
        m = np.clip(0.5 + cc * (p - 0.5) * w, 0, 1).mean()
        lo, hi = (cc, hi) if m < p else (lo, cc)
    return np.clip(0.5 + cc * (p - 0.5) * w, 0, 1)


def ev_at(T, p, mode):
    rc, rp, up = T.rc.values, T.rp.values, T.up.values
    rC = np.where(up, rc, rp); rW = np.where(up, rp, rc)
    q = acc_profile(T.mv.values, p, mode)
    return float(np.mean(q * rC + (1 - q) * rW))


def breakeven(T, mode):
    lo, hi = 0.0, 1.0
    if ev_at(T, 1.0, mode) < 0: return None
    if ev_at(T, 0.0 if mode == "random" else 0.5, mode) > 0: return 0.0 if mode == "random" else 0.5
    for _ in range(40):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if ev_at(T, m, mode) < 0 else (lo, m)
    return (lo + hi) / 2


def bankroll(T, p, mode, per_year, frac=0.20, start=170.0, n=4000, seed=11, ruin=20.0):
    rng = np.random.default_rng(seed)
    rc, rp, up = T.rc.values, T.rp.values, T.up.values
    q = acc_profile(T.mv.values, p, mode)
    k = int(per_year)
    idx = rng.integers(0, len(rc), size=(n, k))
    right = rng.random((n, k)) < q[idx]
    r = np.where(right == up[idx], rc[idx], rp[idx])        # right & up -> call; wrong & down -> call (predicted up)
    eq = np.full(n, start); dead = np.zeros(n, bool)
    for j in range(k):
        eq = np.where(dead, eq, eq * (1 + frac * np.maximum(r[:, j], -1)))
        dead |= eq < ruin
    return dict(median=float(np.median(eq)), p10=float(np.percentile(eq, 10)), p90=float(np.percentile(eq, 90)),
                p_grow=float((eq > start).mean()), p_ruin=float(dead.mean()))


def kelly(T, p, mode, grid=(0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30, 0.40, 0.60)):
    """growth-optimal fraction of equity per trade (expected log growth, exact over the empirical distribution)."""
    rc, rp, up = T.rc.values, T.rp.values, T.up.values
    q = acc_profile(T.mv.values, p, mode)
    rC = np.maximum(np.where(up, rc, rp), -1); rW = np.maximum(np.where(up, rp, rc), -1)
    best = (0.0, 0.0)
    for f in grid:
        g = float(np.mean(q * np.log1p(f * rC) + (1 - q) * np.log1p(f * rW)))
        if g > best[1]: best = (f, g)
    return {"f": best[0], "g_per_trade": best[1]}




def bankroll_whole(T, p, mode, per_year, spot_now, mult, frac=0.20, start=170.0, n=3000, seed=11):
    """Whole contracts: each trade buys floor(frac*equity / contract cost); 0 affordable -> the trade is skipped.
    Contract cost = premium as % of spot at that date x today's spot x mult (100 for SPY/QQQ/IWM, 10 for XSP)."""
    rng = np.random.default_rng(seed)
    rc, rp, up, pf = T.rc.values, T.rp.values, T.up.values, T.prem.values
    q = acc_profile(T.mv.values, p, mode)
    k = int(per_year)
    idx = rng.integers(0, len(rc), size=(n, k))
    right = rng.random((n, k)) < q[idx]
    r = np.maximum(np.where(right == up[idx], rc[idx], rp[idx]), -1)
    cost = pf[idx] * spot_now * mult
    eq = np.full(n, start); traded = np.zeros(n)
    for j in range(k):
        nc = np.floor(frac * eq / cost[:, j])
        eq = eq + nc * cost[:, j] * r[:, j]
        traded += nc > 0
    return dict(median=float(np.median(eq)), p_grow=float((eq > start).mean()), p_halve=float((eq < start / 2).mean()),
                trade_share=float(traded.mean() / k))


PER_YEAR = {"0DTE": 252, "1wk": 50, "2wk": 25, "4wk": 12}


def per_year(name):
    for k, v in PER_YEAR.items():
        if name.startswith(k): return v
    return 252


def oracle(verbose=True, ivr=IVR_TERM, zero_mult=1.0, tag="fair", zmode="fair", bank=True):
    J = json.load(open(OUT)) if OUT.exists() else {}
    cal = J.get("calib") or calib(verbose=False)
    k_spy = cal["k_all"]["SPY"]
    c = db()
    rem = pd.Series(cal["var_remaining"])
    spy, vix = load_daily(c, "SPY"), load_daily(c, "^VIX")["close"]
    res = {}
    for sym, venue in (("SPY", "XSP"), ("SPY", "SPY"), ("QQQ", "QQQ"), ("IWM", "IWM")):
        D = build_oracle_frame(c, sym, k_spy, spy=spy, vix=vix, zmode=zmode, kfair=cal["kfair"][sym])
        D = D[(D.index >= START) & (D.index <= END)]
        hr = pd.read_sql("SELECT ts, open FROM bars WHERE symbol=? AND interval='1h' ORDER BY ts", c, params=(sym,))
        hr["d"] = pd.to_datetime(hr.ts.str[:10]); hr["t"] = hr.ts.str[11:16]
        S = structure_returns(D, sym, venue, k_spy, rem, hourly=hr, ivr=ivr, zero_mult=zero_mult)
        spot_now = float(D.close.iloc[-1]); mult = 10.0 if venue == "XSP" else 100.0
        R = {}
        for name, T in S.items():
            T = T[T.index <= END]
            row = {"n": len(T), "start": str(T.index[0].date()),
                   "ev_call_always": float(T.rc.mean()), "ev_put_always": float(T.rp.mean()),
                   "ev": {mode: {str(p): ev_at(T, p, mode) for p in ACC} for mode in ("random", "bigger")},
                   "breakeven": {mode: breakeven(T, mode) for mode in ("random", "bigger")}}
            # by VIX bucket (random errors)
            T2 = T.copy(); T2["b"] = pd.cut(T2.vix, [0, 13, 16, 20, 30, 100])
            row["vix"] = {str(b): {"n": len(x), "be": breakeven(x, "random"), "ev60": ev_at(x, 0.60, "random"),
                                   "ev55": ev_at(x, 0.55, "random"), "be_big": breakeven(x, "bigger")}
                          for b, x in T2.groupby("b", observed=True) if len(x) > 30}
            row["2015+"] = {"be": breakeven(T[T.index >= "2015-01-01"], "random"), "ev60": ev_at(T[T.index >= "2015-01-01"], 0.6, "random")}
            T23 = T[T.index >= "2023-11-08"]
            row["2023-11+"] = {"be": breakeven(T23, "random"), "ev60": ev_at(T23, 0.6, "random"), "call": float(T23.rc.mean()), "put": float(T23.rp.mean())}
            row["2022+"] = {"be": breakeven(T[T.index >= "2022-01-01"], "random"), "ev60": ev_at(T[T.index >= "2022-01-01"], 0.6, "random")}
            if venue == "XSP" and bank:
                T15 = T[T.index >= "2015-01-01"]
                row["kelly"] = {str(p): kelly(T15, p, "random") for p in ACC}
            if bank:
                T15 = T[T.index >= "2015-01-01"]
                cost_now = float(T15.prem[T15.index >= "2025-10-01"].median() * spot_now * mult)
                row["contract_cost_$"] = cost_now
                row["min_capital_$"] = cost_now / 0.20
                row["bank_whole"] = {str(int(st)): {str(p): bankroll_whole(T15, p, "random", per_year(name), spot_now, mult, start=st)
                                                   for p in (0.5, 0.55, 0.6, 0.65, 0.7)} for st in (170.0, 1000.0, 5000.0)}
                row["bank"] = {mode: {str(p): bankroll(T15, p, mode, per_year(name)) for p in ACC} for mode in ("random", "bigger")}
                if "prem" in T.columns:
                    row["prem_median_$"] = float(T.prem[T.index >= "2025-10-01"].median() * 100)
            R[name] = row
        res[f"{sym}|{venue}"] = R
        if verbose:
            print(f"\n=== {sym} priced as {venue} ({tag}) ===")
            print(f"{'structure':22s} {'n':>5s} {'call':>6s} {'put':>6s} | " + " ".join(f"{int(p*100):>5d}" for p in ACC) + " | BE-rand BE-big  BE15+ BE22+ BE23-11+")
            for name, row in R.items():
                ev = row["ev"]["random"]
                be, bb = row["breakeven"]["random"], row["breakeven"]["bigger"]
                f = lambda x: f"{x*100:5.1f}" if x is not None else "  n/a"
                print(f"{name:22s} {row['n']:5d} {row['ev_call_always']*100:6.1f} {row['ev_put_always']*100:6.1f} | " +
                      " ".join(f"{ev[str(p)]*100:5.0f}" for p in ACC) + f" | {f(be)}  {f(bb)}  {f(row['2015+']['be'])} {f(row['2022+']['be'])} {f(row['2023-11+']['be'])}")
            if venue == "XSP" and bank:
                print("  bankroll (2015+ bootstrap, $170, 20% of equity per trade, 1y), median / P(grow) / P(ruin) at each accuracy [random errors]:")
                for name, row in R.items():
                    b = row["bank"]["random"]
                    print(f"  {name:22s} " + " ".join(f"{int(float(p)*100)}%:${x['median']:.0f}/{x['p_grow']*100:.0f}/{x['p_ruin']*100:.0f}" for p, x in b.items()))
                pass
            if bank:
                print(f"  {sym} as {venue}: contract cost now / MIN CAPITAL (cost / 20%) / whole-contract 1y bankroll median & P(grow) at 50/55/60/65/70% for $170 | $1k | $5k:")
                for name, row in R.items():
                    bw = row["bank_whole"]
                    print(f"  {name:22s} ${row['contract_cost_$']:7.0f} / ${row['min_capital_$']:7.0f} | " + " | ".join(
                        st + ": " + " ".join(f"${x['median']:.0f}/{x['p_grow']*100:.0f}" for x in bw[st].values()) for st in bw))
            if venue == "XSP" and bank:
                print("  growth-optimal (Kelly) fraction per trade / expected log-growth per year at each accuracy:")
                for name, row in R.items():
                    print(f"  {name:22s} " + " ".join(f"{int(float(p)*100)}%:{x['f']:.2f}/{x['g_per_trade']*per_year(name):+.2f}" for p, x in row["kelly"].items()))
                print("  break-even by VIX bucket (random / bigger-moves):")
                for name, row in R.items():
                    print(f"  {name:22s} " + "  ".join(f"{b}: {f(x['be'])}/{f(x['be_big'])} (n{x['n']})" for b, x in row["vix"].items()))
    save(f"oracle_{tag}", res)
    return res


def buyhold(verbose=True):
    """1-year buy-and-hold SPY from $170 (bootstrap of 2015+ daily returns, and the actual rolling 1y distribution)."""
    c = db(); a = load_daily(c, "SPY").adj_close
    r = a.pct_change().dropna(); r15 = r[r.index >= "2015-01-01"]
    roll = (a.shift(-252) / a - 1).dropna(); roll15 = roll[roll.index >= "2015-01-01"]
    out = {"median_end_2015+": float(170 * (1 + roll15.median())), "p_grow_2015+": float((roll15 > 0).mean()),
           "p10": float(170 * (1 + roll15.quantile(0.1))), "p90": float(170 * (1 + roll15.quantile(0.9))),
           "median_end_all": float(170 * (1 + roll[roll.index >= START].median())),
           "p_grow_all": float((roll[roll.index >= START] > 0).mean())}
    save("buyhold", out)
    if verbose: print("buy-and-hold SPY 1y from $170:", {k: round(v, 3) for k, v in out.items()})
    return out


# =====================================================================================================================
# PART 2: pooled ML
# =====================================================================================================================
UNIVERSE_EXTRA = [  # ~100 liquid optionable large caps + ETFs not already in market.db
    "JPM", "BAC", "WFC", "C", "GS", "MS", "V", "MA", "AXP", "BRK-B", "SCHW", "BLK",
    "XOM", "CVX", "COP", "SLB", "OXY", "EOG",
    "JNJ", "PFE", "MRK", "ABBV", "LLY", "UNH", "CVS", "AMGN", "GILD", "BMY", "TMO", "ABT", "MDT",
    "PG", "KO", "PEP", "WMT", "COST", "HD", "LOW", "MCD", "NKE", "SBUX", "TGT", "DIS", "NFLX", "CMCSA", "T", "VZ",
    "INTC", "AMD", "QCOM", "TXN", "MU", "CSCO", "ORCL", "CRM", "ADBE", "IBM", "NOW", "AMAT", "LRCX", "UBER", "PYPL",
    "SHOP", "PLTR", "COIN", "MSTR", "BA", "CAT", "DE", "GE", "HON", "LMT", "RTX", "UPS", "FDX", "MMM", "F", "GM",
    "EEM", "EFA", "FXI", "EWZ", "EWJ", "GLD", "SLV", "GDX", "XBI", "IBB", "XRT", "XOP", "HYG", "LQD", "IEF", "VNQ",
    "ARKK", "KWEB", "SOXX", "XLB", "XLP", "SPY", "QQQ", "IWM"]
DB_TRADABLE = ["AAPL", "AMZN", "AVGO", "DIA", "GOOGL", "ITB", "IWM", "IYT", "KRE", "META", "MSFT", "NVDA", "QQQ", "RINF", "SMH",
               "SPY", "TIP", "TLT", "TSLA", "UGA", "USO", "XHB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLRE", "XLU", "XLV", "XLY"]
BROAD = {"SPY", "QQQ", "IWM", "DIA"}
SECTOR = {"XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY", "SMH", "SOXX", "KRE", "ITB", "XHB", "IYT",
          "XBI", "IBB", "XRT", "XOP", "GDX", "VNQ", "ARKK"}
MACRO_ETF = {"TLT", "TIP", "IEF", "HYG", "LQD", "GLD", "SLV", "USO", "UGA", "RINF", "EEM", "EFA", "FXI", "EWZ", "EWJ", "KWEB"}


def aclass(s):
    return "broad" if s in BROAD else "sector" if s in SECTOR else "macro/intl" if s in MACRO_ETF else "stock"


def fetch(verbose=True):
    import yfinance as yf
    have = pickle.load(open(ML_CACHE, "rb")) if ML_CACHE.exists() else {}
    need = [s for s in UNIVERSE_EXTRA if s not in have and s not in ("SPY", "QQQ", "IWM")]
    for i in range(0, len(need), 20):
        chunk = need[i:i + 20]
        for attempt in range(3):
            try:
                df = yf.download(chunk, period="max", auto_adjust=False, group_by="ticker", progress=False, threads=True)
                break
            except Exception as e:
                print("retry", e); time.sleep(5)
        for s in chunk:
            try:
                x = df[s].dropna(how="all")
                x = x.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Adj Close": "adj_close", "Volume": "volume"})
                if len(x) > 500:
                    x.index = pd.to_datetime(x.index).tz_localize(None)
                    have[s] = x[["open", "high", "low", "close", "adj_close", "volume"]].astype("float64")
            except Exception as e:
                print("skip", s, e)
        pickle.dump(have, open(ML_CACHE, "wb"))
        if verbose: print(f"fetched {min(i+20, len(need))}/{len(need)}; cache {len(have)} symbols")
    return have


def rsi(c, n):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def sym_features(d, spy_lr):
    """Per-symbol features known at the close of day t (+ next-day gap, for the open->close target only)."""
    d = d[(d.close > 0) & (d.open > 0)].copy()
    af = d.adj_close / d.close
    o, h, l, c, v = d.open * af, d.high * af, d.low * af, d.adj_close, d.volume.replace(0, np.nan)
    lr = np.log(c).diff()
    F = pd.DataFrame(index=d.index)
    for n in (1, 2, 3, 5, 10, 20, 60, 120, 250):
        F[f"r{n}"] = np.log(c / c.shift(n))
    F["oc0"] = np.log(c / o); F["gap0"] = np.log(o / c.shift(1))
    F["rng"] = np.log(h / l); F["clv"] = ((c - l) / (h - l)).clip(0, 1)
    for n in (5, 20, 60):
        F[f"rv{n}"] = lr.rolling(n).std()
    F["rv5_60"] = F.rv5 / F.rv60; F["rv20_60"] = F.rv20 / F.rv60
    F["z1"] = F.r1 / F.rv60; F["z5"] = F.r5 / (F.rv60 * math.sqrt(5))
    F["rsi2"] = rsi(c, 2); F["rsi14"] = rsi(c, 14)
    for n in (10, 20, 50, 200):
        F[f"dma{n}"] = np.log(c / c.rolling(n).mean())
    F["dd252"] = np.log(c / c.rolling(252, min_periods=60).max())
    F["up252"] = np.log(c / c.rolling(252, min_periods=60).min())
    F["vshock"] = np.log(v / v.rolling(20).mean()); F["v5_60"] = np.log(v.rolling(5).mean() / v.rolling(60).mean())
    s = (lr > 0).astype(int) - (lr < 0).astype(int)
    grp = (s != s.shift()).cumsum(); F["streak"] = s.groupby(grp).cumsum().clip(-8, 8)
    sl = spy_lr.reindex(d.index)
    cov = lr.rolling(60).cov(sl); var = sl.rolling(60).var()
    F["beta60"] = (cov / var).clip(-1, 4)
    F["xr1"] = lr - F.beta60 * sl; F["xr5"] = F.r5 - F.beta60 * sl.rolling(5).sum(); F["xr20"] = F.r20 - F.beta60 * sl.rolling(20).sum()
    # earnings-proximity proxy: days since last abnormal gap (|gap| > 3 sd) and position in a 63-day cycle
    big = (F.gap0.abs() > 3 * F.rv60).astype(float)
    last = pd.Series(np.where(big > 0, np.arange(len(big)), np.nan), index=d.index).ffill()
    F["dsince_shock"] = (np.arange(len(big)) - last).clip(upper=120)
    F["qcycle"] = (F.dsince_shock % 63) / 63
    # targets
    Y = pd.DataFrame(index=d.index)
    Y["oc1"] = np.log(c.shift(-1) / o.shift(-1)); Y["cc1"] = np.log(c.shift(-1) / c); Y["cc5"] = np.log(c.shift(-5) / c)
    Y["gap_next"] = np.log(o.shift(-1) / c)      # feature for oc1 only (known at 09:30 of t+1)
    return F.astype("float32"), Y.astype("float32")


def macro_features(c):
    """Market-level features known at the close of t (late-stamped series lagged one day)."""
    cl = lambda s: load_daily(c, s)["close"]
    spy = load_daily(c, "SPY"); idx = spy.index
    vix = cl("^VIX").reindex(idx).ffill()
    M = pd.DataFrame(index=idx)
    M["vix"] = vix; M["dvix1"] = np.log(vix / vix.shift(1)); M["dvix5"] = np.log(vix / vix.shift(5))
    M["vix_pct"] = vix.rolling(252, min_periods=60).rank(pct=True)
    M["vix_vix3m"] = (vix / cl("^VIX3M").reindex(idx).ffill())
    M["vix9d_vix"] = (cl("^VIX9D").reindex(idx).ffill() / vix)
    M["vvix"] = cl("^VVIX").reindex(idx).ffill(); M["skew"] = cl("^SKEW").reindex(idx).ffill()
    tnx, irx = cl("^TNX").reindex(idx).ffill(), cl("^IRX").reindex(idx).ffill()
    M["tnx"] = tnx; M["dtnx5"] = tnx - tnx.shift(5); M["dirx20"] = irx - irx.shift(20); M["slope"] = tnx - irx
    for s, nm in (("CL=F", "oil"), ("DX-Y.NYB", "dxy"), ("GC=F", "gold")):
        x = np.log(cl(s)).reindex(idx).ffill()
        M[f"{nm}5"] = (x - x.shift(5)).shift(1); M[f"{nm}1"] = (x - x.shift(1)).shift(1)
    tlt = np.log(load_daily(c, "TLT").adj_close).reindex(idx).ffill(); M["tlt5"] = tlt - tlt.shift(5)
    a = np.log(spy.adj_close)
    M["spy_r1"] = a.diff(); M["spy_r5"] = a - a.shift(5); M["spy_r20"] = a - a.shift(20)
    M["spy_rsi2"] = rsi(spy.adj_close, 2); M["spy_dma200"] = a - np.log(spy.adj_close.rolling(200).mean())
    fred = pickle.load(open(DIR_CACHE, "rb"))["fred"] if DIR_CACHE.exists() else {}
    for k, lag in (("BAA10Y", 1), ("T10Y2Y", 1), ("NFCI", 6)):
        if k in fred:
            s = fred[k].copy(); s.index = pd.to_datetime(s.index) + pd.Timedelta(days=lag)
            s = s.reindex(idx.union(s.index)).ffill().reindex(idx)
            M[k.lower()] = s
            if k == "BAA10Y": M["dbaa20"] = s - s.shift(20)
    M["dow"] = idx.dayofweek; M["month"] = idx.month; M["dom"] = idx.day
    ym = pd.Series(idx.to_period("M"), index=idx)
    M["td_to_me"] = ym.groupby(ym).cumcount(ascending=False).values
    M["opex_wk"] = ((idx.dayofweek == 4) & (idx.day >= 15) & (idx.day <= 21)).astype(int)
    M["opex_wk"] = M.opex_wk[::-1].rolling(5, min_periods=1).max()[::-1]
    return M.astype("float32")


def build_panel(verbose=True):
    c = db()
    extra = pickle.load(open(ML_CACHE, "rb")) if ML_CACHE.exists() else {}
    spy = load_daily(c, "SPY"); spy_lr = np.log(spy.adj_close).diff()
    earn = pickle.load(open(DIR_CACHE, "rb")).get("earn", {}) if DIR_CACHE.exists() else {}
    frames = []
    syms = sorted(set(DB_TRADABLE) | set(extra))
    for s in syms:
        d = load_daily(c, s) if s in DB_TRADABLE else extra[s]
        d = d[(d.index >= "1998-01-01") & (d.index <= END)]
        if len(d) < 400: continue
        F, Y = sym_features(d, spy_lr)
        if s in earn and len(earn[s]):       # exact earnings proximity for mega caps (yfinance dates), else NaN
            ed = pd.DatetimeIndex(sorted(pd.to_datetime([x[0] if isinstance(x, (tuple, list)) else x for x in earn[s]])))
            pos = np.searchsorted(ed.values, F.index.values)
            nxt = np.where(pos < len(ed), (ed.values[np.minimum(pos, len(ed) - 1)] - F.index.values) / np.timedelta64(1, "D"), np.nan)
            F["days_to_earn"] = np.clip(nxt, 0, 30).astype("float32")   # dates are announced ~4 weeks ahead -> cap at 30
        else:
            F["days_to_earn"] = np.float32(np.nan)
        F = F.join(Y); F["sym"] = s
        frames.append(F)
    P = pd.concat(frames)
    P.index.name = "date"; P = P.reset_index()
    M = macro_features(c).reset_index().rename(columns={"ts": "date"})
    P = P.merge(M, on="date", how="left")
    P["xs_r1"] = P.r1 - P.groupby("date").r1.transform("mean")
    P["xs_r5"] = P.r5 - P.groupby("date").r5.transform("mean")
    P["xs_r20"] = P.r20 - P.groupby("date").r20.transform("mean")
    P["xs_rank5"] = P.groupby("date").r5.rank(pct=True)
    P["xs_rank20"] = P.groupby("date").r20.rank(pct=True)
    P["spy_gap_next"] = P.date.map(np.log(spy.open.shift(-1) / spy.close).astype("float32"))
    P["aclass"] = P.sym.map(aclass)
    P = P[P.date >= "2000-01-01"]
    if verbose: print(f"panel: {len(P):,} rows, {P.sym.nunique()} symbols, {P.date.min().date()}..{P.date.max().date()}")
    return P


NONFEAT = {"date", "sym", "oc1", "cc1", "cc5", "gap_next", "aclass", "spy_gap_next"}


def walk_forward(P, target, feats, years, model="lr", embargo=5, max_train=600_000, seed=0):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.impute import SimpleImputer
    ycol = "cc1" if target == "big" else target
    D = P.dropna(subset=[ycol])
    if target == "big":
        D = D[D[ycol].abs() > D.rv60]           # next-day |move| > 1 sd (trailing 60d): classify up vs down
    dates = np.sort(D.date.unique())
    preds = []
    rng = np.random.default_rng(seed)
    for yr in years:
        t0 = pd.Timestamp(f"{yr}-01-01"); t1 = pd.Timestamp(f"{yr+1}-01-01")
        i0 = np.searchsorted(dates, np.datetime64(t0))
        cut = dates[max(0, i0 - embargo)]                    # purge: drop the last `embargo` sessions before the test year
        tr = D[D.date < cut]; te = D[(D.date >= t0) & (D.date < t1)]
        if len(te) == 0 or len(tr) < 5000: continue
        if len(tr) > max_train:
            tr = tr.iloc[np.sort(rng.choice(len(tr), max_train, replace=False))]
        use = [f for f in feats if tr[f].notna().mean() > 0.05 and tr[f].nunique() > 1]   # drop features not yet available
        Xtr, ytr = tr[use].values, (tr[ycol].values > 0).astype(int)
        if model == "lr":
            m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.05, max_iter=300))
        else:
            m = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.04, max_leaf_nodes=31, min_samples_leaf=800,
                                               l2_regularization=1.0, max_features=0.5, random_state=seed)
        Xtr = np.clip(np.nan_to_num(Xtr, nan=np.nan, posinf=np.nan, neginf=np.nan), -1e6, 1e6)
        m.fit(Xtr, ytr)
        Xte = np.clip(np.nan_to_num(te[use].values, nan=np.nan, posinf=np.nan, neginf=np.nan), -1e6, 1e6)
        p = m.predict_proba(Xte)[:, 1]
        preds.append(pd.DataFrame({"date": te.date.values, "sym": te.sym.values, "p": p, "y": te[ycol].values,
                                   "aclass": te.aclass.values}))
        if yr == years[-1]:
            last_model = (m, te.sample(min(len(te), 40000), random_state=1), use)
    out = pd.concat(preds)
    return out, last_model


def auc(y, p):
    from sklearn.metrics import roc_auc_score
    try: return float(roc_auc_score(y, p))
    except Exception: return float("nan")


def conf_buckets(pr, qs=(0.05, 0.10, 0.20)):
    """Confidence threshold for each test year = quantile of |p-0.5| over all PRIOR OOS years (no look-ahead).
    First OOS year is skipped. Returns dict q -> boolean mask."""
    pr = pr.copy(); pr["yr"] = pr.date.dt.year; pr["c"] = (pr.p - 0.5).abs()
    masks = {q: np.zeros(len(pr), bool) for q in qs}
    yrs = sorted(pr.yr.unique())
    cvals = pr.c.values; yv = pr.yr.values
    for y in yrs[1:]:
        prior = cvals[yv < y]; cur = yv == y
        for q in qs:
            thr = np.quantile(prior, 1 - q)
            masks[q] |= cur & (cvals >= thr)
    return masks, pr


def score(pr, label, mask=None):
    x = pr if mask is None else pr[mask]
    if len(x) == 0: return {}
    up = x.y > 0; pu = x.p > 0.5
    hit = (up == pu)
    # date-clustered t-stat of (hit - always-up hit): average per date, then t across dates
    g = pd.DataFrame({"d": x.date, "e": hit.astype(float) - up.astype(float), "h": hit.astype(float)}).groupby("d").mean()
    t = float(g.e.mean() / (g.e.std(ddof=1) / math.sqrt(len(g)))) if len(g) > 2 and g.e.std() > 0 else float("nan")
    th = float((g.h.mean() - 0.5) / (g.h.std(ddof=1) / math.sqrt(len(g)))) if len(g) > 2 else float("nan")
    yrs = max(1e-9, (x.date.max() - x.date.min()).days / 365.25)
    return {"n": int(len(x)), "acc": float(hit.mean()), "base_up": float(up.mean()), "frac_pred_up": float(pu.mean()),
            "auc": auc(up.astype(int), x.p) if mask is None else None, "t_vs_alwaysup": t, "t_vs_50": th,
            "dates": int(len(g)), "per_year": float(len(x) / yrs), "acc_when_pred_up": float(up[pu].mean()) if pu.any() else None,
            "acc_when_pred_dn": float((~up[~pu]).mean()) if (~pu).any() else None}


def ml(verbose=True, targets=("oc1", "cc1", "cc5", "big"), models=("lr", "hgb"), years=range(2008, 2027)):
    P = build_panel(verbose)
    feats_base = [c for c in P.columns if c not in NONFEAT and P[c].dtype != object]
    res = {}; allpreds = {}
    for tgt in targets:
        feats = feats_base + (["gap_next", "spy_gap_next"] if tgt == "oc1" else [])
        for mdl in models:
            t0 = time.time()
            pr, (m, samp, feats) = walk_forward(P, tgt, feats, list(years), model=mdl)
            pr["date"] = pd.to_datetime(pr.date)
            masks, pr = conf_buckets(pr)
            key = f"{tgt}|{mdl}"
            R = {}
            for per, lo in (("2010+", "2010-01-01"), ("2015+", "2015-01-01"), ("2022+", "2022-01-01")):
                sel = (pr.date >= lo).values
                R[per] = {"all": score(pr[sel], key)}
                for q, mk in masks.items():
                    R[per][f"top{int(q*100)}"] = score(pr[sel & mk], key)
                    for s in ("SPY", "QQQ", "IWM"):
                        R[per][f"top{int(q*100)}_{s}"] = score(pr[sel & mk & (pr.sym == s).values], key)
                for s in ("SPY", "QQQ", "IWM"):
                    R[per][f"all_{s}"] = score(pr[sel & (pr.sym == s).values], key)
            # per-asset / per-class (2015+)
            x = pr[pr.date >= "2015-01-01"].copy(); x["hit"] = (x.y > 0) == (x.p > 0.5); x["upb"] = x.y > 0
            pa = x.groupby("sym").agg(n=("hit", "size"), acc=("hit", "mean"), base=("upb", "mean"))
            pa["edge"] = pa.acc - np.maximum(pa.base, 1 - pa.base)
            pa["se"] = np.sqrt(0.25 / pa.n)
            R["per_asset"] = pa.sort_values("edge", ascending=False).round(4).reset_index().to_dict("records")
            R["per_class"] = x.groupby("aclass").agg(n=("hit", "size"), acc=("hit", "mean"), base=("upb", "mean")).round(4).reset_index().to_dict("records")
            R["by_year"] = {int(y): {"acc": float(g.hit.mean()), "base": float(g.upb.mean()), "auc": auc(g.upb.astype(int), g.p)}
                            for y, g in pr.assign(hit=(pr.y > 0) == (pr.p > 0.5), upb=pr.y > 0).groupby(pr.date.dt.year)}
            # feature importance
            if mdl == "lr":
                coef = m[-1].coef_[0]
                imp = pd.Series(coef, index=feats).sort_values(key=np.abs, ascending=False)
                R["importance"] = imp.head(20).round(4).to_dict()
            else:
                from sklearn.inspection import permutation_importance
                Xs = np.clip(np.nan_to_num(samp[feats].values, nan=np.nan, posinf=np.nan, neginf=np.nan), -1e6, 1e6)
                ys = (samp["cc1" if tgt == "big" else tgt].values > 0).astype(int)
                pi = permutation_importance(m, Xs, ys, scoring="roc_auc", n_repeats=3, random_state=0, n_jobs=-1)
                imp = pd.Series(pi.importances_mean, index=feats).sort_values(ascending=False)
                R["importance"] = imp.head(20).round(5).to_dict()
            res[key] = R
            allpreds[key] = pr
            pickle.dump(allpreds, open(PREDS, "wb"))
            if verbose:
                a = R["2015+"]
                print(f"\n[{key}] {time.time()-t0:.0f}s  2015+: acc {a['all']['acc']*100:.1f}% vs always-up {a['all']['base_up']*100:.1f}%  AUC {a['all']['auc']:.3f}"
                      f"  | top5 {a['top5'].get('acc',0)*100:.1f}% (n/yr {a['top5'].get('per_year',0):.0f}, base {a['top5'].get('base_up',0)*100:.1f})"
                      f"  top10 {a['top10'].get('acc',0)*100:.1f}%  top20 {a['top20'].get('acc',0)*100:.1f}%")
                b = R["2022+"]
                print(f"   2022+: acc {b['all']['acc']*100:.1f}% vs up {b['all']['base_up']*100:.1f}% AUC {b['all']['auc']:.3f}  top10 {b['top10'].get('acc',0)*100:.1f}%")
                for s in ("SPY", "QQQ", "IWM"):
                    q = a[f"top10_{s}"]; z = a[f"all_{s}"]
                    print(f"   {s}: all {z.get('acc',0)*100:.1f}% (up {z.get('base_up',0)*100:.1f})  top10 {q.get('acc',0)*100:.1f}% n={q.get('n',0)} ({q.get('per_year',0):.0f}/yr) up-base {q.get('base_up',0)*100:.1f}")
                print("   top features:", list(R["importance"].items())[:8])
            save("ml", res)
    pickle.dump(allpreds, open(PREDS, "wb"))
    return res


# =====================================================================================================================
# map ML onto the oracle
# =====================================================================================================================
def _whole(r, prem, spot_now, mult, per_year, start, frac=0.20, n=3000, seed=3):
    """bootstrap 1y of the strategy's own OOS trades with whole contracts (skip when floor(frac*equity/cost)=0)."""
    rng = np.random.default_rng(seed)
    k = max(1, int(round(per_year)))
    idx = rng.integers(0, len(r), size=(n, k))
    rr = np.maximum(r[idx], -1); cost = prem[idx] * spot_now * mult
    eq = np.full(n, float(start))
    for j in range(k):
        nc = np.floor(frac * eq / cost[:, j]); eq = eq + nc * cost[:, j] * rr[:, j]
    return {"median": float(np.median(eq)), "p_grow": float((eq > start).mean()), "p_halve": float((eq < start / 2).mean())}


def mapping(verbose=True):
    """Trade the ML's confident calls on SPY(as XSP)/QQQ/IWM with the PART-1 structures (fair 0DTE pricing, IV/VIX 0.85).
    Confidence thresholds are per symbol, from that symbol's PRIOR OOS years only. OOS window for P&L: 2015+."""
    allpreds = pickle.load(open(PREDS, "rb"))
    J = json.load(open(OUT))
    cal = J["calib"]; k_spy = cal["k_all"]["SPY"]; rem = pd.Series(cal["var_remaining"])
    c = db(); spy, vix = load_daily(c, "SPY"), load_daily(c, "^VIX")["close"]
    out = {}
    combos = [("oc1", "0DTE ATM @open"), ("oc1", "0DTE ATM/1% spread"), ("big", "0DTE ATM @open"),
              ("cc5", "1wk ATM"), ("cc5", "1wk ATM/1% spread"), ("cc5", "2wk ATM/1% spread")]
    hdr = False
    for sym, venue in (("SPY", "XSP"), ("QQQ", "QQQ"), ("IWM", "IWM")):
        D = build_oracle_frame(c, sym, k_spy, spy=spy, vix=vix, zmode="fair", kfair=cal["kfair"][sym])
        D = D[(D.index >= START) & (D.index <= END)]
        S = structure_returns(D, sym, venue, k_spy, rem)
        spot_now = float(D.close.iloc[-1]); mult = 10.0 if venue == "XSP" else 100.0
        for tgt, struct in combos:
            for mdl in ("lr", "hgb"):
                key = f"{tgt}|{mdl}"
                if key not in allpreds: continue
                pr = allpreds[key]
                pr = pr[pr.sym == sym].reset_index(drop=True)
                masks, pr2 = conf_buckets(pr, qs=(0.05, 0.10, 0.20, 0.33))
                T = S[struct]
                for q in ("all", 0.05, 0.10, 0.20, 0.33):
                    mk = np.ones(len(pr2), bool) if q == "all" else masks[q]
                    x = pr2[mk & (pr2.date >= "2015-01-01").values]
                    if tgt in ("oc1", "cc1", "big"):   # prediction made at close of `date` for the NEXT session
                        nxt = pd.Series(T.index[1:], index=T.index[:-1])
                        x = x[x.date.isin(nxt.index)]; td = nxt.reindex(x.date).values
                    else:                              # bought at the close of `date`
                        x = x[x.date.isin(T.index)]; td = x.date.values
                    tt = T.reindex(td)
                    long = x.p.values > 0.5
                    r = np.where(long, tt.rc.values, tt.rp.values); rcall = tt.rc.values; prem = tt.prem.values
                    ok = ~np.isnan(r) & ~np.isnan(prem)
                    r, rcall, long, prem, y = r[ok], rcall[ok], long[ok], prem[ok], x.y.values[ok]
                    if len(r) < 10: continue
                    yrs = (END - pd.Timestamp("2015-01-01")).days / 365.25
                    rl = r[long]
                    row = {"n": int(len(r)), "per_year": len(r) / yrs, "acc": float(np.mean((y > 0) == long)),
                           "base_up": float(np.mean(y > 0)), "ev": float(np.mean(r)),
                           "t": float(np.mean(r) / (np.std(r) / math.sqrt(len(r)))),
                           "ev_calls_same_days": float(np.mean(rcall)), "n_long": int(long.sum()),
                           "ev_long_only": float(np.mean(rl)) if len(rl) else None,
                           "t_long_only": float(np.mean(rl) / (np.std(rl) / math.sqrt(len(rl)))) if len(rl) > 2 else None,
                           "ev_2022+": float(np.mean(r[pd.DatetimeIndex(td[ok]) >= "2022-01-01"])) if (pd.DatetimeIndex(td[ok]) >= "2022-01-01").sum() else None,
                           "contract_$": float(np.median(prem) * spot_now * mult), "min_capital_$": float(np.median(prem) * spot_now * mult / 0.2)}
                    row["bank"] = {str(st): _whole(r, prem, spot_now, mult, row["per_year"], st) for st in (170, 1000, 5000)}
                    if len(rl) > 10:
                        row["bank_long"] = {str(st): _whole(rl, prem[long], spot_now, mult, len(rl) / yrs, st) for st in (170, 1000, 5000)}
                    row["bank_calls_same_days"] = {str(st): _whole(rcall, prem, spot_now, mult, row["per_year"], st) for st in (170, 1000, 5000)}
                    out[f"{sym}|{venue}|{key}|{struct}|{q}"] = row
                    if verbose:
                        if not hdr:
                            print("sym/venue model     structure            bucket   n  /yr   acc  up-base   EV     t  | calls-same-days | long-only n  EV    t  | EV22+ | contract minCap | bank median/P(grow) $170 $1k $5k")
                            hdr = True
                        f = lambda v: f"{v*100:+6.1f}" if v is not None else "   n/a"
                        b = row["bank"]
                        print(f"{sym}/{venue:4s} {key:9s} {struct:20s} {str(q):5s} {row['n']:5d} {row['per_year']:4.0f} {row['acc']*100:5.1f} {row['base_up']*100:5.1f} {f(row['ev'])} {row['t']:5.2f} | {f(row['ev_calls_same_days'])} | "
                              f"{row['n_long']:5d} {f(row['ev_long_only'])} {row['t_long_only'] if row['t_long_only'] is None else round(row['t_long_only'], 2)} | {f(row['ev_2022+'])} | "
                              f"${row['contract_$']:5.0f} ${row['min_capital_$']:6.0f} | " + " ".join(f"${b[k]['median']:.0f}/{b[k]['p_grow']*100:.0f}" for k in b))
    save("mapping", out)
    return out


def nonoverlap(verbose=True):
    """Honest t-stats: confident ML CALL entries (cc5 model) vs always-call vs the published RSI2<10 rule, keeping only
    entries at least one holding period apart (overlapping 5-day trades inflate naive t by ~sqrt(5)). 2015+."""
    J = json.load(open(OUT)); cal = J["calib"]; c = db(); P = pickle.load(open(PREDS, "rb")); out = {}
    for sym, venue in (("SPY", "XSP"), ("QQQ", "QQQ"), ("IWM", "IWM")):
        D = build_oracle_frame(c, sym, cal["k_all"]["SPY"], zmode="fair", kfair=cal["kfair"][sym])
        D = D[(D.index >= START) & (D.index <= END)]
        S = structure_returns(D, sym, venue, cal["k_all"]["SPY"], pd.Series(cal["var_remaining"]))
        rsi2 = rsi(load_daily(c, sym).adj_close, 2)
        for struct in ("1wk ATM", "1wk ATM/1% spread", "2wk ATM/1% spread"):
            T = S[struct]; T = T[T.index >= "2015-01-01"]; pos = {d: i for i, d in enumerate(T.index)}
            gap = 5 if struct.startswith("1wk") else 10

            def stat(dates, label):
                keep, last = [], None
                for d in sorted(dates):
                    if last is None or pos[d] - pos[last] >= gap: keep.append(d); last = d
                r = T.loc[keep, "rc"].values
                if len(r) < 5: return
                y = pd.DatetimeIndex(keep); by = pd.Series(r, index=y).groupby(y.year).mean()
                o = dict(n=len(r), per_yr=len(r) / 11.8, ev=float(r.mean()), t=float(r.mean() / (r.std() / math.sqrt(len(r)))),
                         pop=float((r > 0).mean()), ev22=float(r[y >= "2022-01-01"].mean()) if (y >= "2022-01-01").any() else None,
                         n22=int((y >= "2022-01-01").sum()), yrs_pos=f"{(by > 0).sum()}/{len(by)}")
                out[f"{sym}|{struct}|{label}"] = o
                if verbose:
                    print(f"{sym}/{venue} {struct:18s} {label:24s} n={o['n']:4d} ({o['per_yr']:.0f}/yr) EV {o['ev']*100:+6.1f}% t {o['t']:5.2f} "
                          f"PoP {o['pop']*100:3.0f}% | 2022+ n={o['n22']} EV {(o['ev22'] or 0)*100:+6.1f}% | yrs+ {o['yrs_pos']}")
            stat(list(T.index), "always call")
            stat([d for d in T.index if rsi2.get(d, 99) < 10], "RSI2<10 (rule)")
            for mdl in ("lr", "hgb"):
                pr = P[f"cc5|{mdl}"]; pr = pr[pr.sym == sym].reset_index(drop=True)
                m, pr2 = conf_buckets(pr, qs=(0.10, 0.20))
                for q in (0.10, 0.20):
                    x = pr2[m[q] & (pr2.p > 0.5).values & (pr2.date >= "2015-01-01").values]
                    stat([d for d in x.date if d in pos], f"ML cc5 {mdl} top{int(q*100)} calls")
    save("nonoverlap", out)
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("calib", "all"): calib()
    if cmd in ("oracle", "all"):
        oracle(); buyhold()
    if cmd == "oracle_sens":
        oracle(zmode="live", tag="live", bank=False); oracle(zmode="rich", tag="rich", bank=False)
        oracle(ivr=0.6, tag="ivr0.6", bank=False); oracle(ivr=1.0, tag="ivr1.0", bank=False)
    if cmd in ("fetch", "all"): fetch()
    if cmd in ("ml", "all"): ml()
    if cmd in ("map", "all"): mapping(); nonoverlap()
