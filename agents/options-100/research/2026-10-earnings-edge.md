# Earnings-move edge, 2026-10-17: are earnings straddles mispriced, for whom, and predictably?

Owner's ask (10-16): "Of every earnings call throughout the year there should be a select few with predictable odds better than the market... Buying options right before earnings and selling after. Maybe the Fortune 500 are priced in but smaller stocks maybe not? Identify mid caps whose earnings typically move the stock aggressively, then build research models around those stocks/industries to find an edge."

Hard rule unchanged: long premium only (straddles, strangles, single long calls/puts, debit spreads as single legs), nothing that can lose more than the premium. Scripts: `research/earnings/` (`fetch.py`, `build.py`, `analyze.py`, `rhspec.py`, `rhanalyze.py`, `forward.py`); raw data and outputs in `data/research_earnings/` (gitignored). Nothing in PLAN.md or ROUTER.md was changed; section 9 is a proposal.

## 1. Executive summary

__SUMMARY__

## 2. Data sources (and the free-historical-options finding)

| Need | Source used | Coverage / quality |
|---|---|---|
| Earnings dates + BMO/AMC timing | SEC EDGAR 8-K item 2.02 `acceptanceDateTime` (from the `submissions.zip` bulk file already on disk), converted to ET: < 09:30 = BMO, >= 16:00 = AMC, otherwise "mid" | 185k filings, 3,208 tickers, 2004-2026. 29% of filings are "mid" (the 8-K is furnished the next morning or during the session); resolved with Yahoo's timing, else dropped. Non-earnings 2.02 filings (TSLA delivery reports, pre-announcements) are dropped by requiring a Yahoo earnings date within 2 days |
| Earnings dates (cross-check, EPS estimate/actual/surprise) | `yfinance get_earnings_dates(limit=100)` | 177k dates, 3,158 tickers, back to 2006-2010 (the 2026 yfinance 1.7 serves far more than the ~26 quarters seen in the small-cap study). Timing is encoded in the timestamp hour (16:00 = AMC, 06:00-09:00 = BMO) |
| Robinhood `get_earnings_calendar` / `get_earnings_results` | MCP | 2,340 reports with verified am/pm timing for 2026-10-19..11-14 (the forward universe); 8 trailing quarters per symbol with verified timing: the best source for the next report's timing, no history beyond 2 years |
| Daily bars | yfinance (auto-adjusted) for the move panel; a second pull with `auto_adjust=False, actions=True` to recover UNADJUSTED closes for strike selection | 3,284 tickers, 2009-2026. Survivors only: yfinance has no delisted bars, so the panel misses every name that went to zero or was taken out (see 7) |
| Market cap at the event | EDGAR `dei` shares outstanding (point-in-time, by filing date) x entry close; fallback today's cap scaled by price | 87% point-in-time; tiers mega >= $200B, large $10-200B, mid $2-10B, small $0.3-2B, micro < $0.3B |
| Industry | EDGAR SIC (bucketed into 15 groups); GICS for S&P 500/400 names | all tickers |
| Universe | Robinhood calendar names (cap > $1B) + the small-cap cache (SPSM/MDY/IWM holdings) + S&P 500/400 | 3,567 symbols, 2,897 with usable events |
| **Historical option prices** | **Robinhood `get_option_instruments(state='expired')` + `get_option_historicals(interval='day')`** | **see below** |
| Live chains for the forward list | yfinance chains (Saturday snapshot, stale/one-sided quotes filtered: both bids > 0, spread < 50% of mid) | 270 names; spot-check the top names on Robinhood before any paper entry |

**Free historical option data exists on Robinhood.** `get_option_instruments` with `state='expired'` resolves expired contracts back to **early 2018** (MSFT Feb-2018 weekly found; Jan-2017 and Jan-2016 not), and `get_option_historicals` returns **daily OHLC bars for those expired contracts back to at least January 2019** (MSFT 2019-02-01 105C/P: real, non-interpolated bars 2019-01-28..31). Properties measured on 2026-10-16/17:
- Before ~2023 the daily bars are close-only marks (open = high = low = close); from 2023 they are full OHLC.
- Bars are trade-based for thin contracts: `open = 0.01` means no trade yet that day; the close carries the last trade, so for small-cap monthlies the mark can be a day stale. Liquid names (mega/large weeklies) are fine.
- Intraday (5/10-minute) bars for expired contracts come back `interpolated: true` only: there is no intraday history beyond what the 0DTE backfill already found (10-minute bars to ~June 2026, 5-minute ~7 sessions).
- `end_time` is exclusive at day granularity (ask for window end + 1 day). Bars carry no volume or bid/ask.
- Weekly expiries are often absent in the expired listing for small/mid caps (they were never listed); monthlies are reliably present.
- Cost: ~1 instrument call per event (2 contracts, ~1 KB) and one historicals call per 5 events (10 ids, ~15 KB). The pull is MCP-only (no scriptable endpoint from Python), so it was done by sub-agents transcribing bars into `data/research_earnings/rh2_out_*.jsonl`. The spec/batching code is `rhspec.py`.
- First attempt failed on a data-hygiene point now in LEARNINGS: strikes must be built from UNADJUSTED prices (Yahoo's default auto-adjusted close is 6-20% below the real price for dividend payers and 4-20x off for split names; Robinhood lists expired contracts at their original strikes).

Other sources checked: Alpaca's options history (free with any account, indicative feed) starts Feb 2024 only; Polygon (now "Massive") free tier has no options at all (options start at the $79-99/month Developer tier); CBOE DataShop and ORATS are paid. Robinhood is the only free source with 2019+ history, and it is the owner's own broker.

## 3. The realized-move panel (133,517 events, 2,897 tickers, 2009-2026)

Definitions. R = reaction day (the first session whose open can trade on the report). C0 = close before R (the entry close). `cc` = close(R)/C0 - 1 (the earnings move), `co` = open(R)/C0 - 1 (the gap). `hist8` = the mean |cc| of the ticker's previous 8 reports, the naive own-history forecast that the market roughly prices; `ratio8` = |cc| / hist8. IS = 2009-2018, OOS = 2019+.

### 3.1 Segment table (OOS 2019-2026)

| Tier | events | tickers | mean |cc| | median |cc| | mean |gap| | P(>10%) | ratio8 mean | ratio8 median | P(ratio8 > 1) |
|---|---|---|---|---|---|---|---|---|---|
| mega (>= $200B) | 727 | 79 | 4.6% | 3.6% | 3.6% | 9% | 1.12 | 0.90 | 46% |
| large ($10-200B) | 13,353 | 775 | 4.7% | 3.5% | 3.5% | 10% | 1.11 | 0.88 | 45% |
| mid ($2-10B) | 21,138 | 1,476 | 5.8% | 4.3% | 4.2% | 15% | 1.11 | 0.85 | 43% |
| small ($0.3-2B) | 21,979 | 1,567 | 7.2% | 5.2% | 5.0% | 21% | 1.13 | 0.84 | 43% |
| micro (< $0.3B) | 7,284 | 728 | 7.5% | 5.3% | 4.9% | 23% | 1.18 | 0.85 | 44% |

- Moves are right-skewed: the mean |cc| is 1.1-1.4x the median everywhere, so the mean ratio to own history is ~1.12 while the median is ~0.86 and only 43-46% of reports beat their own average. A straddle buyer is paid by the tail: at fair pricing you win 43-46% of the time.
- Earnings moves have grown every year: small caps 4.4% (2010) -> 6.2% (2019) -> 8.6% (2025) -> 8.3% (2026 YTD); large caps 2.9% -> 3.9% -> 5.3% -> 5.7%; mega 2.8% -> 4.3% -> 4.6% -> 5.6%. Any "own history" model lags this drift, which is one reason ratio8 averages above 1.
- Timing: AMC reports move more (6.5% vs 5.5% BMO, OOS) but the ratio to own history is the same (1.12 vs 1.12).
- Industry (OOS mean |cc|): software/internet 9.4%, medtech/health services 8.4%, semis 8.4%, hardware/electronics 8.4%, retail 7.7%, services/media 7.3%, biotech/pharma 6.7%, industrials/materials 6.2%, consumer goods 6.0%, insurance 5.2%, energy 4.6%, transport/utilities/telecom 4.4%, banks/finance 3.8%, REITs 3.4%. The ratio to own history is 1.10-1.15 in every industry (no industry "surprises more than it used to" in a way the others don't).

### 3.2 Is the realized move vs own history predictable? (features known at the entry close)

Top-minus-bottom quintile spread of ratio8 (clipped 0-4), t-stats clustered by report week; 20 features, 11 pass Benjamini-Hochberg (q = 0.10) out of sample.

| Feature | IS spread (t) | OOS spread (t) | OOS Spearman | Reading |
|---|---|---|---|---|
| peer_ratio (same industry, reported in the prior 21 days: their ratio8) | +0.32 (13.6) | **+0.23 (8.1)** | +0.07 | peer read-through is real and the strongest ex-ante signal |
| last_acc (last report's |move|) | -0.18 (-8.3) | -0.20 (-10.4) | -0.06 | mean reversion of the ratio (a big last move inflates hist8) |
| dist_hi (distance below the 52-week high) | -0.25 (-10.8) | -0.17 (-7.4) | -0.05 | names near highs surprise more vs history; beaten-down names less |
| hist8_cv (dispersion of past moves) | +0.13 (5.6) | +0.13 (7.7) | +0.04 | lumpy histories keep surprising |
| vratio (5d/60d volume) | +0.08 (3.4) | +0.11 (5.5) | +0.04 | pre-report volume = bigger move |
| rv20 | +0.13 (5.0) | +0.11 (4.9) | +0.02 | current vol > history vol |
| run60 / run20 | -0.24 / -0.17 | -0.12 (-4.9) / -0.04 (-2.0) | -0.04 | run-ups precede quieter reports (vs history) |
| last_surprise (EPS surprise %) | -0.06 (-2.6) | -0.09 (-4.5) | -0.03 | |
| ratio_prior (last ratio8) | +0.11 (4.5) | +0.05 (2.7) | +0.02 | weak positive |
| evol_mult (hist8 / daily E|move| from RV20) | — | -0.46..-0.74 within every tier (t -4 to -19) | | the single biggest effect: when own history is large relative to today's daily vol, the next move disappoints vs history, and vice versa |
| n_prior, adv20, month, prevday, run5, logcap | n.s. OOS | | | |

Walk-forward HistGB (train on all seasons before S, test S, from 2019Q1; 69,476 OOS events): AUC 0.607 for "ratio8 > 1", Spearman 0.22 with ratio8. Top decile realized 1.66x own history (62% beat it), bottom decile 0.76x (28%); the top decile is 1.57-1.72 in every year 2019-2026. **But** the top decile's absolute move is 4.6% and the bottom's 8.1%: the model mostly learns that `hist8` is a stale forecast (mean reversion plus the current-vol level), i.e. it predicts the realized move better than the naive own-history proxy does. Whether it beats the *market's* forecast is the option question in section 4.

### 3.3 Does "moves more than its history" persist by ticker or industry? No.

- Ticker mean ratio8, IS (2009-18) vs OOS (2019+), 1,701 tickers with >= 8 events in each: Spearman **-0.28**. 2019-22 vs 2023+: **-0.40** (n = 1,997). The IS top decile averages 1.08 OOS vs 1.11 for everyone; the IS *bottom* decile averages 1.17. Of 2,442 tickers with >= 12 OOS events, 0 survive BH for "ratio8 > 1".
- The negative correlation is mechanical: a ticker whose last 8 moves were big has a big hist8, and the next move regresses. "Stocks whose earnings typically move them aggressively" is a stable property of the *level* (software/semis/medtech small caps move 8-9% every quarter) but the market prices the level; the *surprise relative to history* does not belong to a ticker.
- Industries: ratio8 1.10-1.15 everywhere IS and OOS; no industry is a persistent surpriser.
- The ranked list by OOS ratio8 (PACK, BLMN, EOSE, GEO, JELD, DERM, THRY, BFAM, XRX, VTEX ... t vs 1 of 2.0-2.4 on n = 15-31) is what noise looks like with 2,442 draws; it is listed in `analyze_out.json` only so nobody re-discovers it.

### 3.4 Direction and drift

- Direction: top-bottom quintile spreads of signed `cc` are 0.1-0.4% for every feature (|t| <= 2.3; the only OOS t > 2 is a 5-day run-up *reversal* of -0.42%, t -2.3, which is far inside option costs). Nothing predicts the sign of the earnings move; the same answer as direction.md, universe.md and smallcap.md.
- Post-gap drift (open -> close of R) is in the direction of the gap: top decile of `cc` gaps +7.6% and adds +9.9 points... no: the top decile's close-to-close is +17.5% on a +7.6% gap, i.e. the gap keeps running on day 0 (oc = close/open - 1 is positive for big up reactions and negative for big down ones). This is the "post-earnings momentum on day 0" effect; it is tradable only if you buy after the open at post-crush IV, see 4.
- PEAD OOS: decile 10 of `cc` (+17.5%) drifts +0.7%/5d and +2.2%/20d vs +0.4%/+1.3% for the middle deciles; decile 1 (-16%) drifts +0.4%/+1.0% (no negative drift). The excess is ~+0.8% per 20 days on the winners, consistent with smallcap.md's finding that it is too small for options.

## 4. The market's price: Robinhood expired-straddle sample

__RH__

## 5. Model results with OOS statistics

__MODELS__

## 6. Ranked tickers and industries

__RANKED__

## 7. What failed

__FAILED__

## 8. Forward paper watchlist (Oct 19 - Nov 14, 2026)

__FORWARD__

## 9. Proposed ROUTER playbook text (proposal only; PLAN.md / ROUTER.md untouched)

__PROPOSAL__

## 10. Methods, caveats, files

__METHODS__
