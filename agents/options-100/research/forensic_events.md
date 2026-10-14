# Forensic red flags ("mini Hindenburg") and binary-event stocks: can long options profit?

2026-10-14. Two owner ideas, both for BUYING options only:
1. **"A mini Hindenburg."** Find short-seller-style red flags before the market does, and buy puts.
2. **"Stocks that hinge on a future event."** Examples: a financial-services name down on pending legislation, FDA decisions, court rulings, mergers. Trade the mispriced binary with options.

**Everything below is statistical screening output. No company is accused of anything.** A flag means a filing pattern that, historically, is associated with higher crash risk. Most flagged companies are innocent: the false-positive rates in §B are the point.

- **Code:** `bot/research_forensic_events.py`. Subcommands: `filings | facts | gc | flags | mypanel | bpanel | partA | partA_pre | partB | partB_earn | screen | fda | legislation | mergers | sp500 | screen_fda | screen_mergers | screen_legislation | econ`.
- **Caches** (gitignored under `data/`, checked with `git check-ignore`):
  - `research_forensic_*.pkl` and `research_forensic_results.json`, which holds all tables;
  - `research_forensic_raw/*.csv`: the event lists, compiled from public sources (firm archives, Wikipedia, SEC filings, news), plus `book_case_study.txt`.
- **Shared inputs:** `data/research_fund_raw/` (EDGAR companyfacts and submissions bulk files, Form 3/4/5 data, and HuggingFace daily bars that include delisted symbols) and `research_fund_{subs,facts,insiders,px_*}.pkl`. These come from the parallel `research_fundamental.py` run and are read only. Its F-score, accruals and peer-valuation work is not repeated here.

## Verdict (short)

| part | question | answer |
|---|---|---|
| A. activist short reports (560 events, 2012–2026) | Is there still exploitable downside after day 0? | **No, not for puts.** Day 0 is −6.8% excess (t −13). After that the mean drift is small, but the median keeps falling: −10% at 120d and −23% at 250d. Fraud-type reports drift −13% excess by 120d (t −3.2). A put bought at the day-1 close still loses, because post-report IV runs about 65%. 6m ATM put: −33% EV (−23% fraud-only); 1y put at fair IV: −6%. |
| A. pre-report signals | Could the screen have caught targets earlier? | **Partly.** The month before the report, targets were 2.7× more likely than base to carry a Beneish flag (20% vs 8%) and 2.6× more likely to carry a recent restatement (8-K 4.02). Soft-asset growth and DSRI were 1.8–1.9× base. 71% had ≥1 flag, against 61% for all filers. |
| B. forensic screen (4,225 firms, $300M–$10B, 2012–18 IS / 2019+ OOS) | Do flags predict 6–12m underperformance and −30% crashes? | **They predict crashes, not alpha.** Every flag raises the 12m crash rate 1.1–2.2× (lift), mostly because flagged firms are more volatile, and own-vol option pricing already charges for that. **Excess returns:** filing-event flags (late filing, going concern, restatement) are negative in both periods (−2 to −10 pts/12m). The accounting flags (Beneish, DSRI, soft assets) are **not**. Only 2 OOS cells pass BH: auditor change −5.3 (t −2.7, but positive IS) and the tiny going-concern-exhibit set. **Puts:** −11% to −35% EV at realistic IV (1.2×RV); best cells reach +0.4% to +6.5% only at IV = realized. |
| C. FDA (280 decisions) | Is the binary mispriced? | **Not in our favour.** Realized \|move\| is about 19% (at a 25% CRL base rate). Live straddles to the first post-event expiry price 15–90% for small/mid caps (the term-kink event part, where estimable: 6–60%). Straddles break even only at an implied move ≤ about 17%. Tails: 22% of CRLs fall more than 50% and 36% fall more than 30%, about −2.3σ in the median. Twenty-percent-OTM puts pay only if implied ≤ 20%. **Lead:** names that fell into the PDUFA (bottom tercile of 20d XBI-relative return) got CRLs at 1.7× the rate in both periods (IS 44% vs 31%; OOS 63% vs 34%). |
| C. legislation / court (45 cases) | Over- or under-priced tails? | **Tails are huge relative to pre-event realized vol:** median \|z\| is 3.9σ, and 44% of cases moved more than 5σ. That is unusable as a backtest: the cases were picked *because* they were memorable, and no historical option quotes exist. "Favorable" outcomes were not preceded by a pending discount (+29% vs +14% run-up). |
| C. merger arb (377 deals, 62 breaks) | Calls on completion or puts on a break when the spread is wide? | **Wide spreads overstate break risk.** Implied break probability >40% realized 18% raw, or 6–11% reweighted to a 6–10% base rate. That favors the completion side, but calls on a pinned stock are capped at the spread (−25% to −55% EV). Puts on a break lose at any IV ≥1.5× the pinned RV (−51% to −83%). |
| C. S&P 500 adds (228) | | Reaction +2.1% overnight (t 6.8), nothing after (−0.25% to effective). Not tradable with options. |
| Owner's book case | | **Not confirmed in any book text.** Best fit: **Sallie Mae (SLM), 2007.** A $60 LBO was pending, Congress cut student-loan subsidies, the buyers walked, and the stock fell 67% Jul-07→Jan-08 while realized vol sat around 25%. Confidence: low–medium (§C3). |

**Recommendation.** Nothing here beats the XSP dip-buy (direction.md). **No strategy is retired.** Per the owner's rule, the following go on a paper/"ready when funded" list (§D):
1. **"Filing-event" puts.** Restatement (4.02) or late filing (NT 10-K/Q) or score ≥4 → 6m ATM put, **only when the quoted IV is near the stock's realized vol**. Ready when funded at $1.5k+.
2. **FDA 20%-OTM puts when the implied event move is ≤ about 20%** and the stock has drifted down into the date.
3. **Merger "completion" exposure** via the stock rather than options. This is outside the long-options mandate, so it is a note, not a strategy.

The activist-report day-1 put is **not recommended even when funded.** It is "NOT YET FOUND", and the 1-year fraud-only variant (−6%) is the only remaining open thread.

---

## A. Activist short-seller reports: event study

**Data.** 583 reports from 20 firms were compiled from firm archives, Wikipedia and news: Spruce Point 130, Hindenburg 64, Kerrisdale 61, Culper 40, Grizzly 37, J Capital 33, Wolfpack 32, Muddy Waters 25, Fuzzy Panda 25, Blue Orca 23, Citron 21, Bonitas 19, plus Night Market, Gotham, Viceroy, Scorpion, Morpheus, Capybara, Glaucus and Prescience.
- 560 have daily bars (HF dataset incl. delisted, plus yfinance). 2012–18: 123; 2019+: 437.
- Allegation types: fraud 186, mixed 278, valuation 96.
- Day 0 = the report date, or the next session if the report came after hours. Most reports have unknown time of day, so CAR(0,1) is also shown.
- Excess = minus SPY (`x`) or minus a SIC-mapped sector ETF (`xs`, IWM fallback).
- **Entry for the drift and put tests = day-1 close.**

**Caveats.**
- Spruce Point's archive lists each company's *latest* report, and some rows may be follow-ups. Spruce's day 0 is −3.7%, against −6.8% overall.
- 16 dates are flagged uncertain.
- About 22 targets later stopped trading. Their returns hold the last price, so put payoffs for wipe-outs are *under*stated.

### A1. Reaction and drift (mean / median, %, t of mean)

| group | n | day 0 x | CAR 0–1 | d1→5 | d1→20 | d1→60 | d1→120 | d1→250 | min within 120d |
|---|---|---|---|---|---|---|---|---|---|
| all | 560 | −6.8 / −4.6 (t −13.2) | −7.4 | +1.4 / +0.1 | +0.4 / −0.5 | −1.5 / −4.8 | −3.3 / −9.9 (t −1.3) | −6.4 / **−23.0** (t −1.6) | −29.5 / −23.5 |
| 2012–18 | 123 | −7.0 | −7.7 | +0.5 | +0.5 | −2.1 | −4.6 | −8.7 / −15.7 | −25.3 |
| 2019+ | 437 | −6.8 | −7.3 | +1.6 | +0.4 | −1.3 | −3.0 / −11.6 | −5.7 / −24.6 | −30.8 |
| fraud | 186 | **−10.5** | −11.0 | 0.0 | −0.6 | −6.8 (t −2.4) | **−13.2 / −21.8 (t −3.2)** | −17.6 / −37.0 (t −2.7) | −36.1 |
| mixed | 278 | −5.0 | −5.8 | +0.3 | +1.5 | +0.2 | −0.6 | −5.6 / −21.1 | −25.1 |
| valuation | 96 | −5.2 | −5.3 | +7.2 | −0.7 | +3.9 | **+7.7** / −6.3 | +12.0 / −10.9 | −29.8 |
| <$300M | 25 | −4.2 | | | +1.0 | −7.7 | −15.3 | −38.6 (t −3.2) | |
| $300M–2B | 133 | −8.1 | | | +1.4 | +4.2 | +9.7 / −6.7 | +19.2 / −7.3 | |
| $2–10B | 125 | −5.7 | | | +2.2 | −3.5 | −4.4 / −11.5 | −11.9 / −24.5 | |
| >$10B | 55 | −4.2 | | | −3.3 | −9.0 (t −2.6) | −14.9 (t −2.8) | −20.0 (t −2.4) | |
| Hindenburg | 58 | **−13.8** | | | **−8.1 (t −2.4)** | −11.2 (t −2.0) | −10.2 / −24.2 | −19.2 | |
| Muddy Waters | 25 | −12.7 | | | +8.8 | +7.6 | −4.1 | | |
| Scorpion | 12 | −13.3 | | | −7.8 | −16.3 | −22.1 | | |
| Spruce Point | 125 | −3.7 | | | +2.0 | +2.2 | −0.5 | | |
| Kerrisdale | 61 | −6.8 | | | +1.5 | +2.1 | +8.7 | | |

- **Recovery.** 78% of targets trade back above the pre-report close at some point within 120 days, but only 42% are above it *at* day 120 (41% at day 250).
- **The mean-vs-median gap** (mean −6%, median −23% at 250d) means most targets keep sliding, while a minority squeeze hard. Valuation calls on $300M–2B names produce the squeezes.
- Big and fraud-type targets drift; small "valuation" targets mean-revert.

### A2. The key question: a put bought at the day-1 close

**Pricing.**
- Black-Scholes, IV = k × the stock's **post-event** realized vol (days 1–21; median 65%, vs 60% pre-report), floored at 25%, with skew 0.8 on OTM puts.
- Exit IV is k × trailing RV20.
- Spread: 10% of mid round trip, with 5% and 20% variants cached.
- k = 1.0 is roughly "fair" (implied = what then realizes). Real post-report IV typically sits *above* realized, so 1.25–1.5 is realistic.

| structure (day-1 close entry) | all, k=1.0 | all, k=1.25 | 2012–18 k=1.25 | 2019+ k=1.25 | fraud k=1.0 (IS / OOS) | fraud k=1.25 OOS | PoP (all, k=1.25) |
|---|---|---|---|---|---|---|---|
| 30d ATM, sell at 20d | −16.6% | −26.0% | −33.4% | −23.9% | | | ~30% |
| 60d ATM, sell at 40d | −20.9% | −29.1% | −36.3% | −27.1% | −46.7 / −20.7% | | |
| 90d ATM, sell at 60d | −17.0% | −25.7% | −32.3% | −23.8% | | | |
| 120d ATM, sell at 90d | −10.9% | −22.2% | −24.1% | −21.7% | +1.8 / −7.7% | | |
| 6m ATM, to expiry | | −33% (OOS) | −19.1% | −33.4% | +23.1 / −4.9% | −22.7% | 30% |
| **1y ATM, to expiry** | 0.0% IS / −10.8% OOS | −18.3 / −27.7% | | | **+29.5 / −6.4%** | −23.4% | |
| 60d 10%-OTM, sell at 40d | −29.6% | −39.7% | | | | | |

- **No subgroup survives.**
  - Every OOS cell at k=1.25 is negative; t-stats run from −1 to −7, i.e. significantly negative.
  - At "fair" k=1.0, IS-positive cells (fraud 6m/1y, $2–10B 1y +68%) flip negative OOS ($2–10B 1y −16.7%, t −1.4).
  - Conditioning on a confirmed reaction (CAR 0–1 ≤ −5%, known at entry) makes it worse (−13% to −42%).
- **Why.** The drift is real for fraud-type reports, but it is about −13% over 120 days against a 6-month ATM put that costs about 18% of spot at 65% vol. The median path does fall, but the expected put payoff is roughly what the elevated IV already charges. The squeezes (valuation names) kill the rest.
- **Answer: after day 0, the remaining downside is already priced into the put premium.** This matches news_trading.md: the information is in the price before a retail put buyer arrives.

### A3. Did the pre-report period show detectable signals?

483 events were mapped to a CIK (ticker plus company-name check, because tickers get reused), and 338 matched the flags panel (XBRL filers only). Flags are taken as of the month before the report. The base is all XBRL filers in the same months, weighted to the event-month mix.

| flag (as of month before report) | targets | base | lift |
|---|---|---|---|
| Beneish M > −1.78 | 20.4% | 7.7% | **2.66** |
| restatement 8-K 4.02 (12m) | 6.5% | 2.5% | **2.62** |
| soft-asset share +10 pts | 15.1% | 8.0% | 1.88 |
| DSRI ≥ 1.4 | 10.7% | 5.8% | 1.84 |
| share count +20% yoy | 21.0% | 13.9% | 1.52 |
| ≥3 officer-change 8-Ks (5.02) | 43.2% | 29.0% | 1.49 |
| auditor change 4.01 (12m) | 14.5% | 10.3% | 1.41 |
| late filing NT 10-K/Q | 14.2% | 19.6% | 0.72 |
| going concern | 8.0% | 11.9% | 0.67 |
| ≥2 flags | 39.1% | 28.6% | 1.37 |

- Insider selling ≥1% of cap over 6m: 16% of targets. The median 6m insider sale was 0.09% of cap.
- Short-interest history was not available for free and was not tested.
- **Reading.** Activists pick aggressive-accounting growth stories (Beneish, DSRI, soft assets, dilution), not distressed filers. Late filers and going-concern names are *under*-represented, being too small or too obvious.
- The screen **would have flagged about 1 in 5 targets in advance.** It would also have flagged about 8% of all filers, a ~12:1 false-positive ratio against the target base rate. That is the false-positive problem of §B, seen from the other side.

## B. Forensic red-flag screen (point-in-time EDGAR)

**Construction** (all as of the **filing date**; nothing is used before it is public):

| flag | definition | source |
|---|---|---|
| beneish | 8-variable M-score > −1.78. Needs ≥5 real components and TATA; non-financials only. | latest 10-K annual XBRL (earliest-filed values, so no restatement look-ahead), ≤15m old |
| dsri | receivables/sales index ≥ 1.4 (DSO growth far above revenue growth) | same |
| soft | (TA − PP&E − cash)/TA up ≥ 10 pts yoy | same |
| auditor | 8-K Item 4.01 in the last 12m | submissions.zip item codes |
| restate | 8-K Item 4.02 non-reliance in the last 12m | same |
| late | NT 10-K or NT 10-Q in the last 12m | same |
| turnover | ≥3 8-Ks with Item 5.02 in 12m. Best effort: 5.02 also covers director and comp changes, so it is noisy. | same |
| gc | 10-K matching going-concern phrases in EDGAR full-text search, ≤15m old. 16,283 hits, 4,376 CIKs, 2011–2026. `gc_ex` = the hit is in an exhibit (auditor consent), i.e. a likely opinion paragraph. | efts.sec.gov |
| rpt | related-party revenue/receivables/transactions ≥1% of assets and up ≥50% | XBRL RPT tags (sparse) |
| insider | open-market insider sales over 6m ≥ 1% of market cap | Form 3/4/5 bulk data |
| dilution | cover-page shares outstanding +20% yoy | dei:EntityCommonStockSharesOutstanding |
| non-GAAP gap | **not feasible.** Non-GAAP numbers sit in press-release exhibits and are not in XBRL. | |

**Universe and prices.**
- Monthly bars come from yfinance (listed names) and the HF daily set for *delisted* names. Delisted names are mapped by 10-K document-name prefix and validated against public float. That maps 6,358 CIKs, 2,194 of them delisted.
- Market cap = cover shares × unadjusted price. Kept: $300M–$10B, price ≥ $2, no SPACs.
- Result: 306,334 firm-months and 4,225 firms.
- Forward returns hold cash at the last price after a delisting.
- Excess = return minus the same-month, same-size-bucket equal-weight mean.
- Crash = a −30% drawdown within 12m, from monthly lows.
- t = Newey-West on the monthly flagged-minus-unflagged spread. BH (q 0.10) is run within each period × size block.

### B1. Do flags predict 12-month underperformance and crashes? (all sizes)

| flag | % of firm-months | 12m excess diff IS (t) | **OOS (t)** | BH OOS | crash rate if flagged IS / OOS | base IS / OOS | lift OOS | **false-pos. rate** (non-crashers flagged) | recall (crashers flagged) |
|---|---|---|---|---|---|---|---|---|---|
| beneish | 4.8 | +0.2 (0.1) | **+4.4 (1.3)** | – | 39 / 50 | 22 / 40 | 1.24 | 5.8% | 8.5% |
| dsri | 3.9 | +2.8 (1.0) | +1.9 (0.6) | – | 36 / 52 | | 1.31 | 3.8% | 6.3% |
| soft | 5.1 | 0.0 | +4.9 (1.1) | – | 32 / 49 | | 1.22 | 5.9% | 8.4% |
| auditor | 3.6 | +0.9 (0.5) | **−5.3 (−2.7)** | **yes** | 25 / 51 | | 1.28 | 3.9% | 6.1% |
| restate | 1.4 | −1.9 (−0.7) | −7.4 (−2.1) | – | 28 / 59 | | 1.48 | 1.1% | 2.4% |
| late | 3.4 | **−2.4 (−3.9)** | −5.4 (−1.9) | IS yes | 30 / 52 | | 1.31 | 3.0% | 4.9% |
| turnover | 37 | +0.5 | +0.4 | – | 24 / 43 | | 1.08 | 34.5% | 39% |
| gc | 1.0 | **−9.8 (−5.4)** | −7.8 (−1.2) | IS yes | 38 / 66 | | 1.65 | 0.8% | 2.3% |
| gc in exhibit | 0.1 | −25 (−1.6) | −27 (−2.9) | yes (tiny n) | 48 / 55 | | 1.37 | 0.1% | 0.2% |
| rpt | 0.7 | +1.3 | −13.0 (−1.2) | – | 23 / 51 | | 1.28 | 0.5% | 0.9% |
| insider | ~9 | +2.9 (1.8) | −0.2 | – | 28 / 51 | | 1.27 | 6.1% | 9.5% |
| dilution | ~7 | **−4.1 (−2.7)** | −1.9 (−0.4) | IS yes | 31 / 54 | | 1.35 | 6.5% | 11.5% |
| score ≥2 | 15 | 0.0 | +0.4 | – | 32 / 52 | | 1.31 | 14.5% | 24% |
| score ≥3 | 4.3 | +1.0 | −1.1 | – | 38 / 59 | | 1.47 | 4.4% | 9.5% |
| score ≥4 | 1.0 | +3.1 | −6.4 (−1.1) | – | 44 / 63 | | 1.58 | 1.2% | 3.2% |

**Score buckets** (12m excess, pts):

| score | IS | OOS |
|---|---|---|
| 0 | +0.1 | −0.2 |
| 1 | −0.1 | +0.5 |
| 2 | −0.3 | +1.1 |
| 3 | 0.0 | −1.3 |
| 4 | +2.5 | −5.9 |
| 5+ | −4.8 | **−20.0** |

Crash rates rise monotonically with score: IS 18 → 48%, OOS 34 → 66%.

**By size, OOS 12m excess (pts):**
- **$300M–2B:** auditor −5.2 (t −2.5, BH yes), rpt −14.3 (t −2.7, BH yes), gc −6.3, restate −8.3, late −4.0.
- **$2–10B:** late −8.0 (t −2.7), gc −12.3 (t −2.4), event_any −4.9 (t −2.9), dilution −6.2. Beneish +6.2 and soft +2.6 are wrong-signed.

**Reading.**
- (1) **Beneish, DSRI and soft-asset flags do not predict underperformance in 2012–2026 mid/small caps.** OOS they even lean positive: they flag fast growers and acquirers (e.g. merger-driven DSRI). They predict *volatility*, i.e. crashes in both directions.
- (2) **Filing-event flags** (late filing, going concern, restatement, auditor change) are the ones with a consistent negative sign. Only auditor change (OOS) and late filing / going concern (IS) clear BH, and auditor change flips sign from IS. Treat them as weak, not proven.
- (3) The multi-flag score only bites at **score ≥5**, which is about 0.3% of firm-months: −20 pts OOS, −4.8 IS.
- (4) False-positive rates are low in absolute terms (1–6% of non-crashers get flagged), but **precision** (the crash rate among flagged names) is only 1.2–1.7× base. Roughly half of flagged names do *not* crash.

### B2. Option economics: puts on flag events

**Pricing.**
- Entry is at the month-end when a flag turns on, with at most one entry per firm per 6 months.
- IV = k × the stock's trailing 3-month realized vol (k 1.0 / 1.2 / 1.4; 1.2 is the realistic case, since single-name IV/RV runs about 1.3–1.4 per universe.md), with skew 0.5.
- Spread: 20% round trip for $300M–2B and 10% for $2–10B (smallcap.md measured 17–28%).
- Settled at expiry on the monthly price ratio. t is clustered by entry month.

| entry signal | period | trades/yr | 6m stock excess | 3m ATM k1.2 | **6m ATM k1.0** | **6m ATM k1.2** (t) | PoP | 6m 10%-OTM k1.2 | 6m, sell at 3m | 6m mid-fill k1.2 | median contract |
|---|---|---|---|---|---|---|---|---|---|---|---|
| beneish | IS / OOS | 81 / 132 | −2.4 / −2.3 | −31 / −16 | −8 / −13 | −24 / −28 (−3.9) | 32% | −33 / −36 | −14 | −22 | $380 |
| auditor | IS / OOS | 79 / 119 | −3.3 / −6.5 | −30 / −21 | −9 / −1 | −25 / −18 (−2.3) | 35% | −22 | −18 | −10 | $313 |
| **restate** | IS / OOS | 28 / 39 | −2.1 / **−9.0** | −41 / −13 | −7 / **+6.5** | −23 / **−11 (−2.5)** | 41% | −18 | −12 | −3 | **$265** |
| late | IS / OOS | 61 / 84 | −3.4 / −9.3 | −37 / −17 | −14 / −7 | −29 / −23 | 33% | −28 | −15 | −16 | $292 |
| gc | IS / OOS | 21 / 34 | −2.9 / −13.6 | −25 / −11 | −8 / −4 | −24 / −20 | 32% | −26 | −11 | −12 | $277 |
| dilution | IS / OOS | 184 / 220 | −2.3 / −5.8 | −30 / −33 | −16 / −15 | −30 / −29 | 29% | −35 | −23 | −23 | $304 |
| insider | IS / OOS | 269 / 240 | +0.6 / 0.0 | −39 / −35 | −27 / −14 | −40 / −29 | 29% | −35 | −24 | −23 | $444 |
| score ≥3 | IS / OOS | 160 / 216 | −0.4 / −4.5 | −30 / −20 | −12 / −5 | −28 / −21 (−4.3) | 34% | −27 | −16 | −14 | $336 |
| **score ≥4** | IS / OOS | 53 / 86 | −3.2 / **−8.8** | −30 / −13 | −2 / **+0.4** | −19 / **−16 (−2.9)** | 36% | −22 | −13 | −9 | $303 |
| score ≥4, $300M–2B | OOS | 66 | −9.6 | −13 | +3.6 | −13.5 | 37% | −18 | −14 | −5 | $255 |
| restate, $300M–2B | OOS | 30 | −8.2 | −7 | **+11.4** | −7.1 | 43% | −13 | −11 | +2 | $238 |
| late, $2–10B | OOS | 19 | −13.5 | −7 | +8.2 | −10.2 | 38% | −14 | −4 | −6 | $470 |

**Variant: buy the put the day before the next earnings release** (score ≥3; the next 8-K Item 2.02 within 100 days; 30d ATM put, sold 20 days later; IV = k × 60d RV):
- **OOS:** flagged names' 2-day earnings reaction is −0.01% vs −0.07% for unflagged controls. A ≤−10% reaction happens 15.7% of the time vs 9.4%: a fatter left tail, but symmetric vol.
- **Put EV:** −17% (k1.2) / −34% (k1.5) for flagged names vs −2.5% / −23% for controls.
- **IS:** flagged −13.5% / −31%.
- **Earnings timing adds nothing.**

**Reading.** Flag events are followed by negative stock excess, about −5 to −14 pts over 6m OOS for event flags. That is about what a 6-month put on a 60–80%-vol stock already costs. Puts are break-even or better **only if bought at IV ≈ realized vol** (k=1.0): restatement +6.5%, score ≥4 +0.4%, and $300M–2B restatement +11%. At realistic quoted IV and spreads, every cell is negative in both periods. **Nothing survives OOS at k ≥ 1.2.**

### B3. Current screen: top flagged names, 2026-10 ($300M–$10B)

1,729 names are in the universe this month. 231 carry ≥2 flags and 75 carry ≥3.
- Liquidity = the expiry nearest 4 months on the yfinance chain (2026-10-14, about 15:00 ET).
- "spread" = (ask−bid)/mid at ATM; "put" = ATM put ask × 100.
- Peer M = the median M-score of the same 2-digit SIC this month.

**Statistical flags only: these are filing patterns, not allegations.** Many are explained by acquisitions, capital raises or fast growth.

| ticker | sector | cap $B | score | flags | M (peer) | shares yoy | exp | IV | spread | OI | ATM put |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ALOY | metal mining | 0.42 | 6 | beneish, dsri, auditor, late, gc, dilution | −1.39 (−2.56) | +1566% | Jan-27 | 97% | 48% | 506 | $120 |
| XMAX | furniture | 0.54 | 5 | beneish, dsri, late, turnover, dilution | 7.93 (−2.78) | +369% | Mar-27 | 40% | 30% | 7 | n/a |
| QUBT | software | 1.45 | 5 | beneish, dsri, soft, turnover, dilution | 7.56 (−2.73) | +42% | Jan-27 | 65% | 9% | 1,876 | $70 |
| UAMY | smelting | 0.41 | 5 | beneish, soft, auditor, turnover, dilution | 3.52 (−2.57) | +24% | Feb-27 | 93% | 13% | 3,480 | $45 |
| CHRN | machinery | 2.20 | 5 | dsri, soft, turnover, gc, dilution | −2.61 | +5452% | no chain | | | | |
| NUAI | oil & gas | 0.37 | 5 | soft, restate, turnover, gc, dilution | −6.78 | +310% | Feb-27 | 180% | 27% | 115 | $100 |
| FLY | aerospace | 2.87 | 4 | beneish, dsri, soft, turnover | 7.45 (−2.54) | +14% | Feb-27 | 89% | 6% | 263 | $340 |
| UMAC | comms equip. | 0.89 | 4 | beneish, dsri, auditor, dilution | 7.30 | +64% | Feb-27 | 87% | 8% | 2,577 | $340 |
| OVID | pharma | 0.43 | 4 | beneish, soft, turnover, dilution | 6.68 | +175% | Jan-27 | 103% | 119% | 6 | $55 |
| APLD | computer services | 6.09 | 4 | beneish, dsri, soft, turnover | 4.81 | +8% | Jan-27 | 85% | 2% | 15,517 | $325 |
| ONDS | comms equip. | 3.54 | 4 | beneish, auditor, turnover, dilution | 2.08 | +160% | Jan-27 | 74% | 7% | 9,442 | $56 |
| BYND | food | 3.48 | 4 | beneish, late, turnover, dilution | 1.99 | +573% | Feb-27 | 98% | 18% | 81 | $260 |
| DJT | software | 2.02 | 4 | beneish, dsri, soft, turnover | 1.82 | 0% | Jan-27 | 65% | 12% | 3,124 | $83 |
| ASPI | chemicals | 0.32 | 4 | beneish, soft, late, dilution | 1.44 | +67% | Jan-27 | 101% | 34% | 913 | $45 |
| GOSS | pharma | 4.38 | 4 | beneish, dsri, turnover, dilution | 0.63 | +115% | Jan-27 | bad quote | | 792 | |
| STOK | pharma | 1.49 | 4 | beneish, soft, auditor, turnover | 0.42 | +18% | Feb-27 | 61% | 129% | 3 | $650 |
| VEEA | IT services | 0.31 | 4 | beneish, late, turnover, dilution | −0.34 | +24% | no chain | | | | |
| AAOI | semis | 7.26 | 4 | beneish, auditor, turnover, dilution | −0.55 | +36% | Feb-27 | 89% | 8% | 86 | $1,360 |
| RDW | aerospace | 2.13 | 4 | beneish, dsri, turnover, dilution | −0.79 | +74% | Feb-27 | 78% | 8% | 779 | $180 |
| LWLG | plastics/photonics | 0.60 | 4 | beneish, dsri, restate, turnover | −0.95 | +19% | Jan-27 | 92% | 14% | 2,347 | $75 |
| DNOW | oilfield equip. | 2.74 | 4 | beneish, dsri, soft, dilution | −1.59 | +72% (merger) | Feb-27 | 46% | 57% | 113 | $140 |
| NFE | gas distribution | 1.09 | 4 | dsri, restate, late, turnover | −2.29 | 0% | Jan-27 | bad quote | | 1,592 | |

- **Read with B1 in mind.** These names crash more often (score ≥4: 63% OOS 12m crash rate vs 40% base), and the ≥4 bucket underperformed by about 6 pts OOS. But their IVs (65–180%) already price that. The B2 rule says a put is only worth it when the quoted IV is near the name's realized vol.
- Liquid enough to watch (spread ≤10%, OI in the thousands): QUBT, APLD, ONDS, UMAC, UAMY, LWLG.
- **CHRN** is a new listing with an implausible share-count change: data artifact likely.

## C. Binary / event-dependent stocks

### C1. FDA decisions (280 decisions with bars; 166 approvals, 114 CRLs; 2013–2026)

**Data.**
- Dates were checked against SEC press-release filings and FDA approval/CRL records (`fda_history.csv`).
- Move = close before → close of the reaction day; a 2-day window is used when the announcement timing is unknown (157 rows).
- **The sample over-represents CRLs** (41% vs a true first-cycle base rate of about 20–30%), so EVs are reweighted to an assumed base rate.

| | n | mean move | median | \|move\| | 10th / 90th pct | ≤ −30% | ≤ −50% | 20d run-up into date (vs XBI) | 60d after |
|---|---|---|---|---|---|---|---|---|---|
| approval | 166 | +7.2% | +1.9% | 15.5% | −14% / +29% | 1.2% | 0% | +5.5% | −2.0% |
| CRL | 114 | **−24.5%** | −20.3% | 27.9% | −63% / +5% | **36%** | **22%** | −3.3% | +10.4% (t 1.6) |
| first approval | 196 | app +9.0 / CRL −29.9 | | | | | | | |
| not first (sNDA etc.) | 84 | app +1.7 / CRL −15.3 | | | | | | | |
| 2013–18 / 2019+ | 95 / 185 | \|move\| 15.6% / 23.1% | | | | | | | |

**The market vs the outcome distribution.** Expected \|move\| = 17.4 / 18.6 / 19.2% at a 15 / 25 / 30% CRL rate. The table gives option EV at fair pricing plus an 8–15% spread.

| implied event move M (straddle ÷ spot) | straddle | ATM put | 20%-OTM put | ATM call |
|---|---|---|---|---|
| 15% | +24% | | | |
| 20% | −7% (−15% incl. spread) | −10% | **+8%** (+27% at 30% CRL) | −17% |
| 30% | −38% | −40% | −54% | −45% |
| 40% | −53% | −55% | −72% | −58% |

- **Over- or under-priced?** A CRL is a −2.3σ day in median terms (relative to pre-event 60d RV), and 22% of CRLs lose half the company. That *is* a fat tail.
- **Live chains price it richly.** The ATM straddle to the first post-event expiry is 10–30% for mid/large caps (IONS, CYTK, VRTX, EXEL, BBIO, AGIO) and 40–93% for small caps (CAPR 93%, SVRA 79%, INO 67%, PRAX 61%). Where the term structure lets the event part be separated, it is 8–60%.
- Against the analog \|move\| (13% for supplemental approvals, 21% for first approvals), small-cap PDUFAs are typically priced at **1–3× the historical move**: over-priced for buyers.
- **The tail is not underestimated by the options market. It is over-paid on average.**
- **Lead: pre-event weakness.** Names in the bottom tercile of 20d XBI-relative return into the decision got CRLs 56% of the time vs 31–34% for the rest. IS 44% vs ~31%; OOS 63% vs ~34% (raw sample shares, n = 94 / 186). It is consistent in both periods; plausibly informed trading or earlier-disclosed review problems.
  - Reweighted to a 25% base rate, the down-tercile CRL odds are about 39–45%.
  - A 20%-OTM put on such names is +12% (all) / +51% (OOS) **only if the implied event move is ≤ 20%**, and negative at 30%.
  - Post-hoc and small: paper-track it.
- **Post-CRL rebound** of +10% at 60d (t 1.6; IS +5%, OOS +12%) is suggestive, not significant.

### C2. Legislation, regulation and court rulings (45 cases with price data, 2007–2026)

Data: `legislation_cases.csv`. The categories covered are GSE/Fannie-Freddie (6), ACA/hospitals (3), insurers and MA rate notices, PBM, payday/CFPB, credit-card rules, Durbin, for-profit education, tobacco/vape, crypto (SEC suit, ETF, CLARITY), cannabis rescheduling, antitrust rulings (SAVE/JBLU, CPRI/TPR, KR/ACI, GOOGL remedies, HPE/JNPR, ATVI) and patents (AMRN).

| statistic | value |
|---|---|
| mean / median \|decision-day move\| | 15.5% / 10.0% |
| median \|move\| in pre-event daily σ | **3.9σ** |
| share of moves > 3σ / > 5σ | 58% / 44% |
| 2-day straddle EV if priced at 1.0 / 1.5 / 2.5 × pre-event RV | +385% / +223% / +94% (medians +243 / +129 / +37%) |
| unfavorable outcomes (n=23): decision move / run-up while pending | −16.0% / +13.6% |
| favorable outcomes (n=22) | +10.2% / +28.8% |

**Largest examples.** AMRN patent loss −70% (2020-03-30); CPRI/TPR injunction −49%; SAVE/JBLU block −47%; FNMA "net worth sweep" ruling −41% (2014-09-30, 15.6σ); CXW DOJ memo −36% (25σ); FNMA 2025 privatization talk +47%; CXW election +43%; TLRY rescheduling +40%.

**Reading.**
- Policy binaries produce moves of many σ, and pre-event realized vol says nothing about them.
- **But the straddle numbers are not tradable evidence.**
  - (i) The cases were collected *because* they moved: selection bias.
  - (ii) Scheduled decisions (court dates, CMS rate notices, FDA/SEC deadlines) carry event premium in IV that we cannot observe historically.
  - (iii) Several decisions were not dated in advance (DOJ memo, legislative passage), so no one could have bought the straddle the day before.
- **No pending discount.** Stocks that later got a *favorable* outcome had already rallied +29% while pending, against +14% for unfavorable ones. The market was, if anything, leaning the right way.

### C3. Owner's options-book case study

- **Not identified in any book text.** Searches covered McMillan (*Options as a Strategic Investment*, full text grepped), Cohen, and Jabbour (no match), and archive.org full-text search. Natenberg, Sinclair, Passarelli and Augen could not be text-searched.
- **Closest match: Sallie Mae (SLM), 2007.** Confidence: **low–medium**, with no citation found.
  - On 2007-04-16, J.C. Flowers/BofA/JPM agreed to buy SLM for $60. The stock jumped +14.7% and +17.7% on Apr 13/16.
  - Congress then moved the College Cost Reduction and Access Act (signed 2007-09-27), cutting lender subsidies. The buyers claimed a material adverse change and walked away.
  - From the 2007-07-02 plateau, SLM fell −22% by 2007-09-26, −34% by 2007-11-30, and **−67% by 2008-01-18**. Yahoo's spin-adjusted series is used, so relative moves only.
  - Realized vol May–Sep 2007 was only about **25%**, because the deal pinned the stock.
  - **Worked example (hindsight, n=1).** Buy a ~200-day put on 2007-07-02, held to 2008-01-18:

    | strike | IV | cost (% of spot) | payoff (× premium) |
    |---|---|---|---|
    | 80% | 25% | 0.75% | **63×** |
    | 80% | 30% | 1.4% | 34× |
    | 90% | 30% | 3.8% | 15× |
    | ATM | 40% | 10.9% | 6× |

  - This is the *merger-break + legislation* binary at its best: deal-pinned vol makes break puts cheap, and the policy risk was public (the bill was in the news from spring 2007).
  - It sits against C4: across 377 deals, break puts lose on average, because most pinned deals close.
- **Other candidates (low):**
  - SLM 1993: −15% on Clinton's direct-lending proposal.
  - Greenblatt's *You Can Be a Stock Market Genius*: its LEAPS example is **Wells Fargo 1992–93**, a bank depressed by California real estate, *not* legislation. Its pending-legislation example is a cable-industry spinoff, not options. The owner may be blending the two.

### C4. Merger arbitrage (377 deals with bars, 2012–2026; 62 terminated)

**Data.**
- `merger_deals.csv`: S&P 500/400 acquisition removals (systematic but **completion-only**) plus hand-found breaks. **The sample cannot give a break rate.** Rates below are reweighted to a 6% or 10% base (Mitchell-Pulvino-type figures).
- Entry is the close the day after announcement.
- Implied break probability p = (offer − P) / (offer − unaffected price).

| implied break prob. (cash deals) | n | implied mean | realized (raw sample) | realized @6% base | realized @10% base |
|---|---|---|---|---|---|
| < 5% | 32 | 1.5% | 12.5% | 4.4% | 7.5% |
| 5–10% | 27 | 7.6% | 7.4% | 2.5% | 4.3% |
| 10–20% | 30 | 13.6% | 16.7% | 6.1% | 10.1% |
| 20–40% | 53 | 28.9% | 9.4% | 3.3% | 5.6% |
| **> 40%** | 40 | **73%** | 17.5% | **6.4%** | **10.7%** |

- **Wide spreads strongly over-state break risk.** That is the classic arb premium, and it pays the *completion* side.
- Broken deals fell −12% from entry (−8% vs the unaffected price; some were later re-bought).
- Completed deals returned +6% from entry.
- Post-announcement realized vol drops to **11%** (pre-deal 34%).

**Options** (6m, IV = k × pinned RV, 15% spread; mean EV, sample / reweighted to a 10% break rate):

| structure | k=1.5 | k=2.5 | k=4 |
|---|---|---|---|
| 10%-OTM put (bet on break) | −51% / −58% | −73% / −75% | −76% |
| 20%-OTM put | −13% / −28% | −80% | −83% |
| ATM call (bet on completion) | −26% / −25% | −45% / −44% | −56% |
| ATM call, spread > 20% bucket (n=9) | | **+46%** | |

- **Calls do not capture the arb premium.** The upside is capped at the spread; if the spread is 2–5%, an ATM call at even 15% IV costs more than that.
- The only positive cell is the >20%-spread bucket (n=9): anecdotal.
- **Puts on wide-spread deals are the wrong side.** The market already prices 30–70% break odds that realize at about 10%.

### C5. Index inclusion (S&P 500 adds, 228, 2015–2026)

- **Reaction (announcement after close → next close, vs SPY):** +2.12% (t 6.8). 2015–19: +0.67%; 2020+: +3.59%.
- **From reaction day to the effective date:** −0.25% (t −0.9).
- **20 days after effective:** +0.2%. 2015–19: +1.8%; 2020+: −1.45%.
- **Not tradable with long options:** it is all in the overnight gap.

### C6. Current screen: binaries in the next ~6 months

**Upcoming PDUFA dates** (`fda_upcoming.csv`; chains 2026-10-14).
- "Straddle" = ATM straddle ÷ spot for the first expiry after the date.
- "Event" = the event-only move from the term-structure kink (0 = kink not identifiable).
- "Analog" = historical expected \|move\| (21% first approvals, 13% supplements; 25% CRL base).

| ticker | date | drug (first approval?) | cap $B | straddle exp | straddle | event | analog | ATM spread | OI | read |
|---|---|---|---|---|---|---|---|---|---|---|
| IONS | 10-26 | bepirovirsen (GSK sponsor) | 7.1 | Nov-20 | 15% | 8.5% | 13% | 20% | 89 | cheap-ish, but royalty exposure only |
| INO | 10-30 | INO-3107 (yes) | 0.10 | Oct-30 | 67% | 19% | 21% | 200% | 117 | untradable spread |
| SMMT | 11-14 | ivonescimab (yes) | 12.1 | Nov-20 | 30% | 20% | 21% | 16% | 634 | fair |
| CYTK | 11-14 | aficamten sNDA | 8.8 | Nov-20 | 14% | – | 13% | 16% | 444 | fair |
| CAPR | 11-22 | deramiocel (yes, resubmission) | 0.39 | Dec-18 | 93% | – | 21% | 37% | 779 | very rich |
| SVRA | 11-22 | molgramostim (yes) | 0.97 | Feb-19 | 79% | 44% | 21% | 86% | 886 | rich |
| BBIO | 11-27 | BBP-418 | 12.7 | Jan-15 | 20% | – | 13% | 30% | 439 | |
| PYPD | 11-28 | D-PLEX100 (yes) | 0.10 | Feb-19 | 46% | – | 21% | 99% | 2,824 | wide |
| COGT | 11-30 | bezuclastinib (yes) | 4.9 | Jan-15 | 27% | 24% | 21% | 55% | 36 | slightly rich |
| VNDA | 12-12 | imsidolimab | 0.26 | Dec-18 | 36% | – | 13% | 78% | 41 | rich, wide |
| CORT | 12-17 | relacorilant (resubmission) | 12.6 | Jan-15 | 28% | 7.8% | 13% | 10% | 115 | event part cheap; liquid |
| MLYS | 12-22 | lorundrostat (yes) | 1.8 | Jan-15 | 41% | 26% | 21% | 25% | 195 | rich |
| PRAX | 12-27 | relutrigine (yes) | 6.6 | Jan-15 | 61% | 60% | 21% | 14% | 3 | very rich |
| IBRX | 01-06 | Anktiva sBLA | 10.5 | Jan-15 | 45% | 20% | 13% | 14% | 77,524 | rich |
| DYN | 01-21 | z-rostudirsen (yes) | 2.8 | Mar-19 | 54% | 23% | 21% | 42% | 138 | fair event part, wide |
| BBIO | 02-04 | infigratinib | 12.7 | Feb-19 | 45% | 41% | 13% | 31% | 70 | rich |
| BMRN | 02-28 | Voxzogo sNDA | 10.7 | Apr-16 | 21% | 5.9% | 13% | 47% | 349 | event part cheap; wide |
| NTLA | 03-10 | lonvo-z (yes) | 1.6 | Apr-16 | 39% | – | 21% | 70% | 199 | |
| ETON | 03-29 | Libervant (label exp.) | 1.5 | May-21 | 44% | 14% | 13% | 33% | 203 | fair |

- **Candidates under the C1 rule** (event part ≤ about 20%, liquid): CORT (event part 7.8% on a resubmission after a CRL; 10% spread), SMMT and IONS.
- **None currently shows pre-event weakness confirmed by data.** Re-check the 20d XBI-relative return the week before each date.
- **Data caveats:**
  - yfinance IVs are noisy.
  - PHAR, NUVL, APMD, INBX, PHVS and ORGO had no usable chain.
  - Several rows' sponsors are partners (IONS/GSK, ACLX/Gilead, CGEM/Taiho).

**Pending mergers** (`merger_pending.csv`: 50 deals, terms from filings and news, *not all re-verified*; live price 2026-10-14). Cash deals with the widest spreads:

| target | acquirer | offer | price | spread | expected close | key risk | 3m IV / ATM spread / OI |
|---|---|---|---|---|---|---|---|
| BHF | (private) | $70.00 | 47.54 | **47%** | 2026 | insurance regulators (DE, NY, MA) | 61% / 65% / 2,585. **Verify the deal is still alive.** |
| PTC | Schneider | $205 | 193.49 | 6.0% | by 2027-Q3 | US/EU/China SAMR, CFIUS | 9% / – / 2,547 |
| CZR | (private) | $31 | 29.35 | 5.6% | – | gaming regulators, financing | 69% / – / 783 |
| TXNM | Blackstone Infra | $61.25 | 58.52 | 4.7% | 2027-H1 | NM PRC + NRC | 29% / 191% / 101 |
| SYNA | onsemi | $123 | 117.73 | 4.5% | mid-2027 | China SAMR; competing bidder | 11% |
| SLAB | TXN | $231 | 221.41 | 4.3% | 2027-H1 | China SAMR | 11% / – / 2,157 |
| PAYO | – | $7.40 | 7.13 | 3.8% | mid-2027 | money-transmitter approvals | 15% |

- Stock and mixed deals (NSC/UNP 15.6%, SUPN/INDV 31%, UNF/CTAS 22%, AXTA/Akzo) are computed from unverified exchange terms. AXTA mixes a EUR price with USD. **Do not use them.**
- **Per C4:** wide spreads overstate break odds, so puts on BHF/CZR/TXNM are the historically losing side. Calls only work when the spread is very wide (>20%), and only BHF qualifies here. Its chain has a 65% spread: untradable.

**Pending policy and legal binaries** (`legislation_upcoming.csv`; current 3m ATM IV / straddle):
- **HUM:** 2028 MA advance notice (about early Feb 2027) and final notice (about 2027-04-05). IV 51%, 3m straddle 13%. HUM moved about 11% on each of the last two final notices.
- **UNH:** IV 31%, 3m straddle 8%.
- **LYV:** remedies after the April-2026 verdict (date TBD). IV 33%, 3m straddle 8%.
- **MSOS / TLRY:** DEA final rescheduling decision. IV 70–75%, 3m straddle 18–19%.
- **COIN / HOOD:** crypto market-structure bill (low odds in the lame duck). IV 64–69%.
- **COF / SYF:** 10% APR-cap bill (no vote scheduled). IV 35–38%.
- **ABBV / LLY:** CMS negotiated prices due 2026-11-30.
- **SU / XOM:** SCOTUS climate-tort case (*Suncor v. Boulder*).
- **FNMA / FMCC:** IPO/release terms, no date. OTC: no listed options.
- Of these, only **HUM's April rate notice** has a fixed date and a measured history (two ~11% moves against a ~3% normal day). It is the closest thing to a repeatable policy binary. Check the March 2027 event-week IV against an 11% analog before buying.

## D. Option economics summary and bankroll odds

- **EV** = mean return on premium per trade. Reliable OOS (2019+) trades or simulated draws.
- **Bankroll** = 1 year of i.i.d. draws, buying floor(20% × equity / cost) contracts, or 1 contract if the cost is ≤60% of equity; otherwise the trade is skipped.
- **P(grow) / P(ruin)**: ruin = equity below 12% of start.
- **Min capital** = contract cost ÷ 20%.

| strategy | n | EV | median | PoP | contract | trades/yr | min capital | $170 | $1k | $5k |
|---|---|---|---|---|---|---|---|---|---|---|
| A day-1 put 6m ATM, all reports, IV 1.25×RV | 425 | −33% | −76% | 30% | $574 | 60 | $2.9k | unaffordable | 0% / 0% | 0% / 29% |
| A same, fraud only | 152 | −23% | −67% | 36% | $568 | 25 | $2.8k | unaffordable | 2% / 0% | 7% / 16% |
| A fraud only, 1y ATM, IV 1.0×RV (optimistic) | 140 | −6% | −47% | 40% | $630 | 25 | $3.2k | unaffordable | 0% / 0% | 27% / 6% |
| B score ≥4 → 6m ATM put, IV 1.2×RV | 623 | −16% | −51% | 36% | $303 | 40 | $1.5k | unaffordable | 5% / 0% | 5% / 43% |
| B score ≥4, IV 1.0×RV | 623 | +0.4% | −41% | 40% | $303 | 40 | $1.5k | unaffordable | 19% / 0% | 24% / 18% |
| **B restatement → 6m ATM put, IV 1.2×RV** | 289 | −11% | −41% | 41% | $265 | 39 | $1.3k | unaffordable | 11% / 0% | 9% / 24% |
| **B restatement, IV 1.0×RV** | 289 | **+6.5%** | −29% | 45% | $265 | 39 | $1.3k | unaffordable | **34% / 0%** | **36% / 8%** |
| B late filing, IV 1.2 / 1.0 | 610 | −23% / −7% | | 33 / 37% | $292 | 40 | $1.5k | – | 2% / 11% | 2–13% |
| B score ≥3, IV 1.2 / 1.0 | 1,583 | −21% / −5% | | 33 / 39% | $336 | 40 | $1.7k | – | 3% / 11% | 3–16% |
| C FDA 20%-OTM put, implied move 20% | sim | +3% | −100% | 14% | ~$50 | 20 | $250 | 8% / 0% | 15% / 42% | 14% / 40% |
| C FDA 20%-OTM put, implied move 30% | sim | −56% | −100% | 11% | ~$115 | 20 | $580 | 0% | 1% / 23% | 1% / 61% |
| C FDA straddle, implied 20% / 30% | sim | −15% / −43% | | 29 / 15% | $320–480 | 20 | $1.6–2.4k | – | 10% / 0% | 12% / 4% |
| *XSP dip-buy (direction.md), reference* | | *+11.4%* | | *48%* | *$84* | *12.5* | | *55–60%, ruin 1%* | | |

- No strategy here has positive EV at realistic IV. The best (restatement puts at IV = realized) has P(grow) of only about 35%.
- Even the positive cells are unaffordable at $170: one contract costs more than 60% of equity.

## Survives out of sample?

| idea | survives? | status (owner's rule: nothing retired) |
|---|---|---|
| day-1 puts after activist reports | **No.** Negative in both periods at every IV ≥ realized, and the IS-positive subgroups flip. | NOT YET FOUND. Open thread: 1-year puts on fraud-type reports at fair IV (−6% OOS), if real IV after reports ever prints near realized. |
| forensic screen → stock underperformance | **Partly.** Event flags (late, going concern, restatement) are negative in both periods; only auditor change (OOS) and late / going concern (IS) pass BH. Beneish / DSRI / soft assets: **no**. | Keep as a *risk filter* (avoid buying calls on score ≥4 names) |
| forensic screen → puts | **No** at IV ≥ 1.2×RV. Restatement / score ≥4 / late are break-even to +11% only at IV = RV. | Ready when funded (≥$1.3–1.5k): buy only when the quoted IV ≤ ~1.05× the 3m realized vol |
| pre-earnings put on flagged names | No (−17% OOS) | Shelved, not retired |
| FDA straddles | No: priced at 1–3× the historical move | Avoid |
| FDA OTM puts | Only if the implied event move is ≤20%; pre-event weakness raises CRL odds 1.7× (IS and OOS) | **Paper-track** ($50–120 per contract: fits the account) |
| legislation / court binaries | Untestable without option history; tails are huge | Case-by-case: HUM rate notice is the most repeatable |
| merger break puts / completion calls | No. Wide spreads overstate break risk; calls capped | Avoid; the arb premium belongs to stockholders |
| index adds | Overnight gap only | Avoid |

## Recommendation

1. **Do not add a "mini Hindenburg" put strategy to the bot.**
   - Flags do find companies that crash more often: 1.2–2.2× lift, and 63% of score ≥4 names crash within 12m.
   - But single-name put buyers pay for that crash risk through IV that already reflects the high volatility. The excess underperformance after event flags (−5 to −14 pts/6m) is about the cost of the put.
2. **Use the screen defensively.** Never buy calls or dip-buy calls on names with score ≥3 or a recent 4.02, NT or going-concern filing. Their crash rate is 59–66% per year (OOS), against 40%.
3. **Ready when funded (≥$1.5k), paper-trade first:** a 6m ATM put after an 8-K 4.02 restatement (39/yr) or score ≥4 (86/yr), **only when the quoted IV ≤ ~1.05 × the 3m realized vol.** Log the actual IV at each trigger. If live IV/RV on these names is routinely >1.2 (likely), the idea stays "not yet found".
4. **FDA, paper only.** Before each PDUFA, compute the event move from the term kink. If it is ≤ about 20% and the stock is in the bottom tercile of 20d XBI-relative return, note a 20%-OTM put (about $50–120, so it fits the $170 account). Track 20+ instances before trading.
5. **HUM Medicare Advantage final rate notice (about 2027-04-05):** a straddle candidate if the event-week straddle is ≤ about 8% (history: two ~11% moves). Check in March 2027.
6. **Keep XSP dip-buy as the primary strategy** (+11.4%/trade, P(grow) 55–60% at $170).

## Caveats

- **No historical option quotes.** Every option P&L is Black-Scholes with IV proxied from realized vol (k sensitivity shown). Post-event and pre-binary IVs are exactly where proxies are weakest. The live chains (C6) are the only real IVs used.
- **Survivorship.**
  - Delisted names are included via the HF bars, but the delisted-name mapping skips the SEC instance-file lookups that research_fundamental.py uses, so fewer delisted CIKs are covered: 2,194 of 6,358 mapped.
  - Delisting returns hold the last price. Both choices make puts look *worse* than reality for bankruptcies. Only about 22 short-report targets and a few percent of flagged firm-months are affected.
- **Event lists are hand-compiled** and biased toward notable cases:
  - FDA over-represents CRLs (reweighted);
  - mergers have no unbiased break rate (reweighted);
  - legislation cases are memorable by construction (not used for EV claims);
  - Spruce Point dates may be follow-ups.
- **Accounting data.** XBRL starts in 2009–2011, so the first IS years are thin. Beneish components are often missing (set neutral, with ≥5 required). The related-party tags are sparse. The non-GAAP gap is not available.
- **Going-concern full-text search** matches risk-factor boilerplate as well as audit opinions. Hits in exhibits (`gc_ex`) are cleaner but rare.
- **No short-interest history** was tested.
