#!/usr/bin/env python3
"""Research: does PEER-RELATIVE fundamental valuation predict returns / collapses in $300M-$10B US stocks?
Owner idea: find under/over-valued small/mid caps vs direct competitors (Fiserv collapse, Alkami "undervalued"),
go long options (calls on cheap, puts on rich). Data: SEC EDGAR XBRL (point-in-time via the 'filed' date).

  python3 agents/options-100/bot/research_fundamental.py <step>     (or: all)
  steps, in order:
    edgar      parse companyfacts.zip -> quarterly point-in-time facts (earliest 'filed' value per period)
    subs       parse submissions.zip -> SIC, 10-K/10-Q list, 8-K item 2.02 (earnings) dates
    prices_yf  yfinance monthly stats for every currently listed ticker (SEC company_tickers_exchange.json)
    prices_hf  HuggingFace paperswithbacktest daily bars (includes DELISTED symbols) -> monthly stats
    insiders   SEC Form 3/4/5 structured data -> monthly open-market insider buys/sells per issuer
    tickers    CIK -> price source (listed: yfinance; delisted: 10-K/10-Q doc-name / XBRL-instance prefix vs HF symbols)
    panel      monthly point-in-time panel 2011-06..2026-10 (as-of merge on 'filed')
    coverage   survivorship: share of EDGAR filers in range (by public float) that have prices
    backtest   Part 1: peer-z quintile spreads, IS 2012-18 / OOS 2019+, size buckets, BH; collapse test (+vol-matched)
    robust     gem signal: by year, liquidity tiers, decile, survivors-only
    case       Part 2: Fiserv post-mortem + false positives; Alkami vs fintech peers + analogs
    screen     Part 3: today's top/bottom lists, live chains (3-6m + LEAPS), earnings dates, liquidity sample
    options    Part 4: 3/6/12-month calls & puts (RV x measured IV/RV, measured spreads), earnings variant, bankroll
    tables     print the markdown tables used in research/fundamental.md

Inputs (untrusted, parsed only, never executed) live in data/research_fund_raw/:
  companyfacts.zip, submissions.zip  (SEC bulk, UA header), company_tickers_exchange.json,
  pwb/train-YYYY-MM.parquet  (HuggingFace paperswithbacktest/Stocks-Daily-Price: daily bars incl. DELISTED symbols)
Caches: data/research_fund_*.pkl / .json (data/ is gitignored).
"""
import socket as _sk
_gai = _sk.getaddrinfo
_sk.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, _sk.AF_INET, *a, **k)   # IPv6 times out on this machine
import sys, json, math, pickle, time, re, zipfile, warnings, datetime as dt
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "research_fund_raw"
UA = {"User-Agent": "options-100 research trevorchico@gmail.com"}
TODAY = pd.Timestamp("2026-10-14")
CAP_LO, CAP_HI, CAP_MID = 3e8, 1e10, 2e9


def P(name):
    return DATA / f"research_fund_{name}"


def save(obj, name):
    tmp = P(name + ".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(obj, f, protocol=4)
    tmp.replace(P(name))


def load(name):
    with open(P(name), "rb") as f:
        return pickle.load(f)


# =====================================================================================  1. EDGAR
# concept groups (us-gaap). Flows -> quarterly discrete values; instants -> balance at quarter end.
FLOW = {
    "rev": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet", "SalesRevenueServicesNet",
            "RevenuesNetOfInterestExpense", "RegulatedAndUnregulatedOperatingRevenue", "OperatingLeasesIncomeStatementLeaseRevenue"],
    "cogs": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices",
             "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization"],
    "gp": ["GrossProfit"],
    "ebit": ["OperatingIncomeLoss"],
    "ni": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "capsw": ["PaymentsToDevelopSoftware", "PaymentsForSoftware"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet"],
    "amort": ["AmortizationOfIntangibleAssets"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "restr": ["RestructuringCharges", "RestructuringCosts"],
    "intexp": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
    "dilsh": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "bassh": ["WeightedAverageNumberOfSharesOutstandingBasic"],
    "nii": ["InterestIncomeExpenseNet", "InterestIncomeExpenseAfterProvisionForLoanLoss"],
    "nonii": ["NoninterestIncome"],
}
INST = {
    "assets": ["Assets"], "ca": ["AssetsCurrent"], "cl": ["LiabilitiesCurrent"], "liab": ["Liabilities"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash"],
    "sti": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "ltd": ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", "DebtLongtermAndShorttermCombinedAmount"],
    "ltdnc": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "ConvertibleNotesPayableNoncurrent",
              "SeniorLongTermNotes", "LongTermNotesPayable", "LongTermLineOfCredit"],
    "ltdc": ["LongTermDebtCurrent", "DebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "stb": ["ShortTermBorrowings", "CommercialPaper", "LinesOfCreditCurrent"],
    "recv": ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
    "inv": ["InventoryNet"],
}
# for "max" groups take the max across concepts per period (totals >= components); others take first-priority
MAXGROUP = {"rev", "cogs", "ltdnc", "ltdc", "stb", "cash", "sti"}
D = np.timedelta64(1, "D")
FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT", "10-KT/A", "10-QT"}


def _d(s):
    return np.datetime64(s, "D")


def _flows(facts, additive=True):
    """facts: list of (start, end, val, filed) -> {end: (val, filed)} quarterly discrete values, earliest-filed
    (no restatement look-ahead). Missing quarters derived from YTD differences (forward: 9M-6M; backward: 6M-Q2)."""
    best = {}
    for s, e, v, fd in facts:
        k = (s, e)
        if k not in best or fd < best[k][1]:
            best[k] = (v, fd)
    items = [(_d(s), _d(e), v, _d(fd)) for (s, e), (v, fd) in best.items()]
    q = {}
    for S, E, v, F in items:
        dur = (E - S) / D
        if 75 <= dur <= 105 and (E not in q or F < q[E][1]):
            q[E] = (v, F)
    if not additive:          # share counts: Q4 proxy = annual weighted average
        for S, E, v, F in items:
            if E not in q and (E - S) / D > 105:
                q[E] = (v, F)
        return q
    derived = {}
    for S, E, v, F in items:
        for S2, E2, v2, F2 in items:
            if (S2, E2) == (S, E):
                continue
            if abs((S2 - S) / D) <= 4 and E2 < E:            # same start: (E2, E] segment
                seg = (E - E2) / D
                if 75 <= seg <= 105:
                    c = (v - v2, max(F, F2))
                    if E not in derived or c[1] < derived[E][1]:
                        derived[E] = c
            if abs((E2 - E) / D) <= 4 and S2 > S:            # same end: [S, S2) segment
                seg = (S2 - S) / D
                if 75 <= seg <= 105:
                    e1 = S2 - D
                    c = (v - v2, max(F, F2))
                    if e1 not in derived or c[1] < derived[e1][1]:
                        derived[e1] = c
    for E, c in derived.items():
        if not any(abs((E - k) / D) <= 6 for k in q):
            q[E] = c
    return q


def _inst(facts):
    best = {}
    for s, e, v, fd in facts:
        E, F = _d(e), _d(fd)
        if E not in best or F < best[E][1]:
            best[E] = (v, F)
    return best


def _parse_one(args):
    zpath, name = args
    try:
        with zipfile.ZipFile(zpath) as z:
            d = json.loads(z.read(name))
    except Exception:
        return None
    facts = d.get("facts", {})
    g = facts.get("us-gaap")
    if not g:
        return None
    cik = int(d.get("cik") or int(name[3:13]))
    dei = facts.get("dei", {})
    out = {"cik": cik, "name": d.get("entityName")}
    # cover-page shares (sum classes within one filing) and public float
    sh = defaultdict(set)
    for f in dei.get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", []):
        sh[(f["accn"], f["filed"], f["end"])].add(f["val"])
    out["cover"] = sorted((fd, e, float(sum(v))) for (a, fd, e), v in sh.items())
    pf = defaultdict(set)
    for f in dei.get("EntityPublicFloat", {}).get("units", {}).get("USD", []):
        pf[(f["accn"], f["filed"], f["end"])].add(f["val"])
    out["float"] = sorted((fd, e, float(sum(v))) for (a, fd, e), v in pf.items())
    if not out["float"] and not out["cover"]:
        return None
    if max([x[2] for x in out["float"] if x[0] >= "2010"] + [0]) < 1e8 and not any(x[0] >= "2011" for x in out["cover"]):
        return None

    def get(concept, unit="USD"):
        c = g.get(concept)
        if not c:
            return []
        u = c.get("units", {}).get(unit) or []
        return [(f.get("start"), f["end"], float(f["val"]), f["filed"]) for f in u if f.get("form", "") in FORMS]

    cols = {}
    for key, concepts in FLOW.items():
        unit = "shares" if key in ("dilsh", "bassh") else "USD"
        per = [_flows([x for x in get(c, unit) if x[0]], additive=unit == "USD") for c in concepts]
        cols[key] = _combine(per, key in MAXGROUP)
    for key, concepts in INST.items():
        per = [_inst(get(c)) for c in concepts]
        cols[key] = _combine(per, key in MAXGROUP)
    # quarter grid = union of ni / rev quarter ends, snapped
    ends = sorted(set(cols["ni"]) | set(cols["rev"]))
    if len(ends) < 4:
        return None
    grid = []
    for E in ends:
        if grid and (E - grid[-1]) / D < 20:
            continue
        grid.append(E)
    rows = []
    for E in grid:
        r = {"qend": E}
        for key, m in cols.items():
            hit = m.get(E)
            if hit is None:
                for dd in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7):
                    hit = m.get(E + dd * D)
                    if hit is not None:
                        break
            if hit is not None:
                r[key] = hit[0]
                r[key + "_f"] = hit[1]
        rows.append(r)
    q = pd.DataFrame(rows)
    q = q[q.qend >= np.datetime64("2008-06-30")]
    if len(q) < 4:
        return None
    for c in q.columns:
        if c.endswith("_f") or c == "qend":
            q[c] = pd.to_datetime(q[c])
        else:
            q[c] = q[c].astype("float64")
    out["q"] = q.reset_index(drop=True)
    return out


def _combine(per, use_max):
    res = {}
    if use_max:
        for m in per:
            for E, (v, F) in m.items():
                if E not in res or v > res[E][0]:
                    res[E] = (v, F)
    else:
        for m in per:          # priority order: first concept wins per period
            for E, (v, F) in m.items():
                if E not in res:
                    res[E] = (v, F)
    return res


def edgar():
    from multiprocessing import Pool
    t0 = time.time()
    zf = RAW / "companyfacts.zip"
    names = [n for n in zipfile.ZipFile(zf).namelist() if n.endswith(".json")]
    print("companyfacts files", len(names))
    res = {}
    with Pool(7) as pool:
        for i, r in enumerate(pool.imap_unordered(_parse_one, [(str(zf), n) for n in names], chunksize=16)):
            if r:
                res[r["cik"]] = r
            if i % 2000 == 0:
                print(f"  {i}/{len(names)} kept {len(res)} {time.time() - t0:.0f}s", flush=True)
    save(res, "facts.pkl")
    print("facts kept", len(res), f"{time.time() - t0:.0f}s")


# =====================================================================================  2. prices
def current_map():
    """CIK -> primary listed ticker (first non-OTC row per CIK in SEC's company_tickers_exchange.json)."""
    d = json.load(open(RAW / "company_tickers_exchange.json"))
    m = {}
    for cik, name, tk, ex in d["data"]:
        if ex in ("Nasdaq", "NYSE", "CBOE") and cik not in m and tk:
            m[int(cik)] = tk
    return m


def _monthly(df):
    """daily frame with close (split-adj), adj (total-return adj), vol, split -> monthly stats."""
    df = df.dropna(subset=["adj"])
    df = df[df.adj > 0]
    if len(df) < 30:
        return None
    # unadjusted close = split-adjusted close x cumulative product of later splits
    sp = df["split"].fillna(0).replace(0, 1.0)
    fut = sp[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
    raw = df["close"] * fut
    r = np.log(df.adj).diff()
    dv = df["close"] * df["vol"]
    g = df.index.to_period("M")
    out = pd.DataFrame({
        "adj": df.adj.groupby(g).last(), "raw": raw.groupby(g).last(),
        "amin": df.adj.groupby(g).min(), "last": pd.Series(df.index, index=df.index).groupby(g).last(),
        "rv": r.groupby(g).std() * np.sqrt(252), "n": r.groupby(g).count(),
        "dvol": dv.groupby(g).median()})
    return out.astype({"adj": "float32", "raw": "float32", "amin": "float32", "rv": "float32", "dvol": "float32"})


def prices_yf():
    import yfinance as yf
    cm = current_map()
    tks = sorted(set(cm.values()))
    out = load("px_yf.pkl") if P("px_yf.pkl").exists() else {}
    todo = [t for t in tks if t not in out]
    print("current tickers", len(tks), "todo", len(todo), flush=True)
    for i in range(0, len(todo), 80):
        b = todo[i:i + 80]
        for attempt in range(3):
            try:
                df = yf.download(b, start="2010-06-01", end="2026-10-15", auto_adjust=False, actions=True,
                                 progress=False, group_by="ticker", threads=True, timeout=60)
                break
            except Exception as e:
                print("retry", e); time.sleep(5)
        else:
            continue
        for t in b:
            try:
                x = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                x = pd.DataFrame({"close": x["Close"], "adj": x["Adj Close"], "vol": x["Volume"],
                                  "split": x["Stock Splits"] if "Stock Splits" in x else 0.0})
                m = _monthly(x)
            except Exception:
                m = None
            out[t] = m
        if (i // 80) % 5 == 0:
            save(out, "px_yf.pkl")
            print(f"  {i + len(b)}/{len(todo)} ok {sum(v is not None for v in out.values())}", flush=True)
    save(out, "px_yf.pkl")
    print("done", sum(v is not None for v in out.values()))


def prices_hf():
    """HuggingFace paperswithbacktest daily bars (includes delisted symbols) -> per-(symbol, month) stats."""
    files = sorted((RAW / "pwb").glob("train-*.parquet"))
    parts = []
    for f in files:
        if f.name < "train-2010-06":
            continue
        df = pd.read_parquet(f, columns=["symbol", "date", "close", "volume", "adj_close"])
        df["date"] = pd.to_datetime(df["date"])
        df = df[(df.adj_close > 0) & df.close.notna()].sort_values(["symbol", "date"])
        df["lr"] = np.log(df.adj_close).groupby(df.symbol).diff()
        df["dv"] = df.close * df.volume
        g = df.groupby("symbol")
        m = pd.DataFrame({"adj": g.adj_close.last(), "raw": g.close.last(), "amin": g.adj_close.min(), "last": g.date.last(),
                          "rv": g.lr.std() * np.sqrt(252), "n": g.lr.count() + 1, "dvol": g.dv.median()})
        m["month"] = pd.Period(f.name[6:13], "M")
        parts.append(m.reset_index())
    hf = pd.concat(parts, ignore_index=True)
    for c in ("adj", "raw", "amin", "rv", "dvol"):
        hf[c] = hf[c].astype("float32")
    save(hf, "px_hf.pkl")
    print("hf rows", len(hf), "symbols", hf.symbol.nunique(), hf.month.min(), hf.month.max())


_ZH = {}


def _zip(path):
    if path not in _ZH:
        _ZH[path] = zipfile.ZipFile(path)
    return _ZH[path]


def _sub_full(args):
    zpath, cik = args
    try:
        z = _zip(zpath)
        d = json.loads(z.read(f"CIK{cik:010d}.json"))
        blocks = [d.get("filings", {}).get("recent", {})]
        for x in d.get("filings", {}).get("files", []):
            try:
                blocks.append(json.loads(z.read(x["name"])))
            except Exception:
                pass
    except Exception:
        return None
    per, e202, dl = [], [], []
    for r in blocks:
        n = len(r.get("form", []))
        for i in range(n):
            f = r["form"][i]
            fd = r["filingDate"][i]
            if f in ("10-K", "10-Q", "10-KT"):
                per.append((f, fd, r.get("reportDate", [""] * n)[i], r["accessionNumber"][i], r.get("primaryDocument", [""] * n)[i]))
            elif f == "8-K" and "2.02" in (r.get("items", [""] * n)[i] or ""):
                e202.append(fd)
            elif f in ("25-NSE", "25", "15-12B", "15-12G", "15-15D"):
                dl.append((f, fd))
    per.sort(key=lambda x: x[1])
    return {"cik": cik, "name": d.get("name"), "sic": d.get("sic"), "sicd": d.get("sicDescription"),
            "tickers": d.get("tickers", []), "exch": d.get("exchanges", []), "former": d.get("formerNames", []),
            "per": per, "e202": sorted(set(e202)), "delist": sorted(dl)}


def subs():
    facts = load("facts.pkl")
    zs = RAW / "submissions.zip"
    have = set(n for n in _zip(str(zs)).namelist())
    ciks = [c for c in facts if f"CIK{c:010d}.json" in have]
    out = {}
    for i, c in enumerate(ciks):     # single process: a 1M-entry zip directory costs ~400MB per opener
        r = _sub_full((str(zs), c))
        if r:
            out[r["cik"]] = r
        if i % 2000 == 0:
            print("  subs", i, len(ciks), flush=True)
    save(out, "subs.pkl")
    print("subs", len(out))


TICK_RE = [re.compile(r"^([a-z]{1,5})-(?:19|20)\d{6}"), re.compile(r"^([a-z]{2,5})(?:19|20)\d{6}x?10[kq]"),
           re.compile(r"^([a-z]{2,5})-?10[kq]_?(?:19|20)\d{2}"), re.compile(r"^([a-z]{2,5})[-_](?:10[kq]|q\d)")]


def _prefixes(docs):
    c = defaultdict(int)
    for d in docs:
        d = (d or "").lower()
        for rx in TICK_RE:
            m = rx.match(d)
            if m:
                c[m.group(1).upper()] += 1
                break
    return c


def _instance_prefix(cik, accn):
    import urllib.request
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/index.json"
    try:
        j = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
    except Exception:
        return None
    for it in j.get("directory", {}).get("item", []):
        m = re.match(r"^([a-z]{1,5})-(?:19|20)\d{6}\.xml$", it.get("name", "").lower())
        if m:
            return m.group(1).upper()
    return None


def tickers():
    """CIK -> price source. Current (listed today): yfinance ticker. Others (delisted / now OTC): HF symbol whose bars
    overlap the company's filing years, chosen from the 10-K/10-Q document-name or XBRL-instance prefix,
    validated by cover shares x price vs reported public float."""
    facts, subs_ = load("facts.pkl"), load("subs.pkl")
    hf = load("px_hf.pkl")
    cur = current_map()
    yfp = load("px_yf.pkl")
    sym_months = hf.groupby("symbol").month.agg(["min", "max", "count"])
    hf_idx = hf.set_index(["symbol", "month"]).raw
    out = {}
    need = []
    for cik, f in facts.items():
        sb = subs_.get(cik, {})
        if cik in cur and yfp.get(cur[cik]) is not None:
            out[cik] = ("yf", cur[cik])
            continue
        per = [x for x in sb.get("per", []) if x[1] >= "2010-06-01"]
        if not per:
            continue
        if max([x[2] for x in f["float"] if x[0] >= "2010"] + [0]) < 1.5e8:     # never big enough for the $300M+ universe
            continue
        need.append(cik)
    print("current mapped", len(out), "need HF mapping", len(need))
    cache = load("instpref.pkl") if P("instpref.pkl").exists() else {}
    fails = defaultdict(int)
    for k, cik in enumerate(need):
        sb = subs_[cik]
        per = [x for x in sb["per"] if x[1] >= "2010-06-01"]
        cands = _prefixes([x[4] for x in per])
        for t in sb.get("tickers", []):
            cands[t.upper().replace(".", "-")] += 5
        if not any(c in sym_months.index for c in cands):
            if cik not in cache:
                ks = [x for x in per if x[0] == "10-K"] or per
                cache[cik] = _instance_prefix(cik, ks[-1][3])
                time.sleep(0.12)
                if len(cache) % 200 == 0:
                    save(cache, "instpref.pkl"); print("  instance lookups", len(cache), flush=True)
            if cache[cik]:
                cands[cache[cik]] += 1
        f0, f1 = pd.Period(per[0][1], "M"), pd.Period(per[-1][1], "M")
        best = None
        for c, w in sorted(cands.items(), key=lambda x: -x[1]):
            if c not in sym_months.index:
                fails["nosym"] += 1
                continue
            mm = sym_months.loc[c]
            ov = min(mm["max"], f1 + 3) - max(mm["min"], f0)
            span = (f1 - f0).n + 1
            if ov.n < 0.5 * span - 3:
                fails["overlap"] += 1
                continue
            # cover shares x price vs public float (float <= cap, typically 0.3-1.0 of cap)
            ok, chk = True, 0
            for fd, e, fl in facts[cik]["float"][-6:]:
                m = pd.Period(e[:7], "M")
                sh = [v for fd2, e2, v in facts[cik]["cover"] if abs((pd.Timestamp(fd2) - pd.Timestamp(e)).days) < 300]
                if not sh or (c, m) not in hf_idx.index or fl <= 0:
                    continue
                cap = sh[0] * float(hf_idx.loc[(c, m)])
                chk += 1
                if not (0.6 <= cap / fl <= 12):
                    ok = False
            if not ok:
                fails["float"] += 1
                continue
            best = c
            break
        if best:
            out[cik] = ("hf", best)
    save(cache, "instpref.pkl")
    save(out, "tickers.pkl")
    n_hf = sum(1 for v in out.values() if v[0] == "hf")
    print("mapped", len(out), "of which HF", n_hf, "unmapped", len(need) - n_hf, dict(fails))


# =====================================================================================  3. panel
def _contig(Q, k, lo, hi):
    dq = (Q.qend - Q.groupby("cik").qend.shift(k)).dt.days
    return (dq >= lo) & (dq <= hi)


def qfeatures(facts, subs_):
    keep = ["qend", "rev_f", "ni_f", "assets_f"]
    parts = []
    for cik, f in facts.items():
        q = f["q"]
        q = q[[c for c in q.columns if not c.endswith("_f") or c in keep]].copy()
        q["cik"] = cik
        parts.append(q)
    Q = pd.concat(parts, ignore_index=True).sort_values(["cik", "qend"]).reset_index(drop=True)
    for c in list(FLOW) + list(INST):
        if c not in Q:
            Q[c] = np.nan
    Q["avail"] = Q[["rev_f", "ni_f", "assets_f"]].max(axis=1)
    sic = {c: int(v["sic"]) if v.get("sic") not in (None, "") else -1 for c, v in subs_.items()}
    Q["sic"] = Q.cik.map(sic).fillna(-1).astype(int)
    fin = (Q.sic >= 6000) & (Q.sic < 6800)
    Q.loc[fin & Q.rev.isna(), "rev"] = Q.nii + Q.nonii.fillna(0)
    Q["gp"] = Q.gp.fillna(Q.rev - Q.cogs)
    Q["capt"] = Q.capex.fillna(0) + Q.capsw.fillna(0)
    Q["ebitda"] = Q.ebit + Q.da.fillna(Q.amort.fillna(0))
    Q["adjx"] = Q.sbc.fillna(0) + Q.amort.fillna(0) + Q.restr.fillna(0)
    d1 = Q.ltd.fillna(0) + Q.stb.fillna(0)
    d2 = Q.ltdnc.fillna(0) + Q.ltdc.fillna(0) + Q.stb.fillna(0)
    Q["debt"] = np.maximum(d1, d2)
    Q["cashx"] = Q.cash.fillna(0) + Q.sti.fillna(0)
    Q["shq"] = Q.dilsh.fillna(Q.bassh)
    g = Q.groupby("cik")
    c3 = _contig(Q, 3, 255, 300)
    for c in ("rev", "gp", "ebit", "ni", "cfo", "capt", "ebitda", "adjx", "sbc"):
        t = Q[c] + g[c].shift(1) + g[c].shift(2) + g[c].shift(3)
        if c in ("capt", "adjx"):
            t = Q[c] + g[c].shift(1).fillna(0) + g[c].shift(2).fillna(0) + g[c].shift(3).fillna(0)
        Q[c + "_t"] = t.where(c3)
    c4 = _contig(Q, 4, 340, 390)
    c2 = _contig(Q, 2, 160, 200)
    g = Q.groupby("cik")
    L4 = lambda c: g[c].shift(4).where(c4)
    # a missing 10-Q in companyfacts (e.g. ALKT Q1-26) breaks YTD differencing: carry cash-flow TTMs forward one quarter
    for c in ("cfo_t", "capt_t"):
        Q[c] = Q[c].fillna(g[c].shift(1).where(_contig(Q, 1, 75, 105)))
    Q["fcf_t"] = Q.cfo_t - Q.capt_t
    Q["g"] = (Q.rev_t / L4("rev_t") - 1).where(L4("rev_t") > 0)
    Q["yoyq"] = (Q.rev / L4("rev") - 1).where(L4("rev") > 0)
    Q["accel"] = Q.yoyq - g["yoyq"].shift(2).where(c2)
    Q["gm"] = (Q.gp_t / Q.rev_t).where(Q.rev_t > 0)
    Q["om"] = (Q.ebit_t / Q.rev_t).where(Q.rev_t > 0)
    g = Q.groupby("cik")
    Q["gm_chg"] = Q.gm - L4("gm")
    Q["om_chg"] = Q.om - L4("om")
    Q["gpa"] = Q.gp_t / Q.assets
    avgA = (Q.assets + L4("assets")) / 2
    Q["acc"] = (Q.ni_t - Q.cfo_t) / avgA
    Q["roa"] = Q.ni_t / Q.assets
    Q["lev"] = Q.debt / Q.assets
    Q["cr"] = Q.ca / Q.cl
    Q["aturn"] = Q.rev_t / Q.assets
    g = Q.groupby("cik")
    comp = pd.DataFrame({
        "f1": Q.roa > 0, "f2": Q.cfo_t > 0, "f3": Q.roa > L4("roa"), "f4": Q.cfo_t > Q.ni_t,
        "f5": Q.lev <= L4("lev"), "f6": Q.cr > L4("cr"), "f7": Q.shq <= L4("shq") * 1.005,
        "f8": Q.gm > L4("gm"), "f9": Q.aturn > L4("aturn")})
    avail_n = pd.DataFrame({"a1": Q.roa.notna(), "a2": Q.cfo_t.notna(), "a3": L4("roa").notna(), "a4": Q.cfo_t.notna() & Q.ni_t.notna(),
                            "a5": L4("lev").notna(), "a6": L4("cr").notna(), "a7": L4("shq").notna(), "a8": L4("gm").notna(),
                            "a9": L4("aturn").notna()}).sum(axis=1)
    Q["fscore"] = (comp.sum(axis=1) * 9 / avail_n.clip(lower=1)).where(avail_n >= 6)
    Q["dil"] = Q.shq / L4("shq") - 1
    Q["dso"] = (Q.recv / Q.rev_t * 365).where(Q.rev_t > 0)
    Q["dso_chg"] = Q.dso - L4("dso")
    Q["recv_g"] = (Q.recv / L4("recv") - 1) - Q.g
    Q["adjgap"] = (Q.adjx_t / Q.rev_t).where(Q.rev_t > 0)
    Q["adjgap_chg"] = Q.adjgap - L4("adjgap")
    Q["sbc_rev"] = (Q.sbc_t / Q.rev_t).where(Q.rev_t > 0)
    Q["g_l4"] = L4("g")
    Q["g_chg"] = Q.g - Q.g_l4
    cols = ["cik", "qend", "avail", "sic", "rev", "rev_t", "gp_t", "ebit_t", "ni_t", "cfo_t", "capt_t", "fcf_t", "ebitda_t", "sbc_t",
            "assets", "equity", "debt", "cashx", "recv", "shq", "g", "yoyq", "accel", "gm", "om", "gm_chg", "om_chg", "gpa", "acc",
            "fscore", "dil", "dso", "dso_chg", "recv_g", "adjgap", "adjgap_chg", "sbc_rev", "g_l4", "g_chg"]
    return Q[cols]


def _px_table(tick, facts, subs_):
    """long monthly price table keyed by cik: adj, raw, amin, rv, dvol (yf for listed, HF for delisted, truncated)."""
    yfp = load("px_yf.pkl")
    hf = load("px_hf.pkl")
    hf_by = {k: v for k, v in hf.groupby("symbol")}
    parts = []
    for cik, (src, t) in tick.items():
        if src == "yf":
            m = yfp.get(t)
            if m is None:
                continue
            m = m.copy()
            m.index = m.index.astype("period[M]")
        else:
            m = hf_by.get(t)
            if m is None:
                continue
            m = m.set_index("month")[["adj", "raw", "amin", "last", "rv", "n", "dvol"]].sort_index()
            per = [x for x in subs_[cik]["per"] if x[1] >= "2010-06-01"]
            f0, f1 = pd.Period(per[0][1], "M") - 15, pd.Period(per[-1][1], "M") + 6
            m = m[(m.index >= f0) & (m.index <= f1)]
            if len(m) < 3:
                continue
            # cut at first gap > 2 months (symbol reuse)
            gaps = np.where(np.diff(m.index.asi8) > 2)[0]
            if len(gaps):
                m = m.iloc[:gaps[0] + 1]
        m = m[["adj", "raw", "amin", "rv", "dvol", "n"]].copy()
        m["cik"] = cik
        m["src"] = src
        parts.append(m.rename_axis("month").reset_index())
    return pd.concat(parts, ignore_index=True)


def _fwd(px, H=(1, 3, 6, 12)):
    """forward total returns + max drawdown; after the last bar (delisting) the position sits in cash at the last price."""
    out = []
    end = pd.Period("2026-10", "M")
    for cik, m in px.groupby("cik"):
        m = m.set_index("month").sort_index()
        idx = pd.period_range(m.index[0], end, freq="M")
        a = m.adj.reindex(idx)
        last_real = m.index[-1]
        a = a.ffill()
        mn = m.amin.reindex(idx)
        mn = mn.fillna(a)
        r = pd.DataFrame(index=m.index)
        for h in H:
            r[f"r{h}"] = (a.shift(-h) / a - 1).reindex(m.index)
            r[f"dd{h}"] = (mn[::-1].rolling(h, min_periods=1).min()[::-1].shift(-1) / a - 1).reindex(m.index)
            # mark incomplete windows (beyond data end) as NaN
            r.loc[r.index + h > pd.Period("2026-09", "M"), [f"r{h}", f"dd{h}"]] = np.nan
        r["delisted_in12"] = (r.index + 12 > last_real) & (last_real < pd.Period("2026-08", "M"))
        r["cik"] = cik
        out.append(r.rename_axis("month").reset_index())
    return pd.concat(out, ignore_index=True)


def insiders():
    """SEC Form 3/4/5 structured data -> monthly open-market insider sales / purchases ($) per issuer CIK."""
    rows = []
    for f in sorted((RAW / "form345").glob("*_form345.zip")):
        try:
            z = zipfile.ZipFile(f)
            sub = pd.read_csv(z.open("SUBMISSION.tsv"), sep="\t", usecols=["ACCESSION_NUMBER", "FILING_DATE", "ISSUERCIK", "DOCUMENT_TYPE"],
                              dtype=str)
            nd = pd.read_csv(z.open("NONDERIV_TRANS.tsv"), sep="\t",
                             usecols=["ACCESSION_NUMBER", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD"],
                             dtype=str)
        except Exception as e:
            print("skip", f.name, e)
            continue
        nd = nd[nd.TRANS_CODE.isin(["S", "P"])]
        nd["v"] = pd.to_numeric(nd.TRANS_SHARES, errors="coerce") * pd.to_numeric(nd.TRANS_PRICEPERSHARE, errors="coerce")
        x = nd.merge(sub, on="ACCESSION_NUMBER")
        x = x[x.DOCUMENT_TYPE.isin(["4", "4/A", "5"])]
        x["date"] = pd.to_datetime(x.FILING_DATE, format="%d-%b-%Y", errors="coerce")
        x["cik"] = pd.to_numeric(x.ISSUERCIK, errors="coerce")
        x = x.dropna(subset=["date", "cik", "v"])
        x = x[(x.v > 0) & (x.v < 5e9)]
        x["month"] = x.date.dt.to_period("M")
        agg = x.groupby(["cik", "month", "TRANS_CODE"]).v.sum().unstack(fill_value=0)
        rows.append(agg)
        print(f.name, len(x), flush=True)
    A = pd.concat(rows).groupby(level=[0, 1]).sum().reset_index()
    A["cik"] = A.cik.astype(int)
    A = A.rename(columns={"S": "ins_sell", "P": "ins_buy"})
    save(A, "insiders.pkl")
    print("insider rows", len(A))


SOFTWARE = set(range(7370, 7380))


def panel():
    t0 = time.time()
    facts, subs_, tick = load("facts.pkl"), load("subs.pkl"), load("tickers.pkl")
    Q = qfeatures(facts, subs_)
    print("quarters", len(Q), f"{time.time() - t0:.0f}s", flush=True)
    px = _px_table(tick, facts, subs_)
    fw = _fwd(px)
    print("price rows", len(px), f"{time.time() - t0:.0f}s", flush=True)
    df = px.merge(fw, on=["cik", "month"], how="left")
    df["date"] = df.month.dt.end_time.dt.normalize()
    df.loc[df.month == pd.Period("2026-10", "M"), "date"] = TODAY
    df = df[df.month >= pd.Period("2011-06", "M")].copy()
    df["date"] = df["date"].astype("datetime64[ns]")
    df = df.sort_values("date")
    Q["avail"] = Q["avail"].astype("datetime64[ns]")
    Q = Q.dropna(subset=["avail"]).sort_values(["avail", "qend"]).drop_duplicates(["cik", "avail"], keep="last")
    df = pd.merge_asof(df, Q, left_on="date", right_on="avail", by="cik", direction="backward")
    df = df[(df.date - df.qend).dt.days <= 200]
    cov = []
    for cik, f in facts.items():
        for fd, e, v in f["cover"]:
            cov.append((cik, pd.Timestamp(fd), v))
    cov = pd.DataFrame(cov, columns=["cik", "cfiled", "cover"]).dropna()
    cov["cfiled"] = cov.cfiled.astype("datetime64[ns]")
    cov = cov.sort_values("cfiled")
    df = pd.merge_asof(df.sort_values("date"), cov, left_on="date", right_on="cfiled", by="cik", direction="backward")
    df.loc[(df.date - df.cfiled).dt.days > 400, "cover"] = np.nan
    ratio = df.cover / df.shq
    df["shares"] = df.cover.where(ratio.between(0.6, 1.6) | df.shq.isna(), df.shq)
    # share-count scale errors (filers tagging in thousands, etc.): >20x off the company's own median -> drop
    medsh = df.groupby("cik").shares.transform("median")
    df.loc[(df.shares / medsh > 20) | (df.shares / medsh < 0.05), "shares"] = np.nan
    df["mcap"] = df.shares * df.raw
    turn = df.dvol / df.mcap
    df.loc[(turn < 2e-5) | (turn > 0.5), "mcap"] = np.nan
    df = df[(df.mcap >= 2e8) & (df.raw >= 2) & ~df.sic.isin([6770, -1, 6221, 6722, 6726])]
    # insiders: 6-month rolling open-market buys / sells
    if P("insiders.pkl").exists():
        A = load("insiders.pkl")
        full = []
        for cik, a in A.groupby("cik"):
            a = a.set_index("month")[["ins_sell", "ins_buy"]].sort_index()
            a = a.reindex(pd.period_range(a.index[0], "2026-10", freq="M"), fill_value=0).rolling(6, min_periods=1).sum()
            a["cik"] = cik
            full.append(a.rename_axis("month").reset_index())
        A6 = pd.concat(full)
        df = df.merge(A6, on=["cik", "month"], how="left")
        df[["ins_sell", "ins_buy"]] = df[["ins_sell", "ins_buy"]].fillna(0)
        df["ins"] = (df.ins_buy - df.ins_sell) / df.mcap
    df["ev"] = df.mcap + df.debt - df.cashx
    fin = (df.sic >= 6000) & (df.sic < 6800)
    df["fin"] = fin
    df["evs"] = (df.ev / df.rev_t).where((df.ev > 0) & (df.rev_t > 0) & ~fin)
    df["ebit_ev"] = (df.ebit_t / df.ev).where((df.ev > 0) & ~fin)
    df["ep"] = df.ni_t / df.mcap
    df["bp"] = df.equity / df.mcap
    df["fcfy"] = (df.fcf_t / df.mcap).where(~fin)
    nde = (df.debt - df.cashx) / df.ebitda_t
    df["nd_ebitda"] = nde.where(df.ebitda_t > 0, np.where(df.debt - df.cashx > 0, 20.0, -1.0)).where(~fin)
    df["rule40"] = (df.g + df.fcf_t / df.rev_t).where(df.sic.isin(SOFTWARE) & (df.rev_t > 0))
    df["fcfm"] = (df.fcf_t / df.rev_t).where(df.rev_t > 0)
    df = df.sort_values(["cik", "month"])
    df["rv3"] = df.groupby("cik").rv.transform(lambda x: x.rolling(3, min_periods=1).mean())
    names = {c: f.get("name") for c, f in facts.items()}
    df["name"] = df.cik.map(names)
    df["ticker"] = df.cik.map({c: v[1] for c, v in tick.items()})
    for c in df.columns:
        if df[c].dtype == "float64":
            df[c] = df[c].astype("float32")
    save(df.reset_index(drop=True), "panel.pkl")
    print("panel rows", len(df), "ciks", df.cik.nunique(), f"{time.time() - t0:.0f}s")


# =====================================================================================  4. signals + backtest
IS0, IS1, OOS0 = pd.Period("2012-01", "M"), pd.Period("2018-12", "M"), pd.Period("2019-01", "M")
LAST = pd.Period("2026-09", "M")
BASE = {  # name: (column, sign)  higher signal = expected outperformance
    "evs_g": ("evs_resid", -1), "ebit_ev": ("ebit_ev", 1), "ep": ("ep", 1), "bp": ("bp", 1), "fcfy": ("fcfy", 1),
    "gpa": ("gpa", 1), "acc": ("acc", -1), "fscore": ("fscore", 1), "accel": ("accel", 1), "dil": ("dil", -1),
    "lev": ("nd_ebitda", -1), "rule40": ("rule40", 1), "om_chg": ("om_chg", 1), "gm_chg": ("gm_chg", 1),
    "growth": ("g", 1), "dso": ("dso_chg", -1), "adjgap": ("adjgap_chg", -1), "ins": ("ins", 1), "sbc": ("sbc_rev", -1),
}
COMPOSITES = {
    "value": ["evs_g", "ebit_ev", "ep", "fcfy"],
    "quality": ["gpa", "acc", "fscore", "om_chg"],
    "risk_inv": ["evs_g", "acc", "accel", "dso", "adjgap"],      # high = SAFE; low = rich + accruals + decel + DSO up + adj gap up
    "gem": ["evs_g", "gpa"],     # chosen AFTER the first run using IS (2012-18) t-stats only: the two best IS signals at 6/12m
}


def peer_assign(u):
    """SIC 4-digit peer group; fall back to 3-, 2-, 1-digit when a month's group has < 5 names."""
    grp = pd.Series(index=u.index, dtype=object)
    todo = pd.Series(True, index=u.index)
    for div, lab in ((1, "s4_"), (10, "s3_"), (100, "s2_"), (1000, "s1_")):
        key = (u.sic // div).astype(int)
        n = u.groupby([u.month, key]).cik.transform("count")
        ok = todo & ((n >= 5) | (div == 1000))
        grp[ok] = lab + key[ok].astype(str)
        todo &= ~ok
    return grp


def _rz(x, keys):
    g = x.groupby(keys)
    med = g.transform("median")
    mad = (x - med).abs().groupby(keys).transform("median") * 1.4826
    sd = g.transform("std")
    n = g.transform("count")
    sc = mad.where(mad > 1e-12, sd)
    z = ((x - med) / sc).clip(-3, 3)
    return z.where(n >= 4)


def signals(u):
    """u: one universe (rows = cik-month). Adds peer, peer-relative returns and z_<signal> columns."""
    u = u.copy()
    u = u.replace([np.inf, -np.inf], np.nan)
    for h, cap in ((1, 1.5), (3, 2.0), (6, 3.0), (12, 4.0)):      # winsorize price-data glitches (bad splits in delisted bars)
        if f"r{h}" in u:
            u[f"r{h}"] = u[f"r{h}"].clip(-1, cap)
    u["peer"] = peer_assign(u)
    keys = [u.month, u.peer]
    # EV/S vs growth residual within peer group
    y = np.log(u.evs.astype(float))
    x = u.g.astype(float).clip(-0.5, 1.0)
    ok = y.notna() & x.notna() & np.isfinite(y)
    yy, xx = y.where(ok), x.where(ok)
    g = pd.DataFrame({"y": yy, "x": xx, "xy": xx * yy, "x2": xx * xx}).groupby(keys)
    m = g.transform("mean")
    n = g.y.transform("count")
    b = (m.xy - m.x * m.y) / (m.x2 - m.x ** 2)
    b = b.where((m.x2 - m.x ** 2) > 1e-4, 0.0)
    u["evs_resid"] = (yy - m.y - b * (xx - m.x)).where(n >= 5)
    for name, (col, sgn) in BASE.items():
        u["z_" + name] = _rz(sgn * u[col].astype(float), keys)
    for name, parts in COMPOSITES.items():
        Z = u[["z_" + p for p in parts]]
        u["z_" + name] = Z.mean(axis=1).where(Z.notna().sum(axis=1) >= max(2, len(parts) // 2))
    u["z_combo"] = u[["z_value", "z_quality"]].mean(axis=1).where(u[["z_value", "z_quality"]].notna().all(axis=1))
    for h in (3, 6, 12):
        pm = u.groupby(keys)[f"r{h}"].transform("mean")
        u[f"x{h}"] = u[f"r{h}"] - pm
    return u


def nw_t(s, L):
    s = pd.Series(s).dropna().values
    n = len(s)
    if n < 8:
        return np.nan
    e = s - s.mean()
    v = e @ e / n
    for l in range(1, min(L, n - 1) + 1):
        v += 2 * (1 - l / (L + 1)) * (e[l:] @ e[:-l]) / n
    return s.mean() / math.sqrt(v / n) if v > 0 else np.nan


def pval(t):
    return math.erfc(abs(t) / math.sqrt(2)) if t == t else np.nan


def bh(ps, q=0.10):
    ps = np.asarray(ps, float)
    ok = ~np.isnan(ps)
    idx = np.where(ok)[0]
    order = idx[np.argsort(ps[idx])]
    m = len(order)
    passed = np.zeros(len(ps), bool)
    kmax = 0
    for k, i in enumerate(order, 1):
        if ps[i] <= q * k / m:
            kmax = k
    passed[order[:kmax]] = True
    return passed


def qspread(u, z, h, months, nq=5, rank_within=None):
    """monthly top-minus-bottom quintile of peer-relative h-month return."""
    d = u[u.month.isin(months) & u[z].notna() & u[f"x{h}"].notna()]
    keys = [d.month] if rank_within is None else [d.month, d[rank_within]]
    pct = d[z].groupby(keys).rank(pct=True)
    qq = np.ceil(pct * nq).clip(1, nq)
    top, bot = d[qq == nq], d[qq == 1]
    tm = top.groupby("month")[f"x{h}"].mean()
    bm = bot.groupby("month")[f"x{h}"].mean()
    sp = (tm - bm).dropna()
    return {"spread": float(sp.mean()) if len(sp) else np.nan, "t": nw_t(sp, h), "n_months": len(sp),
            "pos_months": float((sp > 0).mean()) if len(sp) else np.nan,
            "top_x": float(top[f"x{h}"].mean()), "bot_x": float(bot[f"x{h}"].mean()),
            "top_hit": float((top[f"x{h}"] > 0).mean()), "bot_hit": float((bot[f"x{h}"] > 0).mean()),
            "top_raw": float(top[f"r{h}"].mean()), "n_top": int(len(top)), "series": sp}


def universe(df, lo=CAP_LO, hi=CAP_HI):
    return df[(df.mcap >= lo) & (df.mcap <= hi)]


def _months(a, b):
    return set(pd.period_range(a, b, freq="M"))


def backtest():
    t0 = time.time()
    df = load("panel.pkl")
    U = signals(universe(df))
    U["bucket"] = np.where(U.mcap < CAP_MID, "small", "mid")
    save(U, "U.pkl")
    print("universe rows", len(U), f"{time.time() - t0:.0f}s", flush=True)
    R = {"coverage": {}, "tests": [], "collapse": [], "surv": []}
    # coverage / survivorship of the price sample
    for y in range(2012, 2027):
        x = U[U.month == pd.Period(f"{y}-06" if y < 2026 else "2026-09", "M")]
        R["coverage"][y] = {"names": int(len(x)), "hf_delisted_src": int((x.src == "hf").sum()), "small": int((x.bucket == "small").sum()),
                            "delisted_within_12m": int(x.delisted_in12.sum())}
    sigs = list(BASE) + list(COMPOSITES) + ["combo"]
    periods = {"IS": _months(IS0, IS1), "OOS": _months(OOS0, LAST)}
    for sname in sigs:
        z = "z_" + sname
        for h in (3, 6, 12):
            for b in ("all", "small", "mid"):
                d = U if b == "all" else U[U.bucket == b]
                row = {"signal": sname, "h": h, "bucket": b}
                for pn, mset in periods.items():
                    r = qspread(d, z, h, mset)
                    for k, v in r.items():
                        if k != "series":
                            row[f"{pn}_{k}"] = v
                row["OOS_p"] = pval(row["OOS_t"])
                R["tests"].append(row)
    T = pd.DataFrame(R["tests"])
    T["OOS_bh"] = bh(T.OOS_p.values, 0.10)
    T["same_sign"] = np.sign(T.IS_spread) == np.sign(T.OOS_spread)
    R["tests"] = T.to_dict("records")
    print(f"tests {len(T)}  OOS BH pass {int(T.OOS_bh.sum())}  {time.time() - t0:.0f}s", flush=True)
    show = T[(T.bucket == "all")][["signal", "h", "IS_spread", "IS_t", "OOS_spread", "OOS_t", "OOS_top_hit", "OOS_bot_hit", "OOS_pos_months", "OOS_bh"]]
    print(show.round(3).to_string())
    # ---------------- collapse side
    U["c6"] = U.r6 <= -0.30
    U["c12"] = U.r12 <= -0.30
    U["xc12"] = U.x12 <= -0.30
    rich = U.z_evs_g <= -1
    det = ((U.z_acc <= -0.5).astype(int) + (U.z_accel <= -0.5).astype(int) + (U.z_dso <= -0.5).astype(int)
           + (U.z_adjgap <= -0.5).astype(int) + (U.z_ins <= -0.5).astype(int))
    U["rule_rich_det"] = rich & (det >= 2)
    U["rule_rich_det3"] = rich & (det >= 3)
    flags = {"risk_bottom_decile": None, "rule_rich_det": "rule_rich_det", "rule_rich_det3": "rule_rich_det3"}
    for comp in ["evs_g", "acc", "accel", "dso", "adjgap", "ins", "fscore", "value", "quality", "combo", "growth", "dil", "lev"]:
        flags[f"{comp}_bottom_decile"] = comp
    for fname, spec in flags.items():
        for pn, mset in periods.items():
            for b in ("all", "small", "mid"):
                d = U[U.month.isin(mset)]
                if b != "all":
                    d = d[d.bucket == b]
                if spec is None or fname.endswith("_bottom_decile"):
                    zc = "z_risk_inv" if spec is None else "z_" + spec
                    d = d[d[zc].notna()]
                    pct = d[zc].groupby(d.month).rank(pct=True)
                    f = pct <= 0.10
                else:
                    f = d[spec].fillna(False)
                for ev in ("c6", "c12", "xc12"):
                    hz = 6 if ev == "c6" else 12
                    dd = d[d[f"r{hz}"].notna()]
                    ff = f.reindex(dd.index).fillna(False).astype(bool)
                    base = float(dd[ev].mean())
                    hit = float(dd.loc[ff, ev].mean()) if ff.sum() else np.nan
                    # significance: month-clustered difference
                    mm = dd.groupby("month").apply(lambda x: x.loc[ff.reindex(x.index), ev].mean() - x[ev].mean() if ff.reindex(x.index).sum() else np.nan)
                    R["collapse"].append({"flag": fname, "period": pn, "bucket": b, "event": ev, "n_flag": int(ff.sum()),
                                          "base": base, "rate": hit, "lift": hit / base if base else np.nan,
                                          "t": nw_t(mm, hz), "fp_rate": 1 - hit if hit == hit else np.nan,
                                          "mean_r": float(dd.loc[ff, f"r{hz}"].mean()), "mean_x": float(dd.loc[ff, f"x{hz}"].mean())})
    # volatility-matched baseline: are flagged names just volatile? compare with same-month, same-RV-decile names
    U["rvdec"] = np.ceil(U.rv3.groupby(U.month).rank(pct=True) * 10).clip(1, 10)
    vm = []
    for fname, zc, rule in (("value_bottom_decile", "z_value", None), ("combo_bottom_decile", "z_combo", None),
                            ("risk_bottom_decile", "z_risk_inv", None), ("evs_g_bottom_decile", "z_evs_g", None),
                            ("rule_rich_det3", None, "rule_rich_det3"), ("rule_rich_det", None, "rule_rich_det")):
        for pn, mset in periods.items():
            for b in ("all", "small", "mid"):
                d = U[U.month.isin(mset) & U.r12.notna() & U.rvdec.notna()]
                if b != "all":
                    d = d[d.bucket == b]
                if zc:
                    d = d[d[zc].notna()]
                    f = d[zc].groupby(d.month).rank(pct=True) <= 0.10
                else:
                    f = d[rule].fillna(False).astype(bool)
                cell = d.groupby([d.month, d.rvdec])
                exp_c = cell.c12.transform("mean")
                exp_x = cell.x12.transform("mean")
                exp_r = cell.r12.transform("mean")
                vm.append({"flag": fname, "period": pn, "bucket": b, "n": int(f.sum()), "rate": float(d.c12[f].mean()),
                           "vol_matched_rate": float(exp_c[f].mean()), "lift_vm": float(d.c12[f].mean() / exp_c[f].mean()),
                           "r12": float(d.r12[f].mean()), "r12_vol_matched": float(exp_r[f].mean()),
                           "x12_minus_volmatched": float((d.x12[f] - exp_x[f]).mean()),
                           "t_x": nw_t((d.x12[f] - exp_x[f]).groupby(d.month[f]).mean(), 12)})
    R["collapse_vm"] = vm
    print(pd.DataFrame(vm).round(3).to_string())
    C = pd.DataFrame(R["collapse"])
    print(C[(C.bucket == "all") & (C.event == "c12")].round(3).to_string())
    # ---------------- survivorship: survivors-only (yfinance) vs full sample
    Us = signals(universe(df[df.src == "yf"]))
    for sname in ["value", "quality", "combo", "risk_inv", "evs_g", "acc", "fscore", "gpa", "ep"]:
        for h in (6, 12):
            row = {"signal": sname, "h": h}
            for lab, uu in (("full", U), ("surv", Us)):
                for pn in ("IS", "OOS"):
                    r = qspread(uu, "z_" + sname, h, periods[pn])
                    row[f"{lab}_{pn}_spread"], row[f"{lab}_{pn}_t"] = r["spread"], r["t"]
            R["surv"].append(row)
    for pn in ("IS", "OOS"):
        for lab, uu in (("full", U), ("surv", Us)):
            d = uu[uu.month.isin(periods[pn]) & uu.r12.notna()]
            R["surv"].append({"signal": f"base_c12_{lab}_{pn}", "rate": float((d.r12 <= -0.3).mean()), "mean_r12": float(d.r12.mean()), "n": int(len(d))})
    print(pd.DataFrame(R["surv"]).round(4).to_string())
    with open(P("results.json"), "w") as f:
        json.dump(R, f, default=str, indent=1)
    print(f"done {time.time() - t0:.0f}s")


# =====================================================================================  5. live chains (3-6m + LEAPS) and earnings
def _chain_long(t):
    import yfinance as yf
    out = {"ticker": t}
    try:
        tk = yf.Ticker(t)
        spot = float(tk.fast_info["last_price"])
        out["spot"] = spot
        exps = list(tk.options or [])
    except Exception as e:
        out["err"] = str(e)[:80]
        return out
    today = TODAY.date()
    rows = []
    for e in exps:
        dte = (dt.date.fromisoformat(e) - today).days
        if not (60 <= dte <= 200 or 300 <= dte <= 800):
            continue
        try:
            ch = tk.option_chain(e)
        except Exception:
            continue
        for side, tab in (("call", ch.calls), ("put", ch.puts)):
            if tab is None or not len(tab):
                continue
            tab = tab.copy()
            i = (tab.strike - spot).abs().idxmin()
            r = tab.loc[i]
            bid, ask = float(r.get("bid") or 0), float(r.get("ask") or 0)
            mid = (bid + ask) / 2
            near = tab[(tab.strike / spot).between(0.8, 1.2)]
            rows.append({"exp": e, "dte": dte, "side": side, "strike": float(r.strike), "bid": bid, "ask": ask,
                         "spread": (ask - bid) / mid if mid > 0 and bid > 0 else np.nan, "mid": mid,
                         "oi_atm": float(r.get("openInterest") or 0), "vol_atm": float(r.get("volume") or 0),
                         "oi_near": float(near.openInterest.fillna(0).sum()), "vol_near": float(near.volume.fillna(0).sum()),
                         "iv": float(r.get("impliedVolatility") or np.nan)})
        time.sleep(0.15)
    out["rows"] = rows
    try:
        ed = tk.get_earnings_dates(limit=8)
        fut = [d for d in ed.index if d.tz_localize(None) >= TODAY] if ed is not None else []
        out["next_earn"] = str(min(fut).date()) if fut else None
    except Exception:
        out["next_earn"] = None
    if not out.get("next_earn"):
        try:
            cal = tk.calendar
            d = cal.get("Earnings Date") if isinstance(cal, dict) else None
            out["next_earn"] = str(d[0]) if d else None
        except Exception:
            pass
    return out


def chains(tks, name="chains.pkl"):
    from concurrent.futures import ThreadPoolExecutor
    have = load(name) if P(name).exists() else {}
    todo = [t for t in tks if t not in have]
    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(_chain_long, todo):
            have[r["ticker"]] = r
            if len(have) % 25 == 0:
                save(have, name)
    save(have, name)
    return have


def chain_summary(r):
    """3-6 month (60-200 DTE) ATM liquidity: mean call/put spread, OI, volume; LEAPS spread."""
    rows = pd.DataFrame(r.get("rows") or [])
    if rows.empty:
        return {"spread_36": np.nan, "oi_36": 0, "vol_36": 0, "iv_36": np.nan, "spread_leap": np.nan, "call_cost_6m": np.nan}
    a = rows[rows.dte <= 200]
    b = rows[rows.dte >= 300]
    c6 = a[a.side == "call"]
    c6 = c6.iloc[(c6.dte - 150).abs().argsort()[:1]] if len(c6) else c6
    return {"spread_36": float(a.spread.median()) if len(a) else np.nan, "oi_36": float(a.oi_near.sum()) if len(a) else 0,
            "oi_atm_36": float(a.oi_atm.sum()) if len(a) else 0,
            "vol_36": float(a.vol_near.sum()) if len(a) else 0, "iv_36": float(a.iv.median()) if len(a) else np.nan,
            "spread_leap": float(b.spread.median()) if len(b) else np.nan,
            "call_cost_6m": float(c6.ask.iloc[0] * 100) if len(c6) else np.nan, "dte_6m": int(c6.dte.iloc[0]) if len(c6) else None}


# =====================================================================================  6. Part 2: Fiserv / Alkami
FINTECH = ["FISV", "FIS", "JKHY", "GPN", "ACIW", "ALKT", "QTWO", "NCNO", "EVTC", "FOUR", "PAYO", "MQ", "BLND", "CSGS", "WEX",
           "FLYW", "RPAY", "CASS", "PAYS", "IIIV", "VYX", "PRTH", "TOST", "AFRM", "UPST", "SSNC", "BR", "EEFT"]
FIN_DELISTED = {"MLNK": "MeridianLink", "EPAY": "Bottomline", "EVOP": "EVO Payments", "PAYA": "Paya", "SQ": "Block"}
CASE_COLS = ["mcap", "g", "yoyq", "accel", "gm", "om", "om_chg", "acc", "cfo_ni", "dso", "dso_chg", "evs", "evs_resid", "ebit_ev",
             "ep", "fcfy", "fcfm", "adjgap", "adjgap_chg", "sbc_rev", "dil", "ins", "nd_ebitda", "rule40"]


def peer_z(d, cols):
    """z of each metric vs the peer set's median that month (robust)."""
    out = d.copy()
    for c in cols:
        x = d[c].astype(float)
        med = x.groupby(d.month).transform("median")
        mad = (x - med).abs().groupby(d.month).transform("median") * 1.4826
        out["pz_" + c] = ((x - med) / mad.replace(0, np.nan)).clip(-4, 4)
    return out


def case():
    df = load("panel.pkl")
    R = {}
    fin_ciks = set(df[df.ticker.isin(FINTECH + list(FIN_DELISTED))].cik)
    d = df[df.cik.isin(fin_ciks)].copy()
    d["cfo_ni"] = (d.cfo_t / d.ni_t).where(d.ni_t > 0)
    # growth-adjusted EV/S residual within the fintech peer set
    y = np.log(d.evs.astype(float)); x = d.g.astype(float).clip(-0.5, 1.0)
    ok = y.notna() & x.notna()
    res = pd.Series(np.nan, index=d.index)
    for m, gg in d[ok].groupby("month"):
        if len(gg) >= 5:
            b = np.polyfit(x[gg.index], y[gg.index], 1)
            res[gg.index] = y[gg.index] - np.polyval(b, x[gg.index])
    d["evs_resid"] = res
    d = peer_z(d, CASE_COLS)
    R["fintech_members"] = sorted(d.ticker.dropna().unique().tolist())
    fi = d[d.ticker == "FISV"].set_index("month").sort_index()
    rows = []
    for m in [p for p in fi.index if p >= pd.Period("2023-06", "M") and p.month in (3, 6, 9, 12)] + [pd.Period("2025-10", "M")]:
        if m in fi.index:
            r = fi.loc[m]
            rows.append({"month": str(m), "qend": str(r.qend.date()), **{c: float(r[c]) for c in CASE_COLS},
                         **{"pz_" + c: float(r["pz_" + c]) for c in CASE_COLS}})
    R["fiserv_quarters"] = rows
    # Part-1 risk score, all caps >= $300M (Fiserv is a large cap)
    A = signals(universe(df, CAP_LO, 1e13))
    A["c12"] = A.r12 <= -0.30
    A["c6"] = A.r6 <= -0.30
    fiA = A[A.ticker == "FISV"].set_index("month").sort_index()
    R["fiserv_risk"] = {str(m): {k: float(fiA.loc[m, k]) for k in ["z_risk_inv", "z_value", "z_quality", "z_evs_g", "z_acc", "z_accel", "z_dso",
                                                                    "z_adjgap", "z_ins", "r6", "r12", "x12"] if k in fiA}
                        for m in fiA.index if m >= pd.Period("2024-06", "M")}
    R["fiserv_peer_group"] = str(fiA.peer.iloc[-1])
    # false positives: how often did a score as bad as Fiserv's pre-drop score precede a -30% fall?
    fp = []
    for pre in ["2025-03", "2025-06", "2025-09"]:
        m = pd.Period(pre, "M")
        if m not in fiA.index:
            continue
        sc = float(fiA.loc[m, "z_risk_inv"])
        same = A[(A.month == m) & A.z_risk_inv.notna()]
        worse = same[same.z_risk_inv <= sc]
        hist = A[(A.month <= pd.Period("2025-09", "M")) & A.z_risk_inv.notna() & A.r12.notna()]
        hw = hist[hist.z_risk_inv <= sc]
        fp.append({"month": pre, "fiserv_score": sc, "pct_rank": float((same.z_risk_inv <= sc).mean()),
                   "n_as_bad_same_month": int(len(worse)), "of_which_fell30_6m": int((worse.r6 <= -0.3).sum()),
                   "same_month_r6_known": int(worse.r6.notna().sum()),
                   "hist_n": int(len(hw)), "hist_fell30_12m": float(hw.c12.mean()), "hist_base": float(hist.c12.mean()),
                   "hist_fp_rate": float(1 - hw.c12.mean()), "fiserv_r6": float(fiA.loc[m, "r6"]) if "r6" in fiA else None})
    R["fiserv_false_pos"] = fp
    # Alkami today vs peers
    now = d[d.month == pd.Period("2026-10", "M")]
    tab = now.set_index("ticker")[CASE_COLS + ["evs_resid"]].astype(float)
    R["fintech_today"] = tab.round(4).to_dict("index")
    # Alkami-profile analogs in the Part-1 universe history
    U = signals(universe(df))
    feat = ["z_evs_g", "z_growth", "z_om_chg", "z_fcfy", "z_dil", "z_gpa", "z_acc", "z_accel"]
    al = U[(U.ticker == "ALKT")].sort_values("month")
    if len(al):
        v = al.iloc[-1][feat].astype(float)
        R["alkt_z_today"] = v.round(3).to_dict()
        R["alkt_peer_group"] = str(al.iloc[-1].peer)
        H = U[U.r12.notna() & U[feat].notna().all(axis=1) & (U.ticker != "ALKT")]
        dist = np.sqrt(((H[feat].astype(float) - v.values) ** 2).sum(axis=1))
        nn = H.loc[dist.nsmallest(300).index]
        R["alkt_analogs"] = {"n": int(len(nn)), "max_dist": float(dist.nsmallest(300).max()),
                             "x6": float(nn.x6.mean()), "x12": float(nn.x12.mean()), "r12": float(nn.r12.mean()),
                             "hit12": float((nn.x12 > 0).mean()), "c12": float((nn.r12 <= -0.3).mean()),
                             "all_x12": float(H.x12.mean()), "all_hit12": float((H.x12 > 0).mean()), "all_c12": float((H.r12 <= -0.3).mean()),
                             "x12_t": float(nn.x12.mean() / (nn.x12.std() / math.sqrt(nn.month.nunique()))),
                             "months": int(nn.month.nunique())}
        R["alkt_history"] = {str(r.month): {k: float(r[k]) for k in ["mcap", "z_value", "z_quality", "z_combo", "z_risk_inv", "z_evs_g"]}
                             for _, r in al.iterrows() if r.month.month in (3, 6, 9, 12) or r.month == pd.Period("2026-10", "M")}
    with open(P("case.json"), "w") as f:
        json.dump(R, f, default=str, indent=1)
    print(json.dumps({k: R[k] for k in ("fiserv_false_pos", "alkt_analogs", "fiserv_peer_group", "alkt_peer_group") if k in R}, default=str, indent=1))


# =====================================================================================  7. Part 3: today's screen
UNDER_SIG = "z_gem"          # Part 1 survivor (small caps): cheap-for-growth EV/S + gross profitability; high = undervalued
OVER_SIG = "z_gem"           # low gem = rich for its growth + low profitability (bottom leg -4.3%/12m vs peers OOS, small caps)
SHOW = {"evs": "EV/S", "g": "rev g", "ebit_ev": "EBIT/EV", "fcfy": "FCF yld", "gpa": "GP/A", "acc": "accruals", "fscore": "F",
        "om": "op mgn", "accel": "accel", "dso_chg": "dDSO", "adjgap_chg": "dAdjGap", "dil": "dilution", "ep": "E/P"}


def _why(r, sign):
    zs = {k: float(r["z_" + k]) for k in BASE if pd.notna(r.get("z_" + k))}
    top = sorted(zs.items(), key=lambda x: -sign * x[1])[:3]
    return ", ".join(f"{k} {v:+.1f}" for k, v in top)


def screen():
    df = load("panel.pkl")
    subs_ = load("subs.pkl")
    U = signals(universe(df))
    now = U[U.month == pd.Period("2026-10", "M")].copy()
    now["bucket"] = np.where(now.mcap < CAP_MID, "small", "mid")
    now["sicd"] = now.cik.map({c: v.get("sicd") for c, v in subs_.items()})
    med = now.groupby("peer")[list(SHOW)].transform("median")
    out = {}
    for side, col, asc in (("under", UNDER_SIG, False), ("over", OVER_SIG, True)):
        c = now[now[col].notna()].sort_values(col, ascending=asc).head(45)
        out[side] = c
    rng = np.random.default_rng(3)
    sample = sorted(rng.choice(now.ticker.dropna().unique(), 200, replace=False).tolist())
    tks = sorted(set(pd.concat(out.values()).ticker.dropna()) | set(FINTECH) | set(sample))
    ch = chains(tks)
    # spread / IV-to-RV by size bucket from the random sample (for Part 4 costs)
    liq = []
    for t in sample:
        r = now[now.ticker == t].iloc[0]
        cs = chain_summary(ch.get(t, {}))
        rows = pd.DataFrame(ch.get(t, {}).get("rows") or [])
        liq.append({"ticker": t, "bucket": r.bucket if "bucket" in r else ("small" if r.mcap < CAP_MID else "mid"), "mcap": float(r.mcap),
                    "rv3": float(r.rv3), "has_chain": len(rows) > 0, **cs, "ivrv": cs["iv_36"] / float(r.rv3) if r.rv3 else np.nan})
    res_liq = pd.DataFrame(liq)
    save(res_liq, "liq.pkl")
    print(res_liq.groupby("bucket")[["has_chain", "spread_36", "spread_leap", "ivrv", "oi_36", "vol_36", "call_cost_6m"]].median())
    print(res_liq.groupby("bucket").has_chain.mean())
    res = {}
    for side, c in out.items():
        rows = []
        for _, r in c.iterrows():
            peers = now[(now.peer == r.peer) & (now.cik != r.cik)].copy()
            peers["dcap"] = (np.log(peers.mcap) - np.log(r.mcap)).abs()
            comp = peers.nsmallest(4, "dcap").ticker.tolist()
            cs = chain_summary(ch.get(r.ticker, {}))
            rows.append({"ticker": r.ticker, "name": r["name"], "mcap_b": float(r.mcap) / 1e9, "peer": r.peer, "sicd": r.sicd,
                         "bucket": r.bucket, "risk_inv": float(r.z_risk_inv) if pd.notna(r.z_risk_inv) else None,
                         "score": float(r[UNDER_SIG if side == "under" else OVER_SIG]), "competitors": comp,
                         "why": _why(r, 1 if side == "under" else -1),
                         **{SHOW[k]: float(r[k]) for k in SHOW}, **{SHOW[k] + "_peer": float(med.loc[_, k]) for k in SHOW},
                         **cs, "next_earn": ch.get(r.ticker, {}).get("next_earn"), "spot": ch.get(r.ticker, {}).get("spot")})
        res[side] = rows
    # sector dives: fintech table + two of the largest peer groups
    res["fintech"] = {t: chain_summary(ch.get(t, {})) | {"next_earn": ch.get(t, {}).get("next_earn")} for t in FINTECH}
    big = now.groupby("peer").size().sort_values(ascending=False)
    dives = {}
    for pg in ["s4_7372", "s4_3674", "s4_2834"]:
        g = now[now.peer == pg]
        if len(g) < 8:
            continue
        g = g.sort_values(UNDER_SIG, ascending=False)
        cols = ["ticker", "mcap", UNDER_SIG, OVER_SIG, "evs", "g", "om", "fcfy", "gpa", "acc"]
        dives[pg] = {"n": int(len(g)), "cheap": g.head(6)[cols].to_dict("records"), "rich": g.tail(6)[cols].to_dict("records"),
                     "median": g[["evs", "g", "om", "fcfy", "gpa"]].median().to_dict()}
    res["dives"] = dives
    res["peer_sizes"] = big.head(15).to_dict()
    with open(P("screen.json"), "w") as f:
        json.dump(res, f, default=str, indent=1)
    for side in ("under", "over"):
        print(pd.DataFrame(res[side])[["ticker", "mcap_b", "peer", "score", "why", "spread_36", "oi_36", "vol_36", "call_cost_6m", "next_earn"]]
              .head(25).round(3).to_string())


# =====================================================================================  8. Part 4: option economics
def bs(S, K, T, sig, call=True, r=0.035):
    from scipy.special import ndtr
    S, K, T, sig = map(lambda a: np.asarray(a, float), (S, K, T, sig))
    T = np.maximum(T, 1e-6)
    sig = np.maximum(sig, 0.05)
    d1 = (np.log(S / K) + (r + sig ** 2 / 2) * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    c = S * ndtr(d1) - K * np.exp(-r * T) * ndtr(d2)
    return np.where(call, c, c - S + K * np.exp(-r * T))


def opt_trades(d, call, T_m, hold_m, k, spread, mny=1.0):
    """entry at month-end close: ATM (or mny*S) option, T_m months to expiry, exit after hold_m months.
    IV = rv3 x k (entry) and rv3(exit month) x k; cost = buy mid*(1+s/2), sell mid*(1-s/2)."""
    S0 = np.ones(len(d))
    S1 = 1 + d[f"r{hold_m}"].values.astype(float)
    K = mny * S0 if call else (2 - mny) * S0
    v0 = d.rv3.values.astype(float) * k
    v1 = d[f"rv3_f{hold_m}"].fillna(d.rv3).values.astype(float) * k
    p0 = bs(S0, K, T_m / 12, v0, call)
    rem = (T_m - hold_m) / 12
    p1 = np.where(rem > 1e-6, bs(S1, K, rem, v1, call), np.maximum(S1 - K, 0) if call else np.maximum(K - S1, 0))
    s = d["spr"].values.astype(float) if isinstance(spread, str) else spread
    ret = p1 * (1 - s / 2) / (p0 * (1 + s / 2)) - 1
    return pd.Series(ret, index=d.index), pd.Series(p0, index=d.index)


def options():
    t0 = time.time()
    import yfinance as yf
    U = load("U.pkl")
    subs_ = load("subs.pkl")
    liq = load("liq.pkl")
    lq = liq[liq.has_chain]
    L = {b: {"s36": float(g.spread_36.median()), "sleap": float(g.spread_leap.median()), "ivrv": float(g.ivrv.median()),
             "n": int(len(g)), "chain_share": float(liq[liq.bucket == b].has_chain.mean()),
             "s36_q25": float(g.spread_36.quantile(.25)), "s36_q75": float(g.spread_36.quantile(.75))} for b, g in lq.groupby("bucket")}
    print("liquidity", L)
    R = {"liq": L, "rows": [], "bank": []}
    # exit-month realized vol
    key = U.set_index(["cik", "month"]).rv3
    for h in (3, 6, 12):
        idx = pd.MultiIndex.from_arrays([U.cik, U.month + h])
        U[f"rv3_f{h}"] = key.reindex(idx).values
    # earnings: first 8-K item 2.02 after the entry date
    e202 = {c: np.array(sorted(pd.to_datetime(v["e202"]).values)) for c, v in subs_.items() if v.get("e202")}
    def next_e(row):
        a = e202.get(row.cik)
        if a is None or not len(a):
            return np.nan
        i = np.searchsorted(a, np.datetime64(row.date))
        return (a[i] - np.datetime64(row.date)) / np.timedelta64(1, "D") if i < len(a) else np.nan
    U["days_to_earn"] = [next_e(r) for r in U[["cik", "date"]].itertuples(index=False)]
    spy = yf.download("SPY", start="2011-01-01", auto_adjust=True, progress=False)["Close"].squeeze()
    spym = spy.groupby(spy.index.to_period("M")).last()
    for h in (3, 6, 12):
        U[f"spy{h}"] = (spym.shift(-h) / spym - 1).reindex(U.month).values
    periods = {"IS": _months(IS0, IS1), "OOS": _months(OOS0, LAST)}
    U["pct"] = U.z_gem.groupby([U.month, U.bucket]).rank(pct=True)
    U["pct_all"] = U.z_gem.groupby(U.month).rank(pct=True)
    structs = [("call", 3, 3), ("call", 6, 3), ("call", 6, 6), ("call", 12, 6), ("call", 12, 12),
               ("put", 3, 3), ("put", 6, 6), ("put", 12, 12)]
    TR = {}
    for side, Tm, hold in structs:
        call = side == "call"
        for b in ("small", "mid"):
            base = U[(U.bucket == b) & U[f"r{hold}"].notna() & U.rv3.notna() & U.z_gem.notna()].copy()
            sp = L[b]["sleap"] if Tm >= 12 else L[b]["s36"]
            k = L[b]["ivrv"]
            for lab, kk, ss in (("measured", k, sp), ("half_spread", k, sp / 2), ("mid_fill", k, 0.0), ("iv+20%", k * 1.2, sp), ("iv-20%", k * 0.8, sp)):
                ret, prem = opt_trades(base, call, Tm, hold, kk, ss)
                base["ret"], base["prem"] = ret, prem
                sel = base.pct >= 0.8 if call else base.pct <= 0.2
                for pn, mset in periods.items():
                    inp = base.month.isin(mset)
                    for flt, extra in (("all_months", True), ("earn<=30d", base.days_to_earn <= 30), ("earn<=60d", base.days_to_earn <= 60)):
                        if lab != "measured" and flt != "all_months":
                            continue
                        m_sig = inp & sel & extra
                        m_all = inp & extra
                        if m_sig.sum() < 30:
                            continue
                        r_sig = base.ret[m_sig]
                        # month-clustered excess vs the same structure on every name in the bucket
                        ex = (base.ret[m_sig].groupby(base.month[m_sig]).mean() - base.ret[m_all].groupby(base.month[m_all]).mean()).dropna()
                        row = {"side": side, "T": Tm, "hold": hold, "bucket": b, "variant": lab, "period": pn, "filter": flt,
                               "n": int(m_sig.sum()), "ev": float(r_sig.mean()), "median": float(r_sig.median()), "hit": float((r_sig > 0).mean()),
                               "ev_all_names": float(base.ret[m_all].mean()), "excess": float(ex.mean()), "excess_t": nw_t(ex, hold),
                               "ev_t": nw_t(r_sig.groupby(base.month[m_sig]).mean(), hold),
                               "stock_r": float(base[f"r{hold}"][m_sig].mean()), "spy_r": float(base[f"spy{hold}"][m_sig].mean()),
                               "stock_x_vs_peers": float(base[f"x{hold}"][m_sig].mean()),
                               "prem_pct": float(prem[m_sig].median()), "contract_cost": float((prem * base.raw * 100 * (1 + ss / 2))[m_sig].median()),
                               "spread": ss, "ivrv": kk}
                        R["rows"].append(row)
                        if lab == "measured" and flt == "all_months" and pn == "OOS":
                            TR[(side, Tm, hold, b)] = (base.loc[m_sig, ["month", "ret"]].assign(cost=(prem * base.raw * 100 * (1 + ss / 2))[m_sig]))
    T = pd.DataFrame(R["rows"])
    print(T[(T.variant == "measured") & (T["filter"] == "all_months")][["side", "T", "hold", "bucket", "period", "n", "ev", "median", "hit",
                                                                         "ev_all_names", "excess", "excess_t", "stock_r", "spy_r", "contract_cost"]]
          .round(3).to_string())
    print(T[(T.variant != "measured") & (T.period == "OOS")][["side", "T", "hold", "bucket", "variant", "ev", "excess"]].round(3).to_string())
    print(T[(T["filter"] != "all_months") & (T.period == "OOS")][["side", "T", "hold", "bucket", "filter", "n", "ev", "excess", "excess_t"]].round(3).to_string())
    # bankroll for the main candidate structures (OOS trade distribution, quarterly or semiannual rounds)
    for keyT, rpy in ((("call", 6, 3, "small"), 4), (("call", 12, 6, "small"), 2), (("call", 3, 3, "small"), 4), (("put", 6, 6, "small"), 2)):
        if keyT not in TR:
            continue
        tr = TR[keyT]
        tbm = {m: g.ret.values for m, g in tr.groupby("month")}
        cbm = {m: g.cost.values for m, g in tr.groupby("month")}
        for start, kpos, f in ((170, 1, 0.6), (1000, 3, 0.25), (5000, 5, 0.15), (5000, 10, 0.08)):
            b = bankroll_r(tbm, cbm, start, f=f, k_pos=kpos, rounds=rpy * 3)
            R["bank"].append({"struct": str(keyT), "start": start, "k_pos": kpos, "f": f, **b})
    print(pd.DataFrame(R["bank"]).round(3).to_string())
    with open(P("options.json"), "w") as f:
        json.dump(R, f, default=str, indent=1)
    print(f"done {time.time() - t0:.0f}s")


def bankroll_r(tbm, cbm, start, f=0.25, k_pos=3, rounds=12, n=10000, seed=7):
    """each round: draw a random historical entry month, buy up to k_pos of that month's signal names
    (whole contracts, f of equity each; one contract allowed if it costs <= 60% of equity). 3-year horizon."""
    rng = np.random.default_rng(seed)
    months = list(tbm)
    eq = np.full(n, float(start))
    skipped = 0
    tried = 0
    for _ in range(rounds):
        pick = rng.integers(0, len(months), n)
        for i in range(n):
            rr, cc = tbm[months[pick[i]]], cbm[months[pick[i]]]
            idx = rng.choice(len(rr), size=min(k_pos, len(rr)), replace=False)
            cash = eq[i]
            pnl = 0.0
            for j in idx:
                tried += 1
                nc = int((f * eq[i]) // cc[j])
                if nc == 0 and cc[j] <= 0.6 * eq[i] and cc[j] <= cash:
                    nc = 1
                if nc == 0 or nc * cc[j] > cash:
                    skipped += 1
                    continue
                cash -= nc * cc[j]
                pnl += nc * cc[j] * rr[j]
            eq[i] = max(eq[i] + pnl, 0)
    return {"p_grow": float((eq > start).mean()), "median_end": float(np.median(eq)), "mean_end": float(eq.mean()),
            "ruin": float((eq < 0.12 * start).mean()), "skip_rate": skipped / max(tried, 1), "rounds": rounds}


def robust():
    U = load("U.pkl")
    df = load("panel.pkl")
    R = {}
    sm = U[U.bucket == "small"]
    for h in (6, 12):
        d = sm[sm.z_gem.notna() & sm[f"x{h}"].notna()]
        pct = d.z_gem.groupby(d.month).rank(pct=True)
        top, bot = d[pct > 0.8], d[pct <= 0.2]
        yr = {}
        for y in range(2012, 2026):
            t_ = top[top.month.dt.year == y][f"x{h}"].mean(); b_ = bot[bot.month.dt.year == y][f"x{h}"].mean()
            yr[y] = {"top_x": float(t_), "bot_x": float(b_), "spread": float(t_ - b_)}
        R[f"years_h{h}"] = yr
        for pn, (a, b) in (("IS", (IS0, IS1)), ("OOS", (OOS0, LAST))):
            ms = _months(a, b)
            tt = top[top.month.isin(ms)].groupby("month")[f"x{h}"].mean()
            dd = top[top.month.isin(ms)]
            R[f"top_leg_h{h}_{pn}"] = {"x": float(tt.mean()), "t": nw_t(tt, h), "raw": float(dd[f"r{h}"].mean()),
                                       "hit": float((dd[f"x{h}"] > 0).mean()), "median_x": float(dd[f"x{h}"].median()),
                                       "p90_x": float(dd[f"x{h}"].quantile(.9)), "n": int(len(dd))}
            # decile instead of quintile; liquidity tiers (median $ volume) as a proxy for option tradability
            for lab, cond in (("decile", None), ("dvol>=2M", d.dvol >= 2e6), ("dvol>=10M", d.dvol >= 1e7), ("cap>=750M", d.mcap >= 7.5e8)):
                dd2 = d[d.month.isin(ms)]
                if cond is not None:
                    dd2 = dd2[cond.reindex(dd2.index).fillna(False)]
                    q = qspread(dd2, "z_gem", h, ms)
                else:
                    q = qspread(dd2, "z_gem", h, ms, nq=10)
                R[f"{lab}_h{h}_{pn}"] = {k: v for k, v in q.items() if k != "series"}
    Us = signals(universe(df[df.src == "yf"]))
    Us["bucket"] = np.where(Us.mcap < CAP_MID, "small", "mid")
    for h in (6, 12):
        for pn, (a, b) in (("IS", (IS0, IS1)), ("OOS", (OOS0, LAST))):
            q = qspread(Us[Us.bucket == "small"], "z_gem", h, _months(a, b))
            R[f"survivors_only_h{h}_{pn}"] = {k: v for k, v in q.items() if k != "series"}
    with open(P("robust.json"), "w") as f:
        json.dump(R, f, default=str, indent=1)
    for k, v in R.items():
        if not k.startswith("years"):
            print(k, {a: (round(b, 4) if isinstance(b, float) else b) for a, b in v.items() if a in ("spread", "t", "x", "raw", "hit", "top_x", "n_top", "median_x", "p90_x")})
    print(pd.DataFrame(R["years_h12"]).T.round(3).to_string())


def _f(x, pct=False, d=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    return f"{x * 100:.{d}f}%" if pct else f"{x:.{d}f}"


def tables():
    """print the markdown tables used in research/fundamental.md"""
    S = json.load(open(P("screen.json")))
    U = load("U.pkl")
    now = U[U.month == pd.Period("2026-10", "M")].set_index("ticker")
    for side in ("under", "over"):
        print(f"\n### {side}\n")
        print("| # | ticker | name | cap $B | peer group (SIC) | gem z (EV/S-vs-growth z, GP/A z) | EV/S (peer med) | rev g (peer) | GP/A (peer) | op mgn (peer) | FCF yld (peer) | competitors | 3-6m ATM spread | OI / vol (3-6m, ±20%) | 6m ATM call | next earnings |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        k = 0
        for r in S[side]:
            t = r["ticker"]
            if t not in now.index or k >= 20:
                continue
            k += 1
            z = now.loc[t]
            if isinstance(z, pd.DataFrame):
                z = z.iloc[0]
            nm = (r["name"] or "")[:28]
            print(f"| {k} | {t} | {nm} | {r['mcap_b']:.2f} | {r['peer']} {str(r['sicd'] or '')[:30]} | {r['score']:+.2f} ({z.z_evs_g:+.1f}, {z.z_gpa:+.1f}) | "
                  f"{_f(r['EV/S'])} ({_f(r['EV/S_peer'])}) | {_f(r['rev g'], True, 0)} ({_f(r['rev g_peer'], True, 0)}) | {_f(r['GP/A'], d=2)} ({_f(r['GP/A_peer'], d=2)}) | "
                  f"{_f(r['op mgn'], True, 0)} ({_f(r['op mgn_peer'], True, 0)}) | {_f(r['FCF yld'], True, 0)} ({_f(r['FCF yld_peer'], True, 0)}) | {', '.join(r['competitors'][:3])} | "
                  f"{_f(r['spread_36'], True, 0)} | {int(r['oi_36'] or 0):,} / {int(r['vol_36'] or 0):,} | {('$' + format(r['call_cost_6m'], ',.0f')) if r['call_cost_6m'] == r['call_cost_6m'] and r['call_cost_6m'] else '–'} | {r['next_earn'] or '–'} |")
    print("\n### fintech\n")
    C = json.load(open(P("case.json")))
    ft = pd.DataFrame(C["fintech_today"]).T
    print("| ticker | cap $B | rev g TTM | last-Q yoy | gross mgn | op mgn (GAAP) | FCF mgn | EV/S | EV/S resid vs growth | FCF yld | SBC/rev | dilution yoy | CFO/NI | DSO | 3-6m spread | OI 3-6m | next earn | gem z |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t in ["ALKT", "QTWO", "NCNO", "JKHY", "ACIW", "FIS", "FISV", "GPN", "EVTC", "FOUR", "PAYO", "MQ", "FLYW", "CASS", "PRTH", "IIIV", "TOST", "SSNC", "BR"]:
        if t not in ft.index:
            continue
        r = ft.loc[t]
        cs = S["fintech"].get(t, {})
        gz = now.loc[t, "z_gem"] if t in now.index else np.nan
        gz = gz.iloc[0] if isinstance(gz, pd.Series) else gz
        print(f"| {t} | {r.mcap / 1e9:.1f} | {_f(r.g, True, 0)} | {_f(r.yoyq, True, 0)} | {_f(r.gm, True, 0)} | {_f(r.om, True, 0)} | {_f(r.fcfm, True, 0)} | {_f(r.evs)} | {_f(r.evs_resid, d=2)} | "
              f"{_f(r.fcfy, True, 1)} | {_f(r.sbc_rev, True, 0)} | {_f(r.dil, True, 1)} | {_f(r.cfo_ni)} | {_f(r.dso, d=0)} | {_f(cs.get('spread_36'), True, 0)} | {int(cs.get('oi_36') or 0):,} | {cs.get('next_earn') or '–'} | {_f(gz, d=2)} |")


STEPS = ["edgar", "subs", "prices_yf", "prices_hf", "insiders", "tickers", "panel", "coverage", "backtest", "robust", "case",
         "screen", "options", "tables"]

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    for step in (STEPS if cmd == "all" else [cmd]):
        globals()[step]()
