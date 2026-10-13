#!/usr/bin/env python3
"""Edge engine: is an option cheap or expensive versus what history says the underlying will do?

  edge.py snap  [SYM ...]          archive full option chains (nearest 4 expiries) into option_snaps (free, yfinance)
  edge.py scan  [--sym SPY] [--exp YYYY-MM-DD] [--min-ev 0.10] [--live]
        price every call, put and $1-$5 debit spread on that expiry against a forecast distribution of the
        underlying's move to expiry; print the best expected-value trades at the ASK (buys) / BID (sells).

Forecast (no directional view): empirical distribution of SPY daily open->close and close->close moves since 1993,
conditioned on prior-day VIX within ±2.5 pts of today's, and for the remaining part of the session scaled by
sqrt(remaining minutes / 390). Multi-day expiries compound close->close draws (block bootstrap, 5000 paths).
EV = mean(payoff at expiry) / cost - 1, after $0.04/contract/side fees. Held to expiry = conservative (no early profit-taking).
A trade only qualifies when EV >= --min-ev on a forecast that ignores direction; that is a VOLATILITY mispricing.
"""
import os, sys, sqlite3, math, random, json, statistics, contextlib, io, warnings
from datetime import datetime, timezone, timedelta, date
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "market.db")
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")  # was fixed UTC-4: would break when DST ends Nov 1
FEE = 0.04


def arg(n, d, cast=str):
    return cast(sys.argv[sys.argv.index(n) + 1]) if n in sys.argv else d


def conn():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS option_snaps(ts TEXT, symbol TEXT, expiry TEXT, type TEXT, strike REAL,
                 bid REAL, ask REAL, mark REAL, delta REAL, gamma REAL, theta REAL, vega REAL, iv REAL, oi INTEGER,
                 volume INTEGER, underlying REAL, PRIMARY KEY(ts, symbol, expiry, type, strike))""")
    c.execute("""CREATE TABLE IF NOT EXISTS edge_picks(ts TEXT, symbol TEXT, expiry TEXT, type TEXT, k1 REAL, k2 REAL,
                 cost REAL, ev REAL, p REAL, spot REAL, vix REAL, playbook TEXT, live INTEGER, graded_pnl REAL)""")
    return c


def chains(sym, n_exp=4):
    import yfinance as yf
    t = yf.Ticker(sym)
    with contextlib.redirect_stderr(io.StringIO()):
        exps = list(t.options)[:n_exp]
        spot = float(t.fast_info["last_price"])
        out = []
        for e in exps:
            ch = t.option_chain(e)
            for typ, df in (("call", ch.calls), ("put", ch.puts)):
                for r in df.itertuples():
                    out.append((e, typ, float(r.strike), float(r.bid or 0), float(r.ask or 0),
                                float(r.impliedVolatility or 0), int(r.openInterest or 0) if r.openInterest == r.openInterest else 0,
                                int(r.volume or 0) if r.volume == r.volume else 0))
    return spot, out


def snap():
    syms = [a for a in sys.argv[2:] if not a.startswith("--")] or ["SPY", "QQQ", "IWM"]
    c = conn(); ts = datetime.now(ET).strftime("%Y-%m-%d %H:%M"); n = 0
    for s in syms:
        try:
            spot, rows = chains(s)
        except Exception as e:
            print(f"  ! {s}: {e}"); continue
        for e, typ, k, b, a, iv, oi, vol in rows:
            c.execute("INSERT OR REPLACE INTO option_snaps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (ts, s, e, typ, k, b, a, (b + a) / 2 if a else b, None, None, None, None, iv, oi, vol, spot)); n += 1
    c.commit(); print(f"{ts} archived {n} option quotes ({', '.join(syms)})")


# ---------------------------------------------------------------- forecast
def hist(c, sym):
    px = c.execute("SELECT ts, open, close FROM bars WHERE symbol=? AND interval='1d' ORDER BY ts", (sym,)).fetchall()
    vix = dict(c.execute("SELECT ts, close FROM bars WHERE symbol='^VIX' AND interval='1d'").fetchall())
    rows = []
    for i in range(1, len(px)):
        v = vix.get(px[i - 1][0])
        if v: rows.append((v, px[i][2] / px[i][1] - 1, px[i][2] / px[i - 1][2] - 1))  # (prior VIX, o->c, c->c)
    return rows


def intraday_pool(c, sym, vix_now, mins_left):
    """Real historical returns from the same clock time to the close (1h bars, ~730 sessions), prior-day VIX within ±3,
    demeaned. Anchor = first bar starting at/after now; scaled by sqrt(actual minutes / anchor minutes) for the remainder."""
    vix = dict(c.execute("SELECT ts, close FROM bars WHERE symbol='^VIX' AND interval='1d'").fetchall())
    days = sorted({r[0] for r in c.execute("SELECT DISTINCT substr(ts,1,10) FROM bars WHERE symbol=? AND interval='1h'", (sym,))})
    vdates = sorted(vix)
    now_min = 16 * 60 - mins_left
    starts = [9*60+30 + 60*i for i in range(7)]
    anchor = next((s for s in starts if s >= now_min), None)
    if anchor is None or mins_left <= 0: return None
    a_hm = f"{anchor//60:02d}:{anchor%60:02d}"; a_left = 16*60 - anchor
    scale = math.sqrt(mins_left / a_left) if a_left > 0 else 1.0
    out = []
    for d in days:
        pv = None
        for v in reversed(vdates):
            if v < d: pv = vix[v]; break
        if pv is None or abs(pv - vix_now) > 3: continue
        rows = c.execute("SELECT ts, open, close FROM bars WHERE symbol=? AND interval='1h' AND ts LIKE ? ORDER BY ts", (sym, d + "%")).fetchall()
        st = next((o for t, o, cl in rows if t[11:16] == a_hm), None)
        if st and rows and rows[-1][0][11:16] == "15:30":
            out.append((rows[-1][2] / st - 1) * scale)
    if len(out) < 60: return None
    m = statistics.mean(out); long_pool = [x - m for x in out]
    # Recent-regime pool: last 60+ sessions of 5m bars, same clock time -> close (no VIX filter; it IS the current regime)
    rec = []
    for d in sorted({r[0] for r in c.execute("SELECT DISTINCT substr(ts,1,10) FROM bars WHERE symbol=? AND interval='5m'", (sym,))}):
        rows = c.execute("SELECT ts, open, close FROM bars WHERE symbol=? AND interval='5m' AND ts LIKE ? ORDER BY ts", (sym, d + "%")).fetchall()
        hm = f"{now_min//60:02d}:{(now_min%60)//5*5:02d}"
        st = next((o for t, o, cl in rows if t[11:16] >= hm), None)
        if st and rows and rows[-1][0][11:16] == "15:55": rec.append(rows[-1][2] / st - 1)
    if len(rec) >= 40:
        mr = statistics.mean(rec); rec = [x - mr for x in rec]
        # CONSERVATIVE: use whichever pool implies smaller moves (lower stdev) -> never overstate the edge
        if statistics.pstdev(rec) < statistics.pstdev(long_pool):
            intraday_pool.which = f"recent 5m n={len(rec)} (sd {100*statistics.pstdev(rec):.2f}% < long {100*statistics.pstdev(long_pool):.2f}%)"
            return rec
    intraday_pool.which = f"long 1h n={len(long_pool)}"
    return long_pool


def forecast(c, sym, vix_now, days, frac_today, n=5000, seed=7, mins_left=None):
    rows = hist(c, sym)
    pool = [r for r in rows if abs(r[0] - vix_now) <= 2.5] or rows
    # remove drift: the engine must take no directional view (30y SPY uptrend would otherwise favour calls)
    m_oc = statistics.mean(r[1] for r in pool); m_cc = statistics.mean(r[2] for r in pool)
    pool = [(v, oc - m_oc, cc - m_cc) for v, oc, cc in pool]
    rnd = random.Random(seed); out = []
    ip = intraday_pool(c, sym, vix_now, mins_left) if (mins_left and frac_today < 1) else None
    em = getattr(forecast, "model_emove", None)
    if ip and em:  # volmodel: SCALE from today's VIX + morning range + context, SHAPE from standardized residuals (conditional tails)
        import volmodel
        zp = volmodel.zpool(sym)
        if zp:
            mz = statistics.mean(abs(z) for z in zp)
            ip = [z * em / mz for z in zp]
            intraday_pool.which = f"volmodel E|move| {em*100:.3f}% x standardized shape (n={len(zp)}, sd {100*statistics.pstdev(ip):.2f}%)"
        else:
            cur = statistics.mean(abs(x) for x in ip)
            ip = [x * em / cur for x in ip]
            intraday_pool.which += f", SCALED by volmodel to E|move| {em*100:.3f}% (sd {100*statistics.pstdev(ip):.2f}%)"
    trim = float(sys.argv[sys.argv.index("--trim") + 1]) if "--trim" in sys.argv else 0.0
    if ip and trim > 0:  # drop the largest |move| days: shows the edge on a NORMAL day, not the tail bet
        ip = sorted(ip, key=abs)[: max(20, int(len(ip) * (1 - trim)))]
        intraday_pool.which += f", trimmed top {trim:.0%} -> sd {100*statistics.pstdev(ip):.2f}%"
    forecast.source = f"intraday {getattr(intraday_pool,'which','?')}" if ip else "daily o->c scaled"
    for _ in range(n):
        r = 1.0
        if frac_today > 0:
            r *= 1 + (rnd.choice(ip) if ip else rnd.choice(pool)[1] * math.sqrt(frac_today))
        for _ in range(days):  # whole sessions after today
            r *= 1 + rnd.choice(pool)[2]
        out.append(r)
    return out, len(pool)


VM_OOS_BIAS = 1.10  # walk-forward: model over-predicted E|move| by ~10% out of sample (research_vol.py model)


def implied_sd(q, spot):
    """Normal-model sd (fraction of spot) that best fits the quoted mids: the market's expected move to expiry."""
    pts = [(typ, k, (b + a) / 2) for e, typ, k, b, a, iv, oi, vol in q if a > 0 and (b + a) / 2 >= 0.03]
    if len(pts) < 3: return None
    def price(typ, k, sd):
        s = sd * spot; dd = ((k - spot) if typ == "call" else (spot - k)) / s
        return s * (math.exp(-dd * dd / 2) / math.sqrt(2 * math.pi) - dd * 0.5 * math.erfc(dd / math.sqrt(2)))
    best = min((sum((price(t, k, sd) - m) ** 2 for t, k, m in pts), sd) for sd in [x / 100000 for x in range(20, 2000)])
    return best[1]


def ev_long(paths, spot, typ, k, cost):
    pay = [max(0.0, (spot * g - k) if typ == "call" else (k - spot * g)) for g in paths]
    return statistics.mean(pay) * 100 / (cost * 100 + 2 * FEE) - 1, sum(p > cost for p in pay) / len(pay)


def ev_spread(paths, spot, typ, k1, k2, cost):
    w = abs(k2 - k1)
    pay = [min(w, max(0.0, (spot * g - k1) if typ == "call" else (k1 - spot * g))) for g in paths]
    return statistics.mean(pay) * 100 / (cost * 100 + 4 * FEE) - 1, sum(p > cost for p in pay) / len(pay)


def scan():
    sym = arg("--sym", "SPY"); min_ev = arg("--min-ev", 0.10, float)
    c = conn()
    # PRIOR-day close only: yfinance writes a live partial bar for today, which is not the gate/analog input
    vix_now = c.execute("SELECT close FROM bars WHERE symbol='^VIX' AND interval='1d' AND ts < date('now','localtime') ORDER BY ts DESC LIMIT 1").fetchone()[0]
    qf = arg("--quotes", None)
    if qf:  # REAL-TIME Robinhood quotes written by the cycle: {"spot":..,"expiry":..,"quotes":[{"type","strike","bid","ask","oi"}]}
        J = json.load(open(qf)); spot = float(J["spot"])
        rows = [(J["expiry"], q["type"], float(q["strike"]), float(q["bid"]), float(q["ask"]), 0.0, int(q.get("oi", 0)), 0) for q in J["quotes"]]
        src = f"ROBINHOOD live ({J.get('ts','?')})"
    else:
        spot, rows = chains(sym); src = "Yahoo (delayed ~15m; research only, never for orders)"
    exps = sorted({r[0] for r in rows}); exp = arg("--exp", exps[0])
    now = datetime.now(ET)
    if "--asof" in sys.argv:  # replay a past scan: --asof "YYYY-MM-DD HH:MM" (ET)
        now = datetime.strptime(arg("--asof", None), "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    today = now.date(); ed = date.fromisoformat(exp)
    open_now = now.weekday() < 5 and (9, 30) <= (now.hour, now.minute) < (16, 0)
    mins_left = max(0, (16 * 60) - (now.hour * 60 + now.minute)) if open_now else 0
    frac = mins_left / 390 if open_now else 0
    # sessions after today until expiry (weekdays)
    d = today; sess = 0
    while d < ed:
        d += timedelta(days=1)
        if d.weekday() < 5: sess += 1
    if not open_now and sess > 0:  # after hours: next session is a full open->close; first draw uses o->c via frac=1
        frac, sess = 1.0, sess - 1
    forecast.model_emove = None; vm_note = "volmodel off"
    if open_now and sess == 0 and "--no-model" not in sys.argv:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import volmodel
            o = h = l = None
            if qf and all(k in J for k in ("open", "high", "low")):
                o, h, l = float(J["open"]), float(J["high"]), float(J["low"]); vsrc = "quotes file"
            else:
                tb = volmodel.today_bars(c, sym, today.isoformat(), now.strftime("%H:%M"))
                if tb: o, h, l, _ = tb; vsrc = "5m bars in db"
            if o:
                em, det = volmodel.predict(sym, mins_left, o, h, l, spot, today.isoformat(), c)
                if em:
                    forecast.model_emove = em / VM_OOS_BIAS
                    vm_note = f"volmodel E|move| {em/VM_OOS_BIAS*100:.3f}% (morning range {det['morn_rng']*100:.2f}% from {vsrc})"
            else:
                vm_note = "volmodel: no open/high/low for today -> unscaled pool"
        except Exception as ex:
            vm_note = f"volmodel error {type(ex).__name__}: {ex}"
    paths, npool = forecast(c, sym, vix_now, sess, frac, mins_left=mins_left if open_now else None)
    q = [r for r in rows if r[0] == exp and r[4] > 0]
    res = []
    MIN_PX, MIN_P = arg("--min-px", 0.10, float), arg("--min-p", 0.10, float)
    for e, typ, k, b, a, iv, oi, vol in q:
        if abs(k / spot - 1) > 0.04 or a < MIN_PX: continue
        evv, pw = ev_long(paths, spot, typ, k, a)
        if pw < MIN_P: continue
        res.append((evv, pw, f"BUY {typ} {k:g} @ask {a:.2f}", (typ, k, None, a)))
    by = {}
    for e, typ, k, b, a, iv, oi, vol in q: by[(typ, k)] = (b, a)
    for (typ, k1), (b1, a1) in by.items():
        if abs(k1 / spot - 1) > 0.03: continue
        for w in (1, 2, 3, 5):
            k2 = k1 + w if typ == "call" else k1 - w
            if (typ, k2) not in by: continue
            cost = a1 - by[(typ, k2)][0]
            if cost < MIN_PX: continue
            evv, pw = ev_spread(paths, spot, typ, k1, k2, cost)
            if pw < MIN_P: continue
            res.append((evv, pw, f"BUY {typ} {k1:g}/{k2:g} debit spread @ {cost:.2f} (max {w:g})", (typ, k1, k2, cost)))
    res.sort(reverse=True)
    qual = [r for r in res if r[0] >= min_ev]
    print(f"{sym} {exp}: spot {spot:.2f}, prior VIX {vix_now:.2f} ({npool} analog days), forecast horizon "
          f"{frac*390:.0f} min today + {sess} sessions{'' if open_now else ' [market closed: quotes stale, indicative only]'}")
    print(f"  quotes: {src} | forecast: {getattr(forecast, 'source', '?')}")
    print(f"  {vm_note}")
    imp_sd = implied_sd(q, spot) if open_now and sess == 0 else None
    if imp_sd:
        msd = statistics.pstdev([g - 1 for g in paths])
        print(f"  market-implied sd to close {imp_sd*100:.3f}% vs engine sd {msd*100:.3f}%  (ratio {msd/imp_sd:.2f}; >1 = engine thinks options cheap)")
        if "--log" in sys.argv:
            c.execute("CREATE TABLE IF NOT EXISTS vol_obs(ts TEXT, symbol TEXT, mins_left INTEGER, spot REAL, implied_sd REAL, engine_sd REAL, model_emove REAL, realized REAL)")
            c.execute("INSERT INTO vol_obs VALUES (?,?,?,?,?,?,?,NULL)", (now.strftime("%Y-%m-%d %H:%M"), sym, mins_left, spot, imp_sd, msd, forecast.model_emove))
            c.commit()
    print(f"  {len(res)} structures priced; {len(qual)} with EV ≥ {min_ev:+.0%} vs history (held to expiry, fees in)")
    for evv, pw, desc, oi in res[:10]:
        print(f"  EV {evv:+6.0%}  P(profit) {pw:4.0%}  {desc}")
    print("  worst:", "; ".join(f"{d} EV {e:+.0%}" for e, _, d, _ in res[-3:]))
    if "--log" in sys.argv and open_now:
        c.execute("""CREATE TABLE IF NOT EXISTS edge_picks(ts TEXT, symbol TEXT, expiry TEXT, type TEXT, k1 REAL, k2 REAL,
                     cost REAL, ev REAL, p REAL, spot REAL, vix REAL, playbook TEXT, live INTEGER, graded_pnl REAL)""")
        for evv, pw, desc, (typ, k1, k2, cost) in qual[:5]:
            c.execute("INSERT INTO edge_picks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
                      (now.strftime("%Y-%m-%d %H:%M"), sym, exp, typ, k1, k2, cost, evv, pw, spot, vix_now, "EV", 0))
        c.commit(); print(f"  logged {min(5, len(qual))} picks to edge_picks (shadow)")
    if "--json" in sys.argv: print(json.dumps([{"ev": r[0], "p": r[1], "desc": r[2]} for r in qual]))


def grade():
    """Grade every shadow/live pick whose expiry has closed: payoff at expiry from the daily close in market.db."""
    c = conn(); n = 0; tot = []
    rows = c.execute("SELECT rowid, symbol, expiry, type, k1, k2, cost FROM edge_picks WHERE graded_pnl IS NULL").fetchall()
    for rid, sym, exp, typ, k1, k2, cost in rows:
        r = c.execute("SELECT close FROM bars WHERE symbol=? AND interval='1d' AND ts=?", (sym, exp)).fetchone()
        if not r: continue
        px = r[0]; intr = max(0.0, (px - k1) if typ == "call" else (k1 - px))
        if k2 is not None: intr = min(intr, abs(k2 - k1))
        pnl = (intr - cost) * 100 - (4 if k2 is not None else 2) * FEE
        c.execute("UPDATE edge_picks SET graded_pnl=? WHERE rowid=?", (pnl, rid)); n += 1
    c.commit()
    # Self-learning loop: who forecasts the move-to-close better, the market (implied) or the engine?
    c.execute("CREATE TABLE IF NOT EXISTS vol_obs(ts TEXT, symbol TEXT, mins_left INTEGER, spot REAL, implied_sd REAL, engine_sd REAL, model_emove REAL, realized REAL)")
    for rid, sym, ts, spot in c.execute("SELECT rowid, symbol, ts, spot FROM vol_obs WHERE realized IS NULL").fetchall():
        r = c.execute("SELECT close FROM bars WHERE symbol=? AND interval='1d' AND ts=?", (sym, ts[:10])).fetchone()
        if r and ts[:10] < datetime.now(ET).strftime("%Y-%m-%d") or (r and datetime.now(ET).hour >= 17):
            c.execute("UPDATE vol_obs SET realized=? WHERE rowid=?", (abs(math.log(r[0] / spot)), rid))
    c.commit()
    vo = c.execute("SELECT implied_sd, engine_sd, realized FROM vol_obs WHERE realized IS NOT NULL").fetchall()
    if vo:
        days = c.execute("SELECT COUNT(DISTINCT substr(ts,1,10)) FROM vol_obs WHERE realized IS NOT NULL").fetchone()[0]
        mr = statistics.mean(x[2] for x in vo)
        print(f"vol_obs: {len(vo)} scans over {days} days. realized E|move| {mr*100:.3f}% vs market-implied {statistics.mean(x[0] for x in vo)*0.798*100:.3f}%"
              f" vs engine {statistics.mean(x[1] for x in vo)*0.798*100:.3f}%  -> realized/market {mr/(statistics.mean(x[0] for x in vo)*0.798):.2f},"
              f" realized/engine {mr/(statistics.mean(x[1] for x in vo)*0.798):.2f}  (engine trusted only if realized/market > 1 over >= 20 days)")
    allg = c.execute("SELECT cost, graded_pnl, ev FROM edge_picks WHERE graded_pnl IS NOT NULL").fetchall()
    if allg:
        spent = sum(x[0] * 100 for x in allg); pnl = sum(x[1] for x in allg)
        print(f"graded {n} new; all-time {len(allg)} picks, return on premium {pnl/spent:+.0%} "
              f"(engine predicted avg EV {statistics.mean(x[2] for x in allg):+.0%}), win rate {sum(x[1]>0 for x in allg)/len(allg):.0%}")
        for side in ("call", "put"):  # calls trade at lower IV than puts (skew); check the engine is not mistaking skew for edge
            g = c.execute("SELECT cost, graded_pnl, ev FROM edge_picks WHERE graded_pnl IS NOT NULL AND type=?", (side,)).fetchall()
            if g:
                sp = sum(x[0] * 100 for x in g)
                print(f"  {side}s: {len(g)} picks, return {sum(x[1] for x in g)/sp:+.0%} vs predicted {statistics.mean(x[2] for x in g):+.0%}, "
                      f"win {sum(x[1]>0 for x in g)/len(g):.0%}")
    else:
        print(f"graded {n}; nothing graded yet")


if __name__ == "__main__":
    {"snap": snap, "scan": scan, "grade": grade}.get(sys.argv[1] if len(sys.argv) > 1 else "scan", scan)()
