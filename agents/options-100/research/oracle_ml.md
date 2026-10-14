# Oracle break-even map + pooled ML direction model

2026-10-14. Owner's questions:
- "If we could predict direction, how would it do?"
- "Build a serious ML model, find what CAN work."

Owner update mid-sprint: account size is not a filter. Rank by edge; show MIN CAPITAL separately; simulate $170, $1k and $5k.

- **Code:** `bot/research_oracle_ml.py` (`calib | oracle | oracle_sens | fetch | ml | map`). `nonoverlap` runs inside `map`.
- **Cache:** `data/research_ml_cache.pkl` holds 99 yfinance names (daily, max history).
- **Outputs:** result JSON and predictions go to `$ORACLE_ML_OUT` (default: system temp), not the repo.
- **Runtime:** oracle ≈10 s; ML ≈40 min.

## Verdict (short)

1. **The break-even accuracy depends more on option *pricing* than on the structure.** At "fair" 0DTE pricing (implied E|move| = realized E|move| in each VIX bucket), an ATM 0DTE call/put bought at the open breaks even at **51.5% accuracy on XSP** (50.8% on SPY). The calibration brackets this:
   - Live quotes from this repo (option_snaps / vol_obs, VIX≈15) extrapolated over 2007–2026: **34%**.
   - The research_direction.py convention: **69%**.
   - So the first job is to *measure* realized/implied with real quotes. Since 2025-06 the realized open→close at VIX 14–16 (0.34%) is about the live implied (0.26–0.32%), i.e. roughly fair now.
2. **Term structures need about 54–57%:**

   | structure | break-even accuracy |
   |---|---|
   | 1-week ATM | ≈56% |
   | 2-week ATM | ≈56% |
   | 4-week ATM | ≈54% |
   | ATM/+1% debit spread, XSP | 55–56% |
   | ATM/+1% debit spread, SPY/QQQ (tighter spreads) | 52–53% |

   - Entering 0DTE later in the day is worse: 10:30 / 12:30 / 14:30 entries need 55–59% on SPY and 62–69% on QQQ/IWM.
   - Puts are the problem side: drift plus VRP make "always put" lose 20–28% on 1–4 week tenors.
3. **Accuracy alone is not enough: sizing kills.**
   - At the requested 20%-of-equity sizing, daily 0DTE needs ≈65% accuracy just to have a positive median year.
   - Growth-optimal sizing is 3% at 55% accuracy and 7% at 60% (Kelly).
4. **The pooled ML (130 symbols, 782k rows, strict walk-forward 2008–2026) never beats "always up" overall** on any target. AUC is 0.511–0.530.
   - The confident buckets do reach **56–68%**, but almost entirely by picking **days with a high base rate of up moves** (after selloffs, high VIX, VIX/VIX3M inversion). Bucket accuracy ≈ that bucket's up-rate; it does not call down days.
5. **Where it crosses break-even, and does it add anything?**
   - **0DTE.** On SPY, the confident oc1 bucket (top 10%, 56.7–62.1%, 8–10 trades/yr) crosses the fair break-even: EV **+23% per trade, t≈1.3–1.5**. Not significant.
   - **1-week calls.** The confident cc5 buckets (64–71%) cross the 56% break-even. With *non-overlapping* trades:

     | 1-week XSP calls | EV per trade | t |
     |---|---|---|
     | ML hgb top 10% | +38% | 2.25 |
     | ML lr top 20% | +14% | 1.1 |
     | RSI2<10 rule (known in advance) | +27% | 2.34 |

     The RSI2<10 rule held in 9 of 12 years and returned +45% per trade in 2022+. **The ML adds nothing over the RSI2<10 rule on SPY.**
   - **Multiple testing.** 36 non-overlapping ML tests, Bonferroni |t| > 3.2. **None pass.**
6. **Against buy-and-hold SPY:**
   - Buy-and-hold over 1 year (2015+, $170 start): median **$194**, P(grow) **83%**.
   - Best candidate, RSI2<10 → 1-week ATM XSP call with whole contracts, $1k start: median **$1,155 (+15.5%)**, P(grow) **59%**, P(halve) 10%. That is about the same median with far more variance.
   - **Nothing found here beats buy-and-hold risk-adjusted.** Per the owner's stance nothing is retired: this is not proof that no model can. The 0DTE pricing question is the open variable that could flip the answer (see "What to try next").

## Part 1: oracle / break-even map

### Pricing assumptions

| item | value | source |
|---|---|---|
| 0DTE E\|move\| at the open, **fair** (primary) | k(VIX)·VIX/√252·relvol | k = SPY realized mean \|open→close\| ÷ VIX/√252 per VIX bucket, 2007–2026: 0.40 / 0.43 / 0.47 / 0.52 / 0.60 at VIX 12 / 14.5 / 18 / 24 / 41 (QQQ 0.42–0.63, IWM 0.49–0.67). This gives realized/implied ≈ 1.00 in every bucket. |
| 0DTE, **live** (sensitivity) | k = 0.29 × VIX1D shape | Median ATM straddle / spot in `option_snaps`, 81 snapshots, Oct 8–14 2026, VIX≈15. Matches edge.py's "≈0.30% E\|move\| to close at VIX 15". VIX-level shape is from VIX1D open / VIX (1.05 / 1.00 / 1.02 / 1.11 / 1.15 / 1.25 across VIX buckets). |
| 0DTE, **rich** (sensitivity) | session sd = 0.8·VIX/√252 | research_direction.py convention. Realized/implied 0.63–0.95. |
| Intraday entries | E\|move\| × √(remaining variance share) | U-shaped profile from SPY 1h bars. Remaining share: 1.00 @09:30, 0.77 @10:30, 0.50 @12:30, 0.19 @14:30. Hourly bars start at :30, so entries are 10:30 / 12:30 / 14:30. |
| 0.30Δ wings | IV × 0.95 (call), × 1.10 (put) | assumption |
| 1–4 week ATM IV | **0.85 × VIX** × relvol | Long-run norm. Oct-2026 snapshots imply ~0.6; 0.6 and 1.0 are shown as sensitivities. |
| Term skew | IV(K) = IV_atm·(1−5·ln K/S) | Same as direction.md |
| Relative vol (QQQ, IWM) | rolling 60d RV(sym)/RV(SPY), lagged | |
| Bid-ask (full width, half paid each side) | SPY 1.4% / 3% / 0.6% (0DTE ATM / 0.30Δ / 1–4wk). QQQ 1.1 / 2.5 / 0.6. IWM 3 / 6 / 1.6. **XSP 4 / 8 / 3 (assumed)** | Medians from `option_snaps`. Intraday 0DTE spreads widen 1.2× / 1.6× / 2.5×. |
| Exit | ETF ITM sold at a 0.5% haircut; XSP cash-settles at no cost; $0.03/contract/side fee | |

Errors are random (accuracy p on every trade). The **"bigger"** variant gives each trade accuracy 0.5 + c·(p−0.5)·|move|/mean|move| (clipped, with the same mean p), so the predictor is better on big days. Sample: 2007-01 → 2026-10-13 (n≈4,970 sessions; hourly entries 2023-11+, n≈730).

### Expected return on premium vs accuracy (fair pricing, random errors)

**SPY priced as XSP** (what a small account can buy):

| structure | always call | always put | 50% | 55% | 60% | 65% | 70% | 80% | 100% | **BE** | BE big-moves | BE 2015+ | BE 2022+ | BE 2023-11+ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0DTE ATM @open | −1.2% | −4.8% | −3 | +7 | +16 | +26 | +36 | +55 | +94 | **51.5%** | 50.9 | 51.8 | 49.1 | 52.8 |
| 0DTE 0.30Δ @open | +0.1 | −12.3 | −6 | +3 | +13 | +22 | +32 | +50 | +88 | **53.2** | 51.4 | 53.6 | 49.6 | 55.6 |
| 0DTE ATM/1% spread | −3.6 | −9.2 | −6 | +3 | +12 | +22 | +31 | +50 | +87 | **53.4** | 52.3 | 53.4 | 50.7 | 54.1 |
| 0DTE ATM @10:30 | −7.6 | −14.8 | −11 | −2 | +7 | +15 | +24 | +42 | +78 | **56.3** | 53.2 | | | 56.3 |
| 0DTE ATM @12:30 | −12.3 | −18.0 | −15 | −7 | +2 | +10 | +19 | +36 | +70 | **58.9** | 54.1 | | | 58.9 |
| 0DTE ATM @14:30 | −11.0 | −12.4 | −12 | −3 | +6 | +15 | +24 | +41 | +77 | **56.6** | 53.2 | | | 56.6 |
| 1wk ATM (hold 5d) | −0.6 | −21.1 | −11 | −2 | +7 | +16 | +25 | +43 | +78 | **56.1** | 53.6 | 56.3 | 53.9 | 57.3 |
| 2wk ATM (hold 10d) | +3.4 | −26.3 | −11 | −3 | +6 | +15 | +24 | +42 | +77 | **56.5** | 53.9 | 55.8 | 53.7 | 58.2 |
| 4wk ATM (hold 20d) | +13.4 | −27.7 | −7 | +2 | +11 | +21 | +30 | +48 | +86 | **53.9** | 52.4 | 53.0 | 52.0 | 54.6 |
| 1wk ATM/1% spread | +1.2 | −21.2 | −10 | −1 | +8 | +17 | +26 | +44 | +80 | **55.5** | 54.7 | 55.6 | 54.4 | 55.2 |
| 2wk ATM/1% spread | +3.2 | −25.0 | −11 | −2 | +7 | +16 | +25 | +43 | +78 | **56.1** | 55.4 | 56.2 | 54.9 | 56.5 |

**Break-even accuracy, other venues** (fair pricing, random errors):

| structure | SPY | QQQ | IWM |
|---|---|---|---|
| 0DTE ATM @open | 50.8 | 50.6 | 50.2 |
| 0DTE 0.30Δ | 51.5 | 51.6 | 51.7 |
| 0DTE ATM/1% spread | 51.9 | 51.2 | 50.5 |
| 0DTE @10:30 / 12:30 / 14:30 | 55.5 / 57.8 / 54.8 | 62.1 / 67.3 / 64.7 | 62.6 / 69.1 / 68.5 |
| 1wk / 2wk / 4wk ATM | 55.4 / 55.8 / 53.3 | 53.4 / 53.4 / 51.3 | 54.2 / 55.0 / 53.6 |
| 1wk / 2wk ATM/1% spread | 52.9 / 52.6 | 51.7 / 51.8 | 52.7 / 53.4 |

How to read the break-even tables:
- The 50.2–50.8% 0DTE values for SPY/QQQ/IWM are only about costs. Fair pricing means "no VRP", so the venue spread is the whole hurdle. QQQ's term structures also benefit from relvol scaling plus 2015+ tech drift.
- In 2023-11+ the hourly-entry break-evens should be compared with the **@open break-even in the same window** (52.8 XSP). Late entries cost an extra 3–6 points on SPY and much more on QQQ/IWM, because late-day spreads are wider relative to premium.

### Sensitivity: break-even by pricing assumption (XSP)

| | 0DTE ATM | 0DTE 0.30Δ | 0DTE 1% spread | 1wk ATM | 4wk ATM | 1wk 1% spread |
|---|---|---|---|---|---|---|
| **fair (primary)** | **51.5** | **53.2** | **53.4** | **56.1** | **53.9** | **55.5** |
| live-quote k=0.29 | 34.0 | 27.1 | 38.9 | — | — | — |
| rich (direction.md) | 69.2 | 93.4 | 65.2 | — | — | — |
| term IV/VIX = 0.6 | — | — | — | 39.6 | 38.0 | 49.7 |
| term IV/VIX = 1.0 | — | — | — | 66.0 | 63.4 | 57.9 |

Under live-quote pricing, **every** 0DTE trade is positive at 50% (always call +50%, always put +44%). Over 20 years that would be one of the largest anomalies in finance, so I do not believe it as history. It does say the current low-realized regime is not rich. The rich convention makes 0DTE nearly hopeless. **This one number moves the answer more than any model can.**

### Break-even by VIX bucket (XSP, fair pricing; random errors / bigger-move errors)

| structure | VIX<13 | 13–16 | 16–20 | 20–30 | 30+ |
|---|---|---|---|---|---|
| 0DTE ATM @open | 52.5 / 51.2 | 51.8 / 51.0 | 51.3 / 50.8 | 51.3 / 50.8 | 50.6 / 50.3 |
| 0DTE 0.30Δ | 53.4 / 51.3 | 53.3 / 51.3 | 53.3 / 51.5 | 53.3 / 51.6 | 52.5 / 51.1 |
| 0DTE 1% spread | 55.0 / 52.8 | 54.5 / 52.7 | 53.0 / 51.9 | 52.6 / 51.9 | 51.6 / 51.3 |
| 0DTE @10:30 (2023-11+) | 47.2 / 50 (n68) | 55.7 / 52.7 | 60.1 / 55.3 | 60.0 / 55.7 | — |
| 1wk ATM | 65.2 / 58.2 | 57.2 / 54.0 | 56.1 / 53.9 | 53.4 / 52.1 | **49.4 / 50.0** |
| 2wk ATM | 60.9 / 55.8 | 57.4 / 54.4 | 55.5 / 53.4 | 55.8 / 53.8 | 52.3 / 51.3 |
| 4wk ATM | 51.5 / 51.0 | 54.5 / 52.3 | 53.0 / 51.9 | 54.7 / 53.0 | 56.8 / 54.3 |
| 1wk 1% spread | 61.5 / 58.1 | 54.8 / 53.8 | 53.9 / 53.2 | 54.5 / 53.9 | 56.3 / 55.8 |

- High VIX lowers the bar for short-dated longs: a 1-week ATM needs <50% at VIX 30+. This is the same "buy after selloffs" family again.
- Low VIX (<13) makes 1–2 week longs need 61–65%.

### Bankroll: $170, 20% of equity per trade, 1 year (2015+ bootstrap, XSP, fair pricing)

Cells are median end / P(grow) / P(ruin <$20). Fractional sizing.

| structure (trades/yr) | 50% | 55% | 60% | 65% | 70% | 80% |
|---|---|---|---|---|---|---|
| 0DTE ATM (252) | $18 / 0 / 99 | $18 / 4 / 94 | $19 / 22 / 73 | $890 / 58 / 38 | $207k / 86 / 13 | huge / 99 / 1 |
| 0DTE 0.30Δ (252) | $18 / 0 / 100 | $18 / 0 / 100 | $18 / 1 / 99 | $18 / 4 / 95 | $18 / 13 / 84 | $287 / 51 / 48 |
| 1wk ATM (50) | $19 / 5 / 75 | $20 / 13 / 57 | $51 / 26 / 38 | $132 / 45 / 21 | $331 / 65 / 10 | $1,799 / 92 / 1 |
| 2wk ATM (25) | $43 / 13 / 32 | $65 / 22 / 20 | $101 / 34 / 11 | $154 / 47 / 6 | $241 / 62 / 2 | $585 / 85 / 0 |
| 4wk ATM (12) | $95 / 25 / 1 | $115 / 33 / 1 | $146 / 43 / 0 | $182 / 53 / 0 | $221 / 62 / 0 | $340 / 80 / 0 |
| 1wk 1% spread (50) | $19 / 7 / 62 | $44 / 19 / 37 | $113 / 39 / 18 | $292 / 64 / 6 | $745 / 86 / 2 | $4,557 / 99 / 0 |
| 2wk 1% spread (25) | $57 / 14 / 19 | $90 / 26 / 9 | $142 / 43 / 4 | $230 / 61 / 1 | $357 / 78 / 0 | $902 / 96 / 0 |
| *buy-and-hold SPY* | median $194, P(grow) 83%, p10 $160, p90 $220 | | | | | |

**Growth-optimal (Kelly) fraction per trade** (XSP):

| structure | 55% | 60% | 65% | 70% |
|---|---|---|---|---|
| 0DTE ATM | 0.03 | 0.07 | 0.15 | 0.20 |
| 0DTE 0.30Δ | 0.01 | 0.02 | 0.05 | 0.07 |
| 1wk ATM | 0 | 0.03 | 0.07 | 0.15 |
| 4wk ATM | 0.02 | 0.07 | 0.15 | 0.20 |
| 1wk 1% spread | 0 | 0.07 | 0.15 | 0.20 |

**20% sizing is over-Kelly for every structure below 65–70% accuracy.**

### Min capital and whole-contract bankrolls (owner update)

- **MIN CAPITAL** = today's median contract cost ÷ 0.20.
- Whole contracts: buy floor(20%·equity / cost); if that is 0, skip the trade.
- Bankroll cells are median end / P(grow) at 60% and 65% accuracy, at each starting capital.

| venue / structure | contract | min capital | $170: 60% → 65% | $1k: 60% → 65% | $5k: 60% → 65% |
|---|---|---|---|---|---|
| XSP 0DTE ATM | $20 | $100 | $46/20% → $101/48% | $79/30% → $12.6k/70% | $669/32% → $79k/74% |
| XSP 0DTE 0.30Δ | $9 | $46 | ruin-like | ruin-like | ruin-like |
| XSP 1wk ATM | $63 | $314 | can't trade | $387/26% → $773/44% | $1,789/28% → $4,232/46% |
| XSP 4wk ATM | $126 | $631 | can't trade | $880/41% → $1,008/51% | $4,307/42% → $5,231/52% |
| XSP 1wk 1% spread | $34 | $169 | $133/18% → $136/29% | $743/41% → $1,679/65% | $3,604/42% → $8,702/66% |
| XSP 2wk 1% spread | $37 | $186 | $144/18% → $148/23% | $849/43% → $1,298/61% | $4,227/42% → $6,565/61% |
| SPY 0DTE ATM | $197 | $983 | — | $449/14% → $468/36% | $545/32% → $91k/69% |
| SPY 1wk 1% spread | $339 | $1,694 | — | — | $5,089/50% → $11,420/73% |
| QQQ 1wk 1% spread | $364 | $1,822 | — | — | $7,480/62% → $18,944/84% |
| IWM 0DTE ATM | $115 | $573 | — | $313/38% → $31.8k/69% | $3,673/47% → $410k/83% |
| IWM 1wk 1% spread | $135 | $676 | — | $858/47% → $2,020/68% | $5,893/55% → $14,407/78% |

## Part 2: pooled ML direction model

### Setup

**Universe:** 31 tradable symbols from market.db plus 99 from yfinance = **130 symbols**: 4 broad ETFs, 24 sector ETFs, 16 macro/international ETFs, 86 stocks. 2000-01 → 2026-10-13; **781,743 rows**.

**Features (≈80), all known at the close of t:**
- **Returns and vol:** returns over 1/2/3/5/10/20/60/120/250 days; today's open→close and gap; range and close location; RV 5/20/60 and their ratios; z-scored returns; RSI 2/14.
- **Trend and volume:** distance from 10/20/50/200d MA; drawdown from the 252d high and distance from the 252d low; volume shock (1d/20d, 5d/60d); up/down streak.
- **Relative:** beta-60 and beta-adjusted excess returns; cross-sectional demeaned returns and ranks.
- **Volatility state:** VIX level, 1d/5d change, 1y percentile, VIX/VIX3M, VIX9D/VIX, VVIX, SKEW.
- **Rates and credit:** 10y and 13w yields, curve slope; BAA10Y, T10Y2Y, NFCI (FRED, lagged to availability).
- **Commodities, FX, bonds:** oil/gold/DXY 1d/5d, lagged 1 day because they settle late; TLT 5d.
- **SPY state:** r1/r5/r20, RSI2, 200d distance.
- **Calendar:** day of week, month, day of month, trading days to month-end, opex week.
- **Earnings:** exact days-to-earnings for 8 mega caps (cached); an earnings-cycle proxy for the rest (days since the last >3σ gap, mod 63).
- **Open→close target only:** the next-day gap (own and SPY), which is known at 09:30.

**Targets:**
- next-day open→close sign (`oc1`);
- close→close sign (`cc1`);
- 5-day sign (`cc5`);
- big-move up vs down (`big`: next-day |cc1| > 1 trailing-60d sd).

**Models:** standardized L2 logistic (C=0.05) and HistGradientBoosting (250 iters, lr 0.04, 31 leaves, min leaf 800, L2 1, 50% feature subsampling). LightGBM would not load (no libomp).

**Walk-forward:**
- Retrain every January for 2008…2026 on all prior data, with a 5-session purge before the test year.
- Pooled across symbols, so a date in the test year never appears in training.
- Train is capped at 600k random rows.

**Confidence buckets:** |p−0.5| thresholds come from **prior OOS years only**, so the first OOS year is excluded. Significance uses date-clustered t-stats.

### Overall and confident-bucket accuracy (pooled, 2015+)

| target·model | AUC | acc | always-up | top 5% acc (its up-rate) | top 10% | top 20% | top-10% rows/yr (pooled) |
|---|---|---|---|---|---|---|---|
| oc1 · LR | 0.514 | 51.1 | 50.8 | 56.6 (55.0) | 54.3 (52.2) | 53.2 (51.7) | 1,102 |
| oc1 · HGB | 0.517 | 51.0 | 50.8 | **56.7 (51.2)** | 54.5 (51.6) | 53.9 (50.3) | 1,357 |
| cc1 · LR | 0.514 | 51.8 | 52.1 | 54.7 (54.6) | 54.7 (54.5) | 54.1 (53.9) | 2,266 |
| cc1 · HGB | 0.511 | 50.9 | 52.1 | 56.5 (55.6) | 55.5 (54.6) | 54.5 (53.3) | 2,234 |
| cc5 · LR | 0.530 | 54.3 | 54.5 | 54.1 (54.0) | 59.6 (59.5) | 60.2 (60.1) | 1,589 |
| cc5 · HGB | 0.522 | 51.9 | 54.5 | 63.6 (63.9) | 61.9 (62.4) | 58.0 (59.5) | 2,415 |
| big · LR | 0.514 | 52.0 | 52.3 | 55.8 (55.7) | 54.6 (54.6) | 53.8 (53.6) | 444 |
| big · HGB | 0.511 | 51.2 | 52.3 | 56.0 (56.0) | 55.1 (54.2) | 55.1 (54.1) | 592 |

**2022+:**

| target·model | acc | always-up | top 10% acc (its up-rate) |
|---|---|---|---|
| oc1 · LR | 51.2 | 50.9 | 54.1 (48.9) |
| oc1 · HGB | 51.1 | 50.9 | 51.2 (52.0) |
| cc5 · LR | 53.2 | 52.8 | 71.9 (69.4) |
| cc5 · HGB | 50.5 | 52.8 | 68.8 (65.7) |

What the tables show:
- **No model beats "always up" overall.** Its edge over the majority class is negative in most years (cc5·HGB in 13 of 19 years).
- In every confident bucket **except oc1·HGB**, accuracy equals the bucket's up-rate. The model is selecting bullish regimes, not calling direction.
- oc1·HGB top 5% is the one exception (56.7% against a 51.2% up-rate, 2015+). It disappears in 2022+ (top 10%: 51.2% against a 52.0% up-rate).

**Per symbol (2015+, all predictions):**

| | SPY acc (up-rate) | QQQ | IWM |
|---|---|---|---|
| oc1 · LR | 51.3 (53.5) | 53.3 (53.7) | 51.3 (50.7) |
| cc5 · LR | 60.1 (60.5) | 59.6 (60.0) | 55.9 (54.5) |

- No asset class beats its own up-rate: broad 58.4 against 58.2, sector 55.1/55.0, stock 54.1/54.4, macro 52.9/53.3 (cc5·LR).
- Best and worst single tickers sit at ±2–3 pp (cc5·LR: XBI +2.2, XRT +2.1; LLY −2.5). With n≈2,960 per ticker (se ≈0.9 pp) and 130 tickers, that spread is what noise produces. **No ticker stands out.**

**Feature importance:**
- **LR, by standardized coefficient:**
  - yield-curve slope (10y−3m, −) and T10Y2Y (+);
  - own 5-day return (−, short-term reversal);
  - turn-of-month (day of month, days to month-end);
  - cross-sectional 5d and 20d return;
  - SPY 200d distance (−) and NFCI.
- **HGB, by permutation AUC:**
  - **VIX/VIX3M**, SPY RSI2, gold 5d, BAA spread and its change, DXY 1d, VIX9D/VIX, VVIX, VIX percentile.
- Both point at the same two things found in direction.md: **regime/macro levels**, which flipped sign after 2015 there, and **oversold/volatility state**.

### Mapping confident buckets onto option P&L (SPY as XSP; 2015+; fair pricing)

| signal → structure | trades/yr | acc | EV/trade | t (naive) | EV 2022+ | min capital |
|---|---|---|---|---|---|---|
| oc1·HGB top 10% → 0DTE ATM | 10 | 56.7 | +23.7% | 1.5 | +20% | $170 |
| oc1·HGB top 20% → 0DTE ATM | 27 | 57.3 | +12.2% | 1.4 | +17% | $136 |
| oc1·LR top 10% → 0DTE ATM | 8 | 62.1 | +22.7% | 1.3 | +100% | $230 |
| oc1 all days → 0DTE ATM | 251 | 51.1–51.3 | −0.6 / −3.2% | — | | $95 |
| cc5·LR top 20% → 1wk ATM call | 28 | 67.2 | +28.9% | 4.0 | +94% | $455 |
| cc5·HGB top 10% → 1wk ATM call | 18 | 68.1 | +37.5% | 4.0 | +58% | $513 |
| cc5·HGB top 10% → 1wk 1% spread | 18 | 68.1 | +15.9% | 2.7 | +41% | $193 |
| *always call 1wk ATM* | 251 | 60.5 | +1.6% | | | $303 |

Non-overlapping version, the honest one: entries at least one holding period apart, call trades only.

| 1-week ATM call | SPY/XSP: n · EV · t · years positive · EV 2022+ (n) | QQQ | IWM |
|---|---|---|---|
| always call | 592 · +0.6% · 0.1 · 6/12 · +4% | 592 · +9.1% · 1.7 · 9/12 | 592 · −1.9% · −0.4 |
| **RSI2<10 rule** | **147 · +27.3% · 2.34 · 9/12 · +45% (69)** | 141 · +14.1% · 1.2 · 9/12 | 155 · +4.9% · 0.4 |
| ML cc5·LR top 20% | 93 · +14.1% · 1.1 · 8/9 · +63% (6) | 96 · +7.2% · 0.6 | 94 · +30.4% · 2.0 |
| ML cc5·HGB top 10% | 71 · +37.7% · 2.25 · 7/10 · +33% (6) | **69 · +44.8% · 2.72 · 8/10 · +24% (7)** | 63 · +22.3% · 1.2 |
| ML cc5·HGB top 20% | 111 · +24.7% · 1.9 · 8/11 · **−21% (15)** | 109 · +24.8% · 1.9 · −29% (15) | 105 · +19.9% · 1.4 · −38% (12) |

- Only 65–80 of the ML's ~330–370 top-20% days are RSI2<10 days. It finds other high-up-rate days (VIX/VIX3M inversion and so on), but they do not pay more.
- **The "big-move" model must not be read as tradable.** Its +50–70% EVs come from scoring only on days that turned out to have a >1σ move, which is look-ahead. It answers "given a big move, which way?": **52% against a 52–56% up-rate**, i.e. no skill.

### Multiple testing and regime dependence

- The grid covers 4 targets × 2 models × 3 symbols × 3–6 structures × 5 buckets: about 360 mapped rows and 36 non-overlapping ML tests.
- **No ML result reaches Bonferroni |t| > 3.2.** The two best, QQQ HGB top 10% (t 2.7) and SPY HGB top 10% (t 2.25), are what the best of 36 noisy tests looks like.
- The HGB top-20% buckets are **negative in 2022+** on every symbol.
- The RSI2<10 rule was pre-registered in direction.md, so it is one test, not 36. It held in 2022+, but it carries the same caveats: a bull-market period and an assumed IV/VIX of 0.85.

## Conclusion

| question | answer |
|---|---|
| Accuracy needed (fair pricing) | **0DTE ATM ≈51.5% (XSP)**, 0.30Δ ≈53%, 0DTE 1% spread ≈53%, intraday 0DTE 55–59% (SPY) and 62–69% (QQQ/IWM), 1–2wk ATM ≈56%, 4wk ≈54%, 1–2wk 1% spreads ≈55.5% on XSP and ≈52.6–53% on SPY/QQQ. **±17 points depending on the 0DTE pricing assumption.** |
| Accuracy needed to *grow* at 20% sizing | 0DTE ≈65%, 1wk ATM ≈67%, 1wk 1% spread ≈62%. Kelly says size 3–7% at 55–60%. |
| What the ML reaches | Overall 51–54%, **never above always-up**. Confident buckets 56–68%, mostly by choosing bullish days. Calling down days is no better than a coin flip. |
| Where it crosses break-even | (a) SPY 0DTE, confident oc1 buckets: 56.7–62% against 51.5%, +12–24%/trade, t≈1.4 (not significant). (b) 1-week calls on confident cc5 days: 64–71% against 56%, +14–45%/trade non-overlapping, t 1.1–2.7. Neither beats the simple RSI2<10 rule on SPY. Nothing survives correction. |
| vs buy-and-hold SPY | RSI2<10 → XSP 1wk ATM call at $1k: median +15.5%, P(grow) 59%. Buy-and-hold: +14%, P(grow) 83%. **Equal median, much worse odds.** Not yet a reason to retire it (owner's rule), but not a proven edge. |

**Ready when funded** (positive edge in this study, but needs more than $170):
- RSI2<10 → XSP 1-week ATM call or 1–2wk 1% call spread. Min capital **$314** for the ATM call, $169–186 for the spreads.
- RSI2<10 / confident cc5 days → SPY or QQQ 1–2 week ATM/1% call spreads. Tighter spreads than XSP, break-even 52–53%. Min capital **$1.7–2.0k**.
- QQQ cc5·HGB top-10% → 1-week ATM call: +45%/trade, t 2.7, about 6/yr. Min capital **≈$6.4k**. Fails correction, so paper-trade only.
- Any directional 0DTE, *if* real-quote calibration shows realized/implied ≥ 1.0. IWM 0DTE has the lowest break-even (50.2%), min capital **$573**; SPY needs **$983**.

## What to try next

1. **Settle 0DTE pricing with real quotes.** It swings the break-even from 34% to 69%.
   - `vol_obs` already logs implied vs realized. Extend it to log the **XSP and SPY 0DTE ATM straddle mid at 09:35** plus the weekly ATM straddle, every day, then grade against realized. After 20–40 sessions this tells us whether 0DTE is cheap (trade it), fair (needs about 52%) or rich (abandon).
   - Buying historical chains would settle it at once: ThetaData, Polygon or CBOE DataShop, roughly $30–80 a month.
2. **Add intraday features for 0DTE.** The daily model only sees the gap. Opening-range and first-15/30-minute features plus overnight ES moves are the plausible 0DTE edge.
   - Data: 5m bars exist since 2026-07, 1m bars since 2026-09. Building a longer intraday history (Alpaca free tier) is a prerequisite.
3. **Size by Kelly, not a flat 20%.** Use 3–7% at realistic accuracies, with a whole-contract floor. At $170 the floor forces about 12–20% per XSP 0DTE contract, which is the real constraint.
4. **Train a model for the regime that works.** Use meta-labeling: train only on oversold/high-VIX days and predict *whether the dip-buy works*, using breadth, credit and VIX term structure. Do not ask it for unconditional direction.
5. **Paper-trade the RSI2<10 → XSP 1-week call** next to the current engine, as direction.md proposed. This study independently confirms it (+27%/trade non-overlapping, 9/12 years, at a 56% break-even structure).

## Caveats

- Option prices are modeled, not historical quotes. The fair 0DTE k uses the full-sample realized mean, so the pricing *level* is calibrated in-sample. Signals are not.
- XSP spreads are assumed.
- The yfinance universe is today's large caps, so it carries survivorship bias. That inflates the "always up" rate, not model skill.
- Earnings dates are exact for only 8 mega caps; the rest use a proxy.
- Bootstraps ignore autocorrelation and regime runs.
- The 1-week "hold to expiry" assumes 5 sessions = 7 calendar days.
