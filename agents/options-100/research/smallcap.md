# Do simple option-buying edges survive in $1B–$5B small caps?

2026-10-14. Owner's idea: "Expand to small caps ($1B–$5B): big enough to have option liquidity, not on everyone's radar like PLTR/SOFI/COIN." The thesis is that less-crowded names are priced less efficiently, so simple edges survive there.

Code: `bot/research_smallcap.py` (`holdings | caps | chains | prices | cohort | earnings | run | bank | all`). `run` takes about 3 minutes from cache.
Caches (gitignored, under `data/`):
- `research_smallcap_cache.pkl`: holdings, caps, live chains, daily bars, earnings dates;
- `research_smallcap_results.json`: all tables;
- `research_smallcap_bank_t12.json`;
- `research_smallcap_raw/`: the downloaded holdings files, which were parsed only.

## Verdict (short)

1. **The thesis fails on cost, not on signal.** Small-cap option spreads are wide.
   - Across 758 $1–5B names with listed options, the median ATM spread is **44% of mid** (at 37 DTE).
   - Only **11 names** pass the requested filter (ATM OI ≥500, ≥200 contracts/day, spread ≤10%), and **65** pass at ≤20%.
   - The "quiet" names the owner wants are the *least* tradable: median spread **28%** for quiet names against **17%** for crowded ones.
2. **Quiet names show no bigger underlying edge.**
   - RSI2<10 dip-buy, out of sample (2020+), measured as the stock's 5-day return minus the same ticker's unconditional 5-day return: **quiet +0.30% (t 1.1)**, crowded **+0.24% (t 0.8)**.
   - Same size, both insignificant, and both match the large-cap finding of +0.1–0.2% (research/universe.md).
3. **0 of 16 strategy families pass Benjamini–Hochberg out of sample**, with t-stats clustered by entry week. Pooled across 320 names, every long-option structure loses **−10% to −25% of premium per trade** at the measured spreads. At mid fills (zero spread) the dips are about **+4%** and breakouts **+14%**, so the spread alone is the difference.
4. **PEAD, pre-earnings run-up, small-cap lead-lag and per-ticker "character" are all dead** once returns are measured against each ticker's own drift instead of IWM. Against IWM, the survivor-biased universe beats the index by about 10 pts/yr, which manufactures fake drift.
5. **Ticker selection does not persist.** The rank correlation between in-sample (IS) and out-of-sample (OOS) per-ticker edge runs from −0.19 to +0.20. The 6 cells that "pass" BH at ticker level are all *significantly negative* OOS, meaning the in-sample winners reversed.
6. **The only positive pockets are the 65 most liquid names (tiers T1/T2), and that tier is chosen with today's liquidity, which is look-ahead.** Within it, IS-selected RSI2 dip-buys earn **+10% per trade OOS** pooled (+24% in the one-position-at-a-time calendar sim), and **+18–22% when SPY<200dMA**. A contract costs $130–240, so a $170 account skips about 80% of signals.

**Recommendation: do not move the bot to small-cap options.** Keep the XSP dip-buy (direction.md: +11.4%/trade, P(grow) 55–60%, ruin ≈1% at $170) as the primary candidate. Status for small caps is **"NOT YET FOUND", not retired**.
- Paper-track the T1 dip list below.
- The one structural lead worth more work is **52-week-high breakouts in crowded names**: excess +10% IS (t 2.2) and +12% OOS (t 2.6). It is confounded because crowding is measured today.

## 1. Universe construction

| step | source | count |
|---|---|---|
| S&P 600 constituents | SPDR **SPSM** holdings xlsx, live (as of 2026-10-13) | 603 |
| S&P 400 constituents | SPDR **MDY** holdings xlsx, live (2026-10-13) | 400 |
| Russell 2000 constituents | iShares **IWM** CSV via Wayback snapshot (2025-07-15)* | 1,998 |
| union of current lists | | 2,400 |
| yfinance `fast_info` market cap found | | 2,046 |
| **$1B ≤ cap ≤ $5B** | | **810** |
| has a listed option chain | | 758 |

\* The iShares `.ajax?fileType=csv` endpoint now returns an HTML page to scripts (tried with a cookie jar, referer and several UAs). SPDR SLY returns a 404; SPSM is the same index. The Vanguard API is a JS app.

**Liquidity measurement.** On 2026-10-14 at about 13:00 ET, I pulled the yfinance chain for the expiry nearest 30 DTE inside 14–40 days. For most names that is 2026-11-20 at 37 DTE; only 17% have weeklies.
- ATM strike = nearest to spot.
- Option volume = target expiry + nearest expiry, scaled by 1/0.61 for the session fraction.
- Spread = (ask−bid)/mid, averaged over the ATM call and put.
- Min capital = ATM call ask × 100, normalized to 21 DTE by √t.

**Liquidity tiers.**

| tier | rule | names | median spread | median ATM OI | median opt vol/day | median min capital |
|---|---|---|---|---|---|---|
| T1 strict | OI≥500, vol≥200, spread≤10% | **11** | 7.5% | 1,233 | 3,674 | $139 |
| T2 loose | OI≥250, vol≥100, spread≤20% | 54 | 14.2% | 666 | 1,748 | $149 |
| T3 wide | OI≥250 or vol≥200, spread≤50% | 255 | 27.7% | 74 | 763 | $196 |
| none | thinner | 438 | | | | |

- All 758 chains: spread quantiles are 10% / 25% / 50% / 75% / 90% = **14% / 24% / 44% / 85% / 130%** of mid.
- Even among the 100 names that pass OI and volume, the median spread is 23%.
- The ~150–400-name target was not achievable at ≤10% spread. The research universe is therefore T1+T2+T3 = **320 names**, each charged its **own measured spread** (capped at 50%) on every simulated trade.

**Crowded vs quiet.** Score = average percentile rank of daily option notional turnover (option volume × 100 × price / market cap) and stock turnover ($ volume / market cap). Top third = crowded, bottom third = quiet.

| group | median spread | ATM OI | opt vol/day | ATM IV | min capital |
|---|---|---|---|---|---|
| crowded | **16.6%** | 203 | 2,609 | 74% | $236 |
| mid | 21.2% | 128 | 759 | 58% | $198 |
| quiet | **28.2%** | 94 | 400 | 56% | $132 |

Of the 11 T1 names, 8 are "crowded" (ALK, PENG, OMER, WHR, PLNT, STNE, FOUR, PGY); only PRCH is quiet. **Option liquidity in small caps exists only where the crowd is.**

**T1 names:** ALK, PENG, APPS, OMER, WHR, PLNT, STNE, FOUR, PRCH, BFLY, PGY.

**T2 names (54):** SDGR, CIFR, AXTI, AMR, UTI, NVTS, LEU, ACVA, COUR, VSH, GCT, CRK, CPRI, OZK, SHOO, CORZ, SEZL, DHT, CLOV, PPTA, STNG, CXW, SFL, COHU, ABSI, CENX, SEI, FND, OLN, PFSI, CALM, BRZE, FMC, NOG, CNR, CRSR, NTLA, FLG, JBLU, ASAN, VSEC, CNXC, NAT, GLNG, IRON, SXI, KD, PVH, SHLS, GEO, KRMN, PLAB, KRC, NEXT.

**Affordable (21d ATM call ≤ $85) and T1/T2:** STNE $79, NVTS $70, ACVA $38, COUR $30, CRK $68, CLOV $28, SFL $68, NTLA $79, FLG $45, JBLU $17, ASAN $60, NAT $49, KD $79, NEXT $53. APPS and BFLY are $90. Overall, 68 of the 320 research names cost ≤$85.

## 2. Method

- **Data.** yfinance daily bars (adjusted, max history), with a median of 3,700 sessions per name. SPY, IWM and VIX come from `market.db`.
- **Split.** In-sample 2012–2019, out-of-sample 2020-01 → 2026-10-13.
- **Trades.** The signal fires at close t, entry is at close t, and the exit is at the close after `hold` sessions. Positions in one ticker never overlap.
- **Option pricing.** Black-Scholes with sticky-moneyness skew 3.
  - IV_t = RV20_t × ivr_ticker × regime_t.
  - **ivr_ticker** = today's chain ATM IV / (today's RV20 × today's regime), clipped 0.7–2.5. The median is 1.34.
  - **regime_t** = (0.9·VIX/RV20_SPY)_t / its 2012+ median. This applies the universe.md lesson that implied/realized *rises on dip days*, so dip entries are priced richer than a flat multiple would price them.
  - Exit is repriced at the exit-day RV20 × ivr × regime.
- **Cost.** You buy at mid×(1+s/2) and sell at mid×(1−s/2), where s is the ticker's measured ATM spread today. The same spread is applied to all history (see caveats).
- **Excess return (two kinds).**
  - `x` = the option return minus the same ticker's *unconditional* same-structure option return (entering every day) in the same period.
  - `und_xu` = the stock's hold-period return minus the same ticker's unconditional hold-period mean.
  - The vs-IWM excess (`und_x`) is reported but is **contaminated by survivorship** (§6).
- **Statistics.** t-stats on the trade mean use standard errors clustered by entry week, because dip signals fire across many names on the same selloff days.
  - **BH** is applied across the 16 pooled OOS strategy tests.
  - Ticker-level BH is applied across the IS-selected (strategy, ticker) cells.

## 3. Results: pooled strategies, all 320 names

EV = mean net return on option premium. x = excess over the same ticker's unconditional entry, in points of premium. und_xu = stock excess over the same ticker's unconditional drift.

| strategy | IS EV | OOS n | **OOS EV** | OOS PoP | OOS x (t) | OOS und_xu (t) | quiet EV / crowded EV | T1 EV | BH |
|---|---|---|---|---|---|---|---|---|---|
| RSI2<10 → 21d call, 5d | −19.8% | 30,056 | **−17.8%** | 27% | +0.3 (0.2) | +0.22% (0.8) | −22% / −12% | +2.6% | no |
| 3+ down days | −19.0% | 30,333 | −17.9% | 27% | +0.2 (0.1) | +0.28% (1.0) | −23% / −11% | +2.0% | no |
| 1-day drop >2×ATR | −22.7% | 3,915 | −24.6% | 23% | −6.0 (−2.2) | −0.74% (−1.3) | −30% / −17% | −15% | no |
| 3-day drop >3×ATR | −21.1% | 4,161 | −21.4% | 25% | −2.7 (−0.8) | −0.13% | −25% / −12% | +3.7% | no |
| close < lower BB | −18.7% | 11,254 | −18.4% | 27% | +0.2 (0.1) | −0.09% | −23% / −12% | −4.5% | no |
| RSI2<10 & <lower BB | −18.7% | 10,073 | −18.4% | 27% | +0.2 (0.1) | −0.04% | −23% / −12% | +0.1% | no |
| RSI2<10 → 30d call, 10d | −16.7% | 22,995 | −15.9% | 29% | −0.8 | +0.24% (0.6) | −22% / −8% | +6.6% | no |
| RSI2<10 & SPY>200dMA | −19.5% | 23,165 | −19.5% | 26% | −1.4 | +0.11% (0.5) | −23% / −14% | −3.5% | no |
| **RSI2<10 & SPY<200dMA** | −22.2% | 7,597 | −14.4% | 30% | +3.9 (0.8) | +0.29% (0.3) | −21% / **−5%** | **+22%** | no |
| **RSI2<10 & VIX>20** | −20.8% | 15,393 | −17.6% | 27% | +0.7 (0.3) | **+0.76% (1.4)** | −23% / −9% | **+11%** | no |
| **fresh 52w-high close → 30d call, 10d** | −5.5% | 2,383 | −9.7% | 31% | **+4.8 (1.8)** | +0.23% (0.6) | −22% / **+4.8%** | **+27%** (n=64) | no (p=0.08) |
| volume >3× & +4% day → call | −11.6% | 2,714 | −12.1% | 28% | −1.3 | +0.14% | −25% / −0% | +29% (n=135) | no |
| same → put (fade) | −28.3% | 2,714 | −20.8% | 21% | −0.2 | | | | no |
| SPY >+1.5% day, stock lagged → call, 3d | −7.3% | 2,509 | −18.0% | 28% | +1.5 (0.2) | −1.60% (−1.0) | −27% / −10% | +15% | no |
| same, hold 5d | −4.0% | 2,440 | −18.3% | 27% | +0.4 | −1.85% (−1.1) | | | no |
| RSI2>95 → put | −21.9% | 18,376 | −20.2% | 21% | +2.3 (1.6) | | | | no |

**Sensitivity** (OOS EV, all 320 names, RSI2<10 → 21d call):

| IV / spread assumption | EV |
|---|---|
| ratio model (primary) | −17.8% |
| flat 1.0×RV20 | −8.0% |
| flat 1.2×RV20 | −13.8% |
| flat 1.5×RV20 | −19.0% |
| ratio model + dip-day entry IV ×1.14 | −27.7% |
| spread 0 (mid fills) | **+4.1%** |
| spread ×0.5 | −7.6% |
| spread ×2 | −34.9% |

For the 52-week breakout: +14.3% at spread 0, +1.5% at half spread, and −9.7% at the full spread.

**Reading.** The underlying dip effect in small caps is about as small as in large caps: +0.2–0.3% over 5 days against the ticker's own drift. VIX>20 dips are the strongest at +0.76%, which is the market-wide dip effect already captured by XSP. Option spreads of 15–30% swamp it.

## 4. Quiet vs crowded: the owner's thesis, tested directly

| OOS 2020+ | quiet | crowded |
|---|---|---|
| RSI2<10 stock excess vs own drift | +0.30% (t 1.1) | +0.24% (t 0.8) |
| 3-down stock excess | +0.29% (t 1.0) | +0.27% (t 0.9) |
| RSI2<10 & VIX>20 stock excess | +0.68% (t 1.3) | +1.05% (t 1.9) |
| 52w breakout stock excess (10d) | **−0.73% (t −1.8)** | **+1.22% (t 1.8)** |
| RSI2<10 option EV | −22% | −12% |
| 52w breakout option EV | −22% | **+4.8%** |
| median spread | 28% | 17% |
| PEAD 20d drift vs IWM, big reactions 2023+ | −0.1% | +1.2% |

**Verdict: rejected as stated.**
- Quiet small caps do not show larger mean-reversion edges.
- Momentum (52-week breakouts) works only in **crowded** names. It holds in both periods (option x +10% IS, t 2.2; +12% OOS, t 2.6) and is negative in quiet names.
- Quiet names cost roughly 2× more to trade.
- "Off the radar" here means "nobody makes a market". The inefficiency, if any, sits in the spread and goes to the market maker.

## 5. Other families

- **(b) PEAD.** Earnings dates come from yfinance (Yahoo serves only 2020+, about 26 quarters, so the split is 2020–22 vs 2023+).
  - Signal: a big reaction, |day-1 excess vs IWM| ≥ max(4%, 1.5σ); 4,140 events.
  - Signed 5-day drift vs own drift: **+0.08% (t 0.3) / +0.29% (t 1.4)**. 20-day: +0.53% (t 1.1) / +0.40% (t 1.1).
  - "Surprise agrees with reaction" (using the actual EPS Surprise(%)): 20-day +0.71% (t 0.9) / +0.04%.
  - Against IWM, "big up" looks like +1.2–1.4% (t 2.2) per 20 days, but **that is the survivor drift**; against own drift it is −0.8% / +0.15%.
  - Options (14d/45d ATM, post-crush IV): −1% to −22%.
  - **Dead, as in direction.md for mega-caps.** "Stronger in small caps" does not show here.
- **(e) Pre-earnings run-up** (buy 5 sessions before the print, exit the close before it).
  - Stock vs IWM: +0.60% (t 2.6) in 2020–22 and +0.44% (t 2.8) in 2023+. Against own drift: +0.57% (t 1.0) and +0.21% (t 0.5).
  - 21d call: −14% / −18% with flat IV, and −6% / −9% if IV rises 15% into the print.
  - IV crush asymmetry cannot be tested without historical option quotes.
- **(f) Lead-lag.** Regress next-day (equal-weight universe − SPY) on SPY_t and on the gap (EW − SPY)_t.
  - IS: SPY_t β +0.033 (t 2.1), gap β +0.063 (t 2.8).
  - **OOS: SPY_t β −0.022 (t −1.0)**, gap +0.044 (t 1.7).
  - After big SPY up days (>1.5%), small caps that lagged by >0.5% then *underperform* by −0.14% over 3 days (n=25).
  - Small caps no longer lag large caps. **Dead.**
- **(d) Character.** VR(5) IS→OOS rank correlation is **0.08**; lag-1 autocorrelation is 0.14. A name's mean-reversion character does not persist.
  - OOS dip-buy excess by IS VR tercile: mean-reverting −0.3, mid +0.6, trending +0.3 points of premium.
  - Breakout excess is +11 / +10 / +4 points, slightly *better* in IS-mean-reverting names. **No usable sorting.**

## 6. Out-of-sample ranking and ticker selection

**Selecting tickers in-sample fails out of sample.** Take the (strategy, ticker) cells with IS excess t ≥ 1.5 and look at their OOS excess against the rest:

| strategy | top cells | top OOS x | rest OOS x | IS→OOS rank corr |
|---|---|---|---|---|
| RSI2<10 | 6 | −0.6 | +0.2 | −0.04 |
| RSI2 & BB | 15 | +3.4 | +0.2 | +0.15 |
| lower BB | 13 | −8.0 | +0.4 | +0.11 |
| 52w breakout | 12 | −5.5 | +8.5 | −0.19 |
| RSI2 & SPY<200 | 7 | +7.6 | +3.4 | +0.20 |

Ticker-level BH (q=0.10) "passes" 6 cells, and all 6 are **significant OOS losers**: KSS breakout, TH/ALGT/HOG ATR dips, and CLSK BB dips. In-sample winners reverted.

**OOS ranking inside T1+T2** (65 names), with cells selected on IS only (n_IS ≥ 5, IS EV > 0, IS x > 0). Columns are OOS figures.

| strategy | cells | trades | EV/trade | EV at mid | x | trades/yr (all cells) |
|---|---|---|---|---|---|---|
| RSI2<10 & SPY<200dMA | 17 | 405 | **+18.1%** | +33.5% | +19.7 | 60 |
| RSI2<10 → 30d, hold 10 | 11 | 863 | +14.3% | +26.2% | +2.9 | 127 |
| RSI2<10 | 9 | 888 | +10.2% | +20.6% | +2.6 | 131 |
| RSI2<10 & VIX>20 | 11 | 567 | +8.7% | +21.1% | +13.5 | 84 |
| 3 down days | 9 | 936 | +7.9% | +18.5% | +2.7 | 138 |
| volume-shock breakout | 13 | 140 | +7.7% | +21.0% | −3.4 | 21 |
| RSI2 & BB | 10 | 335 | +4.1% | +16.5% | +7.4 | 49 |
| 52w breakout | 16 | 157 | +3.0% | +17.7% | +3.1 | 23 |
| 2×ATR drop | 11 | 140 | −20.0% | −10.3% | −20.7 | 21 |

The same T1+T2 names *without* IS selection give RSI2 −4.3% and 52-week breakout +6.5%.

These positives come from two sources:
- (i) these names' own calls did well in 2020+: x is small except in the SPY<200 / VIX>20 regimes, which is again the market-dip effect;
- (ii) the tier is defined by **today's** liquidity, which favours names that became popular, i.e. went up.

## 7. Shortlist: liquid + IS-selected + positive OOS (min capital is not a filter)

Selection used IS only. The OOS columns are shown for information, and n is small. **Treat this as a paper-trade watchlist, not a validated edge.**

| ticker | trigger | tier / crowd | min capital | spread | IS n / EV | OOS n | **OOS EV/trade** | OOS PoP | OOS trades/yr |
|---|---|---|---|---|---|---|---|---|---|
| **STNE** | RSI2<10 → 21d ATM call, hold 5 | T1 / crowded | **$79** | 7.9% | 14 / +60% | 104 | **+31%** | 41% | 15 |
| PLNT | RSI2<10 & SPY<200dMA | T1 / crowded | $241 | 7.5% | 11 / +53% | 24 | +85% | 58% | 3.5 |
| PLNT | RSI2<10 & VIX>20 | T1 / crowded | $241 | 7.5% | 13 / +36% | 53 | +57% | 53% | 7.8 |
| PLNT | RSI2<10 | T1 / crowded | $241 | 7.5% | 56 / +39% | 97 | +24% | 43% | 14 |
| OMER | RSI2<10 & SPY<200dMA | T1 / crowded | $139 | 6.9% | 16 / +34% | 24 | +60% | 38% | 3.5 |
| OMER | RSI2<10 & lower BB | T1 / crowded | $139 | 6.9% | 42 / +36% | 34 | +50% | 53% | 5.0 |
| OMER | RSI2<10 | T1 / crowded | $139 | 6.9% | 121 / +19% | 97 | +20% | 31% | 14 |
| APPS | volume shock (>3× vol, +4%) → 30d call, 10d | T1 / mid | **$90** | 5.6% | 30 / +22% | 14 | +54% | 43% | 2.1 |
| APPS | RSI2<10 & VIX>20 | T1 / mid | $90 | 5.6% | 23 / +5% | 56 | +13% | 41% | 8.3 |
| CALM | RSI2<10 & SPY<200dMA | T2 / crowded | $158 | 14.5% | 19 / +14% | 24 | +50% | 54% | 3.5 |
| DHT | RSI2<10 & lower BB | T2 / crowded | $139 | 12.8% | 42 / +4% | 28 | +46% | 54% | 4.1 |
| STNG | RSI2<10 & SPY<200dMA | T2 / crowded | $407 | 13.2% | 25 / +6% | 20 | +59% | 65% | 2.9 |
| AXTI | RSI2<10 | T2 / crowded | $636 | 8.5% | 112 / +6% | 104 | +27% | 39% | 15 |
| LEU | fresh 52w high → 30d call, 10d | T2 / crowded | $731 | 10.4% | 5 / +126% | 11 | +126% | 73% | 1.6 |
| NEXT | volume shock → 30d call | T2 / quiet | **$53** | 19.7% | 6 / +14% | 22 | +32% | 59% | 3.2 |
| NAT | RSI2<10 & SPY<200dMA | T2 / crowded | **$49** | 16.5% | 14 / +31% | 19 | +15% | 32% | 2.8 |

- **Affordable + edge + liquid at $170:** STNE (dip, about 15 a year), plus APPS, NEXT and NAT (few trades, wider spreads). All are crowded or mid names except NEXT.
- **Ready when funded ($1k+):** PLNT, OMER, CALM and DHT dips in market-stress regimes (SPY<200dMA or VIX>20); AXTI RSI2; LEU 52w breakouts.

## 8. Bankroll (1 year, OOS trade distribution, one position at a time)

The simulation buys whole contracts at each ticker's measured cost: floor(f·equity/cost) contracts, or 1 if the cost is ≤60% of equity, otherwise the trade is skipped. Ruin = equity below 12% of the start. 20k paths.

| pool | trades/yr | EV/trade | PoP | contract | $170 P(grow) / skip | $1k P(grow) / ruin @20% | $5k P(grow) / ruin @20% | $5k @35% |
|---|---|---|---|---|---|---|---|---|
| T1/T2 IS-sel. RSI2<10 | 31 | +24% | 38% | $132 | 15% / 78% skipped | 43% / 10% | 52% / 3% | 36% / 30% |
| T1/T2 IS-sel. RSI2 & SPY<200 | 8 | +22% | 42% | $188 | 29% / 81% | 50% / 0% | **58% / 0%** | 49% / 0% |
| T1/T2 IS-sel. RSI2 & VIX>20 | 17 | +7% | 43% | $188 | 41% / 79% | 47% / 1% | 47% / 0% | 37% / 4% |
| T1/T2 IS-sel. volume shock | 11 | +7% | 40% | $136 | 25% / 68% | 27% / 0% | 42% / 0% | 31% / 6% |
| T1/T2 IS-sel. 52w breakout | 12 | −2% | 39% | $196 | 20% / 82% | 27% / 1% | 32% / 0% | 24% / 5% |
| all 320, RSI2<10 | 43 | −13% | 29% | $188 | 9% | 6% / 33% | 6% / 43% | |
| all 320, RSI2 & VIX>20 | 21 | −7% | 31% | $188 | 21% | 18% / 3% | 21% / 3% | |
| **XSP RSI2<10 (direction.md)** | 12.5 | **+11.4%** | 48% | $84 | **55–60%**, ruin 1% | | | |

Every small-cap pool has a lower PoP than XSP (29–43% against 48%), so the median path loses money even when the mean EV is positive. At $170, about 80% of small-cap signals are unaffordable.

## 9. Survivorship and look-ahead

- **The current list is back-filled with winners.** The equal-weight return of today's 320 names, 2012→2026, is **21.0% CAGR against 10.7% for IWM and 11.4% for IJR** (IS 19.7% vs 12.0%; OOS 22.7% vs 9.2%). That is about 10 points a year of selection bias, or ~0.2% per 5 days and ~0.8% per 20 days. This is why every "excess vs IWM" number above is inflated and why this study uses excess vs **each ticker's own drift**.
- **Historical cohorts.**
  - IWM holdings 2018-03-14 (Wayback): yfinance has any history for only **1,118 of 1,957**. The other 839 (43%) are gone (acquired, bankrupt or renamed), and yfinance returns **no bars at all** for delisted tickers (0 of the 177 historic-only names with data had stopped trading). The 1,039 priced survivors returned **+134% EW against +96% for IWM**.
  - IJR holdings 2021-01-13: 445 of 601 available; survivors **+85% against +48% for IJR**.
- **Delisted names could not be included.** No free source of delisted daily bars was found in this sprint. The excess-vs-own-drift measures neutralize level bias but not path bias (the names that crashed and delisted after dip signals are missing). The true dip-buy EV in small caps is therefore **lower** than shown.
- **Liquidity tiers and the crowded/quiet split use today's chains.** Names that are liquid and crowded today got there partly by rising, which flatters breakout and dip results inside T1/T2. Spreads are a single 13:00 ET snapshot on 2026-10-14 applied to all history. Small-cap spreads were probably wider before about 2020.

## 10. Caveats

- Option prices are modeled (Black-Scholes) from RV20 × the ticker's current IV ratio × the market regime; no historical small-cap quotes were used. Some chain IVs are junk: ACVA 12%, and the ivr clip binds for SXI, IRON, ACVA and PRCH.
- The ATM spread is measured at 37 DTE. A 21d contract usually has a similar $ spread on a smaller premium, so the % cost is probably *understated*.
- Earnings dates exist only for 2020+ (Yahoo limit), so PEAD and the run-up have no pre-2020 test.
- The bootstrap draws trades i.i.d. from OOS (2020–26, a strong small-cap tape with big V-recoveries). Dip results in the SPY<200 regime come mainly from 2020 and 2022.
- The 11-name T1 tier is tiny. The shortlist cells have 11–104 OOS trades each, and their per-ticker t-stats do not pass correction.

## Recommendation

1. **Do not switch the bot to small-cap options.** After costs no pooled strategy is positive. Quiet names are the worst on cost, and the underlying edges are no bigger than in large caps.
2. **Keep XSP dip-buy as the directional candidate.** It has the same dip effect, a 1–3% spread instead of 15–30%, and a higher PoP.
3. **Paper-watchlist (not retired, per the owner's rule).**
   - STNE RSI2<10 call ($79, fits today).
   - When funded ≥$1k: PLNT/OMER/CALM/DHT RSI2<10 calls *only when SPY<200dMA or VIX>20*.
   - APPS/NEXT volume-shock calls.
   - Log the live ask/bid on each trigger to replace the modeled spread.
4. **Open leads worth a follow-up.**
   - 52-week breakouts in crowded small caps: +12% x OOS, t 2.6. Re-test with crowding measured *point-in-time*, using historical option volume or short interest.
   - Spreads measured at several times of day and across expiries. If mid-ish fills are achievable with limit orders, breakouts move to about +14%.
   - A delisted-price source (CRSP/Norgate) to close the survivorship gap.
