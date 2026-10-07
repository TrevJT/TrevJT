#!/usr/bin/env python3
"""Historical context for options-100, built from data/market.db (see history.py).

  context.py brief  [--date YYYY-MM-DD]   pre-open regime brief: vol regime, analog days, expected range
  context.py backtest [--sym SPY] [--rvol 1.3] [--atr 0] [--hold 30] [--target 1.0] [--stop 0.6]
                                          replay the live score model on every stored 5m session
  context.py tod [--sym SPY]              time-of-day profile: avg range / trend persistence per 30-min slot

The backtest uses the underlying, not option prices (no free option history). A 'win' is the underlying moving
`target` x ATR5 in the signal direction before moving `stop` x ATR5 against it, within `hold` minutes. With
0.10-0.20 delta 0DTE options, ~1 ATR5 favourable is roughly what +50-100% on premium needs.
"""
import os, sys, sqlite3, statistics, math, json
from datetime import datetime, timedelta
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "market.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def q(sql, *a):
    c = sqlite3.connect(DB)
    return c.execute(sql, a).fetchall()


def daily(sym):
    return q("SELECT ts, open, high, low, close FROM bars WHERE symbol=? AND interval='1d' ORDER BY ts", sym)


def pct_rank(xs, x):
    xs = sorted(xs); lo = 0
    for v in xs:
        if v < x: lo += 1
    return 100.0 * lo / max(1, len(xs))


def arg(name, default, cast=str):
    if name in sys.argv:
        return cast(sys.argv[sys.argv.index(name) + 1])
    return default


# ---------------------------------------------------------------- brief
def brief():
    spy = daily("SPY"); vix = {r[0]: r[4] for r in daily("^VIX")}
    v9 = {r[0]: r[4] for r in daily("^VIX9D")}; v3 = {r[0]: r[4] for r in daily("^VIX3M")}
    tnx = {r[0]: r[4] for r in daily("^TNX")}
    target = arg("--date", spy[-1][0])
    idx = max(i for i, r in enumerate(spy) if r[0] <= target)
    # features for every day i using only data up to the prior close (+ today's open for the gap)
    def feats(i):
        if i < 260: return None
        d, o, h, l, c = spy[i]; pc = spy[i - 1][4]
        rets = [spy[k][4] / spy[k - 1][4] - 1 for k in range(i - 20, i)]
        rv20 = statistics.pstdev(rets) * math.sqrt(252) * 100
        trs = [max(spy[k][2] - spy[k][3], abs(spy[k][2] - spy[k - 1][4]), abs(spy[k][3] - spy[k - 1][4])) / spy[k - 1][4] * 100 for k in range(i - 14, i)]
        vx = vix.get(spy[i - 1][0])
        return {"date": d, "gap": (o / pc - 1) * 100, "prev": (pc / spy[i - 2][4] - 1) * 100,
                "r20": (pc / spy[i - 21][4] - 1) * 100, "rv20": rv20, "atr": statistics.mean(trs),
                "vix": vx, "dd52": (pc / max(r[2] for r in spy[i - 252:i]) - 1) * 100,
                "oc": (c / o - 1) * 100, "rng": (h - l) / o * 100, "trend": abs(c - o) / max(1e-9, h - l)}
    allf = [f for f in (feats(i) for i in range(len(spy))) if f and f["vix"] is not None]
    today = feats(idx)
    out = [f"# Market context for {today['date']} (SPY daily since {spy[0][0]}, VIX since 1990)"]
    vix_hist = [f["vix"] for f in allf]
    out.append(f"- VIX prior close {today['vix']:.2f} = {pct_rank(vix_hist, today['vix']):.0f}th percentile since 1993."
               f" VIX9D/VIX {v9.get(spy[idx-1][0], float('nan'))/today['vix']:.2f}, VIX/VIX3M {today['vix']/v3.get(spy[idx-1][0], float('nan')):.2f} (>1 = inverted, stress).")
    out.append(f"- SPY 20d realized vol {today['rv20']:.1f}% ({pct_rank([f['rv20'] for f in allf], today['rv20']):.0f}th pct); daily ATR {today['atr']:.2f}% ({pct_rank([f['atr'] for f in allf], today['atr']):.0f}th pct).")
    out.append(f"- Gap today {today['gap']:+.2f}% ({pct_rank([abs(f['gap']) for f in allf], abs(today['gap'])):.0f}th pct by size); prior day {today['prev']:+.2f}%; 20d {today['r20']:+.2f}%; {today['dd52']:+.2f}% from 52w high.")
    tk = sorted(tnx)[-6:]
    if len(tk) == 6:
        out.append(f"- 10y yield {tnx[tk[-1]]:.2f}% ({(tnx[tk[-1]]-tnx[tk[0]])*100:+.0f} bp over 5 sessions).")
    # analogs: nearest neighbours on standardized features
    keys = ["gap", "prev", "r20", "vix", "rv20", "dd52"]
    hist = [f for f in allf if f["date"] < today["date"]]
    mu = {k: statistics.mean(f[k] for f in hist) for k in keys}; sd = {k: statistics.pstdev(f[k] for f in hist) or 1 for k in keys}
    w = {"gap": 2.0, "prev": 1.0, "r20": 1.0, "vix": 1.5, "rv20": 1.0, "dd52": 0.7}
    dist = lambda f: math.sqrt(sum(w[k] * ((f[k] - today[k]) / sd[k]) ** 2 for k in keys))
    an = sorted(hist, key=dist)[:30]
    up = sum(1 for f in an if f["oc"] > 0)
    out.append(f"- 30 nearest analog days (gap, prior day, 20d trend, VIX, realized vol, drawdown): open->close up {up}/30,"
               f" median {statistics.median(f['oc'] for f in an):+.2f}%, median range {statistics.median(f['rng'] for f in an):.2f}%,"
               f" trend days (|o-c|/range>0.6) {sum(f['trend']>0.6 for f in an)}/30.")
    out.append("  closest: " + ", ".join(f"{f['date']} ({f['oc']:+.2f}%)" for f in an[:6]))
    exp_rng = statistics.median(f["rng"] for f in an) / 100 * spy[idx][1]
    out.append(f"- Expected SPY intraday range today ≈ ${exp_rng:.2f} (analog median). A 0.10-0.20Δ 0DTE needs most of that range in one direction to double.")
    # base rates in the same VIX bucket
    b = [f for f in hist if abs(f["vix"] - today["vix"]) < 2]
    out.append(f"- Base rate, VIX within ±2 of today ({len(b)} days): trend days {100*sum(f['trend']>0.6 for f in b)/len(b):.0f}%,"
               f" median range {statistics.median(f['rng'] for f in b):.2f}%, |o-c|>0.5%: {100*sum(abs(f['oc'])>0.5 for f in b)/len(b):.0f}%.")
    dow = datetime.strptime(today["date"], "%Y-%m-%d").weekday()
    bd = [f for f in hist if datetime.strptime(f["date"], "%Y-%m-%d").weekday() == dow]
    out.append(f"- Same weekday base rate: trend days {100*sum(f['trend']>0.6 for f in bd)/len(bd):.0f}%, median range {statistics.median(f['rng'] for f in bd):.2f}%.")
    verdict = "TRENDY" if (sum(f['trend'] > 0.6 for f in an) >= 14 or today['vix'] > 22) else ("CHOPPY" if sum(f['trend'] > 0.6 for f in an) <= 9 else "MIXED")
    out.append(f"- Regime call: **{verdict}**. CHOPPY → only take S at ±5 with RVOL≥1.3; TRENDY → normal rules.")
    print("\n".join(out))


# ---------------------------------------------------------------- intraday backtest
from score import score_symbol, _session, ET  # reuse the live model exactly
import score as live


def bars5(sym):
    rows = q("SELECT ts, open, high, low, close, volume FROM bars WHERE symbol=? AND interval='5m' ORDER BY ts", sym)
    out = []
    for ts, o, h, l, c, v in rows:
        t = datetime.strptime(ts, "%Y-%m-%d %H:%M").replace(tzinfo=ET)
        out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    return out


def backtest():
    sym = arg("--sym", "SPY"); min_rvol = arg("--rvol", 0.0, float); min_atr = arg("--atr", 0.0, float)
    hold = arg("--hold", 30, int); tgt = arg("--target", 1.0, float); stp = arg("--stop", 0.6, float)
    thr = arg("--score", 4, int)
    allb = bars5(sym); days = sorted({b["t"].date() for b in allb})
    live._load = lambda s: [b for b in allb if b["t"] < live._cut]  # feed the live scorer from the DB
    res = []; per_day = defaultdict(int)
    for day in days[3:]:
        sess = [b for b in allb if b["t"].date() == day and (9, 30) <= (b["t"].hour, b["t"].minute) < (16, 0)]
        if len(sess) < 70: continue
        taken = 0; next_ok = None
        for i, b in enumerate(sess):
            if next_ok and b["t"] < next_ok: continue
            hm = b["t"] + timedelta(minutes=5)  # decision time = bar close
            if not ((9, 40) <= (hm.hour, hm.minute) <= (11, 0) or (14, 0) <= (hm.hour, hm.minute) <= (15, 10)): continue
            if taken >= 4: break
            live._cut = hm
            s = score_symbol(sym, hm.strftime("%H:%M"), day=day)
            if "error" in s or abs(s["score"]) < thr: continue
            if s["rvol"] < min_rvol or s["atr5"] < min_atr: continue
            d = 1 if s["score"] > 0 else -1; entry = b["c"]; atr = s["atr5"]
            fut = [x for x in sess[i + 1:] if x["t"] < b["t"] + timedelta(minutes=5 + hold)]
            outc = "time"; mfe = 0
            for x in fut:
                fav = (x["h"] - entry) if d > 0 else (entry - x["l"]); adv = (entry - x["l"]) if d > 0 else (x["h"] - entry)
                mfe = max(mfe, fav)
                if adv >= stp * atr: outc = "stop"; break
                if fav >= tgt * atr: outc = "win"; break
            res.append({"day": str(day), "t": hm.strftime("%H:%M"), "dir": d, "S": s["score"], "rvol": s["rvol"], "atr": atr,
                        "out": outc, "mfe_atr": mfe / atr if atr else 0})
            taken += 1; per_day[str(day)] += 1
            next_ok = b["t"] + timedelta(minutes=hold)  # one position at a time per symbol
    n = len(res)
    if not n:
        print(f"{sym}: no signals in {len(days)} days"); return
    w = sum(r["out"] == "win" for r in res); st = sum(r["out"] == "stop" for r in res)
    print(f"{sym} 5m backtest {days[0]}→{days[-1]} ({len(days)} sessions) | score≥{thr} rvol≥{min_rvol} atr5≥{min_atr} hold {hold}m target {tgt}ATR stop {stp}ATR")
    print(f"  signals {n} ({n/len(days):.1f}/day)  win {w} ({100*w/n:.0f}%)  stop {st} ({100*st/n:.0f}%)  timed-out {n-w-st} ({100*(n-w-st)/n:.0f}%)")
    print(f"  median max-favourable move {statistics.median(r['mfe_atr'] for r in res):.2f} ATR5")
    for lab, f in [("window A", lambda r: r["t"] <= "11:00"), ("window B", lambda r: r["t"] >= "14:00"),
                   ("calls", lambda r: r["dir"] > 0), ("puts", lambda r: r["dir"] < 0),
                   ("rvol≥1.3", lambda r: r["rvol"] >= 1.3), ("rvol<1.3", lambda r: r["rvol"] < 1.3), ("|S|≥5", lambda r: abs(r["S"]) >= 5)]:
        sub = [r for r in res if f(r)]
        if sub: print(f"  {lab:<9} n={len(sub):>3} win {100*sum(r['out']=='win' for r in sub)/len(sub):>3.0f}%  stop {100*sum(r['out']=='stop' for r in sub)/len(sub):>3.0f}%")
    if "--json" in sys.argv: print(json.dumps(res))


def tod():
    sym = arg("--sym", "SPY"); allb = bars5(sym); slots = defaultdict(list)
    for b in allb:
        if (9, 30) <= (b["t"].hour, b["t"].minute) < (16, 0):
            slots[f"{b['t'].hour:02d}:{(b['t'].minute//30)*30:02d}"].append((b["h"] - b["l"]) / b["o"] * 100)
    print(f"{sym} avg 5m bar range by 30-min slot ({len({b['t'].date() for b in allb})} sessions):")
    for k in sorted(slots): print(f"  {k}  {statistics.mean(slots[k]):.3f}%  " + "#" * int(statistics.mean(slots[k]) * 300))


if __name__ == "__main__":
    {"brief": brief, "backtest": backtest, "tod": tod}.get(sys.argv[1] if len(sys.argv) > 1 else "brief", brief)()
