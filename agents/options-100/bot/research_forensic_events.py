#!/usr/bin/env python3
"""Research: forensic red flags ("mini Hindenburg") + activist short reports + binary/event-dependent stocks.
Owner ideas: (1) find short-seller-style red flags before the market and BUY PUTS; (2) trade stocks whose value hinges on a
binary event (FDA, legislation, court, merger) with long options. Research only: no orders, statistical flags only.

  python3 agents/options-100/bot/research_forensic_events.py filings   # submissions.zip -> 8-K items 4.01/4.02/5.02, NT 10-K/Q, 10-K dates
  python3 agents/options-100/bot/research_forensic_events.py facts     # companyfacts.zip -> annual Beneish / DSO / soft-asset / RPT inputs
  python3 agents/options-100/bot/research_forensic_events.py gc        # EDGAR full-text search: going-concern 10-Ks (2012+)
  python3 agents/options-100/bot/research_forensic_events.py daily     # daily bars (HF pwb incl. delisted + yfinance) for event tickers
  python3 agents/options-100/bot/research_forensic_events.py partA     # activist short-report event study + day-1 put economics
  python3 agents/options-100/bot/research_forensic_events.py partB     # flag panel, IS 2012-18 / OOS 2019+, BH, size, put economics
  python3 agents/options-100/bot/research_forensic_events.py screen    # today's top flagged names + option liquidity
  python3 agents/options-100/bot/research_forensic_events.py partC     # FDA / legislation / merger-arb / index event studies + screens

Inputs (untrusted, parsed only, never executed):
  data/research_fund_raw/ (shared with research_fundamental.py: companyfacts.zip, submissions.zip, form345, pwb parquet)
  data/research_forensic_raw/*.csv (hand/agent-compiled event lists: short reports, FDA, legislation, mergers)
Caches: data/research_forensic_*.pkl / .json (data/ is gitignored).
"""
import socket as _sk
_gai = _sk.getaddrinfo
_sk.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, _sk.AF_INET, *a, **k)   # IPv6 times out on this machine
import sys, json, math, pickle, time, re, zipfile, warnings, urllib.request, urllib.parse
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FRAW = DATA / "research_fund_raw"
RAW = DATA / "research_forensic_raw"
UA = {"User-Agent": "options-100 research trevorchico@gmail.com"}
TODAY = pd.Timestamp("2026-10-14")
OUT = DATA / "research_forensic_results.json"


def P(name):
    return DATA / f"research_forensic_{name}"


def save(obj, name):
    tmp = P(name + ".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(obj, f, protocol=4)
    tmp.replace(P(name))


def load(name):
    with open(P(name), "rb") as f:
        return pickle.load(f)


def fund(name):
    with open(DATA / f"research_fund_{name}", "rb") as f:
        return pickle.load(f)


_last_req = [0.0]


def sec_get(url, tries=4):
    """SEC request: UA header, <= ~6 req/s, retries. Returns parsed JSON (data only)."""
    for k in range(tries):
        dt_ = time.time() - _last_req[0]
        if dt_ < 0.17:
            time.sleep(0.17 - dt_)
        _last_req[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.loads(r.read())
        except Exception as e:
            if k == tries - 1:
                print("  fail", url[:120], e, flush=True)
                return None
            time.sleep(2 + 3 * k)


def results_update(key, val):
    res = json.load(open(OUT)) if OUT.exists() else {}
    res[key] = val
    json.dump(res, open(OUT, "w"), indent=1, default=str)


# =====================================================================================  1. FILINGS (8-K items, NT forms)
EV_FORMS = {"10-K", "10-K/A", "10-Q", "NT 10-K", "NT 10-Q", "NT 10-K/A", "NT 10-Q/A", "8-K", "8-K/A", "10-KT",
            "25-NSE", "25", "15-12B", "15-12G", "15-15D", "S-1", "S-3", "424B5", "SC 13D", "SC 13G"}


_ZC = {}


def _zip(path):
    """one open ZipFile per worker process (the submissions central directory has ~1M entries)."""
    if path not in _ZC:
        _ZC[path] = zipfile.ZipFile(path)
    return _ZC[path]


def _filings_one(args):
    zpath, cik = args
    try:
        z = _zip(zpath)
        if True:
            d = json.loads(z.read(f"CIK{cik:010d}.json"))
            blocks = [d.get("filings", {}).get("recent", {})]
            for x in d.get("filings", {}).get("files", []):
                try:
                    blocks.append(json.loads(z.read(x["name"])))
                except Exception:
                    pass
    except Exception:
        return None
    ev = defaultdict(list)
    for r in blocks:
        n = len(r.get("form", []))
        items = r.get("items", [""] * n)
        for i in range(n):
            f = r["form"][i]
            fd = r["filingDate"][i]
            if fd < "2009-01-01":
                continue
            if f in ("8-K", "8-K/A"):
                it = items[i] or ""
                for code in ("4.01", "4.02", "5.02", "1.03", "2.06", "3.01"):
                    if code in it and f == "8-K":
                        ev[code].append(fd)
            elif f in ("NT 10-K", "NT 10-Q"):
                ev[f].append(fd)
            elif f in ("10-K", "10-KT"):
                ev["10-K"].append(fd)
            elif f == "10-Q":
                ev["10-Q"].append(fd)
            elif f in ("10-K/A",):
                ev["10-K/A"].append(fd)
            elif f in ("25-NSE", "25", "15-12B", "15-12G", "15-15D"):
                ev["delist"].append(fd)
    return {"cik": cik, "name": d.get("name"), "sic": d.get("sic"), "sicd": d.get("sicDescription"),
            "tickers": d.get("tickers", []), "exch": d.get("exchanges", []), "etype": d.get("entityType"),
            "ev": {k: sorted(set(v)) for k, v in ev.items()}}


def filings():
    from multiprocessing import Pool
    t0 = time.time()
    ciks = sorted(int(n[3:13]) for n in zipfile.ZipFile(FRAW / "companyfacts.zip").namelist() if re.fullmatch(r"CIK\d{10}\.json", n))
    have = set(zipfile.ZipFile(FRAW / "submissions.zip").namelist())
    ciks = [c for c in ciks if f"CIK{c:010d}.json" in have]
    print("ciks", len(ciks), flush=True)
    out = {}
    with Pool(3) as pool:
        for i, r in enumerate(pool.imap_unordered(_filings_one, [(str(FRAW / "submissions.zip"), c) for c in ciks], chunksize=64)):
            if r and r["ev"].get("10-K"):
                out[r["cik"]] = r
            if i % 5000 == 0:
                print(f"  {i}/{len(ciks)} kept {len(out)} {time.time() - t0:.0f}s", flush=True)
    save(out, "filings.pkl")
    c = defaultdict(int)
    for r in out.values():
        for k, v in r["ev"].items():
            c[k] += len(v)
    print("kept", len(out), dict(c), f"{time.time() - t0:.0f}s")


# =====================================================================================  2. FACTS (annual, point-in-time)
A_FLOW = {
    "rev": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet", "SalesRevenueServicesNet"],
    "cogs": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices"],
    "sga": ["SellingGeneralAndAdministrativeExpense", "GeneralAndAdministrativeExpense"],
    "dep": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "Depreciation",
            "DepreciationAmortizationAndAccretionNet"],
    "ni": ["NetIncomeLoss", "ProfitLoss"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "rpt_rev": ["RevenueFromRelatedParties"],
    "rpt_tx": ["RelatedPartyTransactionAmountsOfTransaction", "RelatedPartyTransactionExpensesFromTransactionsWithRelatedParty",
               "RelatedPartyTransactionPurchasesFromRelatedParty"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "gw_imp": ["GoodwillImpairmentLoss", "ImpairmentOfIntangibleAssetsExcludingGoodwill"],
}
A_INST = {
    "recv": ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "AccountsNotesAndLoansReceivableNetCurrent"],
    "ca": ["AssetsCurrent"], "assets": ["Assets"], "cl": ["LiabilitiesCurrent"],
    "ppe": ["PropertyPlantAndEquipmentNet", "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization"],
    "sec": ["MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "ShortTermInvestments",
            "AvailableForSaleSecuritiesCurrent"],
    "ltd": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebt"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "inv": ["InventoryNet"],
    "gw": ["Goodwill"],
    "intang": ["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"],
    "rpt_due": ["DueFromRelatedPartiesCurrent", "DueFromRelatedParties", "AccountsReceivableRelatedPartiesCurrent",
                "DueFromRelatedPartiesCurrentAndNoncurrent", "NotesAndLoansReceivableRelatedPartiesCurrent"],
}
MAXG = {"rev", "cogs"}


def _annual_one(args):
    zpath, name = args
    try:
        d = json.loads(_zip(zpath).read(name))
    except Exception:
        return None
    facts = d.get("facts", {})
    g = facts.get("us-gaap")
    if not g:
        return None
    cik = int(d.get("cik") or int(name[3:13]))
    dei = facts.get("dei", {})
    cover = defaultdict(float)
    seen = set()
    for f in dei.get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", []):
        k = (f["accn"], f.get("filed"), f.get("end"), f["val"])
        if k in seen:
            continue
        seen.add(k)
        cover[(f.get("filed"), f.get("end"))] += float(f["val"])
    cover = sorted((fd, e, v) for (fd, e), v in cover.items() if fd and v > 0)
    if not cover or cover[-1][0] < "2011-06-01":
        return None

    def series(concepts, flow, use_max):
        res = {}
        for c in concepts:
            u = (g.get(c) or {}).get("units", {}).get("USD") or []
            per = {}
            for f in u:
                if f.get("form") not in ("10-K", "10-KT", "10-K/A"):
                    continue
                e = f["end"]
                if flow:
                    s = f.get("start")
                    if not s:
                        continue
                    dur = (pd.Timestamp(e) - pd.Timestamp(s)).days
                    if not 340 <= dur <= 390:
                        continue
                fd = f["filed"]
                if e not in per or fd < per[e][1]:        # earliest filed = as originally reported (no restatement look-ahead)
                    per[e] = (float(f["val"]), fd)
            for e, (v, fd) in per.items():
                if e not in res or (use_max and v > res[e][0]):
                    res[e] = (v, fd) if e not in res else (v, res[e][1])
        return res

    cols = {}
    for k, cs in A_FLOW.items():
        cols[k] = series(cs, True, k in MAXG)
    for k, cs in A_INST.items():
        cols[k] = series(cs, False, False)
    ends = sorted(set(cols["ni"]) | set(cols["rev"]) | set(cols["assets"]))
    if not ends:
        return None
    grid = []
    for e in ends:
        E = pd.Timestamp(e)
        if grid and (E - grid[-1]).days < 300:
            continue
        grid.append(E)
    rows = []
    for E in grid:
        if E < pd.Timestamp("2008-06-01"):
            continue
        r = {"fy": E}
        fmin = None
        for k, m in cols.items():
            hit = None
            for dd in (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7):
                hit = m.get((E + pd.Timedelta(days=dd)).strftime("%Y-%m-%d"))
                if hit is not None:
                    break
            if hit is not None:
                r[k] = hit[0]
                if k in ("ni", "rev", "assets"):
                    fmin = hit[1] if fmin is None else min(fmin, hit[1])
        if fmin is None:
            continue
        r["filed"] = pd.Timestamp(fmin)
        rows.append(r)
    if len(rows) < 2:
        return None
    return {"cik": cik, "name": d.get("entityName"), "a": pd.DataFrame(rows), "cover": cover}


def facts():
    from multiprocessing import Pool
    t0 = time.time()
    zf = FRAW / "companyfacts.zip"
    names = [n for n in zipfile.ZipFile(zf).namelist() if n.endswith(".json")]
    print("companyfacts", len(names), flush=True)
    out = {}
    with Pool(3) as pool:
        for i, r in enumerate(pool.imap_unordered(_annual_one, [(str(zf), n) for n in names], chunksize=32)):
            if r:
                out[r["cik"]] = r
            if i % 2000 == 0:
                print(f"  {i}/{len(names)} kept {len(out)} {time.time() - t0:.0f}s", flush=True)
    save(out, "facts.pkl")
    print("kept", len(out), f"{time.time() - t0:.0f}s")


# =====================================================================================  3. GOING CONCERN (EDGAR FTS)
GC_PHRASES = ['"substantial doubt about the company\'s ability to continue as a going concern"',
              '"raise substantial doubt about its ability to continue as a going concern"']


def gc():
    """10-K documents (main doc or auditor consent/exhibits) containing going-concern phrases, by month 2011-2026.
    Stores (cik, file_date, file_type) hits. Boilerplate risk factors also match: flagged as 'gc_any' with file types."""
    cache = load("gc.pkl") if P("gc.pkl").exists() else {}
    months = pd.period_range("2011-01", "2026-10", freq="M")
    for ph in GC_PHRASES:
        for m in months:
            key = (ph, str(m))
            if key in cache:
                continue
            s, e = m.start_time.strftime("%Y-%m-%d"), m.end_time.strftime("%Y-%m-%d")
            hits, frm, total = [], 0, None
            while True:
                q = urllib.parse.quote(ph)
                url = (f"https://efts.sec.gov/LATEST/search-index?q={q}&forms=10-K&dateRange=custom"
                       f"&startdt={s}&enddt={e}&from={frm}")
                j = sec_get(url)
                if j is None:
                    break
                hh = j.get("hits", {})
                total = hh.get("total", {}).get("value", 0)
                for x in hh.get("hits", []):
                    src = x.get("_source", {})
                    for c in src.get("ciks", []):
                        hits.append((int(c), src.get("file_date"), src.get("file_type"), src.get("adsh")))
                frm += len(hh.get("hits", []))
                if not hh.get("hits") or frm >= total or frm >= 9900:
                    break
            if j is None:
                continue
            cache[key] = hits
            print(ph[:30], m, total, len(hits), flush=True)
            if m.month == 12:
                save(cache, "gc.pkl")
    save(cache, "gc.pkl")
    allh = [h for v in cache.values() for h in v]
    print("gc hits", len(allh), "ciks", len({h[0] for h in allh}))


# =====================================================================================  4. DAILY BARS (event studies)
SECTOR_ETF = ["SPY", "IWM", "XLK", "XLV", "XLF", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "XBI", "IBB",
              "KRE", "SMH", "ARKK"]


def sic_etf(sic):
    try:
        s = int(sic)
    except Exception:
        return "IWM"
    if 2830 <= s <= 2836 or 8731 <= s <= 8734:
        return "XBI"
    if 3840 <= s <= 3851 or 8000 <= s <= 8099 or 5120 <= s <= 5122:
        return "XLV"
    if 1000 <= s <= 1499 or 2900 <= s <= 2999 or 4610 <= s <= 4619:
        return "XLE"
    if 3570 <= s <= 3579 or 3600 <= s <= 3699 or 7370 <= s <= 7379 or 3810 <= s <= 3829:
        return "XLK"
    if 6000 <= s <= 6499 or 6700 <= s <= 6799:
        return "XLF"
    if 6500 <= s <= 6599 or s == 6798:
        return "XLRE"
    if 4800 <= s <= 4899 or 7800 <= s <= 7899 or 2700 <= s <= 2799:
        return "XLC"
    if 4900 <= s <= 4999:
        return "XLU"
    if 2000 <= s <= 2199 or 5400 <= s <= 5499 or 2840 <= s <= 2844:
        return "XLP"
    if 5000 <= s <= 5999 or 7000 <= s <= 7299 or 3711 <= s <= 3716 or 2300 <= s <= 2399:
        return "XLY"
    if 2800 <= s <= 2829 or 2850 <= s <= 2899 or 3300 <= s <= 3399 or 2600 <= s <= 2699:
        return "XLB"
    if 1500 <= s <= 1799 or 3400 <= s <= 3569 or 3700 <= s <= 3799 or 4000 <= s <= 4799 or 8700 <= s <= 8799:
        return "XLI"
    return "IWM"


def load_daily(symbols, name="daily.pkl"):
    """{symbol: DataFrame(open, close, adj, vol)} from HF pwb parquet (includes delisted) + yfinance fallback/extension."""
    import pyarrow.parquet as pq
    have = load(name) if P(name).exists() else {}
    need = sorted(set(s for s in symbols if s and s not in have))
    if need:
        parts = []
        files = sorted((FRAW / "pwb").glob("train-*.parquet"))
        t0 = time.time()
        for f in files:
            t = pq.read_table(f, columns=["symbol", "date", "open", "close", "adj_close", "volume"],
                              filters=[("symbol", "in", need)]).to_pandas()
            if len(t):
                parts.append(t)
        print(f"  pwb read {len(files)} files {time.time() - t0:.0f}s", flush=True)
        df = pd.concat(parts) if parts else pd.DataFrame(columns=["symbol"])
        for s, g in df.groupby("symbol"):
            g = g.assign(date=pd.to_datetime(g.date)).set_index("date").sort_index()
            have[s] = pd.DataFrame({"open": g.open, "close": g.close, "adj": g.adj_close, "vol": g.volume}).astype("float64")
        miss = [s for s in need if s not in have]
        if miss:
            import yfinance as yf
            for i in range(0, len(miss), 50):
                b = miss[i:i + 50]
                try:
                    x = yf.download(b, start="2009-01-01", end="2026-10-15", auto_adjust=False, progress=False,
                                    group_by="ticker", threads=True, timeout=60)
                except Exception as e:
                    print("yf fail", e)
                    continue
                for s in b:
                    try:
                        y = x[s] if isinstance(x.columns, pd.MultiIndex) else x
                        y = y.dropna(subset=["Close"])
                        if len(y):
                            have[s] = pd.DataFrame({"open": y.Open, "close": y.Close, "adj": y["Adj Close"], "vol": y.Volume})
                    except Exception:
                        pass
        for s in need:
            have.setdefault(s, None)
        save(have, name)
    return {s: have.get(s) for s in symbols}


# =====================================================================================  5. OPTION PRICING
from math import erf, sqrt, log, exp


def _N(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


def bs(S, K, T, sig, put=True, r=0.03):
    if T <= 0 or sig <= 0:
        return max(K - S, 0) if put else max(S - K, 0)
    d1 = (log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * sqrt(T))
    d2 = d1 - sig * sqrt(T)
    if put:
        return K * exp(-r * T) * _N(-d2) - S * _N(-d1)
    return S * _N(d1) - K * exp(-r * T) * _N(d2)


def opt_trade(S0, S1, sig0, sig1, dte, held, mny=1.0, put=True, spread=0.10, skew=0.0):
    """Buy at ask (mid*(1+s/2)), sell at bid (mid*(1-s/2)) after `held` calendar days, or settle at expiry.
    mny = K/S0. skew: IV add per unit of log-moneyness for OTM puts (sticky strike approx). Returns net return on premium."""
    K = S0 * mny
    T0 = dte / 365.0
    iv0 = sig0 * (1 + skew * max(0.0, -log(mny) if put else log(mny)))
    p0 = bs(S0, K, T0, iv0, put) * (1 + spread / 2)
    if p0 <= 1e-9:
        return np.nan
    T1 = max(0.0, (dte - held) / 365.0)
    if T1 <= 0:
        p1 = max(K - S1, 0) if put else max(S1 - K, 0)
    else:
        mny1 = K / S1
        iv1 = sig1 * (1 + skew * max(0.0, -log(mny1) if put else log(mny1)))
        p1 = bs(S1, K, T1, iv1, put) * (1 - spread / 2)
    return p1 / p0 - 1


def tstat(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return np.nan
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


def pval(t):
    from scipy.stats import norm
    return 2 * (1 - norm.cdf(abs(t))) if np.isfinite(t) else 1.0


def bh(ps, q=0.10):
    ps = np.asarray(ps, float)
    n = len(ps)
    order = np.argsort(ps)
    passed = np.zeros(n, bool)
    thr = q * (np.arange(1, n + 1)) / n
    ok = ps[order] <= thr
    if ok.any():
        k = np.max(np.where(ok)[0])
        passed[order[:k + 1]] = True
    return passed


def bankroll(rets, cost, trades_per_yr, starts=(170, 1000, 5000), frac=0.20, n_paths=20000, seed=7):
    """1-year bootstrap: buy floor(frac*eq/cost) contracts (or 1 if cost <= 60% equity), i.i.d. draws from rets.
    Returns {start: (p_grow, p_ruin, median_end, skip_rate)}."""
    rng = np.random.default_rng(seed)
    rets = np.asarray([r for r in rets if np.isfinite(r)])
    out = {}
    if len(rets) < 5:
        return out
    n = max(1, int(round(trades_per_yr)))
    for s0 in starts:
        eq = np.full(n_paths, float(s0))
        skips = 0
        draws = rng.choice(rets, size=(n_paths, n))
        for j in range(n):
            k = np.floor(frac * eq / cost)
            k = np.where((k < 1) & (cost <= 0.6 * eq), 1, k)
            skips += (k < 1).sum()
            eq = eq + k * cost * draws[:, j]
            eq = np.maximum(eq, 0)
        out[s0] = {"p_grow": float((eq > s0).mean()), "p_ruin": float((eq < 0.12 * s0).mean()),
                   "median": float(np.median(eq)), "skip": float(skips / (n_paths * n))}
    return out


# =====================================================================================  6. PART A: ACTIVIST SHORT REPORTS
def _cik_map():
    """ticker -> (cik, sic) using SEC current list + research_fundamental ticker map (delisted) if present."""
    d = json.load(open(FRAW / "company_tickers_exchange.json"))
    m = {}
    for cik, name, tk, ex in d["data"]:
        if tk and tk.upper() not in m:
            m[tk.upper()] = int(cik)
    try:
        tk = fund("tickers.pkl")
        for cik, (src, t) in tk.items():
            m.setdefault(t.upper(), cik)
    except Exception:
        pass
    fil = load("filings.pkl") if P("filings.pkl").exists() else {}
    sic = {c: r.get("sic") for c, r in fil.items()}
    return m, sic


_STOP = {"inc", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "holdings", "holding", "group", "the", "sa", "nv",
         "ag", "lp", "llc", "international", "intl", "technologies", "technology", "and", "of", "adr", "class", "a", "de", "se"}


def _norm(s):
    return [w for w in re.sub(r"[^a-z0-9 ]", " ", str(s).lower().replace("&", " and ")).split() if w not in _STOP]


def _name_ok(a, b):
    x, y = set(_norm(a)), set(_norm(b))
    return bool(x and y) and (len(x & y) / min(len(x), len(y)) >= 0.5)


def map_ciks(df, tcol="ticker", ncol="company"):
    """ticker -> CIK, validated by company-name overlap (tickers get reused); falls back to exact normalized-name lookup."""
    cmap, _ = _cik_map()
    fil = load("filings.pkl")
    names = {c: r.get("name") for c, r in fil.items()}
    by_name = defaultdict(list)
    for c, n in names.items():
        by_name[" ".join(_norm(n))].append(c)
    out = []
    for _, r in df.iterrows():
        c = cmap.get(r[tcol])
        nm = r.get(ncol, "")
        if c is not None and (c not in names or not nm or _name_ok(nm, names[c])):
            out.append(c)
            continue
        hits = by_name.get(" ".join(_norm(nm)), [])
        out.append(hits[0] if len(hits) == 1 else np.nan)
    return out


def _tday(idx, d, after=False):
    """first trading day >= d (or > d if after)."""
    i = idx.searchsorted(d, side="right" if after else "left")
    return i if i < len(idx) else None


def partA():
    sr = pd.read_csv(RAW / "short_reports.csv")
    sr["report_date"] = pd.to_datetime(sr.report_date, errors="coerce")
    sr = sr.dropna(subset=["report_date", "ticker"])
    sr["ticker"] = sr.ticker.astype(str).str.upper().str.strip().str.replace(".", "-", regex=False)
    sr = sr[(sr.report_date >= "2012-01-01")].drop_duplicates(["ticker", "report_date"]).reset_index(drop=True)
    cmap, sicmap = _cik_map()
    sr["cik"] = map_ciks(sr)
    sr["etf"] = [sic_etf(sicmap.get(c)) if pd.notna(c) else "IWM" for c in sr.cik]
    px = load_daily(list(sr.ticker.unique()) + SECTOR_ETF)
    rows = []
    for _, e in sr.iterrows():
        d = px.get(e.ticker)
        if d is None or len(d) < 30:
            continue
        idx = d.index
        tod = str(e.get("time_of_day", "")).lower()
        i0 = _tday(idx, e.report_date, after=("after" in tod))
        if i0 is None or i0 < 21 or abs((idx[i0] - e.report_date).days) > 5:
            continue
        a = d.adj.values
        c = d.close.values
        rec = {"ticker": e.ticker, "company": e.company, "firm": e.firm, "date": idx[i0], "type": str(e.allegation_type).lower(),
               "tod": tod, "etf": e.etf, "cik": e.cik, "price0": c[i0 - 1]}
        m = px["SPY"].adj.reindex(idx).ffill().values
        s = (px.get(e.etf) if px.get(e.etf) is not None else px["IWM"]).adj.reindex(idx).ffill().values
        lr = np.diff(np.log(a))
        rec["rv_pre"] = np.nanstd(lr[i0 - 21:i0 - 1]) * np.sqrt(252)
        rec["dvol_pre"] = np.nanmedian((c * d.vol.values)[i0 - 21:i0 - 1])
        rec["r0"] = a[i0] / a[i0 - 1] - 1
        rec["x0"] = rec["r0"] - (m[i0] / m[i0 - 1] - 1)
        rec["xs0"] = rec["r0"] - (s[i0] / s[i0 - 1] - 1)
        rec["open_gap"] = d.open.values[i0] / c[i0 - 1] - 1 if np.isfinite(d.open.values[i0]) else np.nan
        rec["car01"] = (a[i0 + 1] / a[i0 - 1] - 1 - (m[i0 + 1] / m[i0 - 1] - 1)) if i0 + 1 < len(a) else np.nan
        n_after = len(a) - 1 - (i0 + 1)
        rec["n_after"] = n_after
        e1 = i0 + 1   # entry: day-1 close
        for h in (5, 20, 60, 120, 250):
            j = e1 + h
            if j < len(a):
                rec[f"r{h}"] = a[j] / a[e1] - 1
                rec[f"x{h}"] = rec[f"r{h}"] - (m[j] / m[e1] - 1)
                rec[f"xs{h}"] = rec[f"r{h}"] - (s[j] / s[e1] - 1)
                rec[f"min{h}"] = np.nanmin(a[e1:j + 1]) / a[e1] - 1
            elif idx[-1] < TODAY - pd.Timedelta(days=20):     # stopped trading (delisted): hold last price
                rec[f"r{h}"] = a[-1] / a[e1] - 1
                rec[f"x{h}"] = rec[f"r{h}"] - (m[-1] / m[e1] - 1)
                rec[f"xs{h}"] = rec[f"r{h}"] - (s[-1] / s[e1] - 1)
                rec[f"min{h}"] = np.nanmin(a[e1:]) / a[e1] - 1
                rec["delisted"] = True
        # day-0 open entry (for premarket reports): open->close d0 then onward
        if np.isfinite(d.open.values[i0]) and d.open.values[i0] > 0:
            o = d.open.values[i0] * a[i0] / c[i0]
            for h in (20, 60):
                j = i0 + h
                if j < len(a):
                    rec[f"o{h}"] = a[j] / o - 1
        # recovery: back to pre-report close at any point within 120 / 250 days
        for h in (120, 250):
            j = min(len(a) - 1, i0 + h)
            if j > i0 + 5 and (i0 + h < len(a) or idx[-1] < TODAY - pd.Timedelta(days=20)):
                rec[f"recov{h}"] = float(np.nanmax(a[i0 + 1:j + 1]) >= a[i0 - 1])
                rec[f"above{h}"] = float(a[j] >= a[i0 - 1])
        # post-event realized vol (days 1..21) for IV
        rec["rv_post"] = np.nanstd(lr[e1:e1 + 21]) * np.sqrt(252) if e1 + 21 < len(lr) else np.nanstd(lr[e1:]) * np.sqrt(252)
        rec["rv_post60"] = np.nanstd(lr[e1:e1 + 60]) * np.sqrt(252)
        # options from day-1 close
        for k_iv in (1.0, 1.25, 1.5):
            for dte, held, mny in ((30, 20, 1.0), (60, 40, 1.0), (60, 58, 1.0), (90, 60, 1.0), (60, 40, 0.9), (120, 90, 1.0),
                                   (182, 180, 1.0), (365, 360, 1.0), (365, 360, 0.8)):
                j = e1 + int(round(held * 252 / 365))
                if j >= len(a):
                    if idx[-1] < TODAY - pd.Timedelta(days=20):
                        j = len(a) - 1
                    else:
                        continue
                S0, S1 = c[e1], c[e1] * a[j] / a[e1]
                sig0 = max(0.25, k_iv * rec["rv_post"])
                sig1 = max(0.25, k_iv * np.nanstd(lr[max(e1, j - 21):j]) * np.sqrt(252)) if j - e1 > 3 else sig0
                for sp in (0.05, 0.10, 0.20):
                    rec[f"put_{dte}_{held}_{int(mny * 100)}_k{k_iv}_s{int(sp * 100)}"] = opt_trade(S0, S1, sig0, sig1, dte, held, mny, True, sp, 0.8)
        rows.append(rec)
    ev = pd.DataFrame(rows)
    # market cap at event (cover shares x price) if available
    try:
        fa = load("facts.pkl")
        caps = []
        for _, r in ev.iterrows():
            cap = np.nan
            if pd.notna(r.cik) and int(r.cik) in fa:
                cv = [(pd.Timestamp(fd), v) for fd, e_, v in fa[int(r.cik)]["cover"] if pd.Timestamp(fd) <= r.date]
                if cv:
                    cap = cv[-1][1] * r.price0
            caps.append(cap)
        ev["mcap"] = caps
    except Exception:
        ev["mcap"] = np.nan
    save(ev, "partA_events.pkl")
    summarize_A(ev)


def _summ(x, cols):
    o = {"n": int(len(x))}
    for c in cols:
        if c in x:
            v = x[c].astype(float)
            v = v[np.isfinite(v)]
            o[c] = (round(float(v.mean()) * 100, 2), round(float(v.median()) * 100, 2), round(float(tstat(v)), 2) if len(v) > 2 else None, int(len(v)))
    return o


def partA_pre():
    """were the forensic flags already on BEFORE the short report? event rate vs same-month base rate."""
    ev = load("partA_events.pkl")
    F = load("flags.pkl")
    F = F[F.shares.notna() | F.M.notna()]                 # firms with XBRL facts
    ev = ev.dropna(subset=["cik"]).copy()
    ev["m"] = ev.date.dt.to_period("M") - 1
    fl = ["auditor", "restate", "late", "turnover", "gc", "beneish", "dsri_f", "soft", "rpt", "dilution"]
    E = ev.merge(F, left_on=["cik", "m"], right_on=["cik", "month"], how="inner")
    base = F[F.month.isin(E.m.unique())]
    # base weighted to the event-month mix
    w = E.m.value_counts()
    bm = base.groupby("month")[fl + ["n502"]].mean()
    bw = bm.reindex(w.index).mul(w.values, axis=0).sum() / w.sum()
    out = {"n_matched": int(len(E))}
    for f in fl:
        out[f] = {"event_rate": round(float(E[f].mean()) * 100, 1), "base_rate": round(float(bw[f]) * 100, 1),
                  "lift": round(float(E[f].mean() / bw[f]), 2) if bw[f] > 0 else None}
    E["score"] = E[[f for f in fl]].sum(axis=1)
    out["score_ge2"] = {"event": round(float((E.score >= 2).mean()) * 100, 1),
                        "base": round(float((base[fl].sum(axis=1) >= 2).mean()) * 100, 1)}
    out["score_ge1"] = {"event": round(float((E.score >= 1).mean()) * 100, 1),
                        "base": round(float((base[fl].sum(axis=1) >= 1).mean()) * 100, 1)}
    out["M_median_event"] = round(float(E.M.median()), 2)
    out["M_median_base"] = round(float(base.M.median()), 2)
    out["shgrowth_median_event"] = round(float(E.sh_g.median()) * 100, 1)
    out["shgrowth_median_base"] = round(float(base.sh_g.median()) * 100, 1)
    # insider selling: 6m sales $ relative to cap (cap = cover shares x pre-report price)
    E["ins_rel"] = E.ins_sell6 / (E.shares * E.price0)
    out["insider_sell6_rel_median_event"] = round(float(E.ins_rel.median()) * 100, 3)
    out["insider_ge1pct_event"] = round(float((E.ins_rel >= 0.01).mean()) * 100, 1)
    # pre-report price run-up (stock momentum into the report)
    results_update("partA_pre", out)
    print(json.dumps(out, indent=1))


def summarize_A(ev=None):
    ev = load("partA_events.pkl") if ev is None else ev
    out = {}
    cols = ["r0", "x0", "xs0", "car01", "x5", "x20", "x60", "x120", "x250", "xs20", "xs60", "xs120", "min60", "min120"]
    out["all"] = _summ(ev, cols)
    out["recovery"] = {c: round(float(ev[c].mean()), 3) for c in ("recov120", "above120", "recov250", "above250") if c in ev}
    ev["sz"] = pd.cut(ev.mcap, [0, 3e8, 2e9, 1e10, 1e14], labels=["<300M", "300M-2B", "2-10B", ">10B"])
    out["by_size"] = {str(k): _summ(g, cols) for k, g in ev.groupby("sz") if len(g) >= 5}
    out["by_firm"] = {k: _summ(g, ["x0", "x20", "x60", "x120"]) for k, g in ev.groupby("firm") if len(g) >= 5}
    ev["typ"] = ev["type"].str.extract(r"(fraud|valuation|mixed)", expand=False).fillna("other")
    out["by_type"] = {k: _summ(g, cols) for k, g in ev.groupby("typ")}
    ev["yr"] = ev.date.dt.year
    ev["era"] = np.where(ev.yr <= 2018, "2012-18", "2019+")
    out["by_era"] = {k: _summ(g, cols) for k, g in ev.groupby("era")}
    ev["d0b"] = pd.cut(ev.x0, [-9, -0.15, -0.05, 0.0, 9], labels=["d0<-15%", "-15..-5%", "-5..0%", "d0>=0"])
    out["by_day0"] = {str(k): _summ(g, ["x5", "x20", "x60", "x120"]) for k, g in ev.groupby("d0b") if len(g) >= 5}
    pc = [c for c in ev.columns if c.startswith("put_")]
    out["puts"] = {c: _summ(ev, [c])[c] for c in pc}
    out["puts_by_firm"] = {f: {c: _summ(g, [c])[c] for c in pc if c.endswith("_k1.0_s10") or c.endswith("_k1.25_s10")} for f, g in ev.groupby("firm") if len(g) >= 10}
    out["puts_by_era"] = {era: {c: _summ(g, [c])[c] for c in pc if c.endswith("_k1.25_s10")} for era, g in ev.groupby("era")}
    out["puts_by_type"] = {t: {c: _summ(g, [c])[c] for c in pc if c.endswith("_k1.25_s10")} for t, g in ev.groupby("typ")}
    out["puts_by_size"] = {str(t): {c: _summ(g, [c])[c] for c in pc if c.endswith("_k1.25_s10")} for t, g in ev.groupby("sz") if len(g) >= 5}
    out["puts_by_day0"] = {str(t): {c: _summ(g, [c])[c] for c in pc if c.endswith("_k1.25_s10")} for t, g in ev.groupby("d0b") if len(g) >= 5}
    out["rv"] = {"rv_pre_med": float(ev.rv_pre.median()), "rv_post_med": float(ev.rv_post.median()), "rv_post60_med": float(ev.rv_post60.median())}
    out["n_events"] = int(len(ev))
    out["n_delisted"] = int(ev.get("delisted", pd.Series(dtype=bool)).fillna(False).sum())
    results_update("partA", out)
    print(json.dumps({k: out[k] for k in ("all", "recovery", "by_type", "by_era", "rv")}, indent=1, default=str))
    return out


# =====================================================================================  7. PART B: FLAGS PANEL
MONTHS = pd.period_range("2011-01", "2026-10", freq="M")
FLAGS = ["beneish", "dsri", "soft", "auditor", "restate", "late", "turnover", "gc", "rpt", "insider", "dilution"]
FLAG_DESC = {
    "beneish": "Beneish M-score > -1.78 (latest 10-K, filed <= 15m ago)",
    "dsri": "receivables/sales index DSRI >= 1.4 (DSO up 40%+ vs revenue)",
    "soft": "soft-asset share (TA-PPE-cash)/TA up >= 10 pts yoy",
    "auditor": "8-K Item 4.01 auditor change in last 12m",
    "restate": "8-K Item 4.02 non-reliance/restatement in last 12m",
    "late": "NT 10-K / NT 10-Q late-filing notice in last 12m",
    "turnover": ">= 3 8-Ks with Item 5.02 (officer/director change) in last 12m",
    "gc": "going-concern phrase in a 10-K (full-text search) filed in last 15m",
    "rpt": "related-party balances/revenue up >= 50% yoy and >= 1% of assets",
    "insider": "open-market insider sales over 6m >= 1% of market cap",
    "dilution": "cover-page shares outstanding up >= 20% yoy",
}


def _mcount(dates, months=MONTHS, window=12):
    """number of events in the trailing `window` months (inclusive of current), per month."""
    if not dates:
        return np.zeros(len(months), np.int16)
    pm = pd.PeriodIndex([d[:7] for d in dates], freq="M")
    c = pd.Series(1, index=pm).groupby(level=0).sum().reindex(months, fill_value=0)
    return c.rolling(window, min_periods=1).sum().values.astype(np.int16)


def _beneish(a):
    """annual frame (sorted fy) -> per-row M-score + components; needs prior year."""
    a = a.sort_values("fy").reset_index(drop=True)
    out = []
    for i in range(len(a)):
        r = a.iloc[i]
        res = {"fy": r.fy, "filed": r.filed}
        if i > 0 and 300 <= (r.fy - a.iloc[i - 1].fy).days <= 430:
            p = a.iloc[i - 1]
            g = lambda row, k: row.get(k, np.nan)
            S, Sp = g(r, "rev"), g(p, "rev")
            TA, TAp = g(r, "assets"), g(p, "assets")
            if S > 0 and Sp > 0 and TA > 0 and TAp > 0:
                def nz(x, d=0.0):
                    return x if np.isfinite(x) else d
                rec, recp = g(r, "recv"), g(p, "recv")
                dsri = (rec / S) / (recp / Sp) if np.isfinite(rec) and np.isfinite(recp) and recp > 0 and rec >= 0 else np.nan
                cg, cgp = g(r, "cogs"), g(p, "cogs")
                gm, gmp = (S - cg) / S if np.isfinite(cg) else np.nan, (Sp - cgp) / Sp if np.isfinite(cgp) else np.nan
                gmi = gmp / gm if np.isfinite(gm) and np.isfinite(gmp) and gm > 0.01 and gmp > 0 else np.nan
                ca, cap_ = g(r, "ca"), g(p, "ca")
                ppe, ppep = nz(g(r, "ppe")), nz(g(p, "ppe"))
                sec, secp = nz(g(r, "sec")), nz(g(p, "sec"))
                aqi = ((1 - (ca + ppe + sec) / TA) / (1 - (cap_ + ppep + secp) / TAp)) if np.isfinite(ca) and np.isfinite(cap_) and (1 - (cap_ + ppep + secp) / TAp) > 0.02 else np.nan
                sgi = S / Sp
                dep, depp = g(r, "dep"), g(p, "dep")
                depi = ((depp / (depp + ppep)) / (dep / (dep + ppe))) if np.isfinite(dep) and np.isfinite(depp) and dep > 0 and depp > 0 and ppe > 0 and ppep > 0 else np.nan
                sga, sgap = g(r, "sga"), g(p, "sga")
                sgai = ((sga / S) / (sgap / Sp)) if np.isfinite(sga) and np.isfinite(sgap) and sgap > 0 else np.nan
                cl, clp = g(r, "cl"), g(p, "cl")
                lvgi = (((nz(cl) + nz(g(r, "ltd"))) / TA) / ((nz(clp) + nz(g(p, "ltd"))) / TAp)) if (nz(clp) + nz(g(p, "ltd"))) > 0 else np.nan
                ni, cfo = g(r, "ni"), g(r, "cfo")
                tata = (ni - cfo) / TA if np.isfinite(ni) and np.isfinite(cfo) else np.nan
                comp = dict(dsri=dsri, gmi=gmi, aqi=aqi, sgi=sgi, depi=depi, sgai=sgai, lvgi=lvgi, tata=tata)
                c = {k: (min(max(v, -5), 10) if np.isfinite(v) else (0.0 if k == "tata" else 1.0)) for k, v in comp.items()}
                n_real = sum(np.isfinite(v) for v in comp.values())
                M = (-4.84 + 0.92 * c["dsri"] + 0.528 * c["gmi"] + 0.404 * c["aqi"] + 0.892 * c["sgi"] + 0.115 * c["depi"]
                     - 0.172 * c["sgai"] + 4.679 * c["tata"] - 0.327 * c["lvgi"])
                res.update(comp)
                res["M"] = M if (np.isfinite(tata) and n_real >= 5) else np.nan
                cash, cashp = nz(g(r, "cash")), nz(g(p, "cash"))
                res["soft_chg"] = ((TA - ppe - cash) / TA) - ((TAp - ppep - cashp) / TAp)
                rp = nz(g(r, "rpt_rev")) + nz(g(r, "rpt_due")) + nz(g(r, "rpt_tx"))
                rpp = nz(g(p, "rpt_rev")) + nz(g(p, "rpt_due")) + nz(g(p, "rpt_tx"))
                res["rpt_flag"] = bool(rp >= 0.01 * TA and rp >= 1.5 * max(rpp, 1.0))
                res["asset_g"] = TA / TAp - 1
                res["rev_g"] = sgi - 1
        out.append(res)
    return pd.DataFrame(out)


def flags():
    """monthly point-in-time red-flag panel per CIK."""
    t0 = time.time()
    fa, fil = load("facts.pkl"), load("filings.pkl")
    gc_hits = load("gc.pkl") if P("gc.pkl").exists() else {}
    gcd = defaultdict(list)
    for v in gc_hits.values():
        for cik, fd, ftype, adsh in v:
            if fd:
                gcd[cik].append((fd, str(ftype or "")))
    ins = None
    if (DATA / "research_fund_insiders.pkl").exists():
        ins = fund("insiders.pkl")
        ins = {c: g.set_index("month")["ins_sell"] for c, g in ins.groupby("cik")}
    me = MONTHS.to_timestamp(how="end").normalize()
    parts = []
    for k, cik in enumerate(sorted(set(fa) | set(fil))):
        f = fil.get(cik)
        if f is None:
            continue
        ev = f["ev"]
        df = pd.DataFrame({"month": MONTHS})
        df["cik"] = cik
        df["auditor"] = _mcount(ev.get("4.01", [])) > 0
        df["restate"] = _mcount(ev.get("4.02", [])) > 0
        df["late"] = _mcount(ev.get("NT 10-K", []) + ev.get("NT 10-Q", [])) > 0
        df["n502"] = _mcount(ev.get("5.02", []))
        df["turnover"] = df.n502 >= 3
        g_all = sorted(gcd.get(cik, []))
        df["gc"] = _mcount([d for d, t in g_all], window=15) > 0
        df["gc_ex"] = _mcount([d for d, t in g_all if t.upper().startswith("EX-")], window=15) > 0   # auditor consent / exhibit hit
        # annual accounting flags, as of filed date
        a = fa.get(cik)
        if a is not None and len(a["a"]) >= 2:
            b = _beneish(a["a"])
            b = b.dropna(subset=["filed"]).sort_values("filed")
            b["fm"] = b.filed.dt.to_period("M")
            b = b.drop_duplicates("fm", keep="last").set_index("fm")
            cols = ["M", "dsri", "soft_chg", "rpt_flag", "asset_g", "rev_g", "tata", "sgi"]
            b = b.reindex(columns=cols)
            bb = b.reindex(MONTHS).ffill(limit=15)
            for c in cols:
                df[c] = bb[c].values
            # cover shares growth (as of filed)
            cv = pd.DataFrame(a["cover"], columns=["filed", "end", "sh"])
            cv["fm"] = pd.PeriodIndex(cv.filed.str[:7], freq="M")
            cv = cv.groupby("fm").sh.last().reindex(MONTHS).ffill(limit=15)
            df["shares"] = cv.values
            df["sh_g"] = (cv / cv.shift(12) - 1).values
        else:
            for c in ["M", "dsri", "soft_chg", "rpt_flag", "asset_g", "rev_g", "tata", "sgi", "shares", "sh_g"]:
                df[c] = np.nan
        if ins is not None and cik in ins:
            s = ins[cik].reindex(MONTHS, fill_value=0).rolling(6, min_periods=1).sum()
            df["ins_sell6"] = s.values
        else:
            df["ins_sell6"] = 0.0
        df["sic"] = int(f["sic"]) if str(f.get("sic") or "").isdigit() else -1
        parts.append(df)
        if k % 3000 == 0:
            print(f"  {k} {time.time() - t0:.0f}s", flush=True)
    F = pd.concat(parts, ignore_index=True)
    fin = (F.sic >= 6000) & (F.sic < 6800)
    F["beneish"] = (F.M > -1.78) & ~fin
    F["dsri_f"] = (F.dsri >= 1.4) & ~fin
    F["soft"] = (F.soft_chg >= 0.10) & ~fin
    F["rpt"] = F.rpt_flag.fillna(False).astype(bool)
    F["dilution"] = F.sh_g >= 0.20
    for c in ("auditor", "restate", "late", "turnover", "gc", "gc_ex", "beneish", "soft", "rpt", "dilution", "dsri_f"):
        F[c] = F[c].fillna(False).astype(bool)
    for c in F.columns:
        if F[c].dtype == "float64":
            F[c] = F[c].astype("float32")
    save(F, "flags.pkl")
    print("flags rows", len(F), "ciks", F.cik.nunique(), f"{time.time() - t0:.0f}s")
    print(F[F.month >= pd.Period("2012-01", "M")][["auditor", "restate", "late", "turnover", "gc", "gc_ex", "beneish", "dsri_f", "soft", "rpt", "dilution"]].mean())


IS0, IS1, OOS0, LASTM = pd.Period("2012-01", "M"), pd.Period("2018-12", "M"), pd.Period("2019-01", "M"), pd.Period("2026-09", "M")
BFLAGS = ["beneish", "dsri_f", "soft", "auditor", "restate", "late", "turnover", "gc", "gc_ex", "rpt", "insider", "dilution"]
SCORE_FLAGS = ["beneish", "dsri_f", "soft", "auditor", "restate", "late", "turnover", "gc", "rpt", "insider", "dilution"]


def nw_t(s, L):
    s = pd.Series(s).dropna()
    n = len(s)
    if n < 12:
        return np.nan
    x = s.values - s.mean()
    v = (x @ x) / n
    for l in range(1, L + 1):
        w = 1 - l / (L + 1)
        v += 2 * w * (x[l:] @ x[:-l]) / n
    return s.mean() / np.sqrt(v / n) if v > 0 else np.nan


def mypanel():
    """Own monthly price panel (used if research_fundamental's panel.pkl is not ready). Same sources and logic as
    research_fundamental.tickers()/_px_table()/_fwd() (imported helpers), minus the SEC instance-name lookups:
    listed CIKs -> yfinance monthly; delisted -> HF symbol from 10-K/10-Q document-name prefixes, validated by
    filing-span overlap and cover-shares x price vs public float."""
    sys.path.insert(0, str(ROOT / "bot"))
    import research_fundamental as RF
    t0 = time.time()
    subs_ = fund("subs.pkl")
    ffacts = {c: {"cover": f["cover"], "float": f["float"], "name": f.get("name")} for c, f in fund("facts.pkl").items()}
    import gc as _gc
    _gc.collect()
    hf = fund("px_hf.pkl")
    yfp = fund("px_yf.pkl")
    cur = RF.current_map()
    sym_months = hf.groupby("symbol").month.agg(["min", "max", "count"])
    hf_idx = hf.set_index(["symbol", "month"]).raw
    tick = {}
    for cik, sb in subs_.items():
        if cik in cur and yfp.get(cur[cik]) is not None:
            tick[cik] = ("yf", cur[cik])
            continue
        per = [x for x in sb.get("per", []) if x[1] >= "2010-06-01"]
        if not per or cik not in ffacts:
            continue
        cands = RF._prefixes([x[4] for x in per])
        for t in sb.get("tickers", []):
            cands[t.upper().replace(".", "-")] += 5
        f0, f1 = pd.Period(per[0][1], "M"), pd.Period(per[-1][1], "M")
        for c, w in sorted(cands.items(), key=lambda x: -x[1]):
            if c not in sym_months.index:
                continue
            mm = sym_months.loc[c]
            ov = min(mm["max"], f1 + 3) - max(mm["min"], f0)
            if ov.n < 0.5 * ((f1 - f0).n + 1) - 3:
                continue
            ok = True
            for fd, e, fl in ffacts[cik]["float"][-6:]:
                m = pd.Period(e[:7], "M")
                sh = [v for fd2, e2, v in ffacts[cik]["cover"] if abs((pd.Timestamp(fd2) - pd.Timestamp(e)).days) < 300]
                if not sh or (c, m) not in hf_idx.index or fl <= 0:
                    continue
                if not (0.6 <= sh[0] * float(hf_idx.loc[(c, m)]) / fl <= 12):
                    ok = False
            if ok:
                tick[cik] = ("hf", c)
                break
    print("mapped", len(tick), "hf", sum(v[0] == "hf" for v in tick.values()), f"{time.time() - t0:.0f}s", flush=True)
    RF_load = RF.load
    RF.load = lambda name: {"px_yf.pkl": yfp, "px_hf.pkl": hf}[name] if name in ("px_yf.pkl", "px_hf.pkl") else RF_load(name)
    px = RF._px_table(tick, ffacts, subs_)
    fw = RF._fwd(px)
    df = px.merge(fw, on=["cik", "month"], how="left")
    df["date"] = df.month.dt.end_time.dt.normalize()
    cov = []
    for cik, f in ffacts.items():
        for fd, e, v in f["cover"]:
            cov.append((cik, pd.Timestamp(fd), v))
    cov = pd.DataFrame(cov, columns=["cik", "cfiled", "cover"]).dropna().sort_values("cfiled")
    df = pd.merge_asof(df.sort_values("date"), cov, left_on="date", right_on="cfiled", by="cik", direction="backward")
    df.loc[(df.date - df.cfiled).dt.days > 400, "cover"] = np.nan
    df["mcap"] = df.cover * df.raw
    df = df[(df.mcap >= 2e8) & (df.raw >= 2)]
    df = df.sort_values(["cik", "month"])
    df["rv3"] = df.groupby("cik").rv.transform(lambda x: x.rolling(3, min_periods=1).mean())
    df["ticker"] = df.cik.map({c: v[1] for c, v in tick.items()})
    df["name"] = df.cik.map({c: f.get("name") for c, f in ffacts.items()})
    save(df.reset_index(drop=True), "panel.pkl")
    print("panel", len(df), df.cik.nunique(), f"{time.time() - t0:.0f}s")


def bpanel():
    """merge flags with the monthly price panel (point-in-time caps, fwd returns incl. delisted).
    Prefers research_fundamental's panel.pkl; falls back to mypanel()."""
    F = load("flags.pkl")
    if (DATA / "research_fund_panel.pkl").exists():
        pan = fund("panel.pkl")
    else:
        if not P("panel.pkl").exists():
            mypanel()
        pan = load("panel.pkl")
    keep = [c for c in ["cik", "month", "adj", "raw", "mcap", "rv", "rv3", "dvol", "r1", "r3", "r6", "r12", "dd3", "dd6", "dd12",
                        "delisted_in12", "ticker", "name", "ins_sell", "ins_buy"] if c in pan.columns]
    pan = pan[keep]
    df = pan.merge(F.drop(columns=[c for c in ("ins_sell6",) if c in F and "ins_sell" in pan]), on=["cik", "month"], how="inner")
    if "ins_sell" in df:
        df["insider"] = (df.ins_sell / df.mcap) >= 0.01
    else:
        df["insider"] = (df.ins_sell6 / df.mcap) >= 0.01
    df = df[(df.mcap >= 3e8) & (df.mcap <= 1e10) & (df.sic != 6770) & (df.month >= IS0)]
    df["size"] = np.where(df.mcap < 2e9, "300M-2B", "2-10B")
    df["score"] = df[SCORE_FLAGS].sum(axis=1)
    for h in (3, 6, 12):
        df[f"x{h}"] = df[f"r{h}"] - df.groupby(["month", "size"])[f"r{h}"].transform("mean")
    df["crash12"] = (df.dd12 <= -0.30).astype(float).where(df.dd12.notna())
    df["crash6"] = (df.dd6 <= -0.30).astype(float).where(df.dd6.notna())
    save(df.reset_index(drop=True), "bpanel.pkl")
    print("bpanel", len(df), df.cik.nunique(), df.month.min(), df.month.max())
    return df


def _flag_test(df, col, h, per):
    lo, hi = per
    d = df[(df.month >= lo) & (df.month <= hi) & df[f"x{h}"].notna()]
    if d[col].sum() < 30:
        return None
    g = d.groupby(["month", d[col]])[f"x{h}"].mean().unstack()
    if True not in g or False not in g:
        return None
    diff = (g[True] - g[False]).dropna()
    t = nw_t(diff, h - 1)
    ck = f"crash{h if h in (6, 12) else 12}"
    dd = d.dropna(subset=[ck])
    base = dd[ck].mean()
    fl = dd[dd[col]]
    prec = fl[ck].mean()
    crash = dd[dd[ck] == 1]
    non = dd[dd[ck] == 0]
    under = (d.loc[d[col], f"x{h}"] < 0).mean()
    return {"n_flag_obs": int(d[col].sum()), "n_firms": int(d.loc[d[col], "cik"].nunique()), "pct_flagged": round(float(d[col].mean()) * 100, 2),
            "excess_diff_pct": round(float(diff.mean()) * 100, 2), "t_nw": round(float(t), 2), "p": float(pval(t)),
            "flag_x_mean": round(float(d.loc[d[col], f"x{h}"].mean()) * 100, 2),
            "hit_under": round(float(under) * 100, 1),
            "crash_rate_flag": round(float(prec) * 100, 1), "crash_base": round(float(base) * 100, 1),
            "lift": round(float(prec / base), 2) if base > 0 else None,
            "recall_tpr": round(float(crash[col].mean()) * 100, 1), "fpr": round(float(non[col].mean()) * 100, 1)}


def partB():
    df = load("bpanel.pkl") if P("bpanel.pkl").exists() else bpanel()
    res = {"desc": FLAG_DESC, "n_obs": int(len(df)), "n_firms": int(df.cik.nunique())}
    df["s2"] = df.score >= 2
    df["s3"] = df.score >= 3
    df["s4"] = df.score >= 4
    df["acct_any"] = df[["beneish", "dsri_f", "soft"]].any(axis=1)
    df["event_any"] = df[["auditor", "restate", "late", "gc"]].any(axis=1)
    cols = BFLAGS + ["acct_any", "event_any", "s2", "s3", "s4"]
    tests = []
    for per_name, per in (("IS", (IS0, IS1)), ("OOS", (OOS0, LASTM))):
        for size in ("all", "300M-2B", "2-10B"):
            d = df if size == "all" else df[df["size"] == size]
            for c in cols:
                for h in (6, 12):
                    r = _flag_test(d, c, h, per)
                    if r:
                        tests.append({"period": per_name, "size": size, "flag": c, "h": h, **r})
    T = pd.DataFrame(tests)
    for (per_name, size), g in T.groupby(["period", "size"]):
        T.loc[g.index, "bh"] = bh(g.p.values, 0.10)
    # sign consistency: IS negative and OOS negative
    res["tests"] = T.to_dict("records")
    print(T[(T["size"] == "all")][["period", "flag", "h", "n_flag_obs", "pct_flagged", "excess_diff_pct", "t_nw", "bh", "hit_under",
                                     "crash_rate_flag", "crash_base", "lift", "recall_tpr", "fpr"]].to_string())
    # score buckets
    sb = []
    for per_name, (lo, hi) in (("IS", (IS0, IS1)), ("OOS", (OOS0, LASTM))):
        d = df[(df.month >= lo) & (df.month <= hi)]
        for s, g in d.groupby(d.score.clip(upper=5)):
            sb.append({"period": per_name, "score": int(s), "n": int(len(g)), "x6": round(float(g.x6.mean()) * 100, 2),
                       "x12": round(float(g.x12.mean()) * 100, 2), "crash12": round(float(g.crash12.mean()) * 100, 1),
                       "under12": round(float((g.x12 < 0).mean()) * 100, 1)})
    res["score_buckets"] = sb
    print(pd.DataFrame(sb).to_string())
    results_update("partB", res)
    partB_options(df)


def _entries(df, col, gap=6):
    """event entries: month the flag turns on (off in prior month), max one per cik per `gap` months."""
    d = df[["cik", "month", col]].sort_values(["cik", "month"])
    prev = d.groupby("cik")[col].shift(1).fillna(False).astype(bool)
    on = d[d[col] & ~prev]
    out, last = [], {}
    for cik, m in zip(on.cik.values, on.month.values):
        if cik in last and (m - last[cik]).n < gap:
            continue
        last[cik] = m
        out.append((cik, m))
    return pd.DataFrame(out, columns=["cik", "month"])


def partB_options(df=None):
    df = load("bpanel.pkl") if df is None else df
    df["s2"], df["s3"], df["s4"] = df.score >= 2, df.score >= 3, df.score >= 4
    df["acct_any"] = df[["beneish", "dsri_f", "soft"]].any(axis=1)
    df["event_any"] = df[["auditor", "restate", "late", "gc"]].any(axis=1)
    key = df.set_index(["cik", "month"])
    out = []
    trades_all = {}
    for col in BFLAGS + ["acct_any", "event_any", "s2", "s3", "s4"]:
        E = _entries(df, col)
        E = E.merge(df[["cik", "month", "raw", "adj", "rv", "rv3", "mcap", "size", "r3", "r6", "x3", "x6", "dd6"]], on=["cik", "month"])
        E = E.dropna(subset=["r3", "rv3"])
        recs = []
        for _, e in E.iterrows():
            sig = max(0.20, float(e.rv3))
            sp = 0.20 if e["size"] == "300M-2B" else 0.10
            S0 = 100.0
            r = {"cik": e.cik, "month": e.month, "size": e["size"], "x6": e.x6, "r6": e.r6}
            for k in (1.0, 1.2, 1.4):
                r[f"p3_atm_k{k}"] = opt_trade(S0, S0 * (1 + e.r3), k * sig, k * sig, 91, 91, 1.0, True, sp, 0.5)
                if np.isfinite(e.r6):
                    r[f"p6_atm_k{k}"] = opt_trade(S0, S0 * (1 + e.r6), k * sig, k * sig, 182, 182, 1.0, True, sp, 0.5)
                    r[f"p6_otm_k{k}"] = opt_trade(S0, S0 * (1 + e.r6), k * sig, k * sig, 182, 182, 0.9, True, sp, 0.5)
                    # 6m put, sold after 3 months
                    r[f"p6x3_atm_k{k}"] = opt_trade(S0, S0 * (1 + e.r3), k * sig, k * sig, 182, 91, 1.0, True, sp, 0.5)
            r["p3_atm_k1.2_mid"] = opt_trade(S0, S0 * (1 + e.r3), 1.2 * sig, 1.2 * sig, 91, 91, 1.0, True, 0.0, 0.5)
            r["p6_atm_k1.2_mid"] = opt_trade(S0, S0 * (1 + e.r6), 1.2 * sig, 1.2 * sig, 182, 182, 1.0, True, 0.0, 0.5) if np.isfinite(e.r6) else np.nan
            # option cost per contract at the real price (ATM 6m put, k=1.2)
            r["cost6"] = bs(float(e.raw), float(e.raw), 0.5, 1.2 * sig, True) * 100 * (1 + sp / 2)
            r["cost3"] = bs(float(e.raw), float(e.raw), 0.25, 1.2 * sig, True) * 100 * (1 + sp / 2)
            recs.append(r)
        R = pd.DataFrame(recs)
        if R.empty:
            continue
        trades_all[col] = R
        for per_name, lo, hi in (("IS", IS0, IS1), ("OOS", OOS0, LASTM)):
            for size in ("all", "300M-2B", "2-10B"):
                g = R[(R.month >= lo) & (R.month <= hi)]
                if size != "all":
                    g = g[g["size"] == size]
                if len(g) < 15:
                    continue
                row = {"flag": col, "period": per_name, "size": size, "n": int(len(g)), "per_yr": round(len(g) / (7 if per_name == "IS" else 7.5), 1),
                       "x6": round(float(g.x6.mean()) * 100, 2)}
                for c in [c for c in R.columns if c.startswith("p")]:
                    v = g[c].dropna()
                    if len(v):
                        mclust = v.groupby(g.loc[v.index, "month"]).mean()
                        row[c] = round(float(v.mean()) * 100, 1)
                        row[c + "_t"] = round(float(tstat(mclust)), 2)
                        row[c + "_pop"] = round(float((v > 0).mean()) * 100, 1)
                row["cost6_med"] = round(float(g.cost6.median()), 0)
                row["cost3_med"] = round(float(g.cost3.median()), 0)
                out.append(row)
    O = pd.DataFrame(out)
    save(trades_all, "partB_trades.pkl")
    show = ["flag", "period", "size", "n", "per_yr", "x6", "p3_atm_k1.2", "p3_atm_k1.2_t", "p6_atm_k1.0", "p6_atm_k1.2", "p6_atm_k1.2_t",
            "p6_atm_k1.2_pop", "p6_atm_k1.4", "p6_otm_k1.2", "p6x3_atm_k1.2", "p6_atm_k1.2_mid", "cost6_med"]
    print(O[[c for c in show if c in O]].to_string())
    results_update("partB_options", O.to_dict("records"))


# =====================================================================================  8. PART C: BINARY EVENTS
def _ev_window(d, date, timing="unknown"):
    """returns (i_pre, i0): index of the last close before the event and the event-reaction close."""
    idx = d.index
    t = str(timing).lower()
    if "after" in t:
        i0 = _tday(idx, date, after=True)
    else:
        i0 = _tday(idx, date)
    if i0 is None or i0 < 61 or abs((idx[i0] - date).days) > 6:
        return None, None
    return i0 - 1, i0


def fda():
    f = pd.read_csv(RAW / "fda_history.csv")
    f["decision_date"] = pd.to_datetime(f.decision_date, errors="coerce")
    f = f.dropna(subset=["decision_date", "ticker"])
    f["ticker"] = f.ticker.astype(str).str.upper().str.strip()
    f = f.drop_duplicates(["ticker", "decision_date"])
    px = load_daily(list(f.ticker.unique()) + ["XBI", "SPY"])
    xbi = px["XBI"].adj
    rows = []
    for _, e in f.iterrows():
        d = px.get(e.ticker)
        if d is None or len(d) < 80:
            continue
        ip, i0 = _ev_window(d, e.decision_date, e.announce_timing)
        if ip is None or i0 + 1 >= len(d):
            continue
        a = d.adj.values
        idx = d.index
        b = xbi.reindex(idx).ffill().values
        lr = np.diff(np.log(a))
        # unknown timing: 2-day window (pre close -> close day+1) to be safe
        j = i0 + 1 if str(e.announce_timing).lower() == "unknown" else i0
        mv = a[j] / a[ip] - 1
        mvx = mv - (b[j] / b[ip] - 1)
        sd = np.nanstd(lr[ip - 60:ip - 5]) * np.sqrt(252)        # pre-event vol excluding the last week
        rec = {"ticker": e.ticker, "date": idx[i0], "outcome": str(e.outcome).strip(), "first": str(e.first_approval).lower(),
               "adcomm": str(e.adcomm_vote) if pd.notna(e.adcomm_vote) else "", "move": mv, "movex": mvx, "rv60": sd,
               "price": d.close.values[ip], "dvol": np.nanmedian((d.close * d.vol).values[ip - 20:ip]),
               "runup20": a[ip] / a[ip - 20] - 1 - (b[ip] / b[ip - 20] - 1), "runup60": a[ip] / a[ip - 60] - 1 - (b[ip] / b[ip - 60] - 1)}
        for h in (20, 60):
            if j + h < len(a):
                rec[f"post{h}"] = a[j + h] / a[j] - 1 - (b[j + h] / b[j] - 1)
        rows.append(rec)
    E = pd.DataFrame(rows)
    E["crl"] = E.outcome.str.upper().str.contains("CRL")
    save(E, "fda_events.pkl")
    out = {"n": int(len(E)), "n_crl": int(E.crl.sum())}
    for lab, g in (("approved", E[~E.crl]), ("CRL", E[E.crl])):
        out[lab] = {"n": int(len(g)), "mean": round(float(g.move.mean()) * 100, 1), "median": round(float(g.move.median()) * 100, 1),
                    "abs_mean": round(float(g.move.abs().mean()) * 100, 1), "p10": round(float(g.move.quantile(0.1)) * 100, 1),
                    "p90": round(float(g.move.quantile(0.9)) * 100, 1), "le_-50": round(float((g.move <= -0.5).mean()) * 100, 1),
                    "le_-30": round(float((g.move <= -0.3).mean()) * 100, 1), "runup20": round(float(g.runup20.mean()) * 100, 1),
                    "post20": round(float(g.post20.mean()) * 100, 1) if "post20" in g else None,
                    "post60": round(float(g.post60.mean()) * 100, 1) if "post60" in g else None,
                    "rv60_med": round(float(g.rv60.median()) * 100, 0)}
    for lab, g in (("first_approval", E[E["first"] == "yes"]), ("not_first", E[E["first"] != "yes"])):
        out[lab] = {"n": int(len(g)), "crl_share": round(float(g.crl.mean()) * 100, 1),
                    "app_mean": round(float(g[~g.crl].move.mean()) * 100, 1), "crl_mean": round(float(g[g.crl].move.mean()) * 100, 1)}
    # sample over-represents CRLs: reweight to a true CRL base rate p
    ev_tab = []
    am, cm = E[~E.crl].move.values, E[E.crl].move.values
    for p_crl in (0.15, 0.20, 0.25, 0.30, 0.40):
        w_abs = (1 - p_crl) * np.mean(np.abs(am)) + p_crl * np.mean(np.abs(cm))
        row = {"p_crl": p_crl, "E_abs_move": round(float(w_abs) * 100, 1)}
        # 1-day ATM straddle priced at implied move M (= straddle/S): EV = E|move|/M - 1 (ignoring theta for 1-2 days)
        for M in (0.15, 0.20, 0.30, 0.40, 0.50):
            row[f"straddle_M{int(M * 100)}"] = round(float(w_abs / M - 1) * 100, 0)
        # ATM put / 20%-OTM put bought before, priced with implied event move M=0.30 (lognormal-ish two-point avg)
        for M in (0.20, 0.30, 0.40):
            sig = M / 0.8 * np.sqrt(365 / 7)               # 7-day option whose straddle = M (approx)
            prem_atm = bs(1, 1, 7 / 365, sig, True)
            prem_otm = bs(1, 0.8, 7 / 365, sig * 1.1, True)
            pay_atm = (1 - p_crl) * np.mean(np.maximum(-am, 0)) + p_crl * np.mean(np.maximum(-cm, 0))
            pay_otm = (1 - p_crl) * np.mean(np.maximum(-0.2 - am, 0)) + p_crl * np.mean(np.maximum(-0.2 - cm, 0))
            row[f"atm_put_M{int(M * 100)}"] = round(float(pay_atm / (prem_atm * 1.08) - 1) * 100, 0)
            row[f"otm20_put_M{int(M * 100)}"] = round(float(pay_otm / (prem_otm * 1.15) - 1) * 100, 0)
            pay_call = (1 - p_crl) * np.mean(np.maximum(am, 0)) + p_crl * np.mean(np.maximum(cm, 0))
            prem_call = bs(1, 1, 7 / 365, sig, False)
            row[f"atm_call_M{int(M * 100)}"] = round(float(pay_call / (prem_call * 1.08) - 1) * 100, 0)
        ev_tab.append(row)
    out["option_ev"] = ev_tab
    # tail: realized move vs pre-event vol (sigma units for a 1-2 day window)
    E["z"] = E.move / (E.rv60 / np.sqrt(252) * np.sqrt(2))
    out["z_abs_median"] = round(float(E.z.abs().median()), 1)
    out["crl_z_median"] = round(float(E[E.crl].z.median()), 1)
    # run-up strategy: buy 20d before, exit day before decision (stock, vs XBI)
    out["runup20_all"] = (round(float(E.runup20.mean()) * 100, 2), round(float(tstat(E.runup20)), 2))
    out["by_era"] = {}
    for era, g in E.groupby(np.where(E.date.dt.year <= 2018, "2013-18", "2019+")):
        out["by_era"][era] = {"n": int(len(g)), "crl_share": round(float(g.crl.mean()) * 100, 1),
                              "app": round(float(g[~g.crl].move.mean()) * 100, 1), "crl": round(float(g[g.crl].move.mean()) * 100, 1),
                              "abs": round(float(g.move.abs().mean()) * 100, 1)}
    results_update("fda", out)
    print(json.dumps(out, indent=1, default=str))
    return E


def legislation():
    L = pd.read_csv(RAW / "legislation_cases.csv")
    L["decision_date"] = pd.to_datetime(L.decision_date, errors="coerce")
    L["pending_since"] = pd.to_datetime(L.pending_since, errors="coerce")
    L["primary"] = L.tickers.astype(str).str.split(";").str[0].str.strip().str.upper()
    tick = sorted(set(L.primary) | {"SPY"})
    px = load_daily(tick)
    # pre-2010 cases need yfinance (HF starts 2010)
    rows = []
    for _, e in L.iterrows():
        d = px.get(e.primary)
        if (d is None or d.index[0] > e.decision_date - pd.Timedelta(days=120)) and pd.notna(e.decision_date):
            try:
                import yfinance as yf
                y = yf.download(e.primary, start=str((e.pending_since if pd.notna(e.pending_since) else e.decision_date) - pd.Timedelta(days=200))[:10],
                                end=str(e.decision_date + pd.Timedelta(days=200))[:10], auto_adjust=False, progress=False)
                if isinstance(y.columns, pd.MultiIndex):
                    y.columns = y.columns.get_level_values(0)
                d = pd.DataFrame({"open": y.Open, "close": y.Close, "adj": y["Adj Close"], "vol": y.Volume}).dropna()
            except Exception:
                d = None
        if d is None or len(d) < 80 or pd.isna(e.decision_date):
            continue
        ip, i0 = _ev_window(d, e.decision_date)
        if ip is None or i0 + 1 >= len(d):
            continue
        a = d.adj.values
        lr = np.diff(np.log(a))
        sd = np.nanstd(lr[ip - 60:ip - 1])
        mv1 = a[i0] / a[ip] - 1
        mv2 = a[i0 + 1] / a[ip] - 1
        mv = mv1 if abs(mv1) >= abs(mv2) * 0.7 else mv2
        ps = d.index.searchsorted(e.pending_since) if pd.notna(e.pending_since) else None
        pend = a[ip] / a[ps - 1] - 1 if ps and 1 <= ps < ip else np.nan
        rec = {"case": e.case_id, "cat": e.category, "ticker": e.primary, "date": d.index[i0], "outcome": str(e.outcome)[:40],
               "consensus": str(e.predicted_by_consensus)[:30], "move": mv, "sd_daily": sd, "z": mv / sd if sd > 0 else np.nan,
               "pending_ret": pend, "post20": a[min(len(a) - 1, i0 + 20)] / a[i0] - 1}
        # 1-day straddle priced at k x pre-event RV (no event premium) vs with event premium 2x
        for k in (1.0, 1.5, 2.5):
            M = 0.8 * sd * k * np.sqrt(2)          # 2-day straddle cost as fraction of S
            rec[f"straddle_k{k}"] = abs(mv) / M - 1 if M > 0 else np.nan
        rows.append(rec)
    E = pd.DataFrame(rows)
    save(E, "leg_events.pkl")
    out = {"n": int(len(E)), "abs_move_mean": round(float(E.move.abs().mean()) * 100, 1), "abs_move_median": round(float(E.move.abs().median()) * 100, 1),
           "z_abs_median": round(float(E.z.abs().median()), 1), "share_gt3sd": round(float((E.z.abs() > 3).mean()) * 100, 0),
           "share_gt5sd": round(float((E.z.abs() > 5).mean()) * 100, 0),
           "straddle_ev": {k: round(float(E[f"straddle_k{k}"].mean()) * 100, 0) for k in (1.0, 1.5, 2.5)},
           "straddle_med": {k: round(float(E[f"straddle_k{k}"].median()) * 100, 0) for k in (1.0, 1.5, 2.5)},
           "fav_vs_unfav": {lab: {"n": int(len(g)), "move": round(float(g.move.mean()) * 100, 1), "pending_ret": round(float(g.pending_ret.mean()) * 100, 1)}
                            for lab, g in E.groupby(E.outcome.str.startswith("fav"))},
           "cases": E.round(4).to_dict("records")}
    results_update("legislation", out)
    print(E[["case", "cat", "ticker", "date", "outcome", "move", "z", "pending_ret", "post20", "straddle_k1.5"]].round(3).to_string())
    print({k: v for k, v in out.items() if k != "cases"})


def mergers():
    M = pd.read_csv(RAW / "merger_deals.csv")
    M["announce_date"] = pd.to_datetime(M.announce_date, errors="coerce")
    M["end_date"] = pd.to_datetime(M.end_date, errors="coerce")
    M["target_ticker"] = M.target_ticker.astype(str).str.upper().str.strip()
    M = M.dropna(subset=["announce_date"]).drop_duplicates(["target_ticker", "announce_date"])
    M["offer"] = pd.to_numeric(M.offer_price_cash, errors="coerce")
    px = load_daily(list(M.target_ticker.unique()) + ["SPY"])
    rows = []
    for _, e in M.iterrows():
        d = px.get(e.target_ticker)
        if d is None or len(d) < 60:
            continue
        idx = d.index
        i0 = _tday(idx, e.announce_date)
        if i0 is None or i0 < 25 or abs((idx[i0] - e.announce_date).days) > 6 or i0 + 3 >= len(d):
            continue
        gaps = np.where(np.diff(idx.values[i0:]).astype("timedelta64[D]").astype(int) > 10)[0]
        if len(gaps):                                     # symbol reused after delisting: cut at the first long gap
            d = d.iloc[:i0 + gaps[0] + 1]
            idx = d.index
        c, a = d.close.values, d.adj.values
        e1 = i0 + 1                                       # entry: close of day after announcement
        pre = c[i0 - 1]
        rec = {"ticker": e.target_ticker, "date": idx[i0], "cons": e.consideration, "outcome": e.outcome, "src": e.sourced_via,
               "reason": e.break_reason, "pre": pre, "entry": c[e1], "prem": c[e1] / pre - 1}
        broke = str(e.outcome).startswith("terminated")
        rec["broke"] = broke
        if str(e.consideration).strip() == "cash" and np.isfinite(e.offer) and e.offer > 0:
            rec["spread"] = e.offer / c[e1] - 1
        # realized vol after announcement (pinned)
        lr = np.diff(np.log(a))
        rec["rv_post"] = np.nanstd(lr[e1:e1 + 20]) * np.sqrt(252)
        rec["rv_pre"] = np.nanstd(lr[i0 - 60:i0 - 1]) * np.sqrt(252) if i0 > 61 else np.nan
        # end: termination -> price 1 day after end_date; completion -> last trading close
        j_end = None
        if pd.notna(e.end_date):
            j_end = _tday(idx, e.end_date)
            if j_end is not None and broke:
                j_end = min(len(c) - 1, j_end + 1)
        if j_end is not None and not broke:
            j_end = min(j_end, len(c) - 1) - (1 if j_end < len(c) else 0)
        if j_end is None or j_end <= e1:
            j_end = len(c) - 1
        if not broke and np.isfinite(e.offer) and str(e.consideration).strip() == "cash" and abs(c[j_end] / e.offer - 1) > 0.3:
            continue                                      # price series does not converge to the offer: bad mapping
        rec["days"] = int(j_end - e1)
        rec["ret_end"] = a[j_end] / a[e1] - 1
        rec["ret_end_raw"] = c[j_end] / c[e1] - 1
        rec["break_vs_pre"] = c[j_end] / pre - 1 if broke else np.nan
        # option sims from entry: 6m (126d) put 10% OTM and 6m call ATM; IV = k x max(rv_post, 0.15)
        for k in (1.5, 2.5, 4.0):
            sig = k * max(rec["rv_post"], 0.10)
            for name, mny, put in (("put90", 0.9, True), ("put80", 0.8, True), ("callatm", 1.0, False)):
                hold = 182
                jj = min(j_end, e1 + 125) if not broke else min(len(c) - 1, max(e1 + 1, min(j_end, e1 + 125)))
                if broke and j_end > e1 + 125:
                    jj = e1 + 125
                S1 = c[e1] * a[jj] / a[e1]
                held = int((idx[jj] - idx[e1]).days)
                sig1 = sig if not broke or jj < j_end else max(rec["rv_pre"] if np.isfinite(rec["rv_pre"]) else 0.4, 0.3)
                rec[f"{name}_k{k}"] = opt_trade(c[e1], S1, sig, sig1, hold, min(held, hold), mny, put, 0.15, 0.6)
        rows.append(rec)
    E = pd.DataFrame(rows)
    save(E, "merger_events.pkl")
    sysE = E[E.src == "systematic"]
    out = {"n": int(len(E)), "n_broke": int(E.broke.sum()), "sys_n": int(len(sysE)), "sys_break_rate": round(float(sysE.broke.mean()) * 100, 1),
           "break_drop_vs_pre_mean": round(float(E[E.broke].break_vs_pre.mean()) * 100, 1),
           "break_ret_from_entry": round(float(E[E.broke].ret_end.mean()) * 100, 1),
           "complete_ret_from_entry": round(float(E[~E.broke].ret_end.mean()) * 100, 1),
           "rv_post_med": round(float(E.rv_post.median()) * 100, 1), "rv_pre_med": round(float(E.rv_pre.median()) * 100, 1)}
    # implied break probability (cash deals): p = (offer - P) / (offer - P_fallback), fallback = unaffected pre-deal price
    if "spread" in E:
        off = E.entry * (1 + E.spread)
        E["p_impl"] = ((off - E.entry) / (off - E.pre)).where(off - E.pre > 0.02 * off).clip(0, 1)
        # sample over-represents breaks (all hand-found breaks + mostly large completed deals): reweight to a base rate
        nb, nc = E.broke.sum(), (~E.broke).sum()
        for br in (0.06, 0.10):
            w = np.where(E.broke, br / (nb / len(E)), (1 - br) / (nc / len(E)))
            E[f"w{int(br * 100)}"] = w
        cal = []
        q = E.dropna(subset=["p_impl"]).copy()
        q["pb"] = pd.cut(q.p_impl, [-0.01, 0.05, 0.10, 0.20, 0.40, 1.0], labels=["<5%", "5-10%", "10-20%", "20-40%", ">40%"])
        for k, g in q.groupby("pb"):
            if len(g) == 0:
                continue
            cal.append({"implied": str(k), "n": int(len(g)), "implied_mean": round(float(g.p_impl.mean()) * 100, 1),
                        "realized_raw": round(float(g.broke.mean()) * 100, 1),
                        "realized_w6": round(float(np.average(g.broke, weights=g.w6)) * 100, 1),
                        "realized_w10": round(float(np.average(g.broke, weights=g.w10)) * 100, 1)})
        out["calibration"] = cal
    cs = E[E.spread.notna()].copy() if "spread" in E else pd.DataFrame()
    if len(cs):
        cs["sb"] = pd.cut(cs.spread, [-1, 0.02, 0.05, 0.10, 0.20, 9], labels=["<2%", "2-5%", "5-10%", "10-20%", ">20%"])
        out["by_spread"] = {str(k): {"n": int(len(g)), "break_rate": round(float(g.broke.mean()) * 100, 1),
                                     "sys_break_rate": round(float(g[g.src == "systematic"].broke.mean()) * 100, 1) if (g.src == "systematic").any() else None,
                                     "ret_end": round(float(g.ret_end.mean()) * 100, 1),
                                     **{c: round(float(g[c].mean()) * 100, 0) for c in g.columns if c.endswith("_k2.5")}}
                            for k, g in cs.groupby("sb") if len(g)}
    oc = [c for c in E.columns if "_k" in c]
    out["options_all"] = {c: round(float(E[c].mean()) * 100, 0) for c in oc}
    out["options_w10"] = {c: round(float(np.average(E[c].fillna(-1), weights=E.w10)) * 100, 0) for c in oc} if "w10" in E else {}
    out["options_sys"] = {c: (round(float(sysE[c].mean()) * 100, 0), round(float((sysE[c] > 0).mean()) * 100, 0)) for c in oc}
    results_update("mergers", out)
    print(json.dumps(out, indent=1, default=str))


def sp500():
    S = pd.read_csv(RAW / "sp500_adds.csv")
    S["ann"] = pd.to_datetime(S.announcement_date, errors="coerce")
    S["eff"] = pd.to_datetime(S.effective_date, errors="coerce")
    S["ticker"] = S.ticker.astype(str).str.upper().str.strip()
    S = S.dropna(subset=["ann"])
    px = load_daily(list(S.ticker.unique()) + ["SPY"])
    spy = px["SPY"].adj
    rows = []
    for _, e in S.iterrows():
        d = px.get(e.ticker)
        if d is None or len(d) < 30:
            continue
        idx, a = d.index, d.adj.values
        m = spy.reindex(idx).ffill().values
        i = _tday(idx, e.ann, after=True)             # announced after the close: reaction next day
        if i is None or i < 2 or abs((idx[i] - e.ann).days) > 5 or i + 21 >= len(a):
            continue
        je = _tday(idx, e.eff) if pd.notna(e.eff) else None
        x = lambda j0, j1: (a[j1] / a[j0] - 1) - (m[j1] / m[j0] - 1)
        rec = {"ticker": e.ticker, "date": idx[i], "react": x(i - 1, i)}
        if je is not None and je > i:
            rec["to_eff"] = x(i, je - 1)
            if je + 20 < len(a):
                rec["post_eff20"] = x(je - 1, je + 20)
        rec["d1_20"] = x(i, i + 20)
        rows.append(rec)
    E = pd.DataFrame(rows)
    out = {"n": int(len(E))}
    for c in ("react", "to_eff", "post_eff20", "d1_20"):
        if c in E:
            out[c] = (round(float(E[c].mean()) * 100, 2), round(float(E[c].median()) * 100, 2), round(float(tstat(E[c])), 2))
    for era, g in E.groupby(np.where(E.date.dt.year <= 2019, "2015-19", "2020+")):
        out[era] = {c: round(float(g[c].mean()) * 100, 2) for c in ("react", "to_eff", "post_eff20", "d1_20") if c in g}
        out[era]["n"] = int(len(g))
    results_update("sp500", out)
    print(out)


# =====================================================================================  9. LIVE CHAINS + SCREENS
def chain_info(tk, event_date=None, max_exp=8):
    """yfinance live chain -> per-expiry ATM straddle, IV, spread, OI/volume; event-implied move from the term kink."""
    import yfinance as yf
    try:
        t = yf.Ticker(tk)
        exps = list(t.options)[:max_exp]
        fi = t.fast_info
        S = float(fi["last_price"])
        try:
            mcap = float(fi.market_cap or np.nan)
        except Exception:
            mcap = np.nan
    except Exception as e:
        return {"ticker": tk, "err": str(e)[:80]}
    rows = []
    for ex in exps:
        try:
            ch = t.option_chain(ex)
        except Exception:
            continue
        c, p = ch.calls, ch.puts
        if c.empty or p.empty:
            continue
        k = c.strike.iloc[(c.strike - S).abs().argmin()]
        cc, pp = c[c.strike == k].iloc[0], p[p.strike == k]
        if pp.empty:
            continue
        pp = pp.iloc[0]
        cm = (cc.bid + cc.ask) / 2 if cc.ask > 0 else cc.lastPrice
        pm = (pp.bid + pp.ask) / 2 if pp.ask > 0 else pp.lastPrice
        T = max((pd.Timestamp(ex) + pd.Timedelta(hours=16) - TODAY - pd.Timedelta(hours=12)).days, 0.5) / 365
        sp = np.nanmean([(cc.ask - cc.bid) / cm if cm > 0 else np.nan, (pp.ask - pp.bid) / pm if pm > 0 else np.nan])
        rows.append({"exp": ex, "T": T, "K": k, "straddle": cm + pm, "move": (cm + pm) / S, "iv": np.nanmean([cc.impliedVolatility, pp.impliedVolatility]),
                     "spread": sp, "oi": int(np.nansum([cc.openInterest, pp.openInterest])), "vol": int(np.nansum([cc.volume, pp.volume])),
                     "put_ask": pp.ask, "call_ask": cc.ask})
        time.sleep(0.15)
    out = {"ticker": tk, "spot": S, "mcap": mcap, "exps": rows}
    if rows and event_date is not None:
        ev = pd.Timestamp(event_date)
        post = [r for r in rows if pd.Timestamp(r["exp"]) >= ev]
        pre = [r for r in rows if pd.Timestamp(r["exp"]) < ev]
        if post:
            r2 = post[0]
            out["post_exp"], out["post_move"], out["post_iv"], out["post_spread"], out["post_oi"] = r2["exp"], r2["move"], r2["iv"], r2["spread"], r2["oi"]
            # base (non-event) vol: pre-event expiry IV if any; else solve from two post-event expiries
            # (s1^2 T1 = b^2 T1 + e^2 ; s2^2 T2 = b^2 T2 + e^2)
            if pre:
                b2 = pre[-1]["iv"] ** 2
            elif len(post) > 1 and post[1]["T"] > r2["T"] + 0.01:
                b2 = (post[1]["iv"] ** 2 * post[1]["T"] - r2["iv"] ** 2 * r2["T"]) / (post[1]["T"] - r2["T"])
            else:
                b2 = np.nan
            if np.isfinite(b2):
                b2 = max(b2, 0.0)
                ev_var = r2["iv"] ** 2 * r2["T"] - b2 * r2["T"]
                out["event_sd"] = float(np.sqrt(ev_var)) if ev_var > 0 else 0.0
                out["event_absmove"] = 0.8 * out["event_sd"]
                out["base_iv"] = float(np.sqrt(b2))
    return out


def screen_fda():
    U = pd.read_csv(RAW / "fda_upcoming.csv")
    U["event_date"] = pd.to_datetime(U.event_date, errors="coerce")
    U = U[(U.event_date >= TODAY) & (U.event_date <= TODAY + pd.Timedelta(days=200))]
    E = load("fda_events.pkl")
    rows = []
    for _, u in U.iterrows():
        tk = str(u.ticker).upper().strip()
        ci = chain_info(tk, u.event_date)
        r = {"ticker": tk, "drug": str(u.drug)[:40], "date": u.event_date.date(), "first": u.first_approval, "notes": str(u.notes)[:60]}
        for k in ("spot", "mcap", "post_exp", "post_move", "post_iv", "base_iv", "event_absmove", "post_spread", "post_oi"):
            r[k] = ci.get(k)
        # historical analog: same first-approval status, E|move| at 25% CRL base rate
        g = E[E["first"] == ("yes" if str(u.first_approval).lower() == "yes" else "no")] if "first" in E else E
        if len(g) < 20:
            g = E
        r["analog_abs"] = 0.75 * g[~g.crl].move.abs().mean() + 0.25 * g[g.crl].move.abs().mean()
        r["analog_crl_drop"] = g[g.crl].move.median()
        rows.append(r)
    R = pd.DataFrame(rows)
    save(R, "screen_fda.pkl")
    print(R.round(3).to_string())
    results_update("screen_fda", R.round(4).to_dict("records"))
    return R


def screen_mergers():
    M = pd.read_csv(RAW / "merger_pending.csv")
    rows = []
    for _, m in M.iterrows():
        tk = str(m.target_ticker).upper().strip()
        ci = chain_info(tk, None, max_exp=6)
        S = ci.get("spot")
        offer = pd.to_numeric(m.offer_price_cash, errors="coerce")
        r = {"target": tk, "acq": m.acquirer_ticker, "cons": m.consideration, "offer_cash": offer, "exch": m.exchange_ratio, "spot": S,
             "close": m.expected_close, "risk": str(m.key_risk)[:70]}
        if str(m.consideration).strip() == "cash" and S and np.isfinite(offer):
            r["spread"] = offer / S - 1
        elif str(m.consideration).strip() in ("stock", "mixed") and isinstance(m.exchange_ratio, str) and S:
            mm = re.match(r"\s*([\d.]+)", m.exchange_ratio)
            acq = str(m.acquirer_ticker).upper().strip()
            if mm and acq and acq != "NAN":
                try:
                    import yfinance as yf
                    pa = float(yf.Ticker(acq).fast_info["last_price"])
                    val = float(mm.group(1)) * pa + (offer if np.isfinite(offer) else 0)
                    r["deal_value"] = val
                    r["spread"] = val / S - 1
                except Exception:
                    pass
        ex = ci.get("exps") or []
        if ex:
            e3 = min(ex, key=lambda x: abs(x["T"] - 0.25))
            r.update({"iv_3m": e3["iv"], "spread_3m": e3["spread"], "oi_3m": e3["oi"], "exp_3m": e3["exp"]})
        rows.append(r)
    R = pd.DataFrame(rows)
    save(R, "screen_mergers.pkl")
    print(R.round(3).to_string())
    results_update("screen_mergers", R.round(4).to_dict("records"))
    return R


def screen_legislation():
    U = pd.read_csv(RAW / "legislation_upcoming.csv")
    rows = []
    for _, u in U.iterrows():
        for tk in str(u.tickers).split(";")[:2]:
            tk = tk.strip().upper()
            if not re.fullmatch(r"[A-Z]{1,5}", tk):
                continue
            ci = chain_info(tk, None, max_exp=6)
            ex = ci.get("exps") or []
            r = {"ticker": tk, "event": str(u.event)[:70], "when": str(u.expected_date)[:40], "spot": ci.get("spot")}
            if ex:
                e1 = min(ex, key=lambda x: abs(x["T"] - 0.08))
                e3 = min(ex, key=lambda x: abs(x["T"] - 0.25))
                r.update({"iv_1m": e1["iv"], "iv_3m": e3["iv"], "move_3m": e3["move"], "spread_3m": e3["spread"], "oi_3m": e3["oi"]})
            rows.append(r)
    R = pd.DataFrame(rows)
    save(R, "screen_leg.pkl")
    print(R.round(3).to_string())
    results_update("screen_legislation", R.round(4).to_dict("records"))
    return R


def partB_earn(flag="s2", n_ctrl=1500, seed=3):
    """Variant: buy the put the day before the next earnings release (8-K Item 2.02) after a flag fires.
    Compares flagged names' earnings reactions with a random unflagged control (same months)."""
    df = load("bpanel.pkl")
    df["s2"], df["s3"] = df.score >= 2, df.score >= 3
    subs_ = fund("subs.pkl")
    E = _entries(df, flag)
    E = E.merge(df[["cik", "month", "ticker", "size"]], on=["cik", "month"])
    E["grp"] = "flag"
    rng = np.random.default_rng(seed)
    ctrl = df[(df.score == 0) & df.ticker.notna()].sample(n=min(n_ctrl, int((df.score == 0).sum())), random_state=seed)[["cik", "month", "ticker", "size"]]
    ctrl["grp"] = "ctrl"
    A = pd.concat([E, ctrl], ignore_index=True).dropna(subset=["ticker"])
    px = load_daily(list(A.ticker.unique()) + ["SPY"], name="daily_b.pkl")
    spy = px["SPY"].adj
    rows = []
    for _, e in A.iterrows():
        d = px.get(e.ticker)
        ed = [pd.Timestamp(x) for x in subs_.get(int(e.cik), {}).get("e202", [])]
        start = e.month.end_time.normalize()
        nxt = [x for x in ed if start < x <= start + pd.Timedelta(days=100)]
        if d is None or not nxt or len(d) < 80:
            continue
        idx = d.index
        i = _tday(idx, nxt[0])
        if i is None or i < 61 or i + 22 >= len(d) or abs((idx[i] - nxt[0]).days) > 4:
            continue
        a, c = d.adj.values, d.close.values
        m = spy.reindex(idx).ffill().values
        ip = i - 1                                    # 8-K 2.02 usually after close or pre-open: window prev close -> close day+1
        lr = np.diff(np.log(a))
        rv = np.nanstd(lr[ip - 60:ip]) * np.sqrt(252)
        mv = a[i + 1] / a[ip] - 1 - (m[i + 1] / m[ip] - 1)
        rec = {"grp": e.grp, "size": e["size"], "month": e.month, "move2d": mv, "x20": a[ip + 21] / a[ip] - 1 - (m[ip + 21] / m[ip] - 1), "rv": rv}
        sp = 0.20 if e["size"] == "300M-2B" else 0.10
        for k in (1.2, 1.5):
            S1 = c[ip] * a[ip + 14] / a[ip]
            rec[f"put30_k{k}"] = opt_trade(c[ip], S1, k * rv, rv, 30, 20, 1.0, True, sp, 0.5)
        rows.append(rec)
    R = pd.DataFrame(rows)
    out = {}
    for (g, per), x in R.groupby(["grp", np.where(R.month <= IS1, "IS", "OOS")]):
        out[f"{g}_{per}"] = {"n": int(len(x)), "move2d": round(float(x.move2d.mean()) * 100, 2), "move2d_t": round(float(tstat(x.move2d)), 2),
                             "x20": round(float(x.x20.mean()) * 100, 2), "x20_t": round(float(tstat(x.x20)), 2),
                             "neg_big": round(float((x.move2d <= -0.10).mean()) * 100, 1),
                             "put30_k1.2": round(float(x["put30_k1.2"].mean()) * 100, 1), "put30_k1.5": round(float(x["put30_k1.5"].mean()) * 100, 1),
                             "pop": round(float((x["put30_k1.2"] > 0).mean()) * 100, 1)}
    results_update(f"partB_earn_{flag}", out)
    print(json.dumps(out, indent=1))


def screen():
    """Part B current screen: top flagged $300M-$10B names in the latest month (statistical flags only)."""
    df = load("bpanel.pkl")
    fil = load("filings.pkl")
    last = df.month.max()
    d = df[df.month == last].copy()
    d["sicd"] = d.cik.map({c: r.get("sicd") for c, r in fil.items()})
    d["sic2"] = d.sic // 100
    peer = df[df.month == last].groupby(df.sic // 100).agg(peer_M=("M", "median"), peer_flag=("score", lambda x: (x >= 2).mean()))
    d = d.join(peer, on="sic2")
    d["flags"] = d[SCORE_FLAGS].apply(lambda r: ",".join(k for k, v in r.items() if v), axis=1)
    d = d.sort_values(["score", "M"], ascending=[False, False])
    top = d[d.score >= 2].head(40)
    rows = []
    for _, r in top.iterrows():
        tk = r.ticker
        ci = chain_info(tk, None, max_exp=10) if isinstance(tk, str) else {}
        ex = ci.get("exps") or []
        e4 = min(ex, key=lambda x: abs(x["T"] - 0.33)) if ex else None
        rows.append({"ticker": tk, "name": str(r["name"])[:28], "sector": str(r.sicd)[:28], "mcap_B": round(r.mcap / 1e9, 2), "score": int(r.score),
                     "flags": r["flags"], "M": round(float(r.M), 2) if np.isfinite(r.M) else None, "peer_M": round(float(r.peer_M), 2) if np.isfinite(r.peer_M) else None,
                     "sh_g": round(float(r.sh_g) * 100, 0) if np.isfinite(r.sh_g) else None,
                     "exp": e4["exp"] if e4 else None, "iv": round(e4["iv"], 2) if e4 else None, "spread": round(e4["spread"], 3) if e4 else None,
                     "oi": e4["oi"] if e4 else None, "opt_vol": e4["vol"] if e4 else None,
                     "put_cost": round(e4["put_ask"] * 100, 0) if e4 else None, "spot": ci.get("spot")})
        if sum(1 for x in rows if x["exp"]) >= 20 and len(rows) >= 20:
            break
    R = pd.DataFrame(json.loads(json.dumps(rows, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o))))
    save(R, "screen_B.pkl")
    print("month", last, "flagged>=2:", int((d.score >= 2).sum()), ">=3:", int((d.score >= 3).sum()), "of", len(d))
    print(R.to_string())
    results_update("screen_B", {"month": str(last), "n_universe": int(len(d)), "n_ge2": int((d.score >= 2).sum()),
                                "n_ge3": int((d.score >= 3).sum()), "rows": R.to_dict("records")})


def econ():
    """option economics summary + 1-year bankroll odds for the representative strategy of each part."""
    out = {}
    A = load("partA_events.pkl")
    A["typ"] = A["type"].str.extract(r"(fraud|valuation|mixed)", expand=False).fillna("other")
    A["oos"] = A.date.dt.year >= 2019
    # contract cost: ATM put on the real price, IV = k x post-event RV, +5% half-spread
    A["cost182"] = [bs(p, p, 0.5, max(0.25, 1.25 * s), True) * 105 for p, s in zip(A.price0, A.rv_post)]
    A["cost365"] = [bs(p, p, 1.0, max(0.25, 1.0 * s), True) * 105 for p, s in zip(A.price0, A.rv_post)]
    strategies = {
        "A day-1 put 6m ATM, all reports, IV 1.25xRV": (A[A.oos]["put_182_180_100_k1.25_s10"], A.cost182.median(), 60),
        "A day-1 put 6m ATM, fraud only, IV 1.25xRV": (A[A.oos & (A.typ == "fraud")]["put_182_180_100_k1.25_s10"], A[A.typ == "fraud"].cost182.median(), 25),
        "A day-1 put 1y ATM, fraud only, IV 1.0xRV (optimistic)": (A[A.oos & (A.typ == "fraud")]["put_365_360_100_k1.0_s10"], A[A.typ == "fraud"].cost365.median(), 25),
    }
    T = load("partB_trades.pkl")
    for col, lab in (("s4", "B score>=4"), ("restate", "B restatement (4.02)"), ("late", "B late filing (NT)"), ("s3", "B score>=3")):
        R = T[col]
        R = R[R.month >= OOS0]
        strategies[f"{lab} -> 6m ATM put, IV 1.2xRV"] = (R["p6_atm_k1.2"], R.cost6.median(), min(40, len(R) / 7.5))
        strategies[f"{lab} -> 6m ATM put, IV 1.0xRV (optimistic)"] = (R["p6_atm_k1.0"], R.cost6.median(), min(40, len(R) / 7.5))
    E = load("fda_events.pkl")
    share = E.crl.mean()
    w = np.where(E.crl, 0.25 / share, 0.75 / (1 - share))
    rng = np.random.default_rng(5)
    draw = rng.choice(E.move.values, size=4000, p=w / w.sum())
    for M in (0.20, 0.30):
        sig = M / 0.8 * np.sqrt(365 / 7)
        po = bs(1, 0.8, 7 / 365, sig * 1.1, True) * 1.15
        pst = (bs(1, 1, 7 / 365, sig, True) + bs(1, 1, 7 / 365, sig, False)) * 1.08
        strategies[f"C FDA 20%-OTM put, implied move {int(M * 100)}%"] = (pd.Series(np.maximum(-0.2 - draw, 0) / po - 1), po * 100 * 15, 20)
        strategies[f"C FDA straddle, implied move {int(M * 100)}%"] = (pd.Series(np.abs(draw) / pst - 1), pst * 100 * 15, 20)
    for name, (r, cost, n) in strategies.items():
        r = pd.Series(r).dropna()
        out[name] = {"n": int(len(r)), "ev": round(float(r.mean()) * 100, 1), "median": round(float(r.median()) * 100, 0),
                     "pop": round(float((r > 0).mean()) * 100, 0), "t": round(float(tstat(r)), 2), "cost": round(float(cost), 0),
                     "trades_yr": round(float(n), 0), "min_capital_20pct": round(float(cost) / 0.2, -1),
                     "bank": bankroll(r.values, float(cost), n)}
        b = out[name]["bank"]
        print(f"{name:58s} n={len(r):4d} EV {r.mean() * 100:+6.1f}% med {r.median() * 100:+5.0f}% PoP {(r > 0).mean() * 100:3.0f}% cost ${cost:5.0f} "
              + " ".join(f"${k}:{v['p_grow'] * 100:.0f}%/{v['p_ruin'] * 100:.0f}%" for k, v in b.items()))
    results_update("econ", out)


def partC():
    for fn in (fda, legislation, mergers, sp500):
        try:
            fn()
        except Exception as ex:
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    fn = globals().get(cmd.replace("-", "_"))
    if not callable(fn):
        print(__doc__)
        sys.exit(1)
    fn()
