#!/usr/bin/env python3
"""P1 (0DTE momentum score) replay on 1-minute SPY/QQQ history 2007-01 .. 2026-03 with exit-rule variants and VIX bands.

Questions
  1. Does the P1 score (score.py, replicated exactly on 5-minute bars) have any directional edge on the underlying, by prior-VIX band?
  2. Given a signal, which exit rule loses least / earns most on a 0DTE long option (0.15-delta OTM single and ATM single)?
     Written rules (-45% stop, +100% take, 30-min time stop, 12:00 window-A exit) vs no stop, wider stop, resting 2x, VWAP-cross, trailing.
  3. The VIX 16-18 band: with |S|>=5 and RVOL>=1.3, is P1 positive there (reports/2026-10-16.md asked)?

Option prices: Black-Scholes in calendar minutes with sd = K(mins_left) * VIX * sqrt(mins/yr), K fitted on real quotes (common.py).
Three pricing levels: MKT = the Oct 5-16 2026 live-quote level (VIX1D/VIX was 0.45-0.65 that week, vs a 0.79 median since 2023: an unusually
cheap week); V1D = central case, implied E|move| = sample realized / 0.92 (CBOE VIX1D vs realized 2023-26: buyers get 0.90-0.92 of what they pay);
VRP = conservative, sample realized / 0.80 (33-year VIX-based headwind).
VIX is interpolated linearly from the day's VIX open to VIX close (captures the intraday vol rise on trend days; does not use the
close for any decision). QQQ uses VXN/VIX of the prior day. Costs: entry at mid + 50% of half-spread, exit at mid - 50% of half-spread
(fill study: trades print ~37% of the half-spread from mid); full spread 10% for the OTM single, 4% for ATM.
Caveat: daily 0DTE expiries only exist since 2022 (Mon/Wed/Fri since 2016); earlier years are 'as if'.
"""
import json, sys, math
import numpy as np, pandas as pd
from scipy.stats import norm
from common import *

SPREAD = {"otm15": 0.10, "atm": 0.04}
BANDS = [("<16", 0, 16), ("16-18", 16, 18), ("18-20", 18, 20), ("20-25", 20, 25), ("25+", 25, 999)]


def five_min(D):
    P, H, L, V = D["P"], D["H"].astype(float), D["L"].astype(float), D["V"].astype(float)
    n = P.shape[0]
    o5 = P[:, 0:390:5]; c5 = P[:, 5:391:5]
    h5 = H.reshape(n, 78, 5).max(2); l5 = L.reshape(n, 78, 5).min(2); v5 = V.reshape(n, 78, 5).sum(2)
    return o5, h5, l5, c5, v5


def scores(D):
    """Replicates score.py score_symbol at every 5-min bar close j (0..77) for every session. Returns S (n,78), rvol (n,78), vwap (n,78)."""
    o5, h5, l5, c5, v5 = five_min(D)
    n = o5.shape[0]
    tp = (h5 + l5 + c5) / 3
    cpv = np.cumsum(tp * v5, 1); cv = np.cumsum(v5, 1)
    vwap = np.where(cv > 0, cpv / np.maximum(cv, 1e-9), c5)
    slope = np.full_like(vwap, 0.0); slope[:, 3:] = vwap[:, 3:] - vwap[:, :-3]
    # ATR14 over a continuous 5-min bar stream (across sessions), as the bot keeps 3 sessions of bars
    flat_c = c5.reshape(-1); flat_h = h5.reshape(-1); flat_l = l5.reshape(-1)
    prev_c = np.r_[flat_c[0], flat_c[:-1]]
    tr = np.maximum.reduce([flat_h - flat_l, np.abs(flat_h - prev_c), np.abs(flat_l - prev_c)])
    atr = pd.Series(tr).rolling(14, min_periods=1).mean().to_numpy().reshape(n, 78)
    # RVOL: last bar volume / median volume of bars in the prior 2 sessions + today so far, excluding 09:30, 09:35 and 15:55 bars
    keep = np.ones(78, bool); keep[[0, 1, 77]] = False
    rvol = np.zeros((n, 78))
    for i in range(n):
        hist = []
        for d in (i - 2, i - 1):
            if d >= 0:
                hist.append(v5[d, keep])
        base = np.concatenate(hist) if hist else np.array([])
        for j in range(78):
            today = v5[i, :j + 1][keep[:j + 1]]
            pool = np.concatenate([base, today]) if len(base) else today
            med = np.median(pool) if len(pool) else 0
            rvol[i, j] = v5[i, j] / med if med > 0 else 0
    S = np.zeros((n, 78), int)
    comp_side = np.where(c5 > vwap, 1, -1)
    comp_atr = np.where(c5 - vwap > 0.5 * atr, 1, np.where(vwap - c5 > 0.5 * atr, -1, 0))
    comp_slope = np.sign(slope).astype(int)
    up = (c5 > o5).astype(int); dn = (c5 < o5).astype(int)
    ups = np.zeros((n, 78), int); dns = np.zeros((n, 78), int)
    for j in range(78):
        a = max(0, j - 3)
        ups[:, j] = up[:, a:j + 1].sum(1); dns[:, j] = dn[:, a:j + 1].sum(1)
    comp_3of4 = np.where(ups >= 3, 1, np.where(dns >= 3, -1, 0))
    orb_h = h5[:, [0]]; orb_l = l5[:, [0]]
    ph_h = h5[:, 42:54].max(1, keepdims=True); ph_l = l5[:, 42:54].min(1, keepdims=True)
    j = np.arange(78)[None, :]
    winB = (j >= 53) & (j <= 66)
    hi = np.where(winB, ph_h, orb_h); lo = np.where(winB, ph_l, orb_l)
    comp_rb = np.where(c5 > hi, 1, np.where(c5 < lo, -1, 0))
    base = comp_side + comp_atr + comp_slope + comp_3of4 + comp_rb
    comp_rv = np.where(rvol >= 1.3, np.sign(base), 0).astype(int)
    S = base + comp_rv
    return S, rvol, vwap, c5


SMILE = {"put": (0.048, 0.049), "call": (-0.071, 0.079)}     # IV(K)/IV(ATM) = 1 + a|z| + b z^2, fitted on 8 days of live SPY 0DTE quotes


def option_paths(P, K, call, vix_path, kq, m0, mult=1.0, smile=True):
    """mid price matrix (n, 391) for strike K (per day), call flag (per day), vix_path (n,391) in pct, kq multiplier (per day).
    mult scales the implied vol (1.0 = Oct-2026 market calibration; FAIR_MULT/0.8 = realized-matched plus the long-run buyer's headwind)."""
    n = P.shape[0]
    m = np.arange(391)[None, :]
    mins_left = np.maximum(390 - m, 1)
    Tm = mins_left / MINYR
    sig = k_spy(mins_left) * kq[:, None] * vix_path / 100.0 * mult
    if smile:
        z = np.log(K[:, None] / P) / (sig * np.sqrt(Tm))
        otm = np.where(call[:, None], z > 0, z < 0)
        a = np.where(call[:, None], SMILE["call"][0], SMILE["put"][0]); b = np.where(call[:, None], SMILE["call"][1], SMILE["put"][1])
        az = np.minimum(np.abs(z), 4.0)
        ratio = np.where(otm, 1 + a * az + b * az ** 2, 1.0)
        sig = sig * np.clip(ratio, 0.9, 2.5)
    return bs(P, K[:, None], Tm, sig, call[:, None])


def run_exits(mid, m0, m_end, vwap5, c5, call, spread):
    """Simulate exit rules on the 1-min mid path for each trade. mid (k,391) per trade; m0 entry minute (k,), m_end = 15:45 index.
    Returns dict rule -> net return array (k,)."""
    k = mid.shape[0]
    half = spread / 2 * 0.5                          # 50% of the half-spread paid each way
    idx = np.arange(391)[None, :]
    entry = mid[np.arange(k), m0] * (1 + half)
    bidp = mid * (1 - half)
    pnl = bidp / entry[:, None] - 1                   # pnl if sold at the bid at minute m
    held = idx - m0[:, None]
    active = (idx >= m0[:, None]) & (idx <= m_end)
    # VWAP-cross flags at 5-min bar closes: bar j closes at minute 5(j+1). cross if (call and c5<vwap) or (put and c5>vwap)
    cross5 = np.where(call[:, None], c5 < vwap5, c5 > vwap5)          # (k,78)
    cross = np.zeros((k, 391), bool)
    cross[:, 5:391:5] = cross5
    cross &= held >= 5                                               # only bars after entry
    winA = m0 <= T(11, 0)
    noon = idx >= T(12, 0)
    out = {}

    def first_exit(cond):
        """cond (k,391) bool: exit at first minute where cond holds within active; else at m_end."""
        c = cond & active
        has = c.any(1)
        first = np.where(has, c.argmax(1), m_end)
        return first

    def ret_at(mins, tp=None, tp_mult=None):
        r = pnl[np.arange(k), mins]
        if tp is not None:
            # resting limit sell at tp_mult x entry: fills at exactly tp_mult (limit) when mid >= tp_mult*entry before 'mins'
            tp_hit = (mid >= tp_mult * entry[:, None]) & active
            hit = tp_hit.any(1); tmin = np.where(hit, tp_hit.argmax(1), 10 ** 6)
            use = hit & (tmin <= mins)
            r = np.where(use, tp_mult - 1, r)
        return r

    # R0 written rules (single contract): -45% stop, +100% take, 30-min time stop if <+25%, window-A out by 12:00 unless +50%, flat 15:45
    stop = pnl <= -0.45
    take = pnl >= 1.0
    tstop = (held >= 30) & (pnl < 0.25)
    aexit = winA[:, None] & noon & (pnl < 0.5)
    out["R0_written"] = ret_at(first_exit(stop | take | tstop | aexit))
    out["R1_hold_1545"] = ret_at(np.full(k, m_end))
    out["R2_tp2x_hold"] = ret_at(np.full(k, m_end), tp=True, tp_mult=2.0)
    out["R3_stop70_tp2x"] = ret_at(first_exit(pnl <= -0.70), tp=True, tp_mult=2.0)
    out["R4_vwap_cross"] = ret_at(first_exit(cross))
    out["R5_vwap_cross_tp2x"] = ret_at(first_exit(cross), tp=True, tp_mult=2.0)
    out["R6_stop45_only"] = ret_at(first_exit(stop))
    out["R7_stop45_tp2x"] = ret_at(first_exit(stop), tp=True, tp_mult=2.0)
    # trailing: after +50% peak, exit when mid <= 65% of peak (no hard stop)
    peak = np.maximum.accumulate(np.where(active, mid, 0), axis=1)
    trail = (peak >= 1.5 * entry[:, None]) & (mid <= 0.65 * peak)
    out["R8_trail65_after50"] = ret_at(first_exit(trail))
    out["R9_tp3x_hold"] = ret_at(np.full(k, m_end), tp=True, tp_mult=3.0)
    out["R10_written_no_timestop"] = ret_at(first_exit(stop | take | aexit))
    out["R11_stop45_vwap"] = ret_at(first_exit(stop | cross))
    # diagnostics: stopped at -45% then would have finished >= +100% at 15:45
    stopped = (stop & active).any(1)
    out["_stopped45"] = stopped.astype(float)
    out["_stopped_then_double"] = (stopped & (pnl[:, m_end] >= 1.0)).astype(float)
    out["_stopped_then_positive"] = (stopped & (pnl[:, m_end] >= 0.0)).astype(float)
    out["_mfe"] = np.where(active, pnl, -9).max(1)
    out["_premium_pct"] = entry / 1.0
    return out


def main():
    vix = vix_daily()
    vxn = daily("^VXN")
    ratio = (vxn.close / vix.close).dropna()
    results = {"meta": {"variants": 0}}
    tables = []
    trades_all = []
    global FAIR_MULT
    FAIR_MULT = {}
    for sym in ["SPY", "QQQ"]:
        D = sessions(sym)
        _vo = vix.open.reindex(D["dates"]).to_numpy(); _kq = 1.0 if sym == "SPY" else pd.Series(ratio).shift(1).reindex(D["dates"], method="ffill").fillna(1.4).to_numpy()
        _m0 = T(10, 6); _sel = D["ok"] & np.isfinite(_vo) & (_vo > 0)
        _imp = k_spy(390 - _m0) * _kq * _vo / 100 * np.sqrt((390 - _m0) / MINYR) * np.sqrt(2 / np.pi)
        _real = np.abs(np.log(D["P"][:, 390] / D["P"][:, _m0]))
        FAIR_MULT[sym] = float(np.nanmean(_real[_sel]) / np.nanmean(_imp[_sel]))
        results["meta"][f"fair_mult_{sym}"] = round(FAIR_MULT[sym], 3)
        print(sym, "FAIR multiplier on the Oct-2026 market calibration:", round(FAIR_MULT[sym], 3), "-> VRP pricing uses", round(FAIR_MULT[sym] / 0.8, 3))
        ok = D["ok"]
        dates = D["dates"]; P = D["P"]
        S, rvol, vwap5, c5 = scores(D)
        n = len(dates)
        # prior-day VIX close (gate), VIX open/close for today (marking), VXN/VIX prior day for QQQ
        vprior = vix.close.reindex(dates, method="ffill").shift(1).to_numpy()
        vprior = pd.Series(vix.close).shift(1).reindex(dates, method="ffill").to_numpy()
        vopen = vix.open.reindex(dates).to_numpy(); vclose = vix.close.reindex(dates).to_numpy()
        vopen = np.where(np.isfinite(vopen) & (vopen > 0), vopen, vprior)
        vclose = np.where(np.isfinite(vclose), vclose, vopen)
        kq = np.ones(n) if sym == "SPY" else pd.Series(ratio).shift(1).reindex(dates, method="ffill").fillna(1.4).to_numpy()
        m = np.arange(391)[None, :]
        vix_path = vopen[:, None] + (vclose - vopen)[:, None] * (m / 390.0)
        m_end = T(15, 45)
        for thr_name, thr, need_rvol in [("S4", 4, False), ("S5_rvol", 5, True)]:
            for win, (j0, j1) in {"A": (1, 16), "B": (53, 66)}.items():
                sig = (np.abs(S) >= thr)
                if need_rvol:
                    sig &= rvol >= 1.3
                sig[:, :j0] = False; sig[:, j1 + 1:] = False
                has = sig.any(1) & ok & np.isfinite(vprior)
                jfirst = sig.argmax(1)
                days = np.where(has)[0]
                if len(days) == 0:
                    continue
                j = jfirst[days]
                m0 = 5 * (j + 1) + 1                                   # fill one minute after the bar close
                Sdir = np.sign(S[days, j])
                call = Sdir > 0
                S0 = P[days, m0]
                mins0 = 390 - m0
                # underlying: entry -> 15:45 and -> close, in signal direction
                u1545 = Sdir * np.log(P[days, m_end] / S0)
                uclose = Sdir * np.log(P[days, 390] / S0)
                band = np.full(len(days), "", dtype=object)
                for name, lo, hi in BANDS:
                    band[(vprior[days] >= lo) & (vprior[days] < hi)] = name
                period = np.where(dates[days] < pd.Timestamp("2019-01-01"), "IS", "OOS")
                sig_entry = k_spy(mins0) * kq[days] * vix_path[days, m0] / 100
                T0 = mins0 / MINYR
                grid = S0 * 0.0013                                   # $1 strikes on a $770 underlying, kept relative so 2007 prices behave the same
                for pricing, mult in [("MKT", 1.0), ("V1D", FAIR_MULT[sym] / 0.92), ("VRP", FAIR_MULT[sym] / 0.8)]:
                  sig_e = sig_entry * mult
                  for ctype in ["otm15", "atm"]:
                    if ctype == "atm":
                        K = np.round(S0 / grid) * grid
                    else:
                        z = norm.ppf(0.15)
                        K = np.where(call, S0 * np.exp(-z * sig_e * np.sqrt(T0) + 0.5 * sig_e ** 2 * T0),
                                     S0 * np.exp(z * sig_e * np.sqrt(T0) + 0.5 * sig_e ** 2 * T0))
                        K = np.round(K / grid) * grid
                        K = np.where(call, np.maximum(K, (np.floor(S0 / grid) + 1) * grid), np.minimum(K, (np.ceil(S0 / grid) - 1) * grid))
                    mid = option_paths(P[days], K, call, vix_path[days], kq[days], m0, mult=mult)
                    delta0 = np.abs(bs_delta(S0, K, T0, sig_e, call))
                    ex = run_exits(mid, m0, m_end, vwap5[days], c5[days], call, SPREAD[ctype])
                    df = pd.DataFrame({"sym": sym, "thr": thr_name, "win": win, "ctype": ctype, "pricing": pricing, "date": dates[days], "band": band, "period": period,
                                       "vix_prior": vprior[days], "dir": Sdir, "m0": m0, "S0": S0, "K": K, "delta0": delta0, "u1545": u1545, "uclose": uclose,
                                       "prem": mid[np.arange(len(days)), m0] / S0 * 100})
                    for kname, v in ex.items():
                        df[kname] = v
                    # a contract must exist: premium >= 0.015% of spot (= $0.12 on SPY 770; rule: mid 0.15-0.40, bid >= 0.05)
                    df = df[df.prem >= 0.015]
                    trades_all.append(df)
    tr = pd.concat(trades_all, ignore_index=True)
    tr.to_pickle(os.path.join(OUT, "p1_trades.pkl"))
    rules = [c for c in tr.columns if c.startswith("R")]
    diag = [c for c in tr.columns if c.startswith("_")]
    results["meta"]["variants"] = len(rules) * 2 * 2 * 2 * 2 * 3   # rules x ctype x thr x window x symbol x pricing
    results["meta"]["n_trades_rows"] = int(len(tr))
    # 1. underlying edge by band (direction-only, no option)
    rows = []
    for (sym, thr, win, period, band), g in tr[(tr.ctype == "atm") & (tr.pricing == "MKT")].groupby(["sym", "thr", "win", "period", "band"]):
        rows.append(dict(sym=sym, thr=thr, win=win, period=period, band=band, n=len(g), u1545_bp=round(g.u1545.mean() * 1e4, 1), t=round(tstat(g.u1545), 2),
                         hit=round((g.u1545 > 0).mean(), 3), uclose_bp=round(g.uclose.mean() * 1e4, 1)))
    und = pd.DataFrame(rows)
    results["underlying_by_band"] = und.to_dict("records")
    # pooled underlying edge
    rows = []
    for (sym, thr, period), g in tr[(tr.ctype == "atm") & (tr.pricing == "MKT")].groupby(["sym", "thr", "period"]):
        rows.append(dict(sym=sym, thr=thr, period=period, n=len(g), u1545_bp=round(g.u1545.mean() * 1e4, 1), t=round(tstat(g.u1545), 2), hit=round((g.u1545 > 0).mean(), 3)))
    results["underlying_pooled"] = rows
    # 2. exit rules: by ctype, thr, period, band (pooled symbols and windows) and pooled
    rows = []
    for (pricing, ctype, thr, period), g in tr.groupby(["pricing", "ctype", "thr", "period"]):
        for r in rules:
            s = summarize(g[r], r); s.update(pricing=pricing, ctype=ctype, thr=thr, period=period, band="all", mean_cap10=round(float(np.minimum(g[r], 10).mean()), 4)); rows.append(s)
        for b, gb in g.groupby("band"):
            for r in rules:
                s = summarize(gb[r], r); s.update(pricing=pricing, ctype=ctype, thr=thr, period=period, band=b, mean_cap10=round(float(np.minimum(gb[r], 10).mean()), 4)); rows.append(s)
    ex = pd.DataFrame(rows)
    results["exits"] = ex.to_dict("records")
    # 3. diagnostics
    rows = []
    for (pricing, ctype, thr, period), g in tr.groupby(["pricing", "ctype", "thr", "period"]):
        rows.append(dict(pricing=pricing, ctype=ctype, thr=thr, period=period, n=len(g), stopped45=round(g._stopped45.mean(), 3), stopped_then_positive=round(g._stopped_then_positive.mean(), 3),
                         stopped_then_double=round(g._stopped_then_double.mean(), 3), mfe_median=round(g._mfe.median(), 3), mfe_p90=round(g._mfe.quantile(0.9), 3),
                         prem_pct_median=round(g.prem.median(), 3), delta_median=round(g.delta0.median(), 3)))
    results["diagnostics"] = rows
    # 4. VIX 16-18 band, S5+rvol, both windows, by period and ctype, written rules vs best alternatives
    rows = []
    g = tr[(tr.thr == "S5_rvol")]
    for (pricing, ctype, band, period), gg in g.groupby(["pricing", "ctype", "band", "period"]):
        d = dict(pricing=pricing, ctype=ctype, band=band, period=period, n=len(gg), u1545_bp=round(gg.u1545.mean() * 1e4, 1), hit=round((gg.u1545 > 0).mean(), 3))
        for r in ["R0_written", "R1_hold_1545", "R2_tp2x_hold", "R4_vwap_cross", "R7_stop45_tp2x"]:
            d[r] = round(gg[r].mean(), 3)
        rows.append(d)
    results["band_16_18_focus"] = rows
    json.dump(results, open(os.path.join(OUT, "p1_exits.json"), "w"), indent=1, default=str)
    # print compact tables
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    print("== underlying edge (direction-only), ATM rows, bp to 15:45")
    print(und.to_string(index=False))
    print("\n== pooled underlying"); print(pd.DataFrame(results["underlying_pooled"]).to_string(index=False))
    print("\n== exits, all bands")
    print(ex[ex.band == "all"][["pricing", "ctype", "thr", "period", "name", "n", "mean", "mean_cap10", "median", "win", "t", "p_double", "p_lose_half"]].to_string(index=False))
    print("\n== exits by band (OOS, S5_rvol)")
    print(ex[(ex.period == "OOS") & (ex.thr == "S5_rvol") & (ex.band != "all")][["pricing", "ctype", "band", "name", "n", "mean", "mean_cap10", "win", "t", "p_double"]].to_string(index=False))
    print("\n== diagnostics"); print(pd.DataFrame(results["diagnostics"]).to_string(index=False))
    print("\n== band 16-18 focus"); print(pd.DataFrame(results["band_16_18_focus"]).to_string(index=False))


if __name__ == "__main__":
    main()
