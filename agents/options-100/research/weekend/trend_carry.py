#!/usr/bin/env python3
"""Time-series momentum (trend) and carry in FX / commodities / rates / foreign equities, expressed through long options on the ETF proxies.

Universe (TRADEABLE-WITH-MORE-CAPITAL via long calls/puts; the ETFs are the only hard-rule-compliant vehicles):
  FX:   FXE (EUR), FXY (JPY), UUP (USD)            commodities: GLD, SLV, USO            rates: TLT, IEF
  foreign equity: EWJ, FXI, EWZ, EFA, EEM           crypto: IBIT (short history), BTC-USD as reference
  futures references (RESEARCH-ONLY, not tradeable): 6E, 6J, CL, GC, ZN, ES, NQ
Signals (monthly rebalance, all with a 1-day lag):
  TSMOM-12-1: sign of the 12-month return excluding the last month (Moskowitz-Ooi-Pedersen); TSMOM-1 / 3 / 6 month variants
  Carry (FX): 3-month rate differential from FRED (not fetched here; proxied by the 12m futures-vs-spot drift of 6E/6J, which equals carry) -- skipped if unavailable
Option economics: 1-month ATM call (long) or put (short) on the ETF; premium = 0.4 * S * sigma * sqrt(21/252) with sigma = RV20 * 1.1 (ETF options
  trade ~10% above realized) ; cost = 6% of premium round trip (FXE/FXY/EWJ spreads are wide, 5-10%). Return = (intrinsic at expiry) / premium - 1 - cost,
  held 21 sessions. IS 2007-2018 / OOS 2019+; BH over all tests.
"""
import json
import numpy as np, pandas as pd
from common import *

ETFS = ["FXE", "FXY", "UUP", "GLD", "SLV", "USO", "TLT", "IEF", "EWJ", "FXI", "EWZ", "EFA", "EEM"]
FUTS = ["6E=F", "6J=F", "CL=F", "GC=F", "ZN=F", "ES=F", "NQ=F", "BTC-USD"]


def load(sym):
    d = daily(sym)
    c = d.adj_close.where(d.adj_close > 0, d.close) if "adj_close" in d else d.close
    return c.dropna()


def tsmom_tests(c, sym):
    """monthly: at month-end t, signal = sign(ret over lookback, skipping last month for 12-1); hold next 21 sessions."""
    r = np.log(c / c.shift(1))
    out = []
    ends = c.index[c.index.to_period("M") != pd.Series(c.index).shift(-1).dt.to_period("M").to_numpy()]
    for name, lb, skip in [("12-1", 252, 21), ("6-1", 126, 21), ("3", 63, 0), ("1", 21, 0)]:
        rows = []
        for t in ends:
            i = c.index.get_loc(t)
            if i - lb - 1 < 0 or i + 21 >= len(c):
                continue
            sig = np.sign(np.log(c.iloc[i - skip] / c.iloc[i - lb]))
            fwd = np.log(c.iloc[i + 21] / c.iloc[i])
            rv20 = r.iloc[i - 20:i].std() * np.sqrt(252)
            rows.append(dict(t=t, sig=sig, fwd=fwd, rv=rv20))
        d = pd.DataFrame(rows)
        if len(d) < 24:
            continue
        d["x"] = d.sig * d.fwd
        d["period"] = np.where(d.t < "2019-01-01", "IS", "OOS")
        # option: buy 1m ATM in the signal direction
        prem = 0.4 * d.rv * 1.1 * np.sqrt(21 / 252)
        payoff = np.maximum(d.x, 0)
        d["opt"] = payoff / prem - 1 - 0.06
        for per in ["IS", "OOS", "ALL"]:
            g = d if per == "ALL" else d[d.period == per]
            if len(g) < 12:
                continue
            out.append(dict(sym=sym, signal=name, period=per, n=len(g), under_bp=round(g.x.mean() * 1e4, 1), t=round(tstat(g.x), 2), p=pval(tstat(g.x), len(g)), hit=round((g.x > 0).mean(), 3),
                            opt_mean=round(g.opt.mean(), 3), opt_t=round(tstat(g.opt), 2), opt_win=round((g.opt > 0).mean(), 3), prem_pct=round(prem[g.index].mean() * 100, 2)))
    return out


def main():
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
    rows = []
    for sym in ETFS + FUTS:
        try:
            c = load(sym)
        except Exception as e:
            print("skip", sym, e); continue
        c = c[c.index >= "2007-01-01"]
        rows += tsmom_tests(c, sym)
    R = pd.DataFrame(rows)
    print("== TSMOM by instrument (underlying bp per month in signal direction; option = 1m ATM long in signal direction)")
    print(R.to_string(index=False))
    # pooled by signal / period across ETFs (equal weight)
    print("\n== pooled across ETFs")
    pooled = []
    for (sig, per), g in R[R.sym.isin(ETFS)].groupby(["signal", "period"]):
        pooled.append(dict(signal=sig, period=per, n_inst=len(g), n_obs=int(g.n.sum()), under_bp=round(g.under_bp.mean(), 1), mean_t=round(g.t.mean(), 2), pos_share=round((g.under_bp > 0).mean(), 2), opt_mean=round(g.opt_mean.mean(), 3)))
    Pl = pd.DataFrame(pooled); print(Pl.to_string(index=False))
    oos = R[(R.period == "OOS")].copy(); oos["bh"] = bh(oos.p.to_numpy(), 0.10)
    print("\nOOS BH survivors (underlying):", oos[oos.bh][["sym", "signal", "n", "under_bp", "t", "opt_mean"]].to_string(index=False) if oos.bh.any() else "none", f"of {len(oos)} OOS tests")
    # min capital: 1m ATM option cost on each ETF today
    caps = []
    for sym in ETFS:
        try:
            c = load(sym); px = float(c.iloc[-1]); rv = float(np.log(c / c.shift(1)).iloc[-20:].std() * np.sqrt(252))
            prem = 0.4 * px * rv * 1.1 * np.sqrt(21 / 252) * 100
            caps.append(dict(sym=sym, price=round(px, 2), rv20=round(rv * 100, 1), one_month_atm_contract=round(prem, 0), min_capital_at_35pct=round(prem / 0.35, 0)))
        except Exception:
            pass
    C = pd.DataFrame(caps); print("\n== cost of one 1-month ATM contract today and min capital at 35% sizing"); print(C.to_string(index=False))
    json.dump(dict(tests=R.to_dict("records"), pooled=Pl.to_dict("records"), oos_bh=oos[oos.bh].to_dict("records"), n_oos_tests=int(len(oos)), capital=C.to_dict("records")),
              open(os.path.join(OUT, "trend_carry.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
