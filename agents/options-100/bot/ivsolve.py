"""Black-Scholes-Merton implied vol from the bid/ask MID (replaces yfinance's `impliedVolatility`, which runs HIGH).

Why: 2026-10-15 Robinhood live IV vs yfinance: BAH Jan-28 70C 33% vs 46%, REAL Jan-28 10C 72% vs 90%, ACEL Apr-27 12.5C
32% vs 38%. yfinance's field is not reproducible from its own bid/ask with a sane rate; solving from the mid with
r = 13-week T-bill and the stock's dividend yield matches the broker. European BSM (no early exercise) -- fine for
ATM/OTM, slightly understates IV for deep-ITM puts / high-dividend calls.

    from ivsolve import iv_from_mid, rate, div_yield
    iv = iv_from_mid(mid, S, K, T_years, call=True, r=rate(), q=div_yield("BAH", S))

    python3 bot/ivsolve.py BAH REAL      # quick per-expiry ATM table: yfinance IV vs mid-solved IV
"""
import sys

import numpy as np
from scipy.special import ndtr

_RATE = None


def bsm(S, K, T, sig, call=True, r=0.04, q=0.0):
    S, K, T, sig = (np.asarray(a, float) for a in (S, K, T, sig))
    T = np.maximum(T, 1e-6)
    sig = np.maximum(sig, 1e-4)
    sq = sig * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + sig ** 2 / 2) * T) / sq
    d2 = d1 - sq
    c = S * np.exp(-q * T) * ndtr(d1) - K * np.exp(-r * T) * ndtr(d2)
    p = c - S * np.exp(-q * T) + K * np.exp(-r * T)
    return np.where(call, c, p)


def iv_from_price(px, S, K, T, call=True, r=0.04, q=0.0, lo=0.005, hi=5.0, it=80):
    """vectorized bisection; NaN where the price is outside the no-arbitrage band [intrinsic, upper]."""
    px, S, K, T = np.broadcast_arrays(*(np.asarray(a, float) for a in (px, S, K, T)))
    call = np.broadcast_to(np.asarray(call, bool), px.shape)
    a = np.full(px.shape, lo)
    b = np.full(px.shape, hi)
    pa, pb = bsm(S, K, T, a, call, r, q), bsm(S, K, T, b, call, r, q)
    ok = (px > pa) & (px < pb) & np.isfinite(px)
    for _ in range(it):
        m = (a + b) / 2
        pm = bsm(S, K, T, m, call, r, q)
        up = pm < px
        a = np.where(up, m, a)
        b = np.where(up, b, m)
    return np.where(ok, (a + b) / 2, np.nan)


def iv_from_mid(bid, ask, S, K, T, call=True, r=0.04, q=0.0):
    """IV of the bid/ask mid; NaN when bid<=0 or ask<=0 (one-sided / stale quotes)."""
    bid, ask = np.asarray(bid, float), np.asarray(ask, float)
    good = (bid > 0) & (ask > 0) & (ask >= bid)
    mid = np.where(good, (bid + ask) / 2, np.nan)
    return iv_from_price(mid, S, K, T, call, r, q)


def rate(default=0.04):
    """13-week T-bill (^IRX, quoted in percent) as a flat continuous-ish rate; cached; falls back to 4%."""
    global _RATE
    if _RATE is None:
        try:
            import yfinance as yf
            v = float(yf.Ticker("^IRX").history(period="5d").Close.dropna().iloc[-1]) / 100
            _RATE = v if 0 < v < 0.2 else default
        except Exception:
            _RATE = default
    return _RATE


def div_yield(ticker, spot=None, info=None):
    """continuous dividend yield as a FRACTION. Prefers dividendRate/spot (unambiguous); yfinance's `dividendYield`
    switched to percent units in 2025 (2.9 == 2.9%), `trailingAnnualDividendYield` is a fraction."""
    try:
        if info is None:
            import yfinance as yf
            info = yf.Ticker(ticker).info or {}
        spot = spot or info.get("regularMarketPrice") or info.get("currentPrice")
        dr = info.get("dividendRate")
        if dr and spot:
            return float(dr) / float(spot)
        dy = info.get("dividendYield")
        if dy:
            dy = float(dy)
            return dy / 100 if dy > 0.3 else dy
        ty = info.get("trailingAnnualDividendYield")
        return float(ty) if ty else 0.0
    except Exception:
        return 0.0


def _demo(tks):
    import datetime as dt
    import yfinance as yf
    r = rate()
    print(f"r={r:.4f}")
    for t in tks:
        tk = yf.Ticker(t)
        S = float(tk.fast_info["last_price"])
        q = div_yield(t, S)
        print(f"{t} S={S:.2f} q={q:.4f}")
        for e in tk.options:
            dte = (dt.date.fromisoformat(e) - dt.date.today()).days
            ch = tk.option_chain(e)
            for side, tab in (("C", ch.calls), ("P", ch.puts)):
                row = tab.loc[(tab.strike - S).abs().idxmin()]
                iv = iv_from_mid(row.bid, row.ask, S, row.strike, max(dte, 0.5) / 365, side == "C", r, q)
                print(f"  {e} {dte:4d}d {side} K={row.strike:g} bid={row.bid} ask={row.ask} yf={row.impliedVolatility:.3f} mid_iv={float(iv):.3f}")


if __name__ == "__main__":
    _demo(sys.argv[1:] or ["BAH"])
