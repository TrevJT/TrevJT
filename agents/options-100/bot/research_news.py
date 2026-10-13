#!/usr/bin/env python3
"""Research: is single-stock news already priced in by the time a 5-minute RSS poller can act?

  python3 agents/options-100/bot/research_news.py fetch        # download ~730d hourly + 3y daily + earnings dates (cached)
  python3 agents/options-100/bot/research_news.py events       # shock-day event study: drift after 10:30 / 11:30 entries
  python3 agents/options-100/bot/research_news.py contagion    # leader shocks -> do un-moved peers catch up?
  python3 agents/options-100/bot/research_news.py latency [YYYY-MM-DD]   # today's 5m path vs RSS headline times

Data: Yahoo Finance via yfinance (public). Cache: data/research_news_cache.pkl (not market.db; launchd jobs hold that lock).
Shock day: |open/prev_close-1| >= 4% OR |10:30 price/prev_close-1| >= 4%. Direction = sign(10:30 price vs prev close),
i.e. what a bot sees when it acts. Returns are signed in the shock direction (+ = continuation, - = reversal).
Earnings reactions (earnings date on day d, or after-close on d-1) are tagged and excluded by default (--with-earnings).
Implied-move proxy (no historical single-stock IV here): post-shock daily IV = BUMP x 20d realized vol; see implied().
"""
import sys, math, pickle, warnings, contextlib, io
from pathlib import Path
from collections import defaultdict
import numpy as np
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "research_news_cache.pkl"

GROUPS = {
    "memory": ["MU", "STX", "WDC", "SNDK"],
    "semis": ["NVDA", "AMD", "AVGO", "INTC", "QCOM", "TXN", "MRVL", "LRCX", "AMAT", "KLAC", "ON", "NXPI", "ADI",
              "MCHP", "ARM", "TSM", "ASML", "SMCI"],
    "megatech": ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NFLX"],
    "software": ["ORCL", "CRM", "ADBE", "NOW", "PLTR", "SNOW", "CRWD", "PANW", "SHOP", "UBER"],
    "crypto": ["COIN", "MSTR", "HOOD"],
    "banks": ["JPM", "BAC", "GS", "MS", "C", "WFC", "SCHW"],
    "pharma": ["UNH", "LLY", "JNJ", "PFE", "MRK", "ABBV", "MRNA"],
    "retail": ["WMT", "COST", "HD", "NKE", "SBUX", "MCD", "TGT", "LULU", "DIS"],
    "energy": ["XOM", "CVX", "OXY", "SLB"],
    "industrial": ["BA", "CAT", "GE", "DE", "UPS", "FDX"],
    "autos": ["TSLA", "RIVN", "F", "GM"],
    "travel": ["DAL", "UAL", "CCL"],
}
SYM2G = {s: g for g, ss in GROUPS.items() for s in ss}
UNIVERSE = list(SYM2G)
REF = ["SPY", "SMH", "SOXX"]
SHOCK, PEER_MOVE = 0.04, 0.025     # shock threshold; a peer "also moved" at >= 2.5% same sign
BUMP = 1.5                          # assumed post-shock IV / pre-shock 20d RV (sensitivity 1.25 / 2.0 also shown)


# ---------------------------------------------------------------- data
def _dl(syms, period, interval):
    import yfinance as yf
    with contextlib.redirect_stderr(io.StringIO()):
        d = yf.download(syms, period=period, interval=interval, progress=False, auto_adjust=False,
                        prepost=False, group_by="ticker", threads=True)
    out = {}
    for s in syms:
        try:
            x = d[s].dropna(subset=["Close"])
        except KeyError:
            continue
        if x.empty: continue
        idx = x.index
        if interval != "1d":
            idx = idx.tz_convert("America/New_York") if idx.tz is not None else idx.tz_localize("UTC").tz_convert("America/New_York")
        fmt = "%Y-%m-%d" if interval == "1d" else "%Y-%m-%d %H:%M"
        out[s] = {t.strftime(fmt): (float(r.Open), float(r.High), float(r.Low), float(r.Close))
                  for t, r in zip(idx, x.itertuples(index=False))}
    return out


def fetch():
    import yfinance as yf
    syms = UNIVERSE + REF
    print(f"downloading {len(syms)} symbols: daily 3y, hourly 730d ...")
    data = {"daily": _dl(syms, "3y", "1d"), "hourly": _dl(syms, "730d", "1h"), "earn": {}}
    for i, s in enumerate(UNIVERSE):
        try:
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                e = yf.Ticker(s).get_earnings_dates(limit=16)
            idx = e.index.tz_convert("America/New_York")
            data["earn"][s] = [(t.strftime("%Y-%m-%d"), t.hour) for t in idx]
        except Exception as ex:
            data["earn"][s] = None
    miss = [s for s, v in data["earn"].items() if not v]
    CACHE.write_bytes(pickle.dumps(data))
    print(f"daily {len(data['daily'])}  hourly {len(data['hourly'])}  earnings ok {len(UNIVERSE)-len(miss)}"
          + (f"  (no earnings dates: {' '.join(miss)})" if miss else "") + f"\n-> {CACHE}")


def load():
    if not CACHE.exists():
        fetch()
    return pickle.loads(CACHE.read_bytes())


# ---------------------------------------------------------------- per-day panel
def panel(data):
    """rows: one per (symbol, session) with hourly coverage. Every field except the fwd_* targets is known by 10:30."""
    D, H, E = data["daily"], data["hourly"], data["earn"]
    spy = D["SPY"]; spyH = H.get("SPY", {})
    sdays = sorted(spy)
    spx = {}   # SPY prices at the same decision/exit points, for --excess (market-adjusted) returns
    for i in range(1, len(sdays) - 3):
        a, b = spyH.get(sdays[i] + " 09:30"), spyH.get(sdays[i] + " 10:30")
        if a and b:
            spx[sdays[i]] = dict(p1030=a[3], p1130=b[3], c0=spy[sdays[i]][3], c1=spy[sdays[i + 1]][3], c3=spy[sdays[i + 3]][3])
    rows = []
    for s in UNIVERSE:
        if s not in D or s not in H: continue
        d, h = D[s], H[s]
        days = sorted(d)
        hb = defaultdict(dict)
        for ts, v in h.items():
            hb[ts[:10]][ts[11:16]] = v
        earn_days = set()
        for ed, hr in (E.get(s) or []):
            if ed in d:
                k = days.index(ed)
                nxt = days[k + 1] if k + 1 < len(days) else None
                if hr >= 16:                     # after close -> next session reacts
                    earn_days.add(nxt)
                elif 1 <= hr < 9:                # pre-market -> same session
                    earn_days.add(ed)
                else:                            # unknown (00:00) or intraday: tag both, conservatively
                    earn_days.update((ed, nxt))
        for i in range(21, len(days) - 3):
            day = days[i]
            b = hb.get(day, {})
            if "09:30" not in b or "10:30" not in b: continue
            pc = d[days[i - 1]][3]; o = d[day][0]
            p1030, p1130 = b["09:30"][3], b["10:30"][3]
            rets = [math.log(d[days[k]][3] / d[days[k - 1]][3]) for k in range(i - 20, i)]
            sp = spy.get(day); spp = spy.get(days[i - 1]) if days[i - 1] in spy else None
            sb = spyH.get(day + " 09:30")
            rows.append(dict(
                s=s, g=SYM2G[s], d=day, gap=o / pc - 1, fh=p1030 / pc - 1, p1030=p1030, p1130=p1130,
                c0=d[day][3], c1=d[days[i + 1]][3], c3=d[days[i + 3]][3], rv20=float(np.std(rets)),
                earn=day in earn_days, earn_known=bool(E.get(s)), spx=spx.get(day),
                spy_fh=(sb[3] / spp[3] - 1) if (sb and spp) else float("nan"),
                spy_day=(sp[3] / spp[3] - 1) if (sp and spp) else float("nan")))
    return rows


def tag_shocks(rows):
    byday = defaultdict(list)
    for r in rows: byday[r["d"]].append(r)
    for r in rows:
        r["shock"] = abs(r["gap"]) >= SHOCK or abs(r["fh"]) >= SHOCK
        r["dir"] = 1 if r["fh"] > 0 else -1
        peers = [q for q in byday[r["d"]] if q["g"] == r["g"] and q["s"] != r["s"]]
        r["n_peers_moved"] = sum(1 for q in peers if q["fh"] * r["dir"] >= PEER_MOVE)
        r["contagion"] = r["n_peers_moved"] >= 2 or (len(peers) <= 3 and r["n_peers_moved"] >= 1)
    return rows


# ---------------------------------------------------------------- stats
def stat(x, days=None):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    n = len(x)
    if n < 3: return dict(n=n, mean=float("nan"), med=float("nan"), hit=float("nan"), t=float("nan"), tc=float("nan"))
    t = x.mean() / (x.std(ddof=1) / math.sqrt(n)) if x.std() > 0 else float("nan")
    tc = float("nan")
    if days is not None:   # day-clustered t: average per date first (same-day events are not independent)
        g = defaultdict(list)
        for v, dd in zip(x, days): g[dd].append(v)
        m = np.array([np.mean(v) for v in g.values()])
        if len(m) > 2 and m.std() > 0: tc = m.mean() / (m.std(ddof=1) / math.sqrt(len(m)))
    return dict(n=n, mean=x.mean(), med=float(np.median(x)), hit=float(np.mean(x > 0)), t=t, tc=tc)


HORIZ = {  # (entry field, exit field, trading-day variance fraction from entry to exit; 6.5h session, overnight ~ 0.25 of day var)
    "10:30->close": ("p1030", "c0", 5.5 / 6.5 * 0.75),
    "10:30->next close": ("p1030", "c1", 5.5 / 6.5 * 0.75 + 1),
    "10:30->3d close": ("p1030", "c3", 5.5 / 6.5 * 0.75 + 3),
    "11:30->close": ("p1130", "c0", 4.5 / 6.5 * 0.75),
    "11:30->next close": ("p1130", "c1", 4.5 / 6.5 * 0.75 + 1),
    "11:30->3d close": ("p1130", "c3", 4.5 / 6.5 * 0.75 + 3),
}


def implied(r, tfrac, bump=BUMP):
    """ATM straddle-ish expected |move| under the assumed IV: sigma_daily*bump*sqrt(t)*0.798.
    A single long ATM call/put costs ~0.399*sigma*sqrt(t) = half that."""
    return r["rv20"] * bump * math.sqrt(tfrac) * 0.798


def fmt(st):
    return (f"n={st['n']:4d} mean {st['mean']*100:+6.2f}% med {st['med']*100:+6.2f}% hit {st['hit']:5.1%} "
            f"t {st['t']:+5.2f} t(day-clust) {st['tc']:+5.2f}")


EXCESS = "--excess" in sys.argv


def ret(r, a, b):
    """log return entry a -> exit b; with --excess, minus SPY's log return over the same window (beta-1 market adjustment)."""
    x = math.log(r[b] / r[a])
    if EXCESS:
        if not r["spx"]: return float("nan")
        x -= math.log(r["spx"][b] / r["spx"][a])
    return x


def table(sub, title):
    print(f"\n## {title}  ({len(sub)} events, {len({r['d'] for r in sub})} dates){'  [SPY-excess]' if EXCESS else ''}")
    for h, (a, b, tf) in HORIZ.items():
        x = [r["dir"] * ret(r, a, b) for r in sub]
        print(f"  {h:18s} {fmt(stat(x, [r['d'] for r in sub]))}")


def option_proxy(sub, title):
    """Long-option economics proxy. realized E|move| / implied E|move| (straddle) and directional:
    mean max(dir*ret,0) / (0.399*IV*sqrt t) - 1 = return on a continuation ATM option held to the exit (ignores spread, skew)."""
    print(f"\n## option proxy: {title}  (IV assumed = {BUMP} x 20d RV; sensitivity at 1.25x / 2.0x)")
    for h, (a, b, tf) in HORIZ.items():
        rr = np.array([math.log(r[b] / r[a]) for r in sub]); dr = np.array([r["dir"] for r in sub])
        out = []
        cal = np.mean(np.abs(rr)) / np.mean([implied(r, tf, 1.0) for r in sub])
        for bump in (1.25, BUMP, 2.0):
            imp = np.array([implied(r, tf, bump) for r in sub])
            prem = imp / 2
            cont = np.mean(np.maximum(dr * rr, 0)) / np.mean(prem) - 1
            fade = np.mean(np.maximum(-dr * rr, 0)) / np.mean(prem) - 1
            out.append((np.mean(np.abs(rr)) / np.mean(imp), cont, fade))
        print(f"  {h:18s} realized/RV20 {cal:.2f} | realized/implied |move|: " + " / ".join(f"{o[0]:.2f}" for o in out)
              + f"   continuation-option ROI@{BUMP}x {out[1][1]:+.0%}   fade-option ROI@{BUMP}x {out[1][2]:+.0%}")


def events():
    data = load(); rows = tag_shocks(panel(data))
    with_e = "--with-earnings" in sys.argv
    allshock = [r for r in rows if r["shock"]]
    sh = allshock if with_e else [r for r in allshock if not r["earn"]]
    dates = sorted({r["d"] for r in rows})
    print(f"panel: {len(rows)} stock-days, {len({r['s'] for r in rows})} symbols, {dates[0]}..{dates[-1]}")
    print(f"shocks: {len(allshock)} total, {sum(r['earn'] for r in allshock)} earnings-tagged "
          f"({'kept' if with_e else 'excluded'}), {sum(not r['earn_known'] for r in allshock)} on names without earnings dates")
    nonshock = [r for r in rows if not r["shock"] and not r["earn"]]
    table([r for r in nonshock if r["dir"] > 0], "BASELINE non-shock days, first hour UP (control)")
    table([r for r in nonshock if r["dir"] < 0], "BASELINE non-shock days, first hour DOWN (control)")
    for r in rows: r["z"] = abs(r["fh"]) / max(r["rv20"], 1e-4)
    table(sh, "ALL non-earnings shocks")
    mid = dates[len(dates) // 2]
    table([r for r in sh if r["d"] < mid], f"first half (< {mid})")
    table([r for r in sh if r["d"] >= mid], f"second half (>= {mid})")
    table([r for r in sh if r["dir"] < 0], "DOWN shocks")
    table([r for r in sh if r["dir"] > 0], "UP shocks")
    table([r for r in sh if r["contagion"]], "sector CONTAGION (peers also moved >=2.5% same way by 10:30)")
    table([r for r in sh if not r["contagion"]], "IDIOSYNCRATIC")
    table([r for r in sh if r["spy_fh"] > 0], "SPY up at 10:30")
    table([r for r in sh if r["spy_fh"] <= 0], "SPY down at 10:30")
    table([r for r in sh if r["dir"] < 0 and r["spy_fh"] <= 0], "DOWN shock & SPY down at 10:30")
    table([r for r in sh if r["dir"] < 0 and r["spy_fh"] > 0], "DOWN shock & SPY up at 10:30")
    table([r for r in sh if r["g"] in ("memory", "semis")], "semis + memory/storage")
    table([r for r in sh if abs(r["fh"]) >= 0.08], "BIG shocks (|10:30 move| >= 8%)")
    table([r for r in sh if r["z"] >= 3], "VOL-SCALED shocks (|10:30 move| >= 3 x 20d daily RV)")
    table([r for r in sh if r["z"] >= 3 and r["dir"] < 0], "VOL-SCALED DOWN shocks")
    table([r for r in sh if r["z"] >= 3 and r["dir"] > 0], "VOL-SCALED UP shocks")
    table([r for r in sh if r["z"] >= 3 and r["d"] < mid], "VOL-SCALED, first half")
    table([r for r in sh if r["z"] >= 3 and r["d"] >= mid], "VOL-SCALED, second half")
    table([r for r in sh if r["z"] >= 3 and r["contagion"]], "VOL-SCALED, sector contagion")
    table([r for r in sh if r["z"] >= 3 and not r["contagion"]], "VOL-SCALED, idiosyncratic")
    if not with_e:
        table([r for r in allshock if r["earn"]], "(reference) EARNINGS shocks")
    option_proxy(sh, "all non-earnings shocks")
    option_proxy([r for r in sh if r["d"] >= mid], "second half only")
    option_proxy([r for r in sh if r["dir"] < 0], "DOWN shocks")
    option_proxy([r for r in sh if r["dir"] > 0], "UP shocks")
    option_proxy([r for r in sh if r["z"] >= 3], "VOL-SCALED shocks")
    option_proxy([r for r in sh if r["z"] >= 3 and r["d"] < mid], "VOL-SCALED, first half")
    option_proxy([r for r in sh if r["z"] >= 3 and r["d"] >= mid], "VOL-SCALED, second half")
    option_proxy([r for r in rows if not r["shock"] and not r["earn"]][::10], "(calibration) non-shock days, every 10th")
    # how much of the 3-day move already happened by 10:30?
    pre = np.array([abs(math.log(r["p1030"] / (r["p1030"] / (1 + r["fh"])))) for r in sh])
    post = np.array([r["dir"] * math.log(r["c3"] / r["p1030"]) for r in sh])
    print(f"\nshare of (prev close -> 3d close) move done by 10:30, median over shocks: "
          f"{np.median(pre / np.maximum(pre + post, 1e-9)):.0%}  (>100% = it reverted)")


def contagion():
    """Leader = name with |10:30 move| >= 4% (non-earnings). Laggard = same-group peer whose 10:30 move in the leader's
    direction is < 1/3 of the leader's. Does the laggard drift in the leader's direction afterwards?"""
    data = load(); rows = tag_shocks(panel(data))
    byday = defaultdict(list)
    for r in rows: byday[r["d"]].append(r)
    dates = sorted(byday); mid = dates[len(dates) // 2]
    lag, mov = [], []
    for d, rs in byday.items():
        leaders = [r for r in rs if abs(r["fh"]) >= SHOCK and not r["earn"]]
        seen = set()
        for L in sorted(leaders, key=lambda r: -abs(r["fh"])):
            for p in rs:
                if p["g"] != L["g"] or p["s"] == L["s"] or p["s"] in seen or p["earn"]: continue
                seen.add(p["s"])
                own = L["dir"] * p["fh"]
                rec = dict(d=d, dir=L["dir"], lead=L["s"], s=p["s"], own=own,
                           r0=L["dir"] * ret(p, "p1030", "c0"), r1=L["dir"] * ret(p, "p1030", "c1"),
                           r3=L["dir"] * ret(p, "p1030", "c3"), r0b=L["dir"] * ret(p, "p1130", "c0"),
                           rv20=p["rv20"])
                (lag if own < abs(L["fh"]) / 3 else mov).append(rec)
    def show(sub, title):
        print(f"\n## {title}  ({len(sub)} peer-days, {len({x['d'] for x in sub})} dates){'  [SPY-excess]' if EXCESS else ''}")
        for k, lab in (("r0", "10:30->close"), ("r0b", "11:30->close"), ("r1", "10:30->next close"), ("r3", "10:30->3d close")):
            print(f"  {lab:18s} {fmt(stat([x[k] for x in sub], [x['d'] for x in sub]))}")
    show(lag, "LAGGARD peers (moved < 1/3 of leader by 10:30), signed in leader direction")
    show([x for x in lag if x["d"] < mid], "laggards, first half")
    show([x for x in lag if x["d"] >= mid], "laggards, second half")
    show([x for x in lag if x["dir"] < 0], "laggards, leader DOWN")
    show([x for x in lag if x["dir"] > 0], "laggards, leader UP")
    show([x for x in lag if x["lead"] in GROUPS["memory"] + GROUPS["semis"]], "laggards, semis/memory leaders")
    show(mov, "peers that ALREADY moved (>= 1/3 of leader)")
    ex = [x for x in lag if x["lead"] in GROUPS["memory"]]
    if ex:
        print("\nmemory-group laggard cases (leader -> peer: 10:30->close, ->next close):")
        for x in sorted(ex, key=lambda x: x["d"])[-15:]:
            print(f"  {x['d']} {x['lead']:>4}{'v' if x['dir']<0 else '^'} -> {x['s']:<4} own {x['own']*100:+5.1f}%  "
                  f"close {x['r0']*100:+5.1f}%  next {x['r1']*100:+5.1f}%")


# ---------------------------------------------------------------- latency (today's tape vs headline times)
HEADLINES = [("09:13", "CNBC: Micron drops 5% ..."), ("09:51", "CNBC: Micron, Seagate, Western Digital sink as chip sell-off deepens"),
             ("10:38", "StockStory: Seagate and Western Digital Shares Plummet")]


def latency():
    import yfinance as yf
    day = sys.argv[2] if len(sys.argv) > 2 else None
    print("5m bars incl. pre-market (Yahoo; pre-market prints are thin). move = log(price/prev close).")
    print("'% of move' = move at headline time / move at latest bar (latest-bar time shown; day may be in progress).\n")
    for s in ["MU", "STX", "WDC", "SNDK", "SMH", "SOXX", "SPY"]:
        with contextlib.redirect_stderr(io.StringIO()):
            x = yf.download(s, period="5d", interval="5m", progress=False, prepost=True, auto_adjust=False)
            dd = yf.download(s, period="10d", interval="1d", progress=False, auto_adjust=False)
        x.columns = x.columns.get_level_values(0); dd.columns = dd.columns.get_level_values(0)
        x.index = x.index.tz_convert("America/New_York")
        dday = day or str(x.index[-1].date())
        t = x[[str(i.date()) == dday for i in x.index]]
        pc = float(dd[[str(i.date()) < dday for i in dd.index]]["Close"].iloc[-1])
        bars = [(i.strftime("%H:%M"), float(r.Close), float(r.Low), float(r.High)) for i, r in zip(t.index, t.itertuples())]
        def at(hhmm):  # last completed 5m bar before hhmm (bar stamped hh:mm covers hh:mm..hh:mm+5)
            hm = int(hhmm[:2]) * 60 + int(hhmm[3:])
            c = [b for b in bars if int(b[0][:2]) * 60 + int(b[0][3:]) + 5 <= hm]
            return c[-1][1] if c else pc
        last_t, last = bars[-1][0], bars[-1][1]
        tot = math.log(last / pc)
        ext = min(bars, key=lambda b: b[2]) if tot < 0 else max(bars, key=lambda b: b[3])
        ext_px = ext[2] if tot < 0 else ext[3]
        pts = [("08:00", at("08:00")), ("09:30 (open)", at("09:30")), ("09:35", at("09:35"))] + \
              [(f"{h} hdl", at(h)) for h, _ in HEADLINES]
        print(f"{s:5s} prev close {pc:8.2f}  latest {last_t} {last:8.2f} ({tot*100:+.2f}%)   "
              f"extreme {ext[0]} {ext_px:.2f} ({math.log(ext_px/pc)*100:+.2f}%)")
        print("      " + "  ".join(f"{lab} {math.log(p/pc)*100:+.2f}% [{(math.log(p/pc)/tot if tot else 0):.0%}]" for lab, p in pts))
        first = next((b[0] for b in bars if abs(math.log(b[1] / pc)) >= 0.5 * abs(tot) and math.copysign(1, math.log(b[1]/pc)) == math.copysign(1, tot)), "-")
        print(f"      first 5m close with >=50% of the move so far: {first}")
    print("\nheadlines (ET): " + " | ".join(f"{h} {t}" for h, t in HEADLINES))


if __name__ == "__main__":
    {"fetch": fetch, "events": events, "contagion": contagion, "latency": latency}[sys.argv[1] if len(sys.argv) > 1 else "events"]()
