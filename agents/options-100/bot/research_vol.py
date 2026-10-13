#!/usr/bin/env python3
"""Research: can we forecast SPY's move-to-close better than the market does, and is there intraday momentum?

  python3 agents/options-100/bot/research_vol.py vrp        # 33y daily: realized open->close vs VIX-implied
  python3 agents/options-100/bot/research_vol.py model      # 3y hourly: conditional vol model, walk-forward, vs baselines
  python3 agents/options-100/bot/research_vol.py momentum   # 3y hourly: does the morning predict the last hour?
All results are out-of-sample where a fit is involved (walk-forward, expanding window).
"""
import sqlite3, sys, math, statistics
from pathlib import Path
import numpy as np

DB = Path(__file__).resolve().parents[1] / "data" / "market.db"
c = sqlite3.connect(DB, timeout=60)


def daily(sym):
    return {r[0]: r[1:] for r in c.execute(
        "SELECT ts, open, high, low, close FROM bars WHERE symbol=? AND interval='1d' ORDER BY ts", (sym,))}


def vrp():
    spy, vix = daily("SPY"), daily("^VIX")
    days = sorted(d for d in spy if d >= "1993-02-01")
    rows = []
    for i in range(1, len(days)):
        d, p = days[i], days[i - 1]
        if p not in vix: continue
        o, h, l, cl = spy[d]; pc = spy[p][3]
        if not o or not pc: continue
        v = vix[p][3] / 100
        imp = v / math.sqrt(252) * math.sqrt(6.5 / 24)   # rough open->close share of a 24h day's variance... see note
        imp_oc = v / math.sqrt(252) * 0.80                 # empirical: open->close carries ~64% of daily variance
        rows.append((d, v, abs(cl / o - 1), abs(cl / pc - 1), imp_oc, (h - l) / o))
    a = np.array([[r[1], r[2], r[3], r[4], r[5]] for r in rows])
    v, oc, cc, imp, rng = a.T
    print(f"SPY {rows[0][0]}..{rows[-1][0]}: {len(rows)} sessions")
    print(f"  close->close |move| vs VIX/sqrt(252): realized/implied mean ratio {np.mean(cc)/np.mean(v/math.sqrt(252)*0.798):.2f}"
          f"  (1.00 = fairly priced; <1 = options rich)")
    sd_imp_cc = v / math.sqrt(252)
    z = (cc / 0.798) / sd_imp_cc
    print(f"  share of days realized move > implied 1-sd move: {np.mean(cc > sd_imp_cc):.1%} (normal would be 31.7%)")
    for lo, hi in ((0, 13), (13, 16), (16, 20), (20, 30), (30, 99)):
        m = (v * 100 >= lo) & (v * 100 < hi)
        if m.sum() < 50: continue
        print(f"  VIX {lo:>2}-{hi:<2}: n={m.sum():5d}  realized/implied {np.mean(cc[m])/np.mean(sd_imp_cc[m]*0.798):.2f}"
              f"  P(|move|>1sd) {np.mean(cc[m] > sd_imp_cc[m]):.1%}  median o->c range {np.median(rng[m])*100:.2f}%")


def hourly(sym):
    out = {}
    for ts, o, h, l, cl in c.execute("SELECT ts, open, high, low, close FROM bars WHERE symbol=? AND interval='1h' ORDER BY ts", (sym,)):
        out.setdefault(ts[:10], []).append((ts[11:16], o, h, l, cl))
    return {d: b for d, b in out.items() if len(b) == 7 and b[0][0] == "09:30" and b[-1][0] == "15:30"}


def features(sym="SPY"):
    """One row per (session, decision hour). Target: |log(close/price at decision)|. Everything else is known at decision time."""
    H, D, V = hourly(sym), daily(sym), daily("^VIX")
    ddays = sorted(D)
    rows = []
    for d in sorted(H):
        i = ddays.index(d) if d in D else -1
        if i < 21: continue
        p = ddays[i - 1]
        if p not in V: continue
        pc = D[p][3]; vix = V[p][3]
        prior_rng = (D[p][1] - D[p][2]) / D[p][3]
        rv20 = statistics.pstdev([math.log(D[ddays[k]][3] / D[ddays[k - 1]][3]) for k in range(i - 20, i)])
        b = H[d]; o = b[0][1]; close = b[-1][4]
        for k in (1, 2, 4, 5):      # decision at 10:30, 11:30, 13:30, 14:30 (start of bar k)
            px = b[k][1]
            hi = max(x[2] for x in b[:k]); lo = min(x[3] for x in b[:k])
            mins_left = 390 - 60 * k + 30 - 30  # bar k starts at 9:30+60k; session ends 16:00
            mins_left = 16 * 60 - (9 * 60 + 30 + 60 * k)
            rows.append(dict(d=d, k=k, mins=mins_left, vix=vix, rv20=rv20, prior_rng=prior_rng,
                             gap=abs(o / pc - 1), morn_rng=(hi - lo) / o, morn_move=abs(px / o - 1),
                             signed_morn=px / pc - 1, y=abs(math.log(close / px)), ys=math.log(close / px),
                             last_hr=math.log(close / b[-1][1]), first_hr=math.log(b[0][4] / pc)))
    return rows


def model():
    rows = features("SPY")
    days = sorted({r["d"] for r in rows})
    print(f"SPY hourly sessions usable: {len(days)}  ({days[0]}..{days[-1]})")
    def X(r):  # log-linear HAR-style vol model; every input is known at decision time
        t = math.sqrt(r["mins"] / 390)
        return [1, math.log(r["vix"] / 100 * t), math.log(max(r["morn_rng"], 1e-4) / math.sqrt(390 - r["mins"]) * math.sqrt(r["mins"])),
                math.log(max(r["prior_rng"], 1e-4) * t), math.log(max(r["rv20"], 1e-5) * t), math.log(max(r["gap"], 1e-5) + 1e-3)]
    start = len(days) // 3            # first third = initial training window, then expanding walk-forward
    res = {"model": [], "vix_only": [], "pool_uncond": []}
    for j in range(start, len(days)):
        train = [r for r in rows if r["d"] < days[j]]; test = [r for r in rows if r["d"] == days[j]]
        A = np.array([X(r) for r in train]); y = np.log(np.array([max(r["y"], 1e-5) for r in train]))
        beta, *_ = np.linalg.lstsq(A, y, rcond=None)
        resid = y - A @ beta; adj = float(np.mean(np.exp(resid)))  # Duan smearing: log-model -> E|move|
        Av = A[:, :2]; bv, *_ = np.linalg.lstsq(Av, y, rcond=None); adjv = float(np.mean(np.exp(y - Av @ bv)))
        for r in test:
            x = np.array(X(r))
            pred = math.exp(x @ beta) * adj
            pv = math.exp(x[:2] @ bv) * adjv
            same_k = [q["y"] for q in train if q["k"] == r["k"]][-60:]  # what the live engine does today: last 60 sessions, same clock time
            res["model"].append((pred, r["y"])); res["vix_only"].append((pv, r["y"]))
            res["pool_uncond"].append((statistics.mean(same_k), r["y"]))
    print(f"  walk-forward test: {len(res['model'])} decisions over {len(days)-start} sessions\n"
          f"  score = mean |log(predicted E|move| / realized)| (lower better), bias = mean predicted/realized (1.00 = calibrated)")
    for name, pr in res.items():
        p = np.array([x[0] for x in pr]); y = np.array([max(x[1], 1e-5) for x in pr])
        corr = np.corrcoef(np.log(p), np.log(y))[0, 1]
        print(f"  {name:12s} bias {np.mean(p)/np.mean(y):.2f}  log-corr with realized {corr:+.2f}  "
              f"RMSE {math.sqrt(np.mean((p-y)**2))*100:.3f}%")
    # Does the model separate big-move afternoons from quiet ones? Top vs bottom quintile of the model's prediction.
    p = np.array([x[0] for x in res["model"]]); y = np.array([x[1] for x in res["model"]])
    q = np.quantile(p, [0.2, 0.8])
    print(f"  model bottom-20% days: realized mean |move| {np.mean(y[p<=q[0]])*100:.3f}%  |  top-20%: {np.mean(y[p>=q[1]])*100:.3f}%")
    A = np.array([X(r) for r in rows]); yy = np.log(np.array([max(r["y"], 1e-5) for r in rows]))
    beta, *_ = np.linalg.lstsq(A, yy, rcond=None)
    print("  full-sample coefficients [const, log VIX·t, log morning-range-scaled, log prior-range·t, log rv20·t, log gap]:",
          " ".join(f"{b:+.2f}" for b in beta))


def momentum():
    for sym in ("SPY", "QQQ"):
        rows = [r for r in features(sym) if r["k"] == 5]  # one per day; has first_hr and last_hr
        f = np.array([r["first_hr"] for r in rows]); m = np.array([r["signed_morn"] for r in rows]); l = np.array([r["last_hr"] for r in rows])
        print(f"{sym}: {len(rows)} sessions")
        for name, x in (("prev close->10:30 return", f), ("prev close->14:30 return", m)):
            r = np.corrcoef(x, l)[0, 1]; hit = np.mean(np.sign(x) == np.sign(l))
            big = np.abs(x) > np.quantile(np.abs(x), 0.8)
            print(f"  {name} vs last hour (15:30->16:00): corr {r:+.3f}  sign-hit {hit:.1%}  "
                  f"| top-20% |signal| days: hit {np.mean(np.sign(x[big]) == np.sign(l[big])):.1%} n={big.sum()}  "
                  f"avg last-hr move in signal direction {np.mean(np.sign(x[big]) * l[big])*100:+.3f}%")
        half = len(rows) // 2
        for nm, sl in (("first half", slice(0, half)), ("second half", slice(half, None))):
            print(f"    {nm}: corr(prev close->14:30, last hr) {np.corrcoef(m[sl], l[sl])[0,1]:+.3f}")


if __name__ == "__main__":
    if (sys.argv[1:] or ["vrp"])[0] != "edge": {"vrp": vrp, "model": model, "momentum": momentum}[sys.argv[1] if len(sys.argv) > 1 else "vrp"]()


def edge():
    """Buyer's edge test: is realized > VIX-implied on the afternoons the model flags? (proxy: no historical 0DTE IV)"""
    rows = features("SPY"); days = sorted({r["d"] for r in rows}); start = len(days) // 3
    def X(r):
        t = math.sqrt(r["mins"] / 390)
        return [1, math.log(r["vix"] / 100 * t), math.log(max(r["morn_rng"], 1e-4) / math.sqrt(390 - r["mins"]) * math.sqrt(r["mins"])),
                math.log(max(r["prior_rng"], 1e-4) * t), math.log(max(r["rv20"], 1e-5) * t), math.log(max(r["gap"], 1e-5) + 1e-3)]
    out = []
    for j in range(start, len(days)):
        train = [r for r in rows if r["d"] < days[j]]
        A = np.array([X(r) for r in train]); y = np.log(np.array([max(r["y"], 1e-5) for r in train]))
        beta, *_ = np.linalg.lstsq(A, y, rcond=None); adj = float(np.mean(np.exp(y - A @ beta)))
        for r in (q for q in rows if q["d"] == days[j]):
            pred = math.exp(np.array(X(r)) @ beta) * adj
            imp = r["vix"] / 100 * math.sqrt(r["mins"] / (390 * 252)) * 0.798   # VIX-implied E|move| to close
            out.append((pred / imp, r["y"] / imp, r["k"]))
    a = np.array(out)
    print(f"{len(a)} out-of-sample decisions. realized/VIX-implied overall: {a[:,1].mean():.2f}")
    for lo, hi in ((0, .6), (.6, .8), (.8, 1.0), (1.0, 1.2), (1.2, 9)):
        m = (a[:, 0] >= lo) & (a[:, 0] < hi)
        if m.sum() >= 20:
            print(f"  model/implied {lo:.1f}-{hi:.1f}: n={m.sum():4d}  realized/implied {a[m,1].mean():.2f}  "
                  f"P(realized > implied) {np.mean(a[m,1] > 1):.0%}")


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "edge":
    edge()
