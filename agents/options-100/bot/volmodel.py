#!/usr/bin/env python3
"""Conditional move-to-close model (research: bot/research_vol.py model/edge, LEARNINGS 2026-10-12).

E|log(close/now)| = smear * exp(b · [1, log(VIX·t), log(morning range scaled to time left), log(prior range·t), log(rv20·t), log(gap)])
Fit on every SPY/QQQ hourly session we have (~730, 2023-11 onward); refit nightly. Walk-forward: log-corr with realized 0.39
vs 0.23 for the old "last 60 sessions, same clock time" pool; top-20% vs bottom-20% predicted afternoons realize 0.61% vs 0.15%.

  python3 agents/options-100/bot/volmodel.py fit [SYM]          # writes state/volmodel_<SYM>.json
  python3 agents/options-100/bot/volmodel.py now [SYM] [HH:MM]  # prediction using today's 5m bars in market.db
"""
import json, math, sqlite3, statistics, sys
from datetime import datetime
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "market.db"


def _x(vix, mins, morn_rng, prior_rng, rv20, gap):
    t = math.sqrt(mins / 390)
    elapsed = max(390 - mins, 5)
    return [1, math.log(vix / 100 * t), math.log(max(morn_rng, 1e-4) / math.sqrt(elapsed) * math.sqrt(mins)),
            math.log(max(prior_rng, 1e-4) * t), math.log(max(rv20, 1e-5) * t), math.log(max(gap, 1e-5) + 1e-3)]


def _daily(c, sym):
    return {r[0]: r[1:] for r in c.execute("SELECT ts, open, high, low, close FROM bars WHERE symbol=? AND interval='1d' ORDER BY ts", (sym,))}


def _ctx(c, sym, d):
    """Prior-day inputs known before the open of session d."""
    D, V = _daily(c, sym), _daily(c, "^VIX")
    days = sorted(x for x in D if x < d)
    vdays = sorted(x for x in V if x < d)
    if len(days) < 21 or not vdays: return None
    p = days[-1]
    rv20 = statistics.pstdev([math.log(D[days[k]][3] / D[days[k - 1]][3]) for k in range(len(days) - 20, len(days))])
    return dict(pc=D[p][3], prior_rng=(D[p][1] - D[p][2]) / D[p][3], rv20=rv20, vix=V[vdays[-1]][3])


def fit(sym="SPY"):
    sys.path.insert(0, str(Path(__file__).parent))
    from research_vol import features
    rows = features(sym)
    A = np.array([_x(r["vix"], r["mins"], r["morn_rng"], r["prior_rng"], r["rv20"], r["gap"]) for r in rows])
    y = np.log(np.array([max(r["y"], 1e-5) for r in rows]))
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    smear = float(np.mean(np.exp(y - A @ beta)))
    pred = np.exp(A @ beta) * smear
    bias = float(np.mean(pred) / np.mean(np.exp(y)))
    # Conditional SHAPE: signed move / model E|move|. Mixing calm and wild days fakes fat tails; standardizing removes that.
    z = np.array([r["ys"] for r in rows]) / pred
    z = z - z.mean()
    kurt = float(np.mean(z**4) / np.mean(z**2)**2)
    raw = np.array([r["ys"] for r in rows]); kraw = float(np.mean((raw-raw.mean())**4) / np.var(raw)**2)
    out = dict(sym=sym, n=len(rows), sessions=len({r["d"] for r in rows}), beta=[float(b) for b in beta], smear=smear,
               bias=bias, kurtosis_z=kurt, kurtosis_raw=kraw, z=[round(float(x), 4) for x in z],
               fitted=datetime.now().isoformat(timespec="minutes"))
    (ROOT / "state" / f"volmodel_{sym}.json").write_text(json.dumps(out, indent=1))
    print(f"fit {sym}: {out['n']} decisions / {out['sessions']} sessions, in-sample bias {bias:.2f}, beta {' '.join(f'{b:+.2f}' for b in beta)}; kurtosis raw {kraw:.1f} -> standardized {kurt:.1f} (normal 3.0)")
    return out


def predict(sym, mins_left, day_open, day_high, day_low, spot, d=None, c=None):
    """Expected |move| from now to the close, as a fraction. Returns (emove, details) or (None, reason)."""
    f = ROOT / "state" / f"volmodel_{sym}.json"
    if not f.exists(): return None, "no model file (run volmodel.py fit)"
    m = json.loads(f.read_text())
    c = c or sqlite3.connect(DB, timeout=60)
    d = d or datetime.now(ET).strftime("%Y-%m-%d")
    ctx = _ctx(c, sym, d)
    if not ctx or mins_left <= 0: return None, "no context"
    morn = (max(day_high, spot) - min(day_low, spot)) / day_open
    gap = abs(day_open / ctx["pc"] - 1)
    x = np.array(_x(ctx["vix"], mins_left, morn, ctx["prior_rng"], ctx["rv20"], gap))
    em = math.exp(x @ np.array(m["beta"])) * m["smear"] / m["bias"]
    return em, dict(vix=ctx["vix"], morn_rng=morn, gap=gap, prior_rng=ctx["prior_rng"], rv20=ctx["rv20"])


def zpool(sym):
    f = ROOT / "state" / f"volmodel_{sym}.json"
    return json.loads(f.read_text()).get("z") if f.exists() else None


def today_bars(c, sym, d, upto_hm):
    rows = c.execute("SELECT ts, open, high, low, close FROM bars WHERE symbol=? AND interval='5m' AND ts LIKE ? AND substr(ts,12,5) < ? ORDER BY ts",
                     (sym, d + "%", upto_hm)).fetchall()
    if not rows: return None
    return rows[0][1], max(r[2] for r in rows), min(r[3] for r in rows), rows[-1][4]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "now"; sym = sys.argv[2] if len(sys.argv) > 2 else "SPY"
    if cmd == "fit": fit(sym)
    else:
        c = sqlite3.connect(DB, timeout=60); d = datetime.now(ET).strftime("%Y-%m-%d")
        hm = sys.argv[3] if len(sys.argv) > 3 else datetime.now(ET).strftime("%H:%M")
        b = today_bars(c, sym, d, hm)
        if not b: print("no 5m bars for today yet"); sys.exit()
        o, h, l, px = b; mins = 16 * 60 - (int(hm[:2]) * 60 + int(hm[3:]))
        em, det = predict(sym, mins, o, h, l, px, d, c)
        print(f"{sym} {d} {hm}: E|move to close| {em*100:.3f}% (sd≈{em/0.798*100:.3f}%)  inputs {det}")
