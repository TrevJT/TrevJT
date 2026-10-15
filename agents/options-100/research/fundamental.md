# Peer-relative fundamental valuation: does "cheap vs competitors" predict returns or collapses, and can long options capture it?

2026-10-14. **Owner's idea:** "A strategy looking for undervalued and overvalued stocks, going long on options. Fiserv was overvalued and had a huge drop. Alkami is undervalued looking at revenue, P/E and growth. Do an analysis on all stocks, compare direct competitors, and find gems that are under- or overvalued. Keep to small/mid size so big hedge funds can't touch them."

**These are research screens, not personal investment advice.** Nothing here is a recommendation to buy or sell any security. A "rich" or "at-risk" label is a statistical ranking, not a claim about any company.

- **Code:** `bot/research_fundamental.py`. Steps, in order: `edgar | subs | prices_yf | prices_hf | insiders | tickers | panel | coverage | backtest | robust | case | screen | options | tables`, or `all`.
  - From caches, `backtest` runs in about 1 minute and `options` in about 20 s.
  - The EDGAR parse takes about 15 min; `tickers` takes about 15 min because of SEC index lookups.
- **Caches** (gitignored under `data/`, checked with `git check-ignore`): `research_fund_*.pkl` / `.json` and `research_fund_raw/`.
  - The raw folder holds the SEC companyfacts and submissions bulk zips, the Form 3/4/5 quarterly datasets and the HuggingFace daily-bar parquet files. All of it is parsed only, never executed.
  - Result files: `research_fund_results.json` (Part 1), `research_fund_case.json` (Part 2), `research_fund_screen.json` and `research_fund_chains.pkl` (Part 3), `research_fund_options.json` (Part 4), `research_fund_robust.json`.
- **Reused from earlier studies:**
  - smallcap.md: wide small-cap spreads, quiet names cost more, and excess must be measured against peers or own drift, never an index.
  - universe.md: IV/RV is not a constant, so it is measured here.
  - forensic_events.md, run in parallel on the same EDGAR caches: red flags predict crash *odds* through volatility, and IV already charges for that. That result agrees with §1.4.

## Verdict (short)

1. **Peer-relative valuation does predict 6–12-month returns, but only one combination survives, and only in small caps.**
   - The signal ("gem") combines two peer z-scores: **EV/Sales relative to revenue growth**, the residual of a within-industry regression, i.e. "cheap for its growth"; and **gross profit / assets**.
   - In **$300M–$2B** names, top-minus-bottom quintile, peer-relative 12m return:
     - in-sample (2012–18): **+5.5%** (t 3.8);
     - out-of-sample (2019–26): **+7.2%** (t 3.0).
   - It passes Benjamini–Hochberg at q=0.10 across all 216 out-of-sample tests, at 6m and 12m. It was positive in 13 of 14 years.
   - In **$2–10B** names it is −1.3% IS / +3.9% OOS (t 1.6). **The owner's "too small for hedge funds" intuition holds for this signal.** It also fades in the most liquid small caps (≥$10M/day traded).
   - **Classic value is dead out of sample:** P/E, EV/EBIT, FCF yield, P/B and their composite are ≈0 everywhere 2019+. So are Piotroski F-score, accruals, revenue acceleration, dilution, leverage, insider buying/selling and Rule-of-40.
2. **The long leg is small and skewed.**
   - Top-quintile small caps beat their peers by **+3.1%/yr OOS** (t 1.6) with a **45% hit rate** and a −4.6% median. A few big winners carry it.
   - Half the spread comes from the bottom leg (−4.2%/yr).
3. **Collapse prediction mostly measures volatility.** "Overvalued + deteriorating quality" does raise the odds of a −30% fall in 12 months:
   - expensive-and-unprofitable decile: 1.8× IS / 1.6× OOS;
   - rich + ≥3 deterioration flags: 1.5× / 1.3×.
   - **Against names with the same realized vol, the lift shrinks to 1.07–1.27× and the return shortfall is −1 to −3 pts (t ≤ 2.3).** False positives are 74–89%.
   - Options already price that volatility, which is the same conclusion as forensic_events.md.
4. **Fiserv was not predictable from filed fundamentals.**
   - FISV peaked at **$237.79 on 2025-03-03**. It fell −18.5% (2025-04-24), −13.8% (2025-07-23) and **−44.0% (2025-10-29)**, and is **$46 today (−81%)**.
   - In every quarter before the drops its filed numbers looked healthy:
     - GAAP growth 6.6–7.1% and steady;
     - operating margin rising to 30% (peer z +1.0 to +1.35);
     - CFO about 2× net income;
     - DSO flat; buybacks.
   - The only red flag was **valuation: rich vs fintech peers for its growth** (EV/S-vs-growth residual peer z +1.02 in Mar-25).
   - The Part 1 risk score ranked it at the **37th–46th percentile, i.e. unflagged**. Of the 815–994 names scoring as badly in each pre-drop month, about 88% did not fall 30% in the following 12 months.
   - The deterioration (growth to −1%, margin to 22%) appears only in filings made **after** the drops.
5. **Alkami is cheap for its growth vs fintech peers, but not a "gem" by the tested signal**, and its profile has no historical edge.
   - **Numbers:** EV/S 2.9× at 27% growth, against Q2 at 4.2×/14%, nCino 3.6×/9% and JKHY 4.3×/7%.
   - **Why it misses:** growth is acquisition-inflated and decelerating (last quarter +16% yoy), stock comp is 15% of revenue, dilution runs +3.4%/yr, and the GAAP operating margin is −7%.
   - **Where it ranks:** gem z +0.27, about the 60th percentile of prepackaged software.
   - **History:** the 300 nearest historical profiles beat their peers by +1.3% over 12 months, against +0.7% for everyone (t 0.4).
6. **Long options cannot capture the edge** (§4).
   - **Live quotes today:** a 3–6-month ATM option on a $300M–$2B name has a median **59% bid–ask spread** (30% for $2–10B; LEAPS 42% / 19%) and IV ≈ 1.47× realized.
   - **Backtest:**
     - Gem calls lose **−34% to −56% of premium per trade** in small caps OOS. Their excess over random calls in the same bucket is ≈0.
     - Mid-cap 12-month LEAPS lose −9% (+11% only at mid fills).
     - Puts on the "overvalued" side beat random puts by +3 to +5 pts (t 2–4.5) but still lose −41% to −62%.
   - **Today's picks:** the median ~5-month ATM call needs **+21%** to break even, against a historical top-quintile 6m return of +6.9%.
   - **Bankroll:** P(grow over 3 yrs) ≤ 7% at $170, $1k and $5k.

**Recommendation.**
- **Do not add a fundamental-valuation options sleeve.**
- **Status:** "NOT YET FOUND" for options; the stock-level signal is **real** in small caps.
- **Not retired.** Per the owner's rule, the gem signal goes on the "ready when funded" list as a **stock** (or stock long/short) strategy, which this account cannot run today.
- **Paper-track:**
  - the top-20 / bottom-20 lists quarterly against peers;
  - mid-cap gem LEAPS quoted with limit orders at mid, to test whether mid fills are achievable (the one cell that turns positive).
- **Reuse:** a low gem score or a high risk score is a **"never buy calls on this name"** filter for the other strategies.
- XSP dip-buy (direction.md) remains the primary candidate.

---

## 0. Data: point-in-time EDGAR + delisted prices

| item | source | count |
|---|---|---|
| XBRL filers parsed | SEC `companyfacts.zip` bulk (Oct-14 build); us-gaap facts from 10-K/10-Q only (a DEF 14A pay-vs-performance table polluted Alkami's NI otherwise) | 14,250 with float ≥$100M or 2011+ cover shares |
| quarterly rows | earliest-*filed* value per (start, end): no restatement look-ahead; Q4 = FY − 9M; Q1 = 6M − Q2 when a 10-Q is missing (ALKT Q1-26 is absent from companyfacts) | 447,815 |
| industry | `submissions.zip`: SIC code; 10-K/10-Q list; 8-K item 2.02 dates (earnings releases) | 14,250 |
| prices, listed today | yfinance (current ticker via SEC `company_tickers_exchange.json`, NYSE/Nasdaq/CBOE) | 6,006 tickers |
| **prices, delisted** | **HuggingFace `paperswithbacktest/Stocks-Daily-Price`** (30,515 symbols 2010-06→2026-10, incl. TWTR, ATVI, SIVB, FRC…). CIK→symbol via the ticker prefix of 10-K/10-Q document names or XBRL instance names (1,600 SEC index lookups), validated against reported public float | **2,296** of 3,677 delisted/OTC filers with float ≥$150M |
| insider trades | SEC Form 3/4/5 quarterly datasets 2011–2026 (open-market S/P codes) | 290k issuer-months |
| panel | month-end, as-of merge on the `filed` date; stale if the last quarter ended >200 days ago; mcap = cover-page shares (summed over classes; fall back to diluted weighted shares) × unadjusted close | 435,683 rows, 5,381 companies ≥$200M |

**Survivorship, quantified.**
- **Coverage.** Each year, the EDGAR filers whose own reported public float puts them in range ($0.3–7.5B float) are the point-in-time eligible set. The panel prices **84% (2011) → 96% (2025)** of them.
  - A survivors-only (yfinance) sample would price only **49% of the 2011 set** (891/1,828) and 50% of 2012.
  - Of the universe names in 2012–15, **41–44%** come from delisted symbols.
- **Effect of using survivors only.**
  - The 12m crash rate (−30%) is understated by about 21%: 8.2% vs 10.3% IS.
  - The gem IS spread is inflated by about 50%: 8.3% vs 5.5%.
  - The quality composite looks twice as strong OOS: t 5.4 vs 2.7.
  - The value composite's IS spread flips from +1.6% to −1.3%, because cheap names that were later acquired drop out.
  - **Every number below uses the full sample.**
- **Delisting return** = last traded price, then cash. Bankruptcy delistings that kept trading OTC are therefore slightly flattered.
- About 4–16% of eligible names per year are still unpriced: mostly pre-2016 delistings whose document names carry no ticker, or reused symbols.

**Data guards.**
- Share counts more than 20× off the company's own median are dropped (filers tagging in thousands, e.g. RPAY).
- Market caps with implausible daily turnover (<0.002% or >50%) are dropped.
- Forward returns are winsorized at +150/200/300/400% (1/3/6/12m) to neutralise bad splits in delisted bars.
- Commodity trusts, closed-end funds and SPACs are excluded.

## 1. Does peer-relative valuation predict returns? (Part 1)

**Universe.** US common stocks with market cap $300M–$10B at each month-end, 2011-06 → 2026-09. That is 1,400–2,075 names a month and 323k name-months.
- Peer group = 4-digit SIC, falling back to 3-, 2- or 1-digit when a month's group has fewer than 5 names.
- Signals are robust z-scores within the peer group: (x − peer median) / (1.4826·MAD), clipped at ±3.

**Signals** (sign: high = expected to outperform).

| signal | definition |
|---|---|
| EV/S vs growth (`evs_g`) | −residual of log(EV/TTM sales) on TTM revenue growth, regressed within each peer group and month ("cheap for its growth") |
| EV/EBIT, P/E, P/B, FCF yield | EBIT/EV, NI/mcap, book/mcap, (CFO − capex − capitalized software)/mcap |
| GP/A | TTM gross profit / assets |
| accruals | −(NI − CFO) / avg assets |
| F-score | Piotroski 9 (scaled when ≥6 components are available) |
| rev accel | last-Q yoy growth minus yoy growth two quarters earlier |
| dilution | −yoy change in diluted shares |
| leverage | −net debt / EBITDA (EBITDA ≤0 = worst) |
| Rule of 40 | software (SIC 737x) only: growth + FCF margin |
| margin trend | Δ TTM operating margin yoy (and Δ gross margin) |
| DSO | −Δ days sales outstanding yoy |
| adj-GAAP gap | −Δ (SBC + intangible amortization + restructuring) / revenue yoy |
| insiders | (open-market buys − sells, last 6 months) / mcap |
| composites | value = mean(EV/S-g, EV/EBIT, P/E, FCF yld); quality = mean(GP/A, accruals, F, margin trend); **gem = mean(EV/S-g, GP/A)**; risk_inv = mean(EV/S-g, accruals, accel, DSO, adj gap) |

**Test.** Each month, rank the peer z across the universe (or within a size bucket) and form quintiles.
- Return = **forward return minus the equal-weight mean of the same peer group**, so industry moves cancel.
- Spread = top minus bottom quintile, averaged monthly. t-stats are Newey-West with lag = horizon.
- IS = formation months 2012-01…2018-12. OOS = 2019-01…2026-09 (h months earlier for complete windows).
- BH at q = 0.10 over all 216 OOS tests: 24 signals × 3 horizons × 3 buckets.

### 1.1 Results: 12-month peer-relative quintile spread (top − bottom)

| signal | all IS | all OOS (t) | **small $0.3–2B** IS (t) | **small** OOS (t) | mid $2–10B IS (t) | mid OOS (t) |
|---|---|---|---|---|---|---|
| **gem (EV/S-g + GP/A)** | +2.9% (2.2) | **+5.6% (2.6)** | **+5.4% (3.8)** | **+7.2% (3.0) BH** | −1.3% (−0.7) | +3.9% (1.6) |
| EV/S vs growth | +2.0% (1.5) | +4.5% (1.5) | +3.9% (3.1) | +4.9% (2.1) | 0.0% | +3.5% (1.0) |
| GP/A | +4.2% (1.7) | +3.7% (1.8) | +6.5% (2.4) | +3.9% (1.3) | +0.3% | +3.1% (1.4) |
| quality | +1.0% (1.3) | +2.6% (2.7) | +0.8% (1.2) | +2.0% (2.0) | +1.1% (1.1) | +3.1% (2.7) |
| risk_inv (safe − risky) | +0.4% (0.5) | **+2.8% (3.2) BH** | −0.7% (−0.6) | +3.4% (2.9) | +1.6% (2.1) | +1.4% (1.5) |
| margin trend | +0.4% (0.5) | +4.3% (2.2) | +1.4% (1.3) | +4.8% (1.8) | −0.5% | +2.9% (1.7) |
| adj-GAAP gap narrowing | −0.7% (−1.3) | +2.7% (2.6) | −1.1% (−1.4) | +3.7% (2.2) | 0.0% | +1.3% (1.7) |
| value composite | +1.6% (1.0) | +0.4% (0.1) | +3.2% (1.7) | −0.5% (−0.1) | −2.1% (−1.2) | +1.5% (0.4) |
| P/E | +1.6% (1.1) | −1.0% (−0.3) | +2.6% (1.5) | −1.3% (−0.4) | −0.5% | +1.4% (0.5) |
| EV/EBIT | +1.0% (0.7) | +0.6% (0.1) | +2.3% (1.3) | −0.3% | −2.0% (−1.3) | +1.4% (0.4) |
| FCF yield | 0.0% | +0.6% (0.2) | +0.5% (0.3) | +0.7% (0.1) | −1.4% | +0.5% (0.1) |
| P/B | −0.1% | +2.8% (0.8) | −0.6% | +4.5% (1.2) | +0.6% | +0.8% (0.3) |
| Piotroski F | +0.1% | −0.2% | −0.4% | −1.1% | +0.3% | +1.0% (0.5) |
| accruals (low) | +0.1% | +1.2% (1.0) | −1.6% (−2.4) | +0.7% (0.5) | +2.3% (2.3) | +1.2% (1.1) |
| rev acceleration | −0.4% | −0.7% (−0.8) | −0.5% | −0.4% | −0.6% | −1.1% (−1.1) |
| dilution (low) | +1.4% (1.0) | +1.1% (0.3) | +1.1% (0.8) | +1.1% (0.3) | +1.7% (1.2) | +1.4% (0.4) |
| leverage (low) | −0.3% | −2.3% (−0.9) | +0.3% | −4.6% (−1.4) | −1.1% | +0.5% |
| Rule of 40 (software) | +4.2% (1.3) | −2.1% (−0.6) | +5.1% (1.4) | −5.3% (−1.0) | +2.5% (0.9) | −0.4% |
| DSO (falling) | −0.6% (−0.8) | +1.1% (1.2) | −0.8% | +1.9% (1.6) | 0.0% | +0.6% (0.5) |
| insiders (net buying) | +0.1% | +0.8% (0.4) | −0.4% | +1.8% (1.1) | +1.5% (1.1) | −0.9% (−0.5) |
| revenue growth itself | −0.4% | +2.7% (1.3) | −0.8% | +4.4% (1.9) | −0.1% | +1.3% (0.7) |

**OOS BH survivors (q = 0.10, 216 tests).**
- **Gem, small caps:** 6m +3.8% (t 3.2; IS +2.8%, t 3.2) and 12m +7.2% (t 3.0; IS +5.4%, t 3.8).
- **risk_inv, all, 12m:** +2.8% (t 3.2). IS is only +0.4% (t 0.5): same sign, weak.
- **Adj-GAAP-gap narrowing**, 3m small and 6m all/small: OOS t 3.2–3.5, but **IS is negative**. The sign flipped, so it is **not robust**.
  - Narrowing SBC, amortization and restructuring started paying only in the 2022+ SBC-backlash era.

**What survives:** the **gem** signal in $300M–$2B.
- Hit rates are below 50% (the top quintile beats its peer mean 45–47% of the time). The mean comes from right-skewed winners.
- Spread positive in 13 of 14 years. Only 2024 was negative (−2.5%). 2020: +15%, 2021–23: +9–10%/yr.

**Selection-risk caveat.** Gem was formed **after** the first run, by combining the two signals with the best IS t-stats at 6–12m (EV/S-g t 1.9–2.4 and GP/A t 1.8–2.9). The OOS columns were visible at the time.
- Both components are individually positive in both periods in small caps.
- Treat the composite's OOS t as about 2.5, not 3.0.

### 1.2 Size buckets: the owner's "too small for hedge funds" test

| gem quintile spread, peer-relative | 6m IS | 6m OOS | 12m IS | 12m OOS |
|---|---|---|---|---|
| $300M–$2B | **+2.8% (t 3.2)** | **+3.8% (t 3.2)** | **+5.4% (t 3.8)** | **+7.2% (t 3.0)** |
| $2–10B | −0.9% (t −1.2) | +2.9% (t 2.1) | −1.3% (t −0.7) | +3.9% (t 1.6) |
| small, top decile vs bottom decile | +2.9% (2.3) | +4.2% (3.2) | +6.3% (2.8) | +9.1% (3.2) |
| small, median $ volume ≥ $2M/day | +2.4% (2.3) | +3.0% (2.5) | +4.4% (2.9) | +5.7% (2.3) |
| small, median $ volume ≥ $10M/day | −1.6% (−1.0) | +2.9% (1.6) | −1.9% (−1.0) | +6.5% (1.5) |
| small, cap ≥ $750M | +1.3% (1.5) | +2.0% (1.2) | +2.2% (2.0) | +3.7% (1.2) |

**Verdict.** **Supported.** Growth-adjusted valuation works in the smallest, least-traded names and fades as size and liquidity rise. This is the mirror image of smallcap.md: the edge sits exactly where option spreads are widest.

### 1.3 The legs (what a long-only buyer gets)

| small caps, gem | IS top vs peers | OOS top vs peers | OOS bottom vs peers | OOS top raw 12m | OOS top hit | OOS top median |
|---|---|---|---|---|---|---|
| 6m | +2.1% (t 2.9) | +1.4% (t 1.3) | −2.5% | +6.9% | 46% | −2.8% |
| 12m | +4.1% (t 3.8) | +3.1% (t 1.6) | −4.2% | +14.5% (SPY same months +16.8%) | 45% | −4.6% |

Out of sample, the long leg alone is **not significant**. Half of the effect is the bottom leg underperforming.

### 1.4 The collapse side: can "overvalued + deteriorating" predict −30% falls?

Event = 12-month total return ≤ −30%. Base rates: **10.3% IS, 20.0% OOS** (2019+ small caps were brutal). Flags are the bottom decile of the peer z each month unless stated otherwise.

| flag | IS rate (lift) | OOS rate (lift) | OOS false-positive rate | **vol-matched lift** IS / OOS | 12m return vs same-vol names IS / OOS |
|---|---|---|---|---|---|
| expensive & unprofitable (value bottom decile) | 23.0% (1.81×) | 35.8% (1.58×) | 64% | 1.27 / 1.16 | −1.5 / +1.0 pts |
| value + quality combo bottom decile | 20.9% (1.69×) | 33.4% (1.53×) | 67% | 1.25 / 1.17 | −0.9 / −1.4 |
| **rich-for-growth + ≥3 of {accruals, decel, DSO↑, adj-gap↑, insider selling}** | 15.1% (1.46×) | 26.3% (1.32×) | 74% | 1.23 / 1.12 | +0.1 / −2.8 (t −1.0) |
| rich-for-growth + ≥2 of those | 13.2% (1.28×) | 23.9% (1.19×) | 76% | 1.12 / 1.07 | −1.0 / −2.7 (t −1.4) |
| risk score bottom decile | 10.9% (1.15×) | 21.0% (1.16×) | 79% | 1.15 / 1.08 | −0.8 / −1.7 (t −2.3) |
| rich for growth (EV/S-g bottom decile) | 13.7% (1.18×) | 23.1% (1.14×) | 77% | 1.15 / 1.07 | −2.3 (t −2.4) / −1.6 |
| revenue deceleration | 13.2% (1.38×) | 21.3% (1.17×) | 79% | | |
| DSO rising | 15.4% (1.38×) | 23.9% (1.21×) | 76% | | |
| adj-GAAP gap widening | 12.5% (1.32×) | 23.6% (1.31×) | 76% | | |
| low F-score | 13.1% (1.30×) | 24.4% (1.28×) | 76% | | |
| high dilution | 12.3% (1.38×) | 27.3% (1.47×) | 73% | | |
| high accruals | 9.9% (0.98×) | 19.8% (1.03×) | 80% | | |
| insider net selling | 11.0% (1.06×) | 21.3% (1.06×) | 79% | | |

By size, rich + ≥3 flags: OOS lift 1.42× in small caps vs 1.32× in mid.

**Reading.**
- Every "deterioration" flag raises crash odds, as forensic_events.md also found.
- But flagged names are simply **more volatile**. Against same-month, same-realized-vol-decile names the lift is 1.07–1.27×, and the average return gap is −1 to −3 points over 12 months, mostly insignificant.
- A put is priced on volatility, so the extra crash odds are already in the premium (§4: puts lose 41–62%).
- Classic earnings-quality red flags (accruals, insider selling) add **nothing**.

## 2. Case study: Fiserv (FI/FISV) and Alkami (ALKT) (Part 2)

### 2.1 Fiserv: what happened

Prices are from yfinance, adjusted.

| date | close | event |
|---|---|---|
| 2025-03-03 | **$237.79** | all-time high (market cap ≈ $130B: a mega-cap, outside the owner's universe) |
| 2025-04-24 | −18.5% in a day | Q1-25 earnings (8-K 2.02) |
| 2025-07-23 | −13.8% | Q2-25 earnings |
| 2025-09-30 | $128.93 | |
| **2025-10-29** | **−44.0% in a day** ($126 → $70.60) | Q3-25 earnings and guidance reset |
| 2026-05-05 / 06-15 | −8.8% / −10.9% | continued slide |
| 2026-10-14 | **$46.07** | **−81% from peak**; low $44.36 on 2026-10-02 |

### 2.2 Did the signals flag it beforehand, using only data filed before each drop?

The peer set is 32 fintech/payments names, including delisted MLNK, EPAY, EVOP and PAYA. "Peer z" = (Fiserv − peer median) / MAD.

Each row is the panel at that month-end. The quarter shown is the latest one *filed* by then. Each 10-Q came out the day **after** the earnings drop, so before each drop the market had only the previous quarter.

| as of | quarter (filed) | rev g TTM | last-Q yoy | op margin (Δ yoy) | CFO / NI | accruals / assets | DSO (Δ) | EV/S | **EV/S vs growth, peer z** | op-margin peer z | FCF yield |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024-09 | Q2-24 | 7.2% | 7.4% | 28.1% (+5.9) | 1.5 | −2.2% | 69 (+0.5) | 6.4× | +0.67 | +1.00 | 3.7% |
| 2024-12 | Q3-24 | 7.0% | 7.0% | 28.1% (+2.9) | 2.0 | −3.6% | 67 (+0.2) | 6.9× | +0.76 | +1.00 | 3.8% |
| **2025-03** (pre-Apr drop) | Q4-24 (2025-02-20) | 7.1% | 6.8% | 28.7% (+2.5) | 2.1 | −4.2% | 66 (−2.0) | **7.1×** | **+1.02** | +1.04 | 4.1% |
| **2025-06** (pre-Jul drop) | Q1-25 (2025-04-25) | 6.6% | 5.1% | 29.4% (+2.4) | 2.0 | −3.7% | 69 (+2.2) | 5.8× | +0.82 | +1.30 | 5.2% |
| **2025-09** (pre-Oct drop) | Q2-25 (2025-07-24) | 6.7% | **8.0%** | 30.1% (+2.0) | 2.0 | −3.9% | 71 (+2.1) | 4.6× | +0.25 | +1.35 | 7.4% |
| 2025-12 (after) | Q3-25 (2025-10-30) | 5.2% | 0.9% | 29.3% (+1.2) | 1.8 | −3.4% | 68 | 3.0× | −0.04 | +1.32 | 12.8% |
| 2026-09 (after) | Q2-26 | **−1.2%** | **−4.1%** | **22.3% (−7.8)** | 2.1 | −3.7% | 68 | 2.4× | +0.32 | +1.21 | 16.3% |

**Reading.**
- Before the drops, every quality measure the owner suggested looked **fine or better than peers**:
  - growth steady at about 7%;
  - margins rising;
  - cash flow 2× earnings;
  - receivables flat;
  - shares shrinking 5%/yr.
- The only red flag was **valuation**: 7.1× sales for 7% growth, the richest-for-growth third of fintech in Mar-25. In its Part-1 SIC group (7389, business services NEC), the EV/S-vs-growth z was −1.43 in Jan-25.
- The collapse was about **forward guidance**. That covered the Clover merchant business and the make-up of "organic" growth, both non-GAAP segment metrics that GAAP XBRL totals never show.
- The GAAP deterioration appears only in the filings made **after** each drop.

**False positives.** Part 1's collapse score was computed on all US names ≥$300M (Fiserv is a large cap).

| pre-drop month | Fiserv's risk-score percentile | names scoring as badly or worse | of which fell ≥30% in the next 6m | Fiserv's next 6m |
|---|---|---|---|---|
| 2025-03 | 46th (unflagged) | 994 | 29 (2.9%) | −41.6% |
| 2025-06 | 37th | 815 | 49 (6.0%) | −61.0% |
| 2025-09 | 37th | 820 | 112 (13.7%) | −56.7% |

- Across 2012–2025, a risk score as bad as Fiserv's preceded a −30% 12-month fall **12.2–12.5%** of the time, against a 12.4% base. That is **zero information and an ~88% false-positive rate**.
- Using only Fiserv's one real flag (rich for its growth, bottom decile), 13.7% (IS) and 23.1% (OOS) fell 30%, against bases of 11.6% and 20.3%. That is a **77–86% false-positive rate**.
- **Hindsight verdict:** a screen that "caught" Fiserv would also have flagged hundreds of names a month that did fine. The drop was not knowable from filed fundamentals.

### 2.3 Alkami vs peers today (2026-10-14)

- ALKT is at **$13.73** (market cap $1.47B). Its Part-1 peer group is SIC 7372 (prepackaged software).
- In the fintech set, EV/S-vs-growth residual: −0.11 (slightly cheap for its growth).
- **Gem z +0.27** (about the 60th percentile): EV/S-g z +0.85, GP/A z −0.31.
- Profile z-scores: revenue growth +1.19, margin trend +0.23, dilution −0.46, **revenue acceleration −3.0**.

**Fintech / digital-banking competitor comparison** (TTM from the latest filing; options = live chains, 3–6-month ATM):

| ticker | cap $B | rev g TTM | last-Q yoy | gross mgn | op mgn (GAAP) | FCF mgn | EV/S | EV/S resid vs growth | FCF yld | SBC/rev | dilution yoy | CFO/NI | DSO | 3-6m spread | OI 3-6m | next earn | gem z |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ALKT | 1.5 | 27% | 16% | 57% | -7% | – | 2.9 | -0.11 | – | 15% | 3.4% | – | 42 | 20% | 1,552 | 2026-10-28 | 0.27 |
| QTWO | 3.7 | 14% | 13% | 57% | 10% | 22% | 4.2 | 0.52 | 5.1% | 10% | -6.1% | 2.5 | 30 | 34% | 108 | 2026-11-04 | 0.09 |
| NCNO | 2.1 | 9% | 8% | 62% | 8% | 21% | 3.6 | 0.48 | 6.4% | 11% | -8.6% | 4.0 | 72 | 38% | 395 | 2026-12-02 | -0.51 |
| JKHY | 10.8 | 7% | 5% | 44% | 25% | 20% | 4.3 | 0.67 | 4.7% | 1% | -1.4% | 1.5 | 50 | 25% | 639 | 2026-11-03 | – |
| ACIW | 5.1 | 7% | 7% | 49% | 19% | 17% | 3.1 | 0.36 | 6.1% | 4% | -3.3% | 1.5 | 92 | 79% | 175 | 2026-11-05 | -0.28 |
| FIS | 18.1 | 18% | 29% | 36% | 16% | 16% | 3.2 | 0.14 | 10.6% | 2% | -1.5% | 0.9 | – | 17% | 10,009 | 2026-11-03 | – |
| FISV | 24.5 | -1% | -4% | – | 22% | 19% | 2.4 | 0.26 | 16.1% | 2% | -3.4% | 2.1 | 68 | 8% | 50,033 | 2026-11-03 | – |
| GPN | 21.2 | 8% | 70% | 64% | 12% | 8% | 3.8 | 0.55 | 3.9% | 1% | 10.9% | – | 56 | 15% | 19,359 | 2026-11-03 | – |
| EVTC | 1.8 | 12% | 20% | – | 18% | 21% | 2.8 | 0.15 | 11.4% | 3% | -5.3% | 2.4 | 67 | 43% | 12 | 2026-11-04 | – |
| PAYO | 2.4 | 6% | 5% | – | 10% | 11% | – | – | 4.8% | 7% | -11.3% | 4.4 | 4 | 124% | 3,298 | 2026-11-04 | – |
| MQ | 1.9 | 22% | 17% | 70% | -2% | 25% | 1.4 | -0.75 | 8.7% | 14% | -76.9% | 19.3 | 27 | 47% | 2,567 | 2026-11-03 | 0.91 |
| FLYW | 2.2 | 32% | 27% | – | 6% | 22% | 2.6 | -0.31 | 7.3% | 10% | 0.4% | 4.7 | 20 | 47% | 18,499 | 2026-11-03 | – |
| CASS | 0.7 | 4% | 12% | – | – | 21% | 1.4 | -0.41 | 6.1% | 2% | -3.3% | 1.3 | – | 145% | 24 | 2026-10-22 | – |
| PRTH | 0.6 | 9% | 9% | 39% | 14% | 10% | 0.4 | -1.70 | 16.1% | 1% | 5.0% | 2.3 | 34 | 43% | 1,074 | 2026-11-05 | 0.68 |
| IIIV | 0.3 | -8% | 2% | – | 3% | 19% | 1.9 | 0.18 | 13.3% | 8% | -42.4% | 6.1 | 81 | 107% | 32 | 2026-11-19 | – |
| TOST | 17.4 | 23% | 23% | 27% | 6% | 8% | 2.4 | -0.24 | 3.3% | 3% | -2.5% | 1.3 | 8 | 17% | 74,837 | 2026-11-03 | – |
| SSNC | 19.2 | 9% | 10% | 48% | 24% | 27% | 3.6 | 0.46 | 9.1% | 4% | -4.0% | 2.1 | 57 | 28% | 1,097 | 2026-10-22 | – |
| BR | 19.1 | 9% | 7% | 32% | 17% | 16% | 2.9 | 0.27 | 6.5% | 1% | -1.0% | 1.2 | – | 20% | 5,535 | 2026-11-03 | – |

Notes:
- FISV, FIS, GPN, JKHY, TOST, SSNC and BR are >$10B, outside the Part-1 universe, so they have no gem score.
- GPN and FIS growth reflects the 2026 Worldpay / issuer-business swap.
- ALKT's FCF margin is blank because companyfacts lacks its Q1-26 10-Q. The last full TTM (Q4-25) was **FCF $34M, 7.7% of revenue**.

**Alkami, on the owner's metrics.**
- **Revenue.** Cheapest-for-growth digital-banking vendor: 2.9× sales at 27% growth, against Q2 4.2×/14%, nCino 3.6×/9% and Jack Henry 4.3×/7%. **But:**
  - growth is inflated by the Mantl acquisition (2025) and is decelerating fast: last quarter +16% yoy, the worst acceleration z in software;
  - GAAP operating margin −7% (improving 6 pts a year);
  - stock comp 15% of revenue, the highest in the set;
  - dilution +3.4%/yr.
- **P/E.** Not meaningful (GAAP losses).
- **Analogs.** The 300 nearest historical profiles in the $300M–$10B universe (same z-vector, 141 months): 12m peer-relative **+1.3%** vs +0.7% for all names (t 0.4); hit 44% vs 47%; −30% crash rate 13.7% vs 14.7%. **No edge either way.**
- **Options.** ATM 3–6m spread 20%, OI 1,552, next earnings 2026-10-28, and **no LEAPS listed** (last expiry 2027-03).
- **Filings.** Several Schedule 13D filings (non-passive >5% holders) in Mar–Jun 2026 are worth reading before any position. They are not analyzed here.

## 3. Current screen: "gems" and "rich" names (Part 3)

- **Ranking.** The signal that survived Part 1 (gem: EV/S-vs-growth plus GP/A, peer z), applied to today's $300M–$10B universe (1,916 names, latest filings as of 2026-10-14).
  - **Evidence is strong only for $300M–$2B.** Mid caps are unproven in-sample.
  - "Rich" = lowest gem score: expensive for its growth and unprofitable vs peers.
- **Peer medians.** In parentheses: the same peer group (SIC 4-digit, or the fallback level shown).
- **Competitors.** The 3 nearest-size names in that peer group.
- **Options.** Live yfinance chains, 60–200 DTE, ATM ± 20% strikes. Spread = (ask − bid)/mid at the ATM strike.
  - Chains were pulled 15:55–16:10 ET, so some quotes are closing quotes and spreads may be overstated (smallcap.md measured 44% midday at 37 DTE).
- **Earnings.** Next date from Yahoo.

### 3.1 Top-20 "undervalued vs peers" (high gem)

| # | ticker | name | cap $B | peer group (SIC) | gem z (EV/S-vs-growth z, GP/A z) | EV/S (peer med) | rev g (peer) | GP/A (peer) | op mgn (peer) | FCF yld (peer) | competitors | 3-6m ATM spread | OI / vol (3-6m, ±20%) | 6m ATM call | next earnings |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | UPBD | Upbound Group, Inc. | 0.89 | s3_735 Services-Equipment Rental & Le | +2.84 (+2.7, +3.0) | 0.2 (2.5) | 6% (6%) | 0.75 (0.20) | 5% (8%) | 43% (23%) | NPKI, PRG, CTOS | 52% | 1,294 / 89 | $205 | 2026-10-29 |
| 2 | KSS | KOHL’S CORP | 2.37 | s1_5 Retail-Department Stores | +2.46 (+1.9, +3.0) | 0.2 (0.8) | -3% (3%) | 0.47 (0.38) | 4% (6%) | 44% (8%) | RH, BOBS, ARHS | 10% | 23,381 / 1,581 | $330 | 2026-11-24 |
| 3 | ACEL | Accel Entertainment, Inc. | 0.90 | s4_7900 Services-Amusement & Recreatio | +2.23 (+1.5, +3.0) | 0.9 (2.9) | 9% (9%) | 1.26 (0.25) | 8% (-9%) | 9% (7%) | FUN, LUCK, RSVR | 81% | 241 / 556 | $70 | 2026-11-03 |
| 4 | M | Macy's, Inc. | 5.86 | s1_5 Retail-Department Stores | +2.19 (+1.4, +3.0) | 0.3 (0.8) | 0% (3%) | 0.59 (0.38) | 5% (6%) | 18% (8%) | OLLI, BLDR, PSMT | 11% | 40,899 / 1,967 | $261 | 2026-12-02 |
| 5 | UNFI | UNITED NATURAL FOODS, INC. | 2.85 | s2_51 Wholesale-Groceries, General L | +2.19 (+1.5, +2.8) | 0.1 (0.6) | -2% (-0%) | 0.59 (0.25) | 1% (4%) | 11% (11%) | HWKN, CENT, ANDE | 27% | 2,144 / 135 | – | 2026-12-01 |
| 6 | TNC | TENNANT CO | 1.12 | s4_3580 Refrigeration & Service Indust | +2.15 (+1.3, +3.0) | 1.2 (2.2) | -3% (8%) | 0.37 (0.23) | 3% (19%) | -0% (3%) | MFP, HAYW, SXI | 62% | 33 / 15 | $1,240 | 2026-11-02 |
| 7 | TLS | TELOS CORPORATION | 0.31 | s4_7373 Services-Computer Integrated S | +2.11 (+3.0, +1.2) | 1.3 (2.4) | 66% (6%) | 0.51 (0.27) | -10% (11%) | 8% (6%) | VEEA, OSPN, KD | 72% | 886 / 71 | $70 | 2026-11-09 |
| 8 | CMPR | Cimpress plc | 1.79 | s2_27 Commercial Printing | +2.09 (+1.2, +3.0) | 0.8 (0.8) | 10% (-0%) | 0.79 (0.41) | 7% (9%) | 7% (9%) | WBTN, MH, WLY | 33% | 41 / 9 | $2,840 | 2026-10-28 |
| 9 | NRDS | NerdWallet, Inc. | 0.63 | s4_7374 Services-Computer Processing & | +2.07 (+1.1, +3.0) | 0.7 (2.1) | 12% (9%) | 1.92 (0.54) | 10% (9%) | 23% (10%) | IBEX, YEXT, OOMA | 32% | 1,404 / 449 | $150 | 2026-11-05 |
| 10 | MYGN | MYRIAD GENETICS, INC. | 0.41 | s4_2835 In Vitro & In Vivo Diagnostic  | +2.06 (+1.1, +3.0) | 0.5 (4.5) | -3% (-0%) | 0.87 (0.21) | -12% (-31%) | 2% (-4%) | TKNO, ACHV, QDEL | 101% | 238 / 24 | $130 | 2026-11-02 |
| 11 | CRCT | Cricut, Inc. | 1.37 | s4_3559 Special Industry Machinery, NE | +1.97 (+0.9, +3.0) | 1.6 (2.8) | -3% (-3%) | 0.68 (0.23) | 15% (11%) | 13% (2%) | AZTA, VECO, ACLS | 48% | 230 / 16 | $60 | 2026-11-03 |
| 12 | BCRX | BIOCRYST PHARMACEUTICALS, IN | 2.04 | s4_2836 Biological Products, (No Diagn | +1.92 (+0.8, +3.0) | 2.2 (7.1) | 69% (23%) | 1.65 (0.36) | -33% (-94%) | 18% (-8%) | VCEL, RXRX, NVAX | 67% | 9,412 / 258 | $210 | 2026-11-02 |
| 13 | REAL | TheRealReal, Inc. | 1.11 | s4_5900 Retail-Miscellaneous Retail | +1.90 (+0.8, +3.0) | 1.5 (1.8) | 18% (18%) | 1.48 (0.45) | -1% (11%) | 2% (5%) | WINA, SVV, EZPW | 13% | 14,572 / 77 | $125 | 2026-11-09 |
| 14 | YELP | YELP INC | 1.04 | s1_7 Services-Personal Services | +1.88 (+0.8, +3.0) | 0.7 (1.4) | 2% (1%) | 1.33 (0.29) | 12% (12%) | 29% (9%) | DRVN, CSV, MNRO | 58% | 750 / 60 | $310 | 2026-11-05 |
| 15 | NGL | NGL Energy Partners LP | 1.83 | s4_4922 Natural Gas Transmission | +1.87 (+0.7, +3.0) | 1.4 (4.6) | -22% (10%) | 0.25 (0.17) | 4% (19%) | 6% (6%) | KNTK, KGS, AROC | 45% | 260 / 138 | $320 | 2026-11-03 |
| 16 | WEAV | Weave Communications, Inc. | 0.59 | s4_7372 Services-Prepackaged Software | +1.86 (+1.1, +2.6) | 2.1 (3.6) | 17% (14%) | 0.89 (0.40) | -8% (2%) | 2% (5%) | BLZE, GDYN, CCSI | 25% | 1,258 / 13 | $45 | 2026-11-05 |
| 17 | SPT | Sprout Social, Inc. | 0.67 | s4_7372 Services-Prepackaged Software | +1.86 (+2.1, +1.7) | 1.2 (3.6) | 12% (14%) | 0.71 (0.40) | -6% (2%) | 8% (5%) | CCSI, GDYN, RCAT | 38% | 1,365 / 260 | $340 | 2026-11-03 |
| 18 | ZIP | ZIPRECRUITER, INC. | 0.36 | s4_7370 Services-Computer Programming, | +1.85 (+0.7, +3.0) | 1.0 (2.2) | 0% (9%) | 1.25 (0.38) | 0% (1%) | 4% (6%) | BMBL, RXT, PUBM | 66% | 767 / 4 | $120 | 2026-11-04 |
| 19 | VISN | Vistance Networks, Inc. | 1.36 | s4_3663 Radio & Tv Broadcasting & Comm | +1.85 (+2.3, +1.4) | 0.4 (11.2) | -38% (44%) | 0.36 (0.14) | 11% (-43%) | 6% (-5%) | HLIT, UMAC, BKSY | 33% | 2,649 / 157 | $70 | 2026-10-29 |
| 20 | ORN | ORION GROUP HOLDINGS, INC. | 0.34 | s4_1600 Heavy Construction Other Than  | +1.84 (+0.7, +3.0) | 0.5 (0.9) | 7% (7%) | 0.23 (0.16) | 1% (6%) | -1% (4%) | KBR, ROAD, GVA | 76% | 270 / 19 | $330 | 2026-10-27 |

Data caveats:
- **KSS, M (and RH on the other list)** fall back to a broad retail peer group (SIC division 5).
- **UPBD's** GP/A is inflated by lease-to-own accounting.
- **VISN's** revenue (−38%) and EV reflect a divestiture.
- **NGL** is an MLP.
- **BCRX and MYGN** are compared with mostly pre-revenue biotech or diagnostics peers.
- Many of these are **out-of-favor retailers and consumer names**: the factor buys gross profit cheaply, which is what it historically paid for.

### 3.2 Top-20 "overvalued / at-risk vs peers" (low gem)

| # | ticker | name | cap $B | peer group (SIC) | gem z (EV/S-vs-growth z, GP/A z) | EV/S (peer med) | rev g (peer) | GP/A (peer) | op mgn (peer) | FCF yld (peer) | competitors | 3-6m ATM spread | OI / vol (3-6m, ±20%) | 6m ATM call | next earnings |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AVR | Anteris Technologies Global  | 0.60 | s4_3842 Orthopedic, Prosthetic & Surgi | -2.63 (-2.6, -2.7) | 151.8 (3.5) | -10% (10%) | 0.01 (0.36) | -4738% (0%) | -15% (3%) | ENOV, CDRE, SMTI | 70% | 293 / 17 | $100 | 2026-11-12 |
| 2 | KYMR | KYMERA THERAPEUTICS, INC. | 8.89 | s4_2836 Biological Products, (No Diagn | -2.36 (-2.0, -2.7) | 78.1 (7.1) | 135% (23%) | 0.00 (0.36) | -334% (-94%) | -3% (-8%) | TWST, KRYS, IMVT | 15% | 3,585 / 593 | $3,550 | 2026-11-03 |
| 3 | UAMY | UNITED STATES ANTIMONY CORPO | 0.41 | s2_33 Primary Smelting & Refining of | -2.26 (-1.8, -2.7) | 10.2 (1.1) | 36% (15%) | 0.03 (0.22) | -64% (8%) | -17% (5%) | MATW, NX, KALU | 19% | 10,051 / 218 | $80 | 2026-11-16 |
| 4 | DJT | Trump Media & Technology Gro | 2.02 | s4_7370 Services-Computer Programming, | -2.23 (-3.0, -1.5) | 606.2 (2.2) | 22% (9%) | 0.00 (0.38) | -20956% (1%) | 0% (6%) | DV, CSQR, RUM | 12% | 17,521 / 4,989 | $173 | 2026-11-06 |
| 5 | AUR | Aurora Innovation, Inc. | 9.80 | s4_7373 Services-Computer Integrated S | -2.21 (-3.0, -1.5) | 1929.4 (2.4) | 400% (6%) | -0.01 (0.27) | -19400% (11%) | -8% (6%) | OTEX, SAIC, WAY | 14% | 37,764 / 3,997 | $105 | 2026-10-28 |
| 6 | QBTS | D-Wave Quantum Inc. | 4.44 | s4_7374 Services-Computer Processing & | -2.18 (-3.0, -1.4) | 316.6 (2.1) | -44% (9%) | 0.01 (0.54) | -1373% (9%) | -3% (10%) | PEGA, LIF, APLD | 9% | 37,811 / 24,308 | $220 | 2026-11-05 |
| 7 | BBAI | BigBear.ai Holdings, Inc. | 1.05 | s4_7372 Services-Prepackaged Software | -2.18 (-2.5, -1.8) | 7.8 (3.6) | -14% (14%) | 0.04 (0.40) | -118% (2%) | -7% (5%) | GTM, RDVT, COUR | 42% | 28,416 / 1,404 | $71 | 2026-10-27 |
| 8 | SLN | Silence Therapeutics plc | 1.28 | s4_2834 Pharmaceutical Preparations | -2.17 (-3.0, -1.3) | 1964.0 (5.7) | -98% (16%) | 0.00 (0.40) | -11107% (-22%) | -3% (-5%) | QURE, NKTR, SNDX | 177% | 153 / 101 | $490 | 2026-11-05 |
| 9 | LAUR | Laureate Education, Inc. | 5.40 | s4_8200 Services-Educational Services | -2.15 (-3.0, -1.3) | 3.0 (1.3) | 18% (7%) | 0.21 (0.52) | 24% (14%) | 5% (7%) | GHC, CVSA, LOPE | 64% | 83 / 19 | $420 | 2026-10-29 |
| 10 | QUBT | QUANTUM COMPUTING INC. | 1.45 | s4_7372 Services-Prepackaged Software | -2.12 (-2.2, -2.1) | 50.1 (3.6) | 3635% (14%) | -0.00 (0.40) | -775% (2%) | -4% (5%) | CERT, ALKT, XZO | 17% | 43,141 / 5,298 | $145 | 2026-11-09 |
| 11 | LBTYA | Liberty Global Ltd. | 2.79 | s2_48 Cable & Other Pay Television S | -2.11 (-1.2, -3.0) | 1.8 (1.8) | -11% (-5%) | 0.15 (0.28) | -2% (5%) | -9% (16%) | ADEA, ZD, LILA | 79% | 10,628 / 267 | $50 | 2026-11-03 |
| 12 | AI | C3.ai, Inc. | 1.80 | s4_7372 Services-Prepackaged Software | -2.06 (-2.4, -1.7) | 4.9 (3.6) | -38% (14%) | 0.08 (0.40) | -203% (2%) | -9% (5%) | PDFS, LIME, BL | 11% | 38,806 / 959 | $179 | 2026-12-09 |
| 13 | AEVA | AEVA TECHNOLOGIES, INC. | 0.75 | s4_3714 Motor Vehicle Parts & Accessor | -2.02 (-1.9, -2.2) | 26.6 (0.7) | 56% (6%) | 0.03 (0.23) | -611% (7%) | -16% (8%) | SMP, THRM, DCH | 29% | 7,436 / 189 | $400 | 2026-11-04 |
| 14 | SG | SWEETGREEN, INC. | 1.18 | s4_5812 Retail-Eating  Places | -1.97 (-1.1, -2.8) | 1.5 (1.2) | -1% (5%) | 0.09 (0.89) | -21% (4%) | -10% (4%) | BJRI, CBRL, BLMN | 15% | 12,231 / 178 | $245 | 2026-11-05 |
| 15 | NN | NextNav Inc. | 1.79 | s2_38 Search, Detection, Navigation, | -1.95 (-2.5, -1.4) | 393.7 (2.4) | -36% (9%) | -0.01 (0.52) | -1900% (4%) | -3% (2%) | LUNR, EYE, IMAX | 23% | 12,706 / 1,351 | $295 | 2026-11-05 |
| 16 | BZH | BEAZER HOMES USA INC | 0.89 | s4_1531 Operative Builders | -1.91 (-3.0, -0.8) | 1.0 (0.6) | -13% (-10%) | 0.09 (0.19) | -2% (8%) | -17% (4%) | LGIH, DFH, HOV | 83% | 4,815 / 5,504 | – | 2026-11-12 |
| 17 | RH | RH | 2.06 | s1_5 Retail-Furniture Stores | -1.88 (-0.8, -3.0) | 1.2 (0.8) | 3% (3%) | 0.30 (0.38) | 10% (6%) | 12% (8%) | KSS, BOBS, ARHS | 14% | 5,153 / 733 | $2,080 | 2026-12-10 |
| 18 | CVSA | Covista Inc. | 4.39 | s4_8200 Services-Educational Services | -1.81 (-3.0, -0.6) | 2.4 (1.3) | 9% (7%) | 0.37 (0.52) | 20% (14%) | 9% (7%) | LOPE, GHC, LAUR | 28% | 209 / 84 | $1,550 | 2026-10-29 |
| 19 | FEIM | FREQUENCY ELECTRONICS, INC. | 0.80 | s4_3825 Instruments For Meas & Testing | -1.79 (-2.5, -1.0) | 10.1 (3.2) | 6% (11%) | 0.16 (0.23) | 3% (3%) | -0% (2%) | TRNS, ALNT, COHU | 29% | 163 / 20 | $1,550 | 2026-12-10 |
| 20 | PSNL | Personalis, Inc. | 1.70 | s4_8071 Services-Medical Laboratories | -1.78 (-2.3, -1.3) | 21.3 (5.7) | -13% (17%) | 0.03 (0.19) | -164% (-0%) | -6% (1%) | FTRE, CSTL, LMRI | 157% | 15,878 / 101 | $490 | 2026-11-03 |

- **Pre-revenue and story stocks dominate** (EV/S of 50–1,900× in AUR, QBTS, QUBT, DJT, SLN, KYMR, AVR).
- These have the **most liquid** puts (9–17% spreads), but §1.4 and §4 show the put premium already prices their volatility.
- **No company is accused of anything.**

### 3.3 Sector dives (gem z within the 4-digit SIC group, $300M–$10B)

| sector (names) | peer median EV/S · growth · op margin | cheapest for growth + profitability (gem z) | richest (gem z) |
|---|---|---|---|
| Prepackaged software 7372 (68) | 3.6× · 14% · 2% | WEAV +1.86, SPT +1.86, ASAN +1.56, RPD +1.35, KVYO +1.32, TDC +1.28 (… ALKT +0.27, QTWO +0.09) | QUBT −2.12, BBAI −2.18, AI −2.06, SOUN −0.88 |
| Semiconductors 3674 (36) | 4.4× · 19% · −4% | CRUS +1.07, ARRY +0.81, AOSL +0.68, KLIC +0.57, MRAM +0.55, SEDG +0.54 | NVTS −1.71, AXTI −1.37, AAOI −0.80, WOLF −0.69, AMBQ −0.61 |
| Pharma preparations 2834 (156) | 5.7× · 16% · −22% | PBYI +1.32, EOLS +1.20, INDV +1.07, ARDX +1.03, ACAD +0.74, AXSM +0.67 | mostly pre-revenue (no gem score) |
| Fintech / digital banking (§2.3) | | MQ +0.91, PRTH +0.68, ALKT +0.27, QTWO +0.09 | NCNO −0.51, ACIW −0.28 |

## 4. Option economics (Part 4)

**Setup.**
- **Entries.** Month-end. Calls on the gem **top quintile** within each size bucket; puts on the **bottom quintile**. IS 2012–18, OOS 2019–26.
- **Pricing.** Black–Scholes. IV = 3-month realized vol × **today's measured IV/RV**: 1.47 for $300M–$2B and 1.31 for $2–10B (median of a 200-name random sample of the universe; 93% of small caps have listed options). Exit IV = exit-month RV × the same ratio.
- **Costs.** Buy at mid × (1 + s/2), sell at mid × (1 − s/2). s = today's median ATM spread:
  - 3–6m: **59%** small (IQR 38–101%), **30%** mid (18–53%);
  - LEAPS: **42%** small, **19%** mid.
- **"Excess"** = the signal's option return minus the same structure bought on *every* name in that bucket the same month (Newey–West t).

| structure | bucket | IS EV | **OOS EV** | OOS median | OOS hit | OOS excess vs random names (t) | contract (median) |
|---|---|---|---|---|---|---|---|
| 3m ATM call, hold to expiry | small | −49% | **−56%** | −100% | 16% | −0.1 (−0.1) | $316 |
| 6m call, sell at 3m | small | −42% | **−48%** | −62% | 14% | −0.4 (−0.6) | $448 |
| 6m call, hold 6m | small | −43% | −52% | −100% | 18% | +0.6 (0.5) | $451 |
| 12m LEAPS, sell at 6m | small | −26% | **−34%** | −54% | 21% | −0.1 (−0.1) | $595 |
| 12m LEAPS, hold 12m | small | −21% | −37% | −97% | 23% | +0.2 (0.1) | $601 |
| 3m call | mid | −30% | −31% | −87% | 28% | +2.4 (1.9) | $620 |
| 6m call, sell at 3m | mid | −24% | −23% | −44% | 28% | +1.8 (2.0) | $885 |
| 12m LEAPS, sell at 6m | mid | −8% | **−9%** | −33% | 33% | +2.5 (1.8) | $1,194 |
| 12m LEAPS, hold 12m | mid | +1% | −9% | −74% | 32% | +2.9 (1.3); IS **−10.2 (−4.8)** | $1,194 |
| 3m put (bottom quintile) | small | −65% | −62% | −98% | 13% | +1.9 (2.6) | $304 |
| 6m put | small | −68% | −62% | −94% | 13% | +2.8 (3.6) | $418 |
| 12m put | small | −64% | −53% | −90% | 19% | **+4.9 (4.5)**; IS +5.0 (4.5) | $529 |
| 12m put | mid | −55% | −41% | −100% | 25% | +3.9 (2.3) | $1,039 |

**Sensitivity** (OOS EV per trade):

| structure | measured | half spread | mid fill | IV +20% | IV −20% |
|---|---|---|---|---|---|
| small 6m call, sell at 3m | −48% | −29% | −4% | −50% | −43% |
| small 12m LEAPS, sell at 6m | −34% | −18% | +2% | −37% | −28% |
| mid 6m call, sell at 3m | −23% | −11% | +4% | −28% | −16% |
| **mid 12m LEAPS, sell at 6m** | −9% | **+1%** | **+11%** | −14% | 0% |
| mid 12m LEAPS, hold 12m | −9% | 0% | +11% | −23% | +11% |
| small 12m put | −53% | −42% | −29% | −61% | −41% |

**"Enter only within N days before earnings"** (an 8-K 2.02 release within 30 days of entry, OOS):
- small 6m calls −45% (excess +0.3);
- mid 6m calls −23% (+2.3, t 1.3);
- small 12m LEAPS −32% (0.0);
- small 12m puts −52% (+4.5, t 2.5).
- **No improvement.** Earnings-window entries also pay event IV, which this RV-based model does not even charge.

**Stock benchmark** (same entries; the owner's account cannot hold stock).

| | top-quintile gem stock, small: 3m / 6m / 12m | SPY, same months | top − bottom (peer-relative), 12m |
|---|---|---|---|
| IS 2012–18 | +4.7% / +9.2% / **+18.5%** | +3.3% / +6.8% / +14.1% | +5.4% |
| OOS 2019–26 | +3.3% / +6.9% / **+14.6%** | +4.1% / +8.3% / **+16.8%** | **+7.2%** |

- The stock version beats peers but **lags buy-and-hold SPY out of sample**: small caps lagged large caps 2019–26.
- The 7%/yr edge is a long/short, peer-neutral return.

**Why the options fail.**
- Today's top-20 gem names need a median **+21% move in ~5 months** just to break even on an ATM call bought at the ask. The median ask is 16.7% of spot, at IV 46–93%.
- Historically the top quintile returned **+6.9%** in 6 months and beat its peers by 1.4%.
- A 3%/yr peer-relative edge with a 45% hit rate is an order of magnitude smaller than option premium plus spread.

**Bankroll.** 3 years. Each round draws a random OOS entry month and buys k of that month's signal names (whole contracts; one contract allowed if it costs ≤60% of equity); 10k paths. Ruin = <12% of start.

| structure | $170, 1 position: P(grow) / signals skipped | $1k, 3 positions @25%: P(grow) / median / ruin | $5k, 5 @15%: P(grow) / median / ruin | $5k, 10 @8% |
|---|---|---|---|---|
| small 6m call, sell at 3m (12 rounds) | 4% / 97% | 0% / $175 / 18% | 0% / $157 / 100% | 0% / $114 |
| small 12m LEAPS, sell at 6m (6 rounds) | 1% / 99% | 5% / $372 / 2% | 1% / $535 / 56% | 1% / $345 |
| small 3m call (12 rounds) | 7% / 93% | 0% / $98 / 67% | 0% / $82 / 100% | 0% / $59 |
| small 6m put (6 rounds) | 5% / 96% | 0% / $186 / 23% | 0% / $170 / 96% | 0% / $108 |

**Minimum capital.**
- One small-cap 6m ATM call: about **$330–450** (today's picks range $45–$2,840).
- One mid-cap 12m LEAPS: about **$1,200**.
- The edge needs breadth (45% hit rate, a few big winners), so 10–20 names: **$4.5–9k** (small, 6m) or **$12–24k** (mid LEAPS).
- The stock version (equal-weight top quintile, 20+ names, ideally hedged with the bottom quintile) needs about $10k, margin and shorting. Not possible in this account.

## 5. Recommendation and "ready when funded"

1. **Do not trade valuation signals with long options**, at any account size.
   - The one real edge (gem, small caps) is a slow, skewed, peer-relative drift of about 3%/yr on the long leg.
   - Small-cap options charge 59% spreads and about 1.5× realized vol.
   - Status: **"NOT YET FOUND" (options)**, not retired.
2. **Ready when funded (stock, not options).** Small-cap gem long/short, peer-neutral: +7%/yr OOS, t 3.0, rebalanced quarterly, about $10k+, needs margin/short. Paper-track the top-20 / bottom-20 lists quarterly against their peer groups.
3. **Paper-only option test.** Mid-cap ($2–10B) gem **12m LEAPS, sold at 6m, using limit orders at or near mid.**
   - EV is +11% at mid and +1% at half spread, but mid-cap gem was **negative in-sample** (excess t −4.8 on hold-to-expiry).
   - Log live fills before believing it.
   - Minimum capital about $12k for 10 names.
4. **Reuse as a filter.** Low gem / high risk score = "never buy calls on this name" in other strategies. Pre-revenue, rich-for-growth names have the richest IV and the worst peer-relative drift (−4%/yr).
5. **Fiserv-style collapse puts: not recommended.** Collapse flags are 74–89% false positives, their extra crash odds are mostly volatility, and puts lose 41–62%. This agrees with forensic_events.md (filing-event puts only when IV ≈ RV).
6. **XSP dip-buy** (direction.md) stays the primary directional candidate.

## 6. Caveats

- **No historical small-cap option quotes.** Option P&L is modeled (Black–Scholes, RV × today's IV/RV by size bucket). Today's spread snapshot is applied to all history; spreads were probably wider before 2020, so history is flattered.
- **Spread timing.** Spreads were captured at the close (15:55–16:10 ET) and may be overstated. Even at half spread, every small-cap structure loses 18–42%.
- **Delisting returns** use the last trade, then cash. 4–16% of eligible names per year remain unpriced, mostly pre-2016 delistings and reused symbols. The residual survivorship bias flatters the long leg and understates collapses.
- **GAAP XBRL totals only.** No segment, organic-growth or guidance data (Fiserv's real story). SIC peer groups are coarse: Fiserv's is "business services NEC", and retailers fall back to the division level.
- **Gem was formed after a first look** at IS and OOS results. Its components are each positive in both periods, but treat the OOS t as about 2.5.
- **Earnings dates** for the earnings-window variant are actual 8-K 2.02 dates. Schedules are usually announced in advance, so this is a mild look-ahead.
- **Fundamentals use the filing date** (earliest filed value per period); prices are month-end closes on or after it. Companyfacts occasionally omits a 10-Q (ALKT Q1-26); those quarters are derived from later YTD values and dated by the later filing.

## 7. IV correction 2026-10-15

**Why.** yfinance's `impliedVolatility` ran high against Robinhood: BAH Jan-28 70C 46% vs 33%, ACEL Apr-27 12.5C 38% vs 32%, REAL Jan-28 10C 90% vs 72%. §4 priced every option as RV × the yfinance IV/RV ratio.

**Fix.** `bot/ivsolve.py` solves Black-Scholes-Merton IV from the bid/ask **mid**. It takes r from the 13-week T-bill (^IRX, 4.07% today) and q from yfinance `dividendRate`/spot, and skips quotes where bid or ask is ≤0.
- **Live check, 10:10 ET today.** The mid-solved IV matches RH when q = 0 and r ≈ 4%: BAH 70C 33.3% (RH 33%), ACEL 31.7% (RH 32%).
  - RH seems to ignore dividends. With BAH's 3.3% yield the BSM IV is 40%, and only that value makes BAH call and put IVs agree (calls 34%, puts 45% at q = 0).
  - REAL's yfinance quote was 0/0, so it could not be checked. Its last trade solves to 82%.
- **Where yfinance's error shows up.** Near-ATM (0.9–1.1 moneyness), the median yf − mid IV gap is +3–5 pts on BAH, +3–9 on M and +6.5 on ACEL. It is about 0 on SPY, KSS, REAL and BRKR. By DTE bucket across all 7 names: <30d −0.8, 30–120 +0.4, 120–300 +1.2, >300 −0.3 pts.
  - So the error is name-specific and mostly on **calls**, not a uniform offset. Quotes under 30 days with wide spreads are unreliable either way.

**Corrected IV/RV.** Same 200-name random sample and cached 2026-10-14 chains (893 two-sided ATM quotes). IV is solved in §4's own pricing convention (r = 3.5%, q = 0), so model premium equals the quoted mid. Medians across tickers:

| bucket | tenor | yf IV/rv3 (old) | mid IV/rv3 calls | puts | mid IV/rv12 (calls/puts) |
|---|---|---|---|---|---|
| small $0.3–2B | 60–200 DTE | 1.46 (calls 1.54) | **1.34** | 1.30 | 1.13 / 1.09 |
| small | 300+ DTE | 1.33 (calls 1.44) | **1.35** | 1.36 | 1.12 / 1.04 |
| mid $2–10B | 60–200 DTE | 1.34 (calls 1.41) | **1.22** | 1.27 | 1.04 / 1.10 |
| mid | 300+ DTE | 1.30 (calls 1.40) | **1.30** | 1.28 | 1.06 / 1.06 |

- The yf − mid gap on these chains was +1.4/+2.3/+3.1 pts at 60–120, 120–200 and 300+ DTE.
- With dividends (true BSM) the ratios are within 0.04 of these.
- Against 1-year RV the ratios are only 1.04–1.13. The 3-month RV that §4 uses was elevated in Aug–Oct 2026.

**Backtest re-run** (`research_fundamental.py options`; `IVFIX=0` reproduces the old run). OOS EV per trade, before → after. "Typical" fill = 37% of the quoted half-spread paid each way (research_fills.py).

| structure | k old → new | mid fill | typical fill | full spread |
|---|---|---|---|---|
| small 6m call, sell at 3m | 1.48 → 1.34 | −4% → −1% | −22% → −20% | −46% → −44% |
| small 6m call, hold 6m | 1.48 → 1.34 | −14% → −5% | −30% → −23% | −52% → −47% |
| small 12m LEAPS, sell at 6m | 1.48 → 1.35 | +1% → +4% | −14% → −11% | −35% → −33% |
| mid 6m call, sell at 3m | 1.34 → 1.22 | +3% → +7% | −7% → −3% | −22% → −19% |
| mid 6m call, hold 6m | 1.34 → 1.22 | −1% → +8% | −11% → −3% | −25% → −19% |
| **mid 12m LEAPS, sell at 6m** | 1.34 → 1.30 | +11% → +12% | **+4% → +5%** (t 0.9) | −6% → −5% |
| small 12m put, hold 12m | 1.48 → 1.36 | −30% → −23% | −40% → −34% | −55% → −50% |

**Verdict.** The correction helps every structure by 1–9 pts, but **no new structure turns positive at typical fills**. Mid-cap 12m LEAPS (sell at 6m) stays the only positive one: +5%, t 0.9, not significant, and its IS hold-to-expiry was negative.
- Spreads, not IV, decide these trades. A uniform IV/RV shift mostly cancels, because entry and exit are both priced at RV × k, so only the theta cost falls.
- §4's conclusions stand.
- Not re-run: universe.md's IV/RV20 of 1.30–1.43 and research_smallcap.py's `iv_call` also come from yfinance's field and are likely about 0.1× high on calls.
