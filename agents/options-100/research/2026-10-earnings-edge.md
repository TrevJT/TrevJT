# Earnings-move edge, 2026-10-18: are earnings straddles mispriced, for whom, and predictably?

Owner's ask (10-16): "Of every earnings call throughout the year there should be a select few with predictable odds better than the market... Buying options right before earnings and selling after. Maybe the Fortune 500 are priced in but smaller stocks maybe not? Identify mid caps whose earnings typically move the stock aggressively, then build research models around those stocks/industries to find an edge."

Hard rule unchanged: long premium only (straddles, strangles, single long calls/puts, debit spreads as single legs), nothing that can lose more than the premium. Scripts: `research/earnings/` (`fetch.py`, `build.py`, `analyze.py`, `rhspec.py`, `rhanalyze.py`, `forward.py`); raw data and outputs in `data/research_earnings/` (gitignored). Nothing in PLAN.md or ROUTER.md was changed; section 9 is a proposal.

## 1. Executive summary

1. **The owner's hypothesis is backwards on the data: small caps are the *most* over-priced, mega caps the least.** On real Robinhood straddle prices (294 reports, 2022-2026, 123 tickers), an ATM straddle bought at the close before the report and sold at the close after it returns, before spreads: mega +9.4% (n=111, t 1.8), large +0.9% (n=61), mid +2.2% (n=62), small **-10.9%** (n=60, t -2.0). After the spreads measured on live chains (3% round trip mega ... 18% small) the net is mega **+6.4% (t 1.2)**, large -4.1%, mid -7.8% (t -2.2), small **-28.9% (t -5.4)**. Realized move / event-implied move: mega 1.09, large 1.01, mid 1.04, small 0.77; the median is below 1 in every tier (1.06, 0.75, 0.85, 0.53). Earnings straddles are fairly priced to over-priced across the board; only mega caps are not negative, and that is weak evidence (t 1.2, 49.5% win rate).
2. **"Stocks whose earnings typically move them aggressively" exist, but the market prices them.** On 133,517 reports (2,897 tickers, 2009-2026, EDGAR-timed) the level of the earnings move is a stable property (software/semis/medtech small caps move 8-9% a quarter, banks/REITs 3-4%) and it has doubled since 2010 (small caps 4.4% -> 8.6%). But the *surprise relative to a stock's own history* does not persist by ticker (IS -> OOS Spearman **-0.28**; 2019-22 -> 2023+ **-0.40**: last period's big surprisers under-deliver next period) or by industry (every industry's realized/own-history ratio is 1.10-1.15). Of 2,442 tickers, 0 survive BH for "beats its own history". The market's straddle sits 1.24x (mega) to 1.77x (mid) above the own-history mean move, i.e. it already adds a premium on top of history.
3. **Predictable? Vs. own history, yes (AUC 0.61, top decile 1.66x vs bottom 0.76x, stable every year 2019-26). Vs. the market's price, no.** The features that predict realized/own-history (peer read-through t 8.1, last move t -10, distance from 52-week high t -7, current vol, volume ramp) are mostly the market's own inputs: inside the option sample none of them predicts the straddle's net return (16 features, 0 pass BH; the best OOS t are 2.3-3.1 on n ~ 160 with 16 draws), and a walk-forward model on the option sample has Spearman 0.03 with the net return. The straddle's return is 89% explained by realized/implied (r = 0.89), and nothing we can see at the entry close forecasts that ratio.
4. **Costs decide the small-cap answer, as in smallcap.md.** Small-cap straddles already lose 11% at mid; at an 18% round-trip spread they lose 29% and win 23% of the time. Weekly expiries (0-3 DTE after the report) are the only structure near fair (net -0.5%, 46% win); 4-10 DTE weeklies are -16% net, monthlies -8% net.
5. **The free historical option data finding is real and durable.** Robinhood's `get_option_historicals` returns daily bars for EXPIRED contracts back to at least January 2019 (close-only marks before ~2023, full OHLC after; trade-based for thin names; no intraday history). That is the first free source of historical implied moves this repo has had; the pipeline (`rhspec.py` -> MCP sub-agents -> `rhanalyze.py`) is reusable for any event study.
6. **Direction, drift, peers:** nothing predicts the sign of the earnings move (all |t| <= 2.3 on 69k OOS events; a 5-day run-up reverses by 0.4%, far inside costs). Post-earnings drift is +0.8%/20d on the biggest winners and ~0 on losers: real, too small for options (smallcap.md agrees). Peer read-through (a sector peer moved big in the last 3 weeks) is the strongest *move-size* signal in the panel (OOS +0.23 ratio points, t 8.1) and worth watching on live quotes, but in the option sample it did not pay (t 0.2).
7. **Honest bottom line:** there is no "select few with predictable odds better than the market" in the data. Buying the straddle before earnings is a fair-to-losing bet that gets worse as the company gets smaller. The residual that survives is narrow: liquid mega-cap weeklies (META, NFLX, TSLA, AMZN, JPM in this sample: realized/implied 1.2-1.5, net +22% to +46% on 7-9 reports each, which is exactly what P9 was built on, and exactly as fragile as 8 observations). Nothing on the forward list has positive expected value and fits $170; the paper list in section 8 is for measuring, not for believing.

## 2. Data sources (and the free-historical-options finding)

| Need | Source used | Coverage / quality |
|---|---|---|
| Earnings dates + BMO/AMC timing | SEC EDGAR 8-K item 2.02 `acceptanceDateTime` (from the `submissions.zip` bulk file already on disk), converted to ET: < 09:30 = BMO, >= 16:00 = AMC, otherwise "mid" | 185k filings, 3,208 tickers, 2004-2026. 29% of filings are "mid" (the 8-K is furnished the next morning or during the session); resolved with Yahoo's timing, else dropped. Non-earnings 2.02 filings (TSLA delivery reports, pre-announcements) are dropped by requiring a Yahoo earnings date within 2 days |
| Earnings dates (cross-check, EPS estimate/actual/surprise) | `yfinance get_earnings_dates(limit=100)` | 177k dates, 3,158 tickers, back to 2006-2010 (yfinance 1.7 serves far more than the ~26 quarters seen in the small-cap study). Timing is in the timestamp hour (16:00 = AMC, 06:00-09:00 = BMO) |
| Robinhood `get_earnings_calendar` / `get_earnings_results` | MCP | 2,340 reports with verified am/pm timing for 2026-10-19..11-14 (the forward universe); 8 trailing quarters per symbol: the best source for the next report's timing, no history beyond 2 years |
| Daily bars | yfinance (auto-adjusted) for the move panel; a second pull with `auto_adjust=False, actions=True` to recover UNADJUSTED closes for strike selection | 3,284 tickers, 2009-2026. Survivors only: yfinance has no delisted bars, so the panel misses every name that went to zero or was taken out (section 7) |
| Market cap at the event | EDGAR `dei` shares outstanding (point-in-time, by filing date) x entry close; fallback today's cap scaled by price | 87% point-in-time; tiers mega >= $200B, large $10-200B, mid $2-10B, small $0.3-2B, micro < $0.3B |
| Industry | EDGAR SIC (bucketed into 15 groups); GICS for S&P 500/400 names | all tickers |
| Universe | Robinhood calendar names (cap > $1B) + the small-cap cache (SPSM/MDY/IWM holdings) + S&P 500/400 | 3,567 symbols, 2,897 with usable events |
| **Historical option prices** | **Robinhood `get_option_instruments(state='expired')` + `get_option_historicals(interval='day')`** | **see below** |
| Live chains for the forward list | yfinance chains (Saturday snapshot; stale/one-sided quotes filtered: both bids > 0, spread < 50% of mid) | 330 names; spot-check the top names on Robinhood before any paper entry |

**Free historical option data exists on Robinhood.** `get_option_instruments` with `state='expired'` resolves expired contracts back to **early 2018** (MSFT Feb-2018 weekly found; Jan-2017 and Jan-2016 not), and `get_option_historicals` returns **daily OHLC bars for those expired contracts back to at least January 2019** (MSFT 2019-02-01 105C/P: real, non-interpolated bars 2019-01-28..31). Properties measured 2026-10-16..18:
- Before ~2023 the daily bars are close-only marks (open = high = low = close); from 2023 they are full OHLC. The 0DTE backfill (other session) confirms daily bars >= 1 year, real 10-minute bars to ~June 2026, 5-minute ~7 sessions.
- Bars are trade-based for thin contracts: `open = 0.01` means no trade yet that day; the close carries the last trade, so for small-cap monthlies the mark can be a day stale. Liquid names (mega/large weeklies) are fine. Intraday bars for expired contracts come back `interpolated: true` only.
- `end_time` is exclusive at day granularity (ask for window end + 1 day). Bars carry no volume and no bid/ask, so spreads must come from live chains.
- Weekly expiries are often absent in the expired listing for small/mid caps (they were never listed); monthlies are reliably present.
- Cost: ~1-6 instrument calls per event (strike guessing) and one historicals call per 5 events (10 ids, ~15 KB). The pull is MCP-only (no scriptable endpoint from Python), so sub-agents transcribed bars into `data/research_earnings/rh2_out_*.jsonl`; ~6k tokens per event, which is what capped the sample at 294 valid events (of 1,227 specified; 410 attempted, 309 contract pairs found, 15 dropped for stale/one-leg marks or > 6% moneyness).
- Strikes must be built from UNADJUSTED prices: Yahoo's auto-adjusted close is 6-20% below the real price for dividend payers and 4-20x off for split names, and Robinhood lists expired contracts at their original strikes. The first pull attempt (892 of 2,010 rows mis-struck) was discarded; now in LEARNINGS.

Other sources checked: Alpaca's options history (free with any account, indicative feed) starts Feb 2024; Polygon (now "Massive") has no options on the free tier (options start at the $79-99/month Developer tier); CBOE DataShop and ORATS are paid. Robinhood is the only free source with 2019+ history, and it is the owner's own broker.

## 3. The realized-move panel (133,517 events, 2,897 tickers, 2009-2026)

Definitions. R = reaction day (the first session whose open can trade on the report). C0 = close before R (the entry close). `cc` = close(R)/C0 - 1 (the earnings move), `co` = open(R)/C0 - 1 (the gap). `hist8` = the mean |cc| of the ticker's previous 8 reports, the naive own-history forecast; `ratio8` = |cc| / hist8. IS = 2009-2018, OOS = 2019+.

### 3.1 Segment table (OOS 2019-2026)

| Tier | events | tickers | mean abs move | median | mean abs gap | P(>10%) | ratio8 mean | ratio8 median | P(ratio8 > 1) |
|---|---|---|---|---|---|---|---|---|---|
| mega (>= $200B) | 727 | 79 | 4.6% | 3.6% | 3.6% | 9% | 1.12 | 0.90 | 46% |
| large ($10-200B) | 13,353 | 775 | 4.7% | 3.5% | 3.5% | 10% | 1.11 | 0.88 | 45% |
| mid ($2-10B) | 21,138 | 1,476 | 5.8% | 4.3% | 4.2% | 15% | 1.11 | 0.85 | 43% |
| small ($0.3-2B) | 21,979 | 1,567 | 7.2% | 5.2% | 5.0% | 21% | 1.13 | 0.84 | 43% |
| micro (< $0.3B) | 7,284 | 728 | 7.5% | 5.3% | 4.9% | 23% | 1.18 | 0.85 | 44% |

- Moves are right-skewed: the mean is 1.1-1.4x the median everywhere, the mean ratio to own history is ~1.12 while the median is ~0.86, and only 43-46% of reports beat their own average. A straddle buyer is paid by the tail and wins less than half the time even at fair pricing.
- Earnings moves have grown every year: small caps 4.4% (2010) -> 6.2% (2019) -> 8.6% (2025) -> 8.3% (2026 YTD); large 2.9% -> 3.9% -> 5.3% -> 5.7%; mega 2.8% -> 4.3% -> 4.6% -> 5.6%. Any own-history model lags this drift, one reason the mean ratio8 is above 1.
- Timing: AMC reports move more (6.5% vs 5.5% BMO) but the ratio to own history is the same (1.12 vs 1.12).
- Industry (OOS mean |cc|): software/internet 9.4%, medtech/health services 8.4%, semis 8.4%, hardware/electronics 8.4%, retail 7.7%, services/media 7.3%, biotech/pharma 6.7%, industrials/materials 6.2%, consumer goods 6.0%, insurance 5.2%, energy 4.6%, transport/utilities/telecom 4.4%, banks/finance 3.8%, REITs 3.4%. The ratio to own history is 1.10-1.15 in every industry.

### 3.2 Is the realized move vs own history predictable? (features known at the entry close)

Top-minus-bottom quintile spread of ratio8 (clipped 0-4), t-stats clustered by report week; 20 features, 11 pass Benjamini-Hochberg (q = 0.10) out of sample.

| Feature | IS spread (t) | OOS spread (t) | Reading |
|---|---|---|---|
| peer_ratio (same industry, reported in the prior 21 days: their ratio8) | +0.32 (13.6) | **+0.23 (8.1)** | peer read-through is the strongest ex-ante move-size signal; +0.19..+0.27 inside every tier |
| evol_mult (hist8 / today's daily E-move from RV20) | | -0.46 (mega) .. -0.74 (micro), t -4 to -19 | the biggest effect: when own history is large relative to today's vol the next move disappoints vs history |
| last_acc (last report's move) | -0.18 (-8.3) | -0.20 (-10.4) | mean reversion of the ratio (a big last move inflates hist8) |
| dist_hi (distance below the 52-week high) | -0.25 (-10.8) | -0.17 (-7.4) | names near highs surprise more vs history; beaten-down names less |
| hist8_cv (dispersion of past moves) | +0.13 (5.6) | +0.13 (7.7) | lumpy histories keep surprising |
| vratio (5d/60d volume) | +0.08 (3.4) | +0.11 (5.5) | pre-report volume = bigger move |
| rv20 | +0.13 (5.0) | +0.11 (4.9) | current vol above history vol |
| run60 / run20 | -0.24 / -0.17 | -0.12 (-4.9) / -0.04 (-2.0) | run-ups precede quieter reports (vs history) |
| last_surprise, ratio_prior, logcap | small | -0.09 (-4.5), +0.05 (2.7), -0.05 (-2.5) | |
| n_prior, adv20, month, prevday, run5 | | n.s. OOS | |

Walk-forward HistGB (train on all seasons before S, test S, from 2019Q1; 69,476 OOS events): AUC 0.607 for "ratio8 > 1", Spearman 0.22 with ratio8. Top decile realized 1.66x own history (62% beat it), bottom decile 0.76x (28%); the top decile is 1.57-1.72 in every year 2019-2026. **But** the top decile's absolute move is 4.6% and the bottom's 8.1%: the model mostly learns that `hist8` is a stale forecast (mean reversion plus today's vol level). It predicts the realized move better than the naive own-history proxy does; whether it beats the *market's* forecast is section 4.

### 3.3 Does "moves more than its history" persist by ticker or industry? No.

- Ticker mean ratio8, IS (2009-18) vs OOS (2019+), 1,701 tickers with >= 8 events in each: Spearman **-0.28**. 2019-22 vs 2023+: **-0.40** (n = 1,997). The IS top decile averages 1.08 OOS vs 1.11 for everyone; the IS *bottom* decile averages 1.17. Of 2,442 tickers with >= 12 OOS events, 0 survive BH for "ratio8 > 1".
- The negative correlation is mechanical: a ticker whose last 8 moves were big has a big hist8, and the next move regresses. "Stocks whose earnings typically move them aggressively" is a stable property of the *level* (software/semis/medtech small caps move 8-9% every quarter) but the market prices the level (section 4: the straddle sits 1.2-1.8x above hist8); the *surprise relative to history* does not belong to a ticker.
- Industries: ratio8 1.05-1.14 IS and 1.10-1.15 OOS; no industry is a persistent surpriser.
- The ranked list by OOS ratio8 (PACK, BLMN, EOSE, GEO, JELD, DERM, THRY, BFAM, XRX, VTEX ... t vs 1 of 2.0-2.4 on n = 15-31) is what noise looks like with 2,442 draws; it stays in `analyze_out.json` only so nobody re-discovers it.

### 3.4 Direction and drift

- Direction: top-bottom quintile spreads of signed `cc` are 0.1-0.4% for every feature (|t| <= 2.3; the only OOS t beyond 2 is a 5-day run-up *reversal* of -0.42%, t -2.3, far inside option costs). Nothing predicts the sign of the earnings move; the same answer as direction.md, universe.md and smallcap.md.
- Day-0 continuation: for the top decile of reactions the gap is +7.6% and the close-to-close +17.5%, i.e. the move keeps running from the open to the close (and symmetrically for the bottom decile, -6.9% gap, -16.0% close). It is only tradable after the open at post-crush IV; the option sample says selling the straddle at the open (net -9%) is worse than at the close (net -6%), consistent with that continuation.
- PEAD OOS: decile 10 of `cc` (+17.5%) drifts +0.7%/5d and +2.2%/20d vs +0.4%/+1.3% for the middle deciles; decile 1 (-16%) drifts +0.4%/+1.0% (no negative drift). The excess is ~+0.8% per 20 days on the winners, consistent with smallcap.md's finding that it is too small for options.

## 4. The market's price: Robinhood expired-straddle sample (294 reports, 2022-2026)

Sample: stratified by cap tier (13 mega from 2022, 30 large / 45 mid / 35 small from 2024-07; micro has no options), ATM straddle = nearest listed strike (mega/large: weekly after the report, else monthly; mid/small: monthly first because weeklies were rarely listed). Entry = sum of the call and put closes on the session before R; exits = open of R (only when both legs traded), close of R, close of R+1. Event-implied move = straddle / spot with the post-event time value removed in variance (0.8 x RV20 x sqrt(DTE after R / 252)). Costs: round trip at half the quoted spread each way from the live chains measured 2026-10-14 (mega 3%, large 5%, mid 10%, small 18% of premium). t-stats clustered by report week. Coverage note: the pull is MCP-only and token-expensive; 410 of 1,227 specified events were attempted (two more sub-agents were still adding mid/small/large events when this was written; the tables will be refreshed if they finish).

### 4.1 By tier

| Tier | n | straddle / spot | event-implied | realized | realized / implied (mean / median) | straddle / hist8 | gross, close exit (t) | net, close exit (t) | net, open exit | net, next-day exit | P(win, net) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mega | 111 | 6.7% | 6.4% | 6.9% | 1.09 / 1.06 | 1.24 | **+9.4% (1.8)** | **+6.4% (1.2)** | -3.7% | +11.3% | 50% |
| large | 61 | 7.8% | 5.5% | 5.0% | 1.01 / 0.75 | 1.57 | +0.9% (0.2) | -4.1% (-0.7) | -11.5% | +3.3% | 38% |
| mid | 62 | 11.6% | 9.0% | 8.8% | 1.04 / 0.85 | 1.77 | +2.2% (0.6) | -7.8% (-2.2) | -13.2% | -10.0% | 39% |
| small | 60 | 14.8% | 11.6% | 9.5% | **0.77 / 0.53** | 1.41 | **-10.9% (-2.0)** | **-28.9% (-5.4)** | -17.0% | -23.4% | 23% |
| all | 294 | 9.6% | 7.8% | 7.4% | 1.00 / 0.82 | 1.60 | +2.0% (0.7) | -6.0% (-2.1) | -9.2% | -3.0% | 39% |

- The market's straddle is above the own-history mean move in every tier (1.24x mega to 1.77x mid): "the stock usually moves X%" is already in the price plus a premium.
- The mean realized/implied is ~1 in mega/large/mid but the *median* is 0.75-0.85: the straddle buyer loses most of the time and is paid back by the 20% of reports that run 2x. In small caps even the mean is 0.77.
- Selling at the open is worse than at the close in every tier (day-0 continuation plus the thin opening print); holding to the next close helps mega/large (vol has not fully come out) and hurts mid/small.

### 4.2 By expiry, timing, year, industry

| Cut | n | realized / implied | gross close | net close (t) | P(win) |
|---|---|---|---|---|---|
| 0-3 DTE after R (weekly, report week) | 134 | 1.04 / 0.95 | +4.0% | -0.5% (-0.1) | 46% |
| 4-10 DTE (next weekly) | 53 | 0.86 / 0.70 | -3.5% | -16.2% (-2.8) | 30% |
| 11-40 DTE (monthly) | 107 | 1.01 / 0.72 | +2.1% | -7.8% (-2.7) | 36% |
| AMC | 181 | 1.05 / 0.85 | +2.8% | -4.3% (-1.1) | 43% |
| BMO | 21 | 1.03 / 0.87 | +8.4% | -3.3% (-0.4) | 43% |
| 2022 (mega only) | 49 | 1.06 / 0.90 | +4.6% | +1.6% | 45% |
| 2023 (mega only) | 28 | 1.14 / 1.07 | +15.4% | +12.4% | 54% |
| 2024 | 53 | 0.90 / 0.65 | -1.2% | -10.2% (-1.8) | 42% |
| 2025 | 106 | 1.03 / 0.82 | +1.1% | -9.0% (-1.7) | 35% |
| 2026 | 58 | 0.91 / 0.77 | -2.2% | -11.9% (-3.6) | 34% |
| software/internet | 69 | 0.93 / 0.71 | -4.7% | -11.6% (-1.6) | 39% |
| industrials/materials | 30 | 1.17 / 1.20 | +9.1% | +4.0% (0.5) | 47% |
| services/media | 25 | 0.96 / 0.67 | +4.3% | -3.7% | 36% |
| biotech/pharma | 25 | 0.80 / 0.62 | -7.2% | -16.0% (-3.6) | 28% |

- The "weekly in the report week" line is the only structure near fair after costs, and it is dominated by mega caps (they are the names with weeklies). The pre-report IV ramp (straddle on R-1 vs 5 sessions earlier) is -8% to -19% at the median, i.e. the straddle usually *cheapens* into the report as time value decays faster than event IV rises; buying 5 days early is worse.
- The owner's "guidance-heavy industries" (software, biotech) are the worst buys in the sample; industrials the best (n = 30, t 0.5).

### 4.3 Features vs the straddle's net return (top - bottom tercile, n = 294; IS < 2025, OOS 2025+)

evol_mult -0.04 (t -0.4); implied/hist8 -0.11 (-1.5); hist8_cv -0.13 (-1.8); rv20 -0.11 (-1.8); run5/20/60 +0.02..+0.04 (<= 0.6); dist_hi +0.17 (2.0; OOS +0.25, t 2.7); vratio +0.07 (0.8; OOS +0.21, t 2.3); peer_ratio -0.04 (-0.5); ratio_prior +0.06 (1.0); last_acc -0.07 (-1.0); IV ramp -0.21 (-2.5); implied level -0.17 (-2.1); n_prior +0.03 (0.5; OOS +0.21, t 3.1); DTE -0.09 (-1.2). 0 of 16 pass BH on the full sample; the three OOS t > 2 are on ~160 events with 16 draws and flip sign between IS and OOS. Walk-forward HistGB inside the option sample (season by season, 2025Q1+, n = 164): Spearman 0.03 with the net return, top quartile -9% (t -1.3). The panel model's strongest signals (peer read-through, mean reversion of the ratio) do not translate into straddle P&L because the market's implied move already moves with them: straddle/hist8 is 1.2-1.8x precisely where the panel model predicts ratio8 > 1.
- Per-ticker persistence inside the sample (first half vs second half of each ticker's reports, 11 tickers with >= 8): Spearman -0.34 on realized/implied, -0.30 on net return.
- Calibration used by the forward list: net straddle return (close exit) = a + b x (realized / event-implied), r = 0.89; pooled a = -0.61, b = 0.63; mega a = -0.87, b = 0.88; large/mid a = -0.44/-0.46, b = 0.47; small a = -0.59, b = 0.62.

## 5. Model results with OOS statistics (summary of 3.2, 3.3, 4.3)

| Model / test | Sample | OOS metric | Verdict |
|---|---|---|---|
| Walk-forward HistGB, target realized/own-history > 1 (17 features + tier + industry) | 69,476 OOS events 2019Q1-2026Q3, season-by-season | AUC 0.607; top decile 1.66x (62% beat history), bottom 0.76x; stable 1.57-1.72 every year | real, but it forecasts the *move*, not the *mispricing*; the market's straddle is 1.2-1.8x history and tracks the same inputs |
| 20 single-feature quintile tests on ratio8 | same | 11 pass BH q=0.10 (peer_ratio t 8.1, last_acc -10.4, dist_hi -7.4, hist8_cv 7.7, vratio 5.5, rv20 4.9, run60 -4.9, last_surprise -4.5, ratio_prior 2.7, logcap -2.5, run20 -2.0) | same reading |
| Ticker persistence of ratio8 | 1,701 / 1,997 tickers | Spearman -0.28 / -0.40; 0 of 2,442 BH | no "stock that always surprises" |
| Industry persistence | 15 groups | all 1.10-1.15 | none |
| 9 direction features x 2 targets | 69k | all |t| <= 2.3, spreads <= 0.4% | no direction |
| Real straddles by tier (RH sample) | 294 | mega +6.4% net (t 1.2), large -4.1%, mid -7.8% (t -2.2), small -28.9% (t -5.4) | fair-to-overpriced; only mega non-negative |
| 16 features vs straddle net return | 294 | 0 pass BH; walk-forward Spearman 0.03 | no selection rule inside the sample |
| Exit variants (open / close / next close) | 294 | open -9.2%, close -6.0%, next -3.0% net (all); mega -3.7 / +6.4 / +11.3 | sell at the close of R or later, never the open |
| Expiry choice | 294 | report-week weekly -0.5% net; next weekly -16%; monthly -8% | the report-week weekly is the only fair structure |

Tests run: 20 + 7x5 (per tier) + 18 (direction) + 2 (walk-forward) in the panel = 75 families; 16 + 1 in the option sample; the "mega +6.4%" is 1 of 4 tiers x 3 exits = 12 cells (and 0 of 12 pass BH at q = 0.10).

## 6. Ranked tickers and industries

**Persistent realized > implied: none with statistics that survive.** What can be ranked honestly:

- Mega caps in the option sample (realized/implied, net straddle return at the close, n): META 1.49 / +46% / 8; JPM 1.43 / +41% / 7; NFLX 1.29 / +26% / 9; TSLA 1.30 / +23% / 9; AMZN 1.22 / +22% / 8; AVGO 1.25 / +14% / 7; AMD 1.13 / +7% / 9; MSFT 1.08 / +4% / 10; LLY 1.00 / -3% / 9; ORCL 0.87 / -12% / 9; AAPL 0.85 / -20% / 9; GOOGL 0.76 / -24% / 9; CRM 0.68 / -30% / 8. Thirteen names, 7-10 reports each: the spread between the best and worst is what 8 draws of a 50%-vol variable produce, and inside the sample the first-half ranking predicts the second half with Spearman -0.34. Treat META/NFLX/TSLA/AMZN/JPM as "not negative so far", not as edge.
- Industries by realized/implied in the option sample: industrials/materials 1.17 (n 30), services/media 0.96, software/internet 0.93 (n 69), biotech/pharma 0.80 (n 25). By move size in the panel (where to look if one wants big moves, not mispricing): software/internet, medtech, semis, hardware at 8-9% per report; banks and REITs at 3-4%.
- Industries NOT to buy earnings straddles in, on both samples: biotech/pharma (straddle 1.65x history, realized 0.80x implied, net -16% t -3.6; forensic_events.md found the same for PDUFA straddles) and small-cap software (0.93x implied at the widest spreads).
- Tier ranking for a long-straddle program: mega > large > mid >> small. The owner's "smaller stocks are less priced in" is reversed: small-cap straddles carry the largest premium over realized (realized/implied 0.77) *and* the widest spreads.

## 7. What failed

1. **Adjusted prices as strikes.** The first option pull built ATM strikes from Yahoo's auto-adjusted closes; 892 of 2,010 rows were off by > 1.5% (JPM 2019 "82" vs a real $101; AAPL 2019 $42 vs $165), the sub-agents found deep-ITM or no contracts, and the pull was discarded. Rule: strike selection uses unadjusted closes (`yf.download(auto_adjust=False)` Close x future split factors). Robinhood lists expired contracts at their original strikes (TSLA 2019 "20" strike is a real $20 strike, not an adjusted $300).
2. **Trade-based option bars.** An `open` of 0.01 is "no trade yet", not a price; the first version's "sell at the open" returns were -16% to -33% from that artefact. Now filtered (both legs' opens > 0.01); the real open-exit is -4% to -17% net by tier.
3. **The pull itself.** MCP-only data at ~6k tokens per event (strike guessing + transcription) exhausted the session limit twice (14 sub-agents died). 294 valid events instead of the 1,227 specified; mid/small/large tiers have 60 events each, enough for the tier means (t -2 to -5) but not for feature tests. The next version should list each expiry's strikes once per chain (one paginated call) instead of guessing, and run 2 agents at a time on a cheaper model.
4. **Monthly expiries for mid/small.** Weeklies were rarely listed for these names before 2025, so their straddles carry 2-4 weeks of post-event time value; the variance-subtraction adjustment is approximate (it uses RV20, which is itself inflated by past reports). The realized/implied ratio for monthlies is therefore uncertain by perhaps +/-0.1; the net return numbers (which need no adjustment) are not affected.
5. **Survivorship.** No delisted names in the price panel (yfinance). Delisted small caps have the biggest earnings moves (going-concern quarters) and the biggest straddle payoffs; the panel's small-cap ratio8 is biased *down* and the option sample (which is only 2024+ survivors) likewise. This works against the straddle buyer in our numbers but cannot flip a -29% net.
6. **The panel model looks good and means little.** AUC 0.61 vs own history is mostly "the market's forecast is better than an 8-quarter average", which is not a trade. Lesson: a proxy-implied test must be followed by a real-implied test before anything is called predictable.
7. **Short interest, analyst count, estimate revisions** were not tested: no free point-in-time history (today's values would be look-ahead). SUE/surprise is post-event and was used only for drift.
8. **Micro caps** have no listed options in practice (0 in the sample).

## 8. Forward paper watchlist (Oct 19 - Nov 14, 2026)

Method: every calendar name with >= 8 panel events was scored (panel model expected move = predicted ratio x hist8); live straddles from Saturday's yfinance chains at the first expiry after the report (stale/one-sided quotes dropped; 330 names fetched: top by model score, top by historical move size, and all mega caps); event-implied as in section 4; EV = tier calibration (section 4.3) applied to expected/implied, minus half the live spread. **All EVs are model outputs on a sample where the same model had Spearman 0.03 with realized P&L; the list exists to be graded, not traded live.** Nothing with positive EV fits $170.

| Ticker | Report | Expiry | Spot | Straddle mid (ask) | Spread | Implied (event) | hist8 | Model move | Model / implied | EV (close exit) | Cost / contract | Capital label |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| META | Oct 21 AMC | Oct 23 | 709 | $51.75 ($52.6) | 3% | 7.3% (6.7%) | 7.4% | 7.4% | 1.10 | +7% | $5,260 | TRADEABLE-WITH-MORE-CAPITAL (~$15k at 35%) |
| MSFT | Oct 28 AMC | Oct 30 | 529 | $31.95 ($33.1) | 7% | 6.0% (5.9%) | 7.0% | 6.5% | 1.10 | +7% | $3,305 | TRADEABLE-WITH-MORE-CAPITAL (~$9.5k) |
| MXL | Oct 22 AMC | Nov 20 | 71 | $20.10 ($20.8) | 7% | 28% (14% event) | 20.6% | 16.8% | 1.20 | +6% | $2,080 | TRADEABLE-WITH-MORE-CAPITAL (~$6k); monthly, adjustment uncertain |
| HII | Oct 29 BMO | Nov 20 | 272 | $29.50 ($30.9) | 10% | 10.8% (8.6%) | 11.9% | 10.1% | 1.16 | +5% | $3,090 | TRADEABLE-WITH-MORE-CAPITAL (~$9k) |
| HAE | Nov 5 BMO | Nov 20 | 118 | $15.95 ($17.7) | 22% | 13.5% (6.7%) | 11.7% | 11.7% | 1.74 | +24% | $1,770 | TRADEABLE-WITH-MORE-CAPITAL; implied_ev probably too low (adjustment), treat EV as ~0 |
| TMUS | Oct 28 AMC | Oct 30 | 159 | $10.55 ($12.7) | 41% | 6.6% (6.0%) | 6.8% | 7.3% | 1.22 | 0% | $1,270 | weekend quote too wide; re-quote Monday |
| TSLA | Oct 21 AMC | Oct 23 | 355 | $26.28 ($26.4) | 1% | 7.4% (7.2%) | 7.8% | 7.1% | 0.98 | -2% | $2,645 | the P9 trade: fair, not cheap; the 2022-26 sample says TSLA realized 1.30x implied on 9 reports, net +23% |
| NFLX | Oct 21 AMC | Oct 24 | (chain not captured) | | | | 9.6% implied avg | | | | ~$9,000 | realized 1.29x on 9 reports; re-quote Monday |
| CLF | Oct 19 BMO | Oct 23 | 12.1 | $1.48 ($1.57) | 13% | 12.2% (10.7%) | 12.4% | 11.0% | 1.03 | -4% | **$157** | TRADEABLE-NOW, EV negative: the cheapest fair straddle on the list; paper only |
| SOFI | Oct 27 BMO | Oct 30 | 14.6 | $1.61 ($1.63) | 3% | 11.0% (10.4%) | 7.5% | 7.2% | 0.69 | -14% | **$163** | TRADEABLE-NOW, EV negative: do not buy; logged as the "crowded name" control |
| PRGO / IBTA / AGL / PRCH / SEZL / MQ | Nov 2-5 | Nov 20 | | | 15-47% | 10-22% | 13-37% | 11-27% | 1.3-2.5 | +6..+87% (model) | $175-$2,950 | small-cap monthlies: the EV is the time-value adjustment talking, and the tier's real record is -29% net; paper-log only, do not size |

Also on the calendar, for the record from earlier paper lists: BAH 10/23 (BMO, straddle not captured, mid-cap services), ORN 10/27 AMC (small, monthly only, hist8 ~11%), CMPR 10/28, UPBD 10/29: all fall in the "small/mid monthly" bucket that lost -8% to -29% net in the sample; they stay paper LEAPS ideas (fundamental.md), not earnings straddles.

Paper protocol: at 15:50 ET on the entry day, log the live Robinhood ATM straddle (bid/ask, both legs) for the names above plus the 20 highest-model-score names with a weekly expiry; at 15:50 on R log the same; grade realized/implied and the straddle return at the mid and at the ask. 40 graded events (two seasons) before any of this touches the live account.

## 9. Proposed ROUTER playbook text (proposal only; PLAN.md / ROUTER.md untouched)

- **P9 (mega-cap earnings strangle): keep LIVE, narrow the rule.** Evidence now: mega-cap straddles 2022-26 realized 1.09x event-implied, +6.4% net at the close exit (n 111, t 1.2); the strangle version is untested. Rule changes: (a) only weeklies expiring in the report week; (b) exit at the close of R or the next close, never at the open (open exit -3.7% vs close +6.4% net); (c) skip when the straddle is > 1.3x the name's 8-report mean move (section 4: the market's 1.24x is the mega norm); (d) size as now (<= $70), because the t-stat is 1.2.
- **New P16 "earnings straddle, paper": WATCH.** Universe = Robinhood calendar names with a weekly expiry in the report week and a quoted straddle spread <= 8%. Score = panel model expected move / event-implied (`forward.py`). Log 40 events at 15:50 on entry and reaction days before any money; promote only if net realized return at the ask is > 0 with t > 2.
- **Do-not-trade rules (evidence-backed):** no earnings straddles on small caps (< $2B: -29% net, 23% win), on biotech/pharma (-16% net, t -3.6; PDUFA straddles were already dead in forensic_events.md), on monthly expiries when a weekly exists, and never buy the straddle more than 2 sessions before the report (the IV ramp is negative: -8% to -19%).
- **Peer read-through as a watch item, not a rule:** when >= 3 same-industry names realized > 1.3x their own history in the prior 3 weeks, log the later reporters' straddles; the panel says their moves run +0.23 ratio points higher, the option sample says the market already prices it (t 0.2). 40 logged events decide.
- **Engine hygiene:** earnings dates and timing from EDGAR 8-K 2.02 acceptance times (free, exact) with Robinhood `get_earnings_results` for the next report; strikes from unadjusted prices; option history from Robinhood expired contracts (daily only).

## 10. Methods, caveats, files

- Panel: 133,517 (ticker, reaction day) events 2009-2026, 2,897 tickers; sources and timing rules in section 2 and `build.py`. 83,172 events EDGAR-timed, 30,049 EDGAR "mid" resolved with Yahoo, 20,312 Yahoo-only with explicit timing. Moves use auto-adjusted closes (dividend effects < 0.1% on a one-day move). Features known at entry use bars through R-1 only. Peer read-through uses only events with R at least one day earlier.
- Statistics: cluster-robust t by report week; Benjamini-Hochberg q = 0.10 within each family; IS/OOS split 2018/2019 for the panel, 2024/2025 inside the option sample; walk-forward refits by season. Ratio variables clipped at 0-4, returns at -1..+4.
- Option sample: 294 valid of 410 attempted (1,227 specified; see section 7.3). Contract = nearest listed strike to the unadjusted entry close (|strike/spot - 1| < 6% enforced); entry/exit marks are Robinhood daily closes (last trade); costs by tier from live chains. The event-implied adjustment for post-event time value is approximate for monthlies.
- Multiple testing: 75 panel families, 17 option-sample tests, 12 tier x exit cells; every "positive" cell reported above is shown with its t and family size, and none of the positive ones passes BH.
- Files: `research/earnings/fetch.py` (EDGAR/yfinance/caps), `build.py` (panel), `analyze.py` (panel tests -> `analyze_out.json`), `rhspec.py` (option-pull spec), `rhanalyze.py` (option sample -> `rh_events.pkl`, `rh_out.json`), `forward.py` (forward scores, chains, watchlist -> `fwd_table.pkl`). Data under `data/research_earnings/` (gitignored): `edgar_events.pkl`, `yfdates.pkl`, `prices.pkl`, `raw_close.pkl`, `panel.pkl`, `rh2_out_*.jsonl`, `fwd_*.pkl`.
