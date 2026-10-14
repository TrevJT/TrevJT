# Can any indicator predict SPY/QQQ direction well enough to pay for long options?

2026-10-14. Owner's question: "Does direction correlate with news, Fed data, earnings, jobs, unemployment, oil, recession indicators? If we're at a coin flip, improve the model or change strategy."

Code: `bot/research_direction.py` (`fetch | signals | model | options | strategies | all`). It runs in under 10s.
Caches (gitignored): `data/research_direction_cache.pkl` holds FRED data and mega-cap earnings dates. `data/research_direction_results.json` holds all result tables.

## Verdict (short)

1. **Direction: no indicator survives multiple-testing correction.** 560 out-of-sample tests produced 88 nominal p<0.05 hits, 28 expected by chance. **0 pass Benjamini–Hochberg at q=0.05 or q=0.10, and 0 pass Bonferroni.** The excess over chance is real but small, and most of it comes from signals whose *in-sample direction flipped* out of sample. Examples: rising jobless claims, the Sahm trigger and payrolls were bearish before 2015 and bullish after. That is regime instability, not an edge.
2. **The one coherent family that replicates** (in-sample t≥2 and OOS t≥2, holding with 2020 excluded and in the last 3 years) is **"buy short-term oversold"**: RSI(2)<10, three or more down days in a row, RSI(14)<30, and VIX>25 for 20-day returns. It explains 11 of the 11 replicated tests. It is a long-only effect, published before the test period (Connors 2008), and is selection-biased because it was picked after looking at OOS. It does not pass the corrected threshold on its own.
3. **The combined model is a coin flip on the daily horizons.** A walk-forward ridge-logistic model using all 75 features predicts SPY **next-day open→close** with a **50.8% hit rate against 53.5% for "always up"**. Close→close 1d is 52.5% against 54.3%. The top-decile confidence bucket is better (59.8% up, mean +0.14%), but the long-short t is 0.8.
4. **For 0DTE the answer is no.** ATM 0DTE calls and puts lose **−28% / −32% of premium per trade** under our pricing, which matches realized/implied ≈0.76. No signal tested at the 0DTE horizon replicated. The current gate (VIX≥16) with either a straddle or a coin-flip direction runs at **−22% to −23% EV per trade, about 140 trades a year, and ruins the account in the bootstrap 100% of the time** at 15–35% sizing.
5. **Long-dated calls (2–6 weeks) are about break-even to mildly positive**, and almost all of that is the equity drift of 2015–2026 plus the assumed IV/VIX ratio. Bought on oversold days, they show **+11% EV per trade (t 1.7)**. Puts lose in every configuration tested (−10% to −45%).
6. **Affordability matters more than any signal.** One SPY or QQQ contract at 14–45 days costs $835–$1,717, and 0DTE ATM costs $240–$275. A $170 account can only buy **XSP** (mini-SPX, cash-settled). XSP is available on this Robinhood account with daily expiries; I checked the chain read-only. Indicative XSP costs: 0DTE ATM ≈ $24, 14d ATM ≈ $84, 30d ATM ≈ $123.

**Recommendation: stop 0DTE as the default strategy.** Switch to low-frequency **XSP calls, 14–30 days, bought only after short-term selloffs** (RSI2<10, VIX>25 or VIX/VIX3M>1), held about 5–10 sessions, and **paper-trade it first**. This is not a predictive model in the sense the owner hoped. It is a leveraged long-SPY position taken at statistically better times. The realistic 1-year outcome is about a coin flip on growing the account at all, with low ruin probability. It is not a path to $1k.

## Method

- **Data.** Daily bars from `market.db`, using 1993+ for SPY and 1999+ for QQQ. The 2026-10-14 intraday bar is excluded.
  - FRED, aligned on *availability date* = observation date + lag. Lags: UNRATE/PAYEMS/SAHM +40d, CPI +46d, ICSA/NFCI +6d, daily series +1d, USREC +365d.
  - The HY OAS on FRED only covers 3 years now, so Moody's BAA10Y is the credit proxy.
- **Event dates.**
  - FOMC: 1994–2014 hard-coded from the Fed's historical calendar (scheduled meetings only); 2015–2026 from `research/brainstorm/macro_events.py`.
  - CPI: 2015+ from that file only.
  - NFP: that file for 2015+, and the first Friday of each month before 2015 (approximate).
  - Mega-cap earnings: yfinance `get_earnings_dates` (2002+), merged with the news-research cache.
- **Targets.** `oc1` is next-day open→close, i.e. the 0DTE trade, with the next-day gap as an extra feature. `cc1`, `cc5` and `cc20` are close→close over 1, 5 and 20 days.
- **Timing.** Late-stamped series (oil/gold/DXY settle after 16:00; the BTC bar ends 20:00 ET) are lagged one day for close→close targets.
- **Signals.** Continuous features use terciles from the train period (long top, short bottom, or reversed). Binary features are on/off. The **direction is learned on train data** (<2015, or the first 3 years for short series) and frozen.
  - OOS = 2015-01..2026-10.
  - t-stats are Newey-West with lag = horizon.
  - Results are also reported ex-2020 and for the last 3 years (2023-10+).
- **Option pricing.** Black-Scholes.
  - IV = VIX × 0.9 for SPY tenors of 2–6 weeks, and ×1.2 more for QQQ. Exit is repriced at the exit-day VIX.
  - Skew is sticky-moneyness, IV(K) = IV_atm·(1−5·ln K/S), so a +3% call is about −15% IV.
  - 0DTE: session σ = VIX/√252 × 0.8. This implies realized/priced = 0.76 (0.64 at VIX<16, 0.86 at VIX≥20), consistent with earlier findings.
  - Costs: 3% round trip per leg.
- **Bootstrap.** Resample each strategy's OOS trade returns. Draw one year at its observed trade frequency and risk a fixed fraction f of equity per trade (fractional sizing), over 20k paths. Start at $170; ruin means equity < $20.

## 1. Single signals (560 tests, 75 features × 4 horizons × SPY/QQQ)

Bonferroni threshold: p < 8.9e-5 (|t| > 3.92). **No test reaches it; the best OOS |t| is 3.62.** BH passes 0 at q=0.05 and 0 at q=0.10.

Top of the list by OOS p. "hit" is the share of active days where the sign is right; "base" is the share of days the index is up.

| sym | h | feature | dir learned | n on | hit | base | t OOS | t in-sample | t ex-2020 | t last 3y |
|---|---|---|---|---|---|---|---|---|---|---|
| QQQ | cc20 | jobless claims YoY | high→short | 1770 | 39.5 | 66.9 | **−3.62** | +2.46 | −2.72 | −0.56 |
| SPY | cc20 | Sahm trigger ≥0.5 | on→short | 316 | 13.9 | 67.0 | **−3.39** | +2.11 | −2.79 | −1.42 |
| QQQ | cc1 | RSI2<10 | on→long | 275 | 62.5 | 55.8 | +3.21 | +2.57 | +2.64 | +2.42 |
| QQQ | cc1 | RSI14<30 | on→long | 49 | 69.4 | 55.8 | +3.09 | +2.40 | +2.70 | +1.85 |
| QQQ | oc1 | mega-cap earnings day | on→short | 69 | 62.3 | 53.0 | +2.93 | +0.44 | +2.93 | +2.91 |
| SPY | cc20 | VIX>25 | on→long | 389 | 74.8 | 67.0 | +2.85 | +1.15 | +2.08 | +3.61 |
| SPY | cc1 | RSI2<10 | on→long | 275 | 60.4 | 54.3 | +2.84 | +3.60 | +2.28 | +2.45 |
| SPY | cc5 | RSI2<10 | on→long | 275 | 66.5 | 60.5 | +2.58 | +4.06 | +2.65 | +2.22 |
| SPY | cc5 | RSI14<30 | on→long | 49 | 79.6 | 60.5 | +2.61 | +2.47 | +3.97 | +2.88 |

Findings by family:
- **Macro (jobs, unemployment, CPI, recession):** the in-sample sign *reversed* out of sample at the 5–20 day horizon. Bad macro was bearish before 2015 and bullish after (2020 and 2022–23 V-recoveries, the Fed put). Do not trade macro levels for direction.
- **Trend:** the 200-day MA and 12-month momentum also reversed sign OOS. SPY earned +1.9% per 20 days when *below* its 200dMA, against +0.8% when above.
- **Volatility:** VIX term-structure inversion (VIX>VIX3M) is followed by **higher** returns: +3.0% per 20 days against +0.8%, OOS t ≈ −1.8 to −2.1 against the learned "short" direction. Puts on inversion lose −27%.
- **Rates, oil, dollar, gold, BTC, breadth:** nothing consistent. BTC 1d/5d → SPY 20d shows OOS t≈2.8 but in-sample ≈0.3–1.3, so it is likely noise. The overnight oil/dollar/BTC moves known by 09:30 do not predict the same-day open→close.
- **Calendar and events:**
  - FOMC-day / pre-FOMC drift: in-sample t 2.6–3.3 (the published effect), **OOS −1.3 to +0.6**. The hourly test (2023-11+, close t−1 → 13:30 on FOMC day, n=23) gives +0.08%, t 0.6.
  - TOM, CPI, NFP, OPEX, pre-holiday and day-of-week are all |t|<2 OOS, except the QQQ Monday open→close (t −2.5, in-sample 0.3; noise).
- **Mega-cap earnings day → QQQ open→close weaker** (t 2.9, n=69, 2020-10+ only). This is a single noisy test that fails correction.

## 2. Combined model (walk-forward ridge logistic, refit yearly, OOS 2015+)

| | n | P(up) base | hit (p>0.5) | top-decile P(up) | bottom-decile P(down) | long-short t | last-3y hit (base) |
|---|---|---|---|---|---|---|---|
| SPY oc1 (0DTE) | 2961 | 53.5% | **50.8%** | 59.8% | 46.5% | +0.80 | 52.0% (53.1%) |
| SPY cc1 | 2961 | 54.3% | 52.5% | 62.5% | 51.5% | +0.25 | 55.5% (56.3%) |
| SPY cc5 | 2957 | 60.5% | 56.6% | 67.9% | 50.7% | +0.72 | 62.5% (62.3%) |
| SPY cc20 | 2942 | 67.0% | 57.8% | 78.0% | 43.4% | +1.08 | 67.2% (73.7%) |
| QQQ oc1 | 2961 | 53.7% | 51.9% | 54.4% | 50.5% | +1.02 | 51.1% (52.9%) |
| QQQ cc5 | 2957 | 60.0% | 56.4% | 64.9% | 50.7% | +1.60 | 60.2% (60.2%) |

- The model is **worse than "always long"** on raw hit rate at every horizon.
- Confidence helps only on the long side. The top decile has higher P(up) and mean return (SPY cc20 top decile: +2.7% against about +1.1% average). These are mostly high-VIX, post-selloff days, which is the same oversold family as above.
- The bottom decile does **not** reliably predict down moves (P(down) 43–53%), so **there is no usable put signal**.
- Variants restricted to features selected in-sample (|t_ins|≥2.5) do worse (long-short t −0.5 to −2.1).
- **Best OOS direction hit rate on a real horizon:** SPY 5-day, RSI14<30: 79.6% against a 60.5% base (n=49, 2015+). For a frequent signal: SPY 5-day, RSI2<10: 66.5% against 60.5% (n=275).

## 3. Option economics (OOS 2015+, EV = mean net return on premium, PoP = P(profit))

| signal | structure | n | EV | PoP | t | ex-2020 | last 3y |
|---|---|---|---|---|---|---|---|
| always call | SPY 0DTE ATM | 2961 | **−27.6%** | 30% | −14.7 | −27.1% | −29.2% |
| always put | SPY 0DTE ATM | 2961 | **−31.5%** | 25% | −14.1 | −31.5% | −34.2% |
| always call | SPY 0DTE ATM/+0.5% | 2961 | −16.5% | 39% | −9.4 | | −14.5% |
| always call | SPY 7d ATM, hold 1d | 2961 | −2.7% | 41% | −3.2 | | −1.2% |
| always call | SPY 14d ATM, hold 5d | 2957 | −0.3% | 44% | −0.1 | | +6.3% |
| always call | SPY 45d ATM, hold 20d | 2942 | +11.6% | 52% | +2.1 | +11.1% | +28.3% |
| always put | SPY 45d ATM, hold 20d | 2942 | −26.9% | 23% | −3.5 | | |
| RSI2<10 | SPY 14d ATM call, hold 5d | 275 | **+12.7%** | 49% | +2.0 | +12.9% | +29.2% |
| RSI2<10 | QQQ 14d ATM call, hold 5d | 275 | +18.4% | 51% | +2.7 | +18.4% | +36.4% |
| RSI14<30 | SPY 14d ATM call, hold 5d | 49 | +35.0% | 57% | +2.7 | +40.1% | +85% (n=9) |
| VIX>25 | QQQ 30d ATM call to expiry | 389 | +36.4% | 57% | +2.3 | +33.2% | |

How sensitive the long-dated results are:
- The always-call 45d EV is **+20% / +12% / +5% at IV/VIX = 0.8 / 0.9 / 1.0**. The sign of "swing calls are positive" depends on a bull market and on our IV assumption.
- Debit spreads (ATM/+2–3%) look much better without skew, but with realistic skew they are about the same as or worse than a single long call. The short OTM call sells cheap vol. Either way, Robinhood's MCP rejects multi-leg orders.

## 4. Strategy ranking (OOS 2015+; bootstrap of one year from $170 with fractional sizing)

| strategy | trades/yr | OOS EV | PoP | t | last 3y | P(grow) @15/25/35% | P(ruin) @35% | 1 contract today |
|---|---|---|---|---|---|---|---|---|
| **e. PEAD mega-caps**: 7d ATM option in the direction of the reaction day (abs. excess move ≥2%), hold 5d | 25 | +14% (IV 1.2×RV) / **−9% to +37%** across IV 1.0–1.5×RV | 36% | 1.4 | +5% | 45/33/22% | 56% | $300–$1,000+ (unaffordable) |
| **g. SPY RSI2<10**: 14d ATM call, hold 5d | 12.5 | **+11.4%** | 48% | 1.7 | +35% | 60/55/51% | 1% | XSP ≈ $84 |
| **a. Trend-on** (SPY>200dMA and 12m mom>0): 45d ATM call, hold 20d | 9.6 | +10.8% | 51% | 1.4 | +19% | 58/55/50% | 0% | XSP ≈ $151 |
| b4. VIX/VIX3M>1 → 30d ATM call, hold 10d (contrarian) | 4.5 | +10.4% | 55% | 1.0 | +13% | 55/53/51% | 0% | XSP ≈ $123 |
| a0. *baseline: 45d ATM call every month, no signal* | 12.7 | +8.3% | 50% | 1.2 | +18% | 56/51/46% | 2% | |
| b1. VIX +20% in 3d (VIX≥18) → 30d ATM call, hold 10d | 5.6 | +4.5% | 50% | 0.5 | +13% | 49/46/44% | 0% | |
| d. Turn of month: 30d / 14d ATM call, 4 sessions | 12 | +0.9% / −1.1% | 48% | 0.3 | +8% | 48/45/42% | 0% | |
| c. Pre-FOMC: 14d call, close t−1 → close t | 8 | −1.5% | 38% | −0.4 | −1% | 41/39/38% | 0% | |
| b3. VIX/VIX3M>1 → puts | 4.5 | −27% | 22% | −1.7 | −51% | 19/16/13% | 0% | |
| a3. Trend-off → puts | 2.3 | −40% | 29% | −2.5 | | 18/16/15% | 0% | |
| **f. Current 0DTE engine**: ATM straddle at VIX≥16 | 140 | **−22.5%** | 29% | −13.8 | −29% | **0/0/0%** | **100%** | SPY $239; XSP $24 |
| f. 0DTE straddle only at VIX≥20 | 75 | −18.2% | 30% | −7.7 | −19% | 0/0/0% | 100% | |
| f. 0DTE coin-flip call/put at VIX≥16 | 140 | −23.2% | 30% | −7.8 | −34% | 0/0/0% | 100% | |

How to read the ranking:
- **PEAD's underlying drift is the most statistically solid finding in this sprint.** The signed 5-day SPY-excess return after a ≥2% earnings reaction is +0.71% (t 3.0, hit 59%, n=296) for 2015+, +0.43% (t 1.4) before 2015, and +0.83% (t 1.75) over the last 3 years. It was a single pre-specified hypothesis, so it survives a Bonferroni correction across the ~15 strategies.
  - It is **not a good options trade.** Post-earnings IV is uncertain, so EV swings from −9% to +37% across the IV assumption. PoP is only 36%, and bootstrap ruin is high. Mega-cap weeklies cost $300+ a contract.
  - If tested, use it on cheaper names or as a share-based paper signal.
- **Strategies g, a and b4 are all "be long SPY with leverage, preferably after a dip".** Their edge over the no-signal baseline a0 (+8.3%) is +2 to +3 points for trend (a1) and roughly +11 points for RSI2 against a same-tenor baseline. None of these differences is significant after correction.
- At 15–35% sizing they offer about a **50–60% chance the account is bigger after a year**, ruin under 3%, and a median end of about $180–$186 at 25% sizing.
- **0DTE as the bot runs it today is certain to lose with these numbers.** The −20% per-trade drag at 140 trades a year compounds to zero. Earlier work with real quotes found that ATM 0DTE debit spreads at VIX≥20 are much closer to fair (−6%; research/SYNTHESIS.md), so our 0DTE pricing may be somewhat rich. Even so, no direction or timing signal turns 0DTE positive.

## Recommendation

1. **Stop opening routine 0DTE directional or straddle trades.** No indicator predicts the same-day direction:
   - this study: 0 of 151 0DTE-horizon tests survive, and the model scores 50.8% against a 53.5% base;
   - earlier work: the intraday-momentum correlation is ≈0, and the 60-session coin flip.
   - Every 0DTE structure we priced has a structurally negative EV. Keep 0DTE only for the specific vol events that already show realized > implied (TSLA/META earnings strangles, P9).
2. **Switch the directional sleeve to "dip-buy XSP calls".** Rules:
   - **Buy:** a 14–30 day ATM XSP call when SPY RSI(2)<10, VIX>25, or VIX/VIX3M>1.
   - **Exit:** after 5 sessions (RSI2) or 10 sessions (VIX triggers). Hold one position at a time.
   - **Expected frequency:** about 12–15 trades a year. Size at 1 contract (≈$84–$123 now, which is 50–70% of the account, so expect a bumpy ride).
   - **Never buy puts for direction.** They lost money in every test.
   - **Paper-trade it for 2–3 months first**, logging the entries alongside what the 0DTE engine would have done.
3. **Set expectations honestly.** This is a thin, regime-dependent edge built on the 2015–2026 bull market and an assumed IV/VIX ratio of 0.9. A 2000–02 or 2008-style bear market would turn it negative. Growing $170 into something meaningful within a year is unlikely under any long-only-options strategy we can test. The bootstrap gives the best candidates about a 55% chance of being up at all.

## Caveats

- Option prices are modeled from VIX, not taken from historical quotes. Skew, the IV/VIX ratio and the 0DTE calibration are assumptions; sensitivities are shown above.
- QQQ IV is proxied as 1.2× SPY. The PEAD IV is 1.0–1.5× trailing 20-day realized vol.
- The "replicated" oversold signals were selected after seeing OOS results. They are a known published anomaly, but treat their EV as optimistic.
- The bootstrap uses fractional sizing. Real XSP sizing is one whole contract at 50–70% of the account, which raises variance (see the @60% columns in `strategies` output).
- NFP dates before 2015 are approximated (first Friday). CPI is tested only for 2015+. The mega-cap earnings-day QQQ test covers 2020-10+.
- Overlapping 5d/20d observations are handled with Newey-West. Persistent regressors (macro levels) still have inflated t-stats, which makes the "nothing survives" conclusion conservative.
