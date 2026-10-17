#!/usr/bin/env python3
"""Earnings-edge study (2026-10): data fetch.

  python3 research/earnings/fetch.py edgar     # 8-K item 2.02 filings with acceptance time (BMO/AMC) + SIC, from data/research_fund_raw/submissions.zip
  python3 research/earnings/fetch.py prices    # yfinance daily bars 2009+ for the universe (survivors only: yfinance has no delisted bars)
  python3 research/earnings/fetch.py caps      # market cap today (yfinance fast_info) for names not in the small-cap cache
  python3 research/earnings/fetch.py yfdates   # yfinance get_earnings_dates (EPS estimate / actual / surprise, Yahoo's own timing)
  python3 research/earnings/fetch.py all

Universe = Robinhood earnings calendar 2026-10-19..11-14 (cap > $1B, 2,340 names) + small-cap cache (SPSM/MDY/IWM, 2,400 names)
+ S&P 500/400 (Wikipedia, with GICS). Everything lands in data/research_earnings/ (gitignored).
Timing rule: EDGAR acceptance time converted to ET. < 09:30 -> BMO (reaction day = that date); >= 16:00 -> AMC (reaction day =
next session); otherwise 'mid' (intraday release or late 8-K; cross-checked against Yahoo's timing in build.py).
"""
import socket as _sk
_gai = _sk.getaddrinfo
_sk.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, _sk.AF_INET, *a, **k)   # IPv6 times out on this machine
import sys, json, pickle, time, zipfile, warnings, io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "research_earnings"
D.mkdir(parents=True, exist_ok=True)
RAW = ROOT / "data" / "research_fund_raw"
SCRATCH = Path("/private/tmp/claude-501/-Users-trevorthompson-Desktop-stocks/74e8f7e2-d921-494b-8820-b6e65ac5b3fa/scratchpad/earn")


def universe():
    f = D / "universe.json"
    if f.exists():
        return json.load(open(f))
    syms = set(json.load(open(SCRATCH / "universe_syms.json")))
    for n in ("sp500.csv", "sp400.csv"):
        p = SCRATCH / n
        if p.exists():
            syms |= set(pd.read_csv(p)["Symbol"].astype(str).str.replace(".", "-", regex=False))
    syms = sorted(s for s in syms if s and s.replace("-", "").isalnum() and len(s) <= 6)
    json.dump(syms, open(f, "w"))
    return syms


def edgar():
    syms = universe()
    ex = json.load(open(RAW / "company_tickers_exchange.json"))
    rows = pd.DataFrame(ex["data"], columns=ex["fields"])
    rows["t"] = rows.ticker.str.upper().str.replace(".", "-", regex=False)
    m = rows[rows.t.isin(syms)].drop_duplicates("t")
    cik_of = dict(zip(m.t, m.cik))
    print("mapped", len(cik_of), "of", len(syms))
    z = zipfile.ZipFile(RAW / "submissions.zip")
    names = set(z.namelist())
    ev, meta = [], {}
    for i, (t, cik) in enumerate(cik_of.items()):
        fn = f"CIK{cik:010d}.json"
        if fn not in names:
            continue
        d = json.loads(z.read(fn))
        meta[t] = {"cik": cik, "name": d.get("name"), "sic": d.get("sic"), "sicd": d.get("sicDescription"),
                   "exch": d.get("exchanges"), "fye": d.get("fiscalYearEnd")}
        blocks = [d["filings"]["recent"]] + [json.loads(z.read(f["name"])) for f in d["filings"].get("files", []) if f["name"] in names]
        for r in blocks:
            n = len(r.get("form", []))
            for k in range(n):
                if r["form"][k] in ("8-K", "8-K/A") and "2.02" in (r.get("items", [""] * n)[k] or ""):
                    ev.append((t, cik, r["filingDate"][k], r["acceptanceDateTime"][k], r["items"][k], r["form"][k], r["accessionNumber"][k]))
        if i % 500 == 0:
            print("  edgar", i, len(cik_of), len(ev), flush=True)
    E = pd.DataFrame(ev, columns=["t", "cik", "fdate", "acc", "items", "form", "acc_no"])
    E["acc_et"] = pd.to_datetime(E.acc, utc=True).dt.tz_convert("America/New_York")
    E["rdate"] = E.acc_et.dt.strftime("%Y-%m-%d")
    hhmm = E.acc_et.dt.hour * 60 + E.acc_et.dt.minute
    E["timing"] = np.where(hhmm < 9 * 60 + 30, "bmo", np.where(hhmm >= 16 * 60, "amc", "mid"))
    E = E.sort_values(["t", "acc_et"]).reset_index(drop=True)
    E.to_pickle(D / "edgar_events.pkl")
    pd.DataFrame(meta).T.to_pickle(D / "edgar_meta.pkl")
    print("events", len(E), "tickers", E.t.nunique(), E.timing.value_counts().to_dict())


def prices():
    import yfinance as yf
    syms = universe()
    out = {}
    f = D / "prices.pkl"
    if f.exists():
        out = pd.read_pickle(f)
    todo = [s for s in syms if s not in out]
    print("prices todo", len(todo))
    for i in range(0, len(todo), 150):
        b = todo[i:i + 150]
        try:
            df = yf.download(b, start="2009-01-01", auto_adjust=True, group_by="ticker", threads=8, progress=False)
        except Exception as e:
            print("batch err", e); time.sleep(5); continue
        for s in b:
            try:
                x = df[s].dropna(subset=["Close"]) if len(b) > 1 else df.dropna(subset=["Close"])
                if len(x) > 50:
                    out[s] = x[["Open", "High", "Low", "Close", "Volume"]].astype("float32")
            except Exception:
                pass
        print("  prices", i + len(b), len(out), flush=True)
        pd.to_pickle(out, f)
    pd.to_pickle(out, f)
    print("prices", len(out))


def caps():
    import yfinance as yf
    syms = universe()
    f = D / "caps.pkl"
    out = pd.read_pickle(f) if f.exists() else {}
    sc = pd.read_csv(SCRATCH / "smallcap_caps.csv")
    for r in sc.itertuples():
        if r.symbol not in out and r.mcap == r.mcap:
            out[r.symbol] = {"mcap": float(r.mcap), "shares": None, "src": "smallcap_cache"}
    todo = [s for s in syms if s not in out]
    print("caps todo", len(todo))

    def one(s):
        for _ in range(2):
            try:
                fi = yf.Ticker(s).fast_info
                return s, {"mcap": fi.get("marketCap"), "shares": fi.get("shares"), "src": "fast_info"}
            except Exception:
                time.sleep(1)
        return s, None
    with ThreadPoolExecutor(6) as ex:
        for k, (s, v) in enumerate(ex.map(one, todo)):
            if v:
                out[s] = v
            if k % 200 == 0:
                pd.to_pickle(out, f); print("  caps", k, len(out), flush=True)
    pd.to_pickle(out, f)
    print("caps", len(out))


def yfdates():
    import yfinance as yf
    syms = universe()
    f = D / "yfdates.pkl"
    out = pd.read_pickle(f) if f.exists() else {}
    todo = [s for s in syms if s not in out]
    print("yfdates todo", len(todo))

    def one(s):
        for _ in range(2):
            try:
                ed = yf.Ticker(s).get_earnings_dates(limit=100)
                return s, ed if ed is not None else pd.DataFrame()
            except Exception:
                time.sleep(1.5)
        return s, None
    with ThreadPoolExecutor(4) as ex:
        for k, (s, v) in enumerate(ex.map(one, todo)):
            if v is not None:
                out[s] = v
            if k % 100 == 0:
                pd.to_pickle(out, f); print("  yfdates", k, len(out), flush=True)
    pd.to_pickle(out, f)
    print("yfdates", len(out))


if __name__ == "__main__":
    for step in sys.argv[1:]:
        if step == "all":
            edgar(); prices(); caps(); yfdates()
        else:
            globals()[step]()
