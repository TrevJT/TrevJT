#!/usr/bin/env python3
"""Prediction-market feed for options-100 (Polymarket + Kalshi, public APIs, no credentials).
Stores into data/market.db:
  pm_markets(source, market_id, topic, question, event, end_date, volume, token)   one row per market
  pm_prices(source, market_id, ts, prob)                                             odds time series (ts = YYYY-MM-DD or YYYY-MM-DD HH:MM ET)

  predictions.py update      discover markets for every TOPIC, backfill daily odds history, add a live snapshot
  predictions.py now         print the current odds board (what the bot reads pre-open)
  predictions.py movers      biggest 1-day and 5-day odds moves among tracked markets
"""
import os, sys, json, sqlite3, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "market.db")
ET = timezone(timedelta(hours=-4))
UA = {"User-Agent": "options-100-research/0.1"}

# topic -> Polymarket search queries
TOPICS = {
    "iran": ["iran", "US Iran ceasefire", "Iran nuclear deal", "Strait of Hormuz", "Israel Iran"],
    "midterms": ["House 2026", "Senate 2026", "midterms", "trifecta"],
    "trump": ["Trump", "Trump tariffs", "Trump approval", "Trump impeach"],
    "fed": ["Fed rate", "Fed decision", "Warsh"],
    "macro": ["recession", "inflation", "government shutdown", "S&P 500"],
    "china": ["China Taiwan", "US China trade", "Xi Trump"],
    "ukraine": ["Ukraine ceasefire", "Russia Ukraine"],
    "oil": ["oil price", "crude oil", "OPEC"],
}
MIN_VOLUME = 150_000          # ignore thin markets
KALSHI_SERIES = {"fed": ["KXFEDDECISION", "KXRATECUTCOUNT", "KXFED"], "macro": ["KXCPIYOY", "KXPAYROLLS", "KXRECSSNBER", "KXGDP", "KXU3"],
                 "markets": ["KXSPXFOMC"], "oil": ["KXOILW"]}


def get(url, params=None, tries=3):
    if params: url += "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS pm_markets(source TEXT, market_id TEXT, topic TEXT, question TEXT, event TEXT,
                 end_date TEXT, volume REAL, token TEXT, PRIMARY KEY(source, market_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS pm_prices(source TEXT, market_id TEXT, ts TEXT, prob REAL,
                 PRIMARY KEY(source, market_id, ts))""")
    return c


def poly_discover(c):
    now = datetime.now(timezone.utc).isoformat()
    found = {}
    for topic, qs in TOPICS.items():
        for q in qs:
            d = get("https://gamma-api.polymarket.com/public-search", {"q": q, "limit_per_type": 20, "events_status": "active"}) or {}
            for e in d.get("events") or []:
                if e.get("closed"): continue
                for m in e.get("markets") or []:
                    if m.get("closed") or not m.get("active", True): continue
                    if float(m.get("volume") or 0) < MIN_VOLUME: continue
                    if (m.get("endDate") or "9999") < now: continue
                    try:
                        tok = json.loads(m.get("clobTokenIds") or "[]")[0]
                        prob = float(json.loads(m.get("outcomePrices") or "[]")[0])
                    except Exception:
                        continue
                    found[m["id"]] = (topic, m.get("question"), e.get("title"), m.get("endDate"), float(m.get("volume") or 0), tok, prob)
    for mid, (topic, qn, ev, end, vol, tok, prob) in found.items():
        c.execute("INSERT OR REPLACE INTO pm_markets VALUES (?,?,?,?,?,?,?,?)", ("poly", mid, topic, qn, ev, end, vol, tok))
        c.execute("INSERT OR REPLACE INTO pm_prices VALUES (?,?,?,?)", ("poly", mid, datetime.now(ET).strftime("%Y-%m-%d %H:%M"), prob))
    return found


def poly_history(c, found):
    n = 0
    for mid, (*_, tok, _p) in found.items():
        h = get("https://clob.polymarket.com/prices-history", {"market": tok, "interval": "max", "fidelity": 1440}) or {}
        rows = [("poly", mid, datetime.fromtimestamp(p["t"], ET).strftime("%Y-%m-%d"), float(p["p"])) for p in h.get("history", [])]
        c.executemany("INSERT OR REPLACE INTO pm_prices VALUES (?,?,?,?)", rows); n += len(rows)
    return n


def kalshi(c):
    n = 0; ts = datetime.now(ET).strftime("%Y-%m-%d %H:%M")
    for topic, series in KALSHI_SERIES.items():
        for s in series:
            d = get("https://api.elections.kalshi.com/trade-api/v2/markets", {"series_ticker": s, "status": "open", "limit": 200}) or {}
            for m in d.get("markets") or []:
                vol = float(m.get("volume") or m.get("volume_fp") or 0)
                p = m.get("last_price_dollars") or m.get("yes_bid_dollars")
                if p is None: continue
                c.execute("INSERT OR REPLACE INTO pm_markets VALUES (?,?,?,?,?,?,?,?)",
                          ("kalshi", m["ticker"], topic, m.get("title"), m.get("event_ticker"), m.get("close_time"), vol, s))
                c.execute("INSERT OR REPLACE INTO pm_prices VALUES (?,?,?,?)", ("kalshi", m["ticker"], ts, float(p))); n += 1
    return n


def snap():
    """Fast intraday snapshot of every tracked market's current odds (Polymarket by id, Kalshi by series).
    Run every 15 min in market hours; builds an intraday odds history for lead-lag research."""
    c = conn(); ts = datetime.now(ET).strftime("%Y-%m-%d %H:%M"); n = 0
    ids = [r[0] for r in c.execute("SELECT market_id FROM pm_markets WHERE source='poly' AND (end_date IS NULL OR end_date > ?)",
                                    (datetime.now(timezone.utc).isoformat(),))]
    for i in range(0, len(ids), 40):
        q = "&".join("id=" + x for x in ids[i:i + 40])
        for m in get("https://gamma-api.polymarket.com/markets?" + q + "&limit=40") or []:
            try:
                p = float(json.loads(m.get("outcomePrices") or "[]")[0])
            except Exception:
                continue
            c.execute("INSERT OR REPLACE INTO pm_prices VALUES (?,?,?,?)", ("poly", str(m["id"]), ts, p)); n += 1
    n += kalshi(c); c.commit(); print(f"{ts} snapped {n} odds")


def update():
    c = conn()
    found = poly_discover(c)
    hist = poly_history(c, found)
    k = kalshi(c)
    c.commit()
    print(f"polymarket: {len(found)} markets, {hist} daily history points | kalshi: {k} markets")


def latest(c):
    return c.execute("""SELECT m.source, m.market_id, m.topic, m.question, m.volume, p.ts, p.prob FROM pm_markets m
        JOIN pm_prices p ON p.source=m.source AND p.market_id=m.market_id
        WHERE p.ts=(SELECT MAX(ts) FROM pm_prices q WHERE q.source=m.source AND q.market_id=m.market_id)""").fetchall()


def prob_at(c, src, mid, day):
    r = c.execute("SELECT prob FROM pm_prices WHERE source=? AND market_id=? AND ts<=? ORDER BY ts DESC LIMIT 1", (src, mid, day)).fetchone()
    return r[0] if r else None


def now():
    c = conn(); rows = latest(c); by = {}
    for r in rows: by.setdefault(r[2], []).append(r)
    d1 = (datetime.now(ET) - timedelta(days=1)).strftime("%Y-%m-%d"); d5 = (datetime.now(ET) - timedelta(days=5)).strftime("%Y-%m-%d")
    for topic in list(TOPICS) + ["markets"]:
        rs = sorted(by.get(topic, []), key=lambda r: -r[4])[:8]
        if not rs: continue
        print(f"## {topic}")
        for src, mid, _, q, vol, ts, p in rs:
            a, b = prob_at(c, src, mid, d1), prob_at(c, src, mid, d5)
            ch = f"{(p-a)*100:+.0f}pt 1d" if a is not None else ""; ch5 = f"{(p-b)*100:+.0f}pt 5d" if b is not None else ""
            print(f"  {p*100:5.1f}%  {q[:78]:<78} {ch:>9} {ch5:>9}  ${vol/1e6:.1f}M {src}")


def movers():
    c = conn(); out = []
    d1 = (datetime.now(ET) - timedelta(days=1)).strftime("%Y-%m-%d"); d5 = (datetime.now(ET) - timedelta(days=5)).strftime("%Y-%m-%d")
    for src, mid, topic, q, vol, ts, p in latest(c):
        a, b = prob_at(c, src, mid, d1), prob_at(c, src, mid, d5)
        if b is not None and 0.01 < p < 0.99: out.append((abs(p - b), p - b, (p - a) if a is not None else 0, topic, q, p))
    for _, ch5, ch1, topic, q, p in sorted(out, reverse=True)[:15]:
        print(f"  {ch5*100:+5.0f}pt 5d  {ch1*100:+4.0f}pt 1d  now {p*100:5.1f}%  [{topic}] {q[:80]}")


if __name__ == "__main__":
    {"update": update, "snap": snap, "now": now, "movers": movers}.get(sys.argv[1] if len(sys.argv) > 1 else "now", now)()
