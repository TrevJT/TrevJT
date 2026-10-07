#!/usr/bin/env python3
"""Correlation scanner: do prediction-market odds moves lead market moves?

  correlate.py scan [--min-days 60] [--top 25]
  correlate.py pair <poly market_id> <ASSET>     detail for one pair

For every Polymarket market with >= min-days of daily odds and every asset below, it measures:
  same : corr(Δodds_t, close-to-close return_t)           (co-movement, not tradeable by itself)
  lead : corr(Δodds_t, open-to-close return_{t+1})        (tradeable: odds are stamped ~20:00 ET, before the next open)
Each corr is computed on the first and second half of the overlap separately. A finding is only reported as
STABLE if both halves agree in sign and each |r| >= 0.15, and the full-sample p-value survives a Bonferroni
correction across every test run. Everything else is noise until proven otherwise.
"""
import os, sys, sqlite3, math, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "market.db")
ASSETS = ["SPY", "QQQ", "IWM", "^VIX", "CL=F", "XLE", "^TNX", "TLT", "GC=F", "DX-Y.NYB", "SMH", "XLF", "BTC-USD"]


def arg(n, d, cast=int):
    return cast(sys.argv[sys.argv.index(n) + 1]) if n in sys.argv else d


def corr(a, b):
    n = len(a)
    if n < 10: return 0.0
    ma, mb = statistics.mean(a), statistics.mean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return 0.0 if sa == 0 or sb == 0 else sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def pval(r, n):
    if n < 4 or abs(r) >= 1: return 0.0 if abs(r) >= 1 else 1.0
    t = abs(r) * math.sqrt((n - 2) / (1 - r * r))
    return math.erfc(t / math.sqrt(2))  # normal approx, two-sided


def load(c):
    px = {}
    for sym in ASSETS:
        rows = c.execute("SELECT ts, open, close FROM bars WHERE symbol=? AND interval='1d' ORDER BY ts", (sym,)).fetchall()
        d = {}
        for i in range(1, len(rows)):
            d[rows[i][0]] = (rows[i][2] / rows[i - 1][2] - 1 if sym not in ("^VIX", "^TNX") else rows[i][2] - rows[i - 1][2],
                             rows[i][2] / rows[i][1] - 1 if sym not in ("^VIX", "^TNX") else rows[i][2] - rows[i][1])
        px[sym] = d
    mk = {}
    for mid, q, topic, vol in c.execute("SELECT market_id, question, topic, volume FROM pm_markets WHERE source='poly'"):
        s = c.execute("SELECT ts, prob FROM pm_prices WHERE source='poly' AND market_id=? AND length(ts)=10 ORDER BY ts", (mid,)).fetchall()
        if s: mk[mid] = (q, topic, vol, s)
    return px, mk


def scan():
    c = sqlite3.connect(DB); px, mk = load(c)
    min_days = arg("--min-days", 60); top = arg("--top", 25)
    spy_days = sorted(px["SPY"])
    res = []; tests = 0
    for mid, (q, topic, vol, s) in mk.items():
        if len(s) < min_days: continue
        probs = dict(s)
        days = [d for d in spy_days if d in probs]
        if len(days) < min_days: continue
        dp = {days[i]: probs[days[i]] - probs[days[i - 1]] for i in range(1, len(days))}
        if statistics.pstdev(dp.values()) < 0.005: continue  # odds never move: nothing to learn
        for a in ASSETS:
            for kind in ("same", "lead"):
                xs, ys = [], []
                for i, d in enumerate(days[1:], 1):
                    if kind == "same":
                        if d in px[a]: xs.append(dp[d]); ys.append(px[a][d][0])
                    else:
                        nxt = days[i + 1] if i + 1 < len(days) else None
                        if nxt and nxt in px[a]: xs.append(dp[d]); ys.append(px[a][nxt][1])
                if len(xs) < min_days - 5: continue
                tests += 1
                h = len(xs) // 2
                r, r1, r2 = corr(xs, ys), corr(xs[:h], ys[:h]), corr(xs[h:], ys[h:])
                res.append((abs(r), r, r1, r2, len(xs), pval(r, len(xs)), kind, a, topic, q, mid))
    alpha = 0.05 / max(1, tests)
    stable = [x for x in res if x[2] * x[3] > 0 and min(abs(x[2]), abs(x[3])) >= 0.15]
    print(f"{len(mk)} markets, {tests} tests, Bonferroni threshold p < {alpha:.1e}\n")
    for title, rows in (("LEAD (odds today -> next-day open-to-close)", [x for x in stable if x[6] == "lead"]),
                        ("SAME-DAY co-movement", [x for x in stable if x[6] == "same"])):
        print(f"## {title}: {len(rows)} stable pairs")
        for _, r, r1, r2, n, p, kind, a, topic, q, mid in sorted(rows, reverse=True)[:top]:
            sig = "SIGNIFICANT" if p < alpha else ""
            print(f"  r={r:+.2f} (halves {r1:+.2f}/{r2:+.2f}) n={n:<4} p={p:.1e} {sig:<11} {a:<8} [{topic}] {q[:70]}  #{mid}")
        print()


def pair():
    c = sqlite3.connect(DB); px, mk = load(c)
    mid, a = sys.argv[2], sys.argv[3]; q, topic, vol, s = mk[mid]
    probs = dict(s); days = [d for d in sorted(px["SPY"]) if d in probs]
    print(f"{q}\n{len(days)} overlapping days {days[0]} -> {days[-1]}")
    big = [(probs[days[i]] - probs[days[i - 1]], days[i], days[i + 1] if i + 1 < len(days) else None) for i in range(1, len(days))]
    for dp, d, nxt in sorted(big, key=lambda x: -abs(x[0]))[:12]:
        same = px[a].get(d, (float('nan'),))[0]; nx = px[a].get(nxt, (None, float('nan')))[1] if nxt else float('nan')
        print(f"  {d}  odds {dp*100:+5.1f}pt   {a} same-day {same*100 if a not in ('^VIX','^TNX') else same:+.2f}   next-day o->c {nx*100 if a not in ('^VIX','^TNX') else nx:+.2f}")


if __name__ == "__main__":
    {"scan": scan, "pair": pair}.get(sys.argv[1] if len(sys.argv) > 1 else "scan", scan)()
