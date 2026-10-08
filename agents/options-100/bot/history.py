#!/usr/bin/env python3
"""Market-history store for options-100. SQLite at agents/options-100/data/market.db.

  history.py update            fetch/refresh everything (idempotent; run pre-open and after close)
  history.py status            row counts and date ranges per symbol/interval

Source: Yahoo Finance via yfinance (public, no credentials). Depth available:
  1d  : full history (SPY 1993-, QQQ 1999-, ^VIX 1990-, ...)
  1h  : last 730 days      5m : last 60 days      1m : last ~7 days
Intraday windows roll off, so running `update` every trading day archives them permanently.
Bars are stored with ET timestamps (YYYY-MM-DD HH:MM) and never deleted.
"""
import os, sys, json, sqlite3, warnings, contextlib, io
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "market.db")

# Underlyings we trade or that explain them (index, vol, rates, dollar, oil, sectors driving SPY/QQQ)
DAILY = ["SPY", "QQQ", "IWM", "DIA", "^GSPC", "^NDX", "^RUT", "^VIX", "^VIX9D", "^VIX3M", "^VVIX", "^SKEW",
         "^TNX", "^IRX", "TLT", "DX-Y.NYB", "CL=F", "GC=F", "BTC-USD",
         "XLK", "XLF", "XLE", "XLY", "XLV", "XLI", "XLC", "SMH",
         "XLRE", "IYT", "KRE", "XLU", "XHB", "ITB", "TIP", "RINF", "UGA", "USO", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "AVGO", "TSLA"]
INTRADAY = {"5m": ("60d", ["SPY", "QQQ", "IWM", "^VIX"]),
            "1m": ("7d", ["SPY", "QQQ"]),
            "1h": ("730d", ["SPY", "QQQ", "IWM", "^VIX"])}


def conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS bars(symbol TEXT, interval TEXT, ts TEXT, open REAL, high REAL,
                 low REAL, close REAL, adj_close REAL, volume REAL, PRIMARY KEY(symbol, interval, ts))""")
    c.execute("CREATE INDEX IF NOT EXISTS bars_si ON bars(symbol, interval, ts)")
    c.execute("""CREATE TABLE IF NOT EXISTS option_snaps(ts TEXT, symbol TEXT, expiry TEXT, type TEXT, strike REAL,
                 bid REAL, ask REAL, mark REAL, delta REAL, gamma REAL, theta REAL, vega REAL, iv REAL, oi INTEGER,
                 volume INTEGER, underlying REAL, PRIMARY KEY(ts, symbol, expiry, type, strike))""")
    return c


def _fetch(sym, period, interval):
    import yfinance as yf
    with contextlib.redirect_stderr(io.StringIO()):
        d = yf.download(sym, period=period, interval=interval, progress=False, auto_adjust=False, prepost=False)
    if d is None or d.empty:
        return []
    if hasattr(d.columns, "levels"):
        d.columns = d.columns.get_level_values(0)
    idx = d.index
    if interval in ("1m", "5m", "1h"):
        idx = idx.tz_convert("America/New_York") if idx.tz is not None else idx.tz_localize("UTC").tz_convert("America/New_York")
        fmt = "%Y-%m-%d %H:%M"
    else:
        fmt = "%Y-%m-%d"
    rows = []
    for t, r in zip(idx, d.itertuples(index=False)):
        rr = r._asdict()
        o, h, l, c = rr.get("Open"), rr.get("High"), rr.get("Low"), rr.get("Close")
        if c is None or c != c:
            continue
        rows.append((sym, interval, t.strftime(fmt), float(o), float(h), float(l), float(c),
                     float(rr.get("Adj_Close", rr.get("Adj Close", c)) or c), float(rr.get("Volume") or 0)))
    return rows


def update():
    c = conn(); total = 0
    jobs = [(s, "max", "1d") for s in DAILY] + [(s, p, iv) for iv, (p, syms) in INTRADAY.items() for s in syms]
    for sym, period, iv in jobs:
        try:
            rows = _fetch(sym, period, iv)
        except Exception as e:
            print(f"  ! {sym} {iv}: {e}"); continue
        c.executemany("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?,?)", rows)
        total += len(rows)
    c.commit()
    print(f"upserted {total} bars -> {DB}")


def status():
    c = conn()
    for r in c.execute("""SELECT symbol, interval, COUNT(*), MIN(ts), MAX(ts) FROM bars
                          GROUP BY symbol, interval ORDER BY interval, symbol"""):
        print(f"{r[1]:>3} {r[0]:<9} {r[2]:>6}  {r[3]} -> {r[4]}")
    n = c.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM option_snaps").fetchone()
    print(f"option_snaps {n[0]} rows {n[1]} -> {n[2]}")
    print(f"db size {os.path.getsize(DB)/1e6:.1f} MB")


def snap():
    """stdin: JSON lines {ts,symbol,expiry,type,strike,bid,ask,mark,delta,gamma,theta,vega,iv,oi,volume,underlying}
    Archive every option quote the bot sees, so our own 0DTE option history accumulates."""
    c = conn(); n = 0
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        d = json.loads(line)
        c.execute("INSERT OR REPLACE INTO option_snaps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  tuple(d.get(k) for k in ("ts","symbol","expiry","type","strike","bid","ask","mark","delta","gamma",
                                           "theta","vega","iv","oi","volume","underlying"))); n += 1
    c.commit(); print(f"archived {n} option quotes")


if __name__ == "__main__":
    {"update": update, "status": status, "snap": snap}.get(sys.argv[1] if len(sys.argv) > 1 else "status", status)()
