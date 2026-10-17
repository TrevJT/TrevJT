# Weekend edge hunt, 2026-10-17: "there is a way to beat the market with AI"

Owner's ask (10-16): step up the strategy; more data, more context, correlation/ML on every foreign market, forex, futures, perpetuals; brainstorm, run the data models, report back. Hard rule unchanged: only the $100 can be lost, so everything below is long premium / defined risk, and anything else is labelled RESEARCH-ONLY. Scripts: `research/weekend/` (one file per study, outputs in `research/weekend/out/`). Nothing in PLAN.md or ROUTER.md was changed; section 7 is a proposal list.

## 1. Executive summary

1. **No directional edge was found, again, and this time across 38 ideas and ~1,900 tests** (28 cross-asset features x 2 targets x 2 periods, 4 walk-forward ML models, 444 volatility-regime subgroups, 246 prediction-market tests, 84 crypto tests, 252 trend tests, 720 P1 exit cells). Zero directional tests survive Benjamini-Hochberg out of sample. The P1 momentum score is a coin flip on the underlying (+0.2 to +1.4 bp to 15:45, t 0.2-1.2, 49-52% hit, 4,841 sessions). Asia/Europe closes, FX, crude, gold, rates, credit, BTC, VIX term structure: none predicts the US open->close direction (0 of 56 OOS, AUC 0.50-0.51).
2. **The single most important finding is about pricing, not signals.** Every 0DTE conclusion in this repo flips with the assumed option price level. The 8 days of live quotes (Oct 8-16) priced a SPY 0DTE straddle at only 0.90-1.0x VIX in calendar minutes, which is 1.4-1.5x *cheaper* than 19 years of realized moves; under that level every long-option idea looks +20-50%. But CBOE's VIX1D index (built from real 0DTE/1DTE SPX quotes since 2023, 874 days) says buyers receive **0.90-0.92 of the implied move** on average. That week's VIX1D/VIX was 0.45-0.65 vs a 0.79 median: it was an unusually cheap week, not the norm. The report therefore quotes three levels: MKT (that week), **V1D (central, 0.92)**, VRP (0.80, the 33-year VIX-based figure). Decisions should use V1D.
3. **Exit rules cannot rescue a coin-flip signal.** On 19 years of 1-minute SPY/QQQ, with the real Oct-2026 smile and spread costs, the written P1 exits (-45% stop, +100% take, 30-min time stop, 12:00 exit) are the *least bad* rule: -6% per trade (V1D, OOS, ATM single) vs -17% hold-to-15:45, -18% resting 2x, -11% VWAP-cross, -13% stop-only. The Oct-16 "stopped out before a 12x" case happens on 2% of trades under central pricing (6-8% under the cheap-week level); the stop saves more than it costs. On the real Oct-16 quotes the written rules actually exited at -8% via the 30-minute time stop at 10:28; a bare -45% stop would have lost 69% at 10:58. **The VIX 16-18 band is negative (-8% OOS, 46.7% hit): strike it, do not add it.** The 18-20 band is the only positive cell (+9 bp underlying, 57% hit, option -0.3%) and is one of 10 band cells, so it is a watch item, not evidence.
4. **Three non-directional findings are worth paper money (all weak, +5 to +20% EV, none robust to multiple testing yet):**
   - **Big-gap mornings are cheap for a 0DTE ATM straddle.** In the VIX1D era (2023-26, n=875), realized |open->close| / implied is 1.16-1.18 (t 2.1-2.3) when the SPY, TLT or HYG gap is in its top quintile (|gap| >= ~0.7%), vs 1.0-1.04 in the bottom quintile. EV ~ +5% (proportional pricing) to +15% (variance-share pricing) per straddle after 2% costs. Vehicle: XSP 0DTE ATM straddle ~$40. TRADEABLE-NOW, paper first.
   - **Iran/oil odds shocks lead crude by hours.** 226 de-clustered >= 5-pt / 60-min odds moves since 2025-07: crude moves +38 bp in the next hour (t 2.4) and +86 bp over 24h (t 3.4) in the risk direction; QQQ/SPY effects vanish after de-clustering. It is entirely a 2026 effect (2025: n=29, -29 bp), and 94% of events are outside RTH. This is the best evidence P5 has had (was n=19). Vehicle: USO 1-week option ~$120 (OTM) / ~$350 (ATM). TRADEABLE-WITH-MORE-CAPITAL (~$1k), probe-size now.
   - **VIX term structure is a gate for any long-premium trade.** 0DTE straddle EV (V1D, OOS): -30% when VIX9D/VIX is in the bottom tercile, -16% middle, -1.4% top tercile; -24% when VIX fell over 5 days vs -4% when it rose; +3-4% at VIX >= 25 (t 0.5-0.7). Nothing is positive, but the spread between terciles is 29 points. Proposal: no long premium of any playbook when VIX9D/VIX is in its bottom tercile.
5. **Dead, with numbers:** BTC perp funding (contrarian in-sample, momentum out-of-sample, t -2); BTC overnight -> COIN/MSTR/MARA continuation (t 2.5-3.8 before fixing a bar-label leak, t 0.1-1.4 after); BTC weekend -> Monday equities (n=85, ~0); FX/commodity/foreign-index trend via ETF options (0/84 OOS, pooled 3-month momentum +31 bp/month t 0.6, option EV +1-4%); overnight-premium 1DTE calls (SPY -2%, QQQ +5% V1D / -2.5% VRP: break-even); end-of-day momentum (rho 0.00); OPEX / weekday / pre-holiday long vol (all negative); ML direction (AUC 0.50); ML long-vol regime (p>0.6 +13%, t 1.5, inconsistent by year).
6. **Two look-ahead leaks were caught and are now a rule:** yfinance and Coinbase hourly bars are labelled by their START time, so the "09:00" bar closes at 10:00 and overlaps the 09:30 open. Using it produced a t = 4.7 "NQ overnight predicts QQQ" result and a t = 3.8 "BTC overnight predicts MARA" result; both are zero with the 08:00 bar.
7. **Honest bottom line:** with the data on this machine, no strategy beats the market after costs out of sample as a *directional* bet, in any asset class tested. The volatility side has three small, plausible, untested-live edges, all of which depend on the 0DTE price level that only ~60 days of logged live straddles (already being collected in `option_snaps`) will settle. The account can run them on XSP and paper-size USO while that data accumulates. Section 8 lists what would be needed to find more.

## 2. The pricing-level problem (read this before any 0DTE number)

| Convention | Implied E|move| from the open, VIX 16 | Source | Always-long 0DTE ATM straddle, OOS 2019-26 | P1 ATM written rules, OOS |
|---|---|---|---|---|
| MKT | 0.37% | live SPY/QQQ straddles Oct 8-16 (k ~ 0.92-1.0 x VIX, calendar minutes); that week VIX1D/VIX = 0.45-0.65 | **+31%** (t 12) | +1% |
| **V1D (central)** | 0.56% | CBOE VIX1D vs realized, 2023-04..2026-10, n=874: realized close->close = 0.903 x implied, open->close = 0.915 x; proportional intraday share | **-17%** | **-6%** |
| VRP (conservative) | 0.64% | 33-year VIX-based daily VRP (research_vol.py): realized = 0.80 x implied | -28% | -8% |

- The MKT calibration (`zdte_calibration` in `common.py`, `k_spy(mins_left)` interpolated from hourly medians of 400 real ATM straddles) is kept because it is the only *shape* information: the market's implied sd from time t to the close is k(t) x VIX x sqrt(t/yr) with k = 1.0 at 09:30, 0.88 at 11:00, 1.37 at 14:00, 1.52 at 15:00 (0DTE premium decays slower than sqrt(time) into the close). The real smile from the same quotes is applied to OTM strikes (put IV +17% at 1.5 sd, +38% at 2.5 sd).
- The *level* is set by matching 19 years of realized moves (FAIR multiplier 1.38-1.46 on MKT for SPY, 1.22-1.53 for QQQ) and dividing by the VIX1D-measured buyer's share (0.92). Under V1D, the intraday-only ratio comes out 1.085 if the market splits daily variance like realized (69% intraday), i.e. the open->close straddle may be ~fair to slightly cheap; the close->close straddle is 0.90. The truth for 0DTE from the open is between 0.90 and 1.08; the report uses 0.92.
- Consequence for prior work: intraday.md's "always-call +27%" and the engine's "+30-200% EV" picks are MKT-level artefacts; direction.md's -28% is VRP-level. The 10-14 note ("collect real 0DTE quotes before trusting any 0DTE EV") stands and now has a target: `vol_obs` + `option_snaps` need ~60 sessions, then `k_spy` and the level get re-fitted from them, not from one week.

## 3. Ranked idea table (38 ideas; EV per trade on premium, V1D pricing unless stated)

Labels: NOW = tradeable now under the hard rule; CAP = tradeable with more capital (min capital = one contract / 35% sizing); RO = research-only (violates the hard rule or needs data we do not have). Confidence: how likely the stated effect is real (not how big).

| # | Idea | Label | Min capital | Data | Result | Conf. |
|---|---|---|---|---|---|---|
| 1 | 0DTE ATM straddle on big-gap mornings (SPY/TLT/HYG gap top quintile), buy 09:35, hold to close | NOW (XSP) | $40 (XSP) / $380 (SPY) | VIX1D era 2023-26, n=875 | realized/implied 1.16-1.18 (t 2.1-2.3) vs 1.00-1.04 bottom quintile; EV +5..+15% | medium-low |
| 2 | Iran/Hormuz/oil odds shock (>= 5 pt in 60 min) -> crude, 1h-24h | CAP (USO weekly; probe NOW) | $120 OTM / $350 ATM; ~$1k proper | 226 de-clustered events 2025-07..2026-10 | CL +38 bp 1h (t 2.4), +86 bp 24h (t 3.4); 2026-only; 94% of events overnight | medium-low |
| 3 | Term-structure gate: skip all long premium when VIX9D/VIX in bottom tercile | NOW (filter) | 0 | 2011-26 | 0DTE straddle -30% (bottom) vs -1% (top tercile); 5d straddle -18% vs -3% | high (as a filter) |
| 4 | VIX >= 25 long 0DTE straddle | NOW (XSP) | $60 | 2007-26 | +3..+4% (t 0.5-0.7, n=348 OOS): break-even, not edge | medium |
| 5 | P1 exits: keep the written rules | NOW | - | 1-min SPY/QQQ 2007-26, 18,935 signals | written -6% vs hold -17%, 2x -18%, VWAP -11%, stop-only -13% (OOS, ATM); no rule turns positive | high |
| 6 | P1 in the VIX 16-18 band (the 10-16 question) | NOW | - | 1,013 OOS signals | underlying -1.7 bp, 46.7% hit; ATM -8%, OTM -18%: **remove the band** | high |
| 7 | P1 in the VIX 18-20 band | NOW | - | 688 OOS | +9 bp underlying, 57% hit, ATM written -0.3%; 1 of 10 cells | low |
| 8 | P1 OTM 0.15-delta singles (the original P1 contract) | NOW | - | same | -15% written, -44..-51% hold/2x: never use 0.15-delta singles | high |
| 9 | Resting 2x take-profit (ROUTER universal rule) | NOW | - | same | worse than written rules under V1D (-18% vs -6%); only wins under the cheap-week level | medium |
| 10 | ML long-vol regime classifier (HistGB, 19 features, yearly refit 2013+) | NOW | $40 | 3,094 OOS days | p>0.6: +13.5% (n=138, t 1.5), years alternate sign; AUC 0.62 | low |
| 11 | 1DTE ATM call 15:55 -> 09:35 (overnight premium) | NOW (XSP) / CAP (QQQ $310) | $35 / $900 | 2007-26 | SPY -2% (t -1.2), QQQ +5% (t 2.2) V1D; -7% / -2.5% VRP: break-even | low |
| 12 | Overnight vs intraday return split | RO (needs shares) | - | 2007-26 | overnight 4.6%/yr SPY, 9.3% QQQ (t 1.7 / 3.1) vs intraday 3.0 / 4.1: real but captured by shares, not options | high |
| 13 | Crypto-equity residual gap fade (gap beyond 1.5x BTC fades 09:35->close) | RO / CAP (shares) | shares ~$2k | 437 OOS sessions | MARA -207 bp (t -3.6), RIOT -136 (t -2.5), MSTR -115 (t -2.0); 1 BH survivor of 42; options at 100%+ IV cannot carry it | medium-low |
| 14 | Weekly straddle (5d) timing by regime | NOW (XSP) | $150 | 2011-26 | every subgroup negative (-3% best: VIX9D/VIX top tercile) | high (negative) |
| 15 | Cross-asset overnight -> SPY/QQQ direction (Nikkei, HSI, Shanghai, KOSPI, ASX, DAX, STOXX, FTSE, EURUSD, USDJPY, DXY, CL, GC, BTC, gaps of TLT/GLD/USO/HYG/UUP, VIX term structure, RV) | NOW | $40 | 2010-26 daily; 2024-26 hourly | 0/56 OOS BH; |rho| <= 0.06; walk-forward logit/HistGB AUC 0.50-0.51; hourly ES/NQ overnight -> fade -16 bp (t -1.7) | high (negative) |
| 16 | Cross-asset overnight -> |move| (straddle) | NOW | $40 | 2019-26 | gaps in HYG/TLT/QQQ top quintile -> ratio 1.5-1.7x bottom quintile under MKT (= idea 1 under V1D) | medium |
| 17 | BTC perp funding (1d/7d, z-scored) -> BTC 1/3/7d | RO (BTC) / CAP (IBIT) | IBIT 1-wk ATM ~$260 | Deribit 2019-26 | IS contrarian +30..+250 bp (t 1-1.7), OOS momentum -44..-128 bp (t -1.2..-2.4): sign flips | high (negative) |
| 18 | BTC overnight (prior 16:00 -> 09:00) -> COIN/MSTR/MARA/RIOT/CLSK/HOOD open->close | NOW (options) | COIN 1-wk ATM ~$600 | 2021-26 | t 0.1-1.4 after the leak fix (was t 2.5-3.8) | high (negative) |
| 19 | BTC weekend (Fri 16:00 -> Mon 09:00) -> Monday crypto equities | NOW | same | 85 Mondays OOS | ~0 (t -0.7..+0.7) | medium (negative) |
| 20 | BTC weekend move reverses Mon-Wed (on BTC itself) | RO (BTC) / CAP (IBIT) | $260 | 214 weekends 2022-26 | Spearman -0.19 (1d), -0.23 (2d) with the weekend move: a reversal lead, not yet option-tested | low |
| 21 | FX/commodity/foreign-index time-series momentum (12-1, 6-1, 3, 1 month) via 1-month ATM ETF options | CAP | UUP $56, FXY $116, FXE $200, TLT $330, EWJ $580, EWZ $730, SLV $750, USO $2.3k, GLD $2.9k | 2007-26, 21 instruments | 0/84 OOS; pooled 3-month momentum +31 bp/month (t 0.6), option EV +1..+4% | medium (negative) |
| 22 | FX carry (rate differentials) | CAP | as above | not fetched (FRED foreign short rates) | not tested | - |
| 23 | Futures options (ES/MES/CL weeklies) as cheaper index/oil vehicles | RO (Robinhood support unverified) | MES ~$200, ES ~$2k | - | not tested; flag: unknown if the Agentic account can trade them | - |
| 24 | Outright futures / perpetuals / spot FX on margin | RO (hard rule) | n/a | - | signals above are the only legal use (none found) | - |
| 25 | ML direction model (logit / HistGB on 28 overnight features) | NOW | $40 | 1,688 OOS days | AUC 0.504-0.51; confident subsets 51-54% = base rate | high (negative) |
| 26 | Prediction-market shock -> SPY/QQQ | NOW | $40 | 226 clusters | QQQ -11 bp 24h (t 1.3), SPY -5 bp (t 1.1) after de-clustering: nothing | medium (negative) |
| 27 | Fed-odds shock -> ZN / VIX | CAP (TLT) | $330 | 468 events | ZN ~0; VIX +36 bp 1h (t 2.5) on Fed-odds moves: pre-FOMC clustering, not tradeable | low |
| 28 | Does the market lead the odds? (hour-before returns, 1h cross-correlation) | - | - | same | hour-before ~0; all 1h cross-correlations |rho| < 0.03: odds and prices move together or odds first | medium |
| 29 | Day-of-week long vol (Mon worst -29%, Thu best -9%) | NOW | $40 | 2007-26 | all negative; the Thursday/Friday tilt is a size modifier at most | medium |
| 30 | OPEX-day long vol | NOW | $40 | 90 OOS opex days | -13% vs -17% other days: no effect | medium (negative) |
| 31 | Pre-holiday long vol | NOW | $40 | 74 days | -29%: worse (and short vol is not allowed) | medium (negative) |
| 32 | VVIX low -> long 0DTE vol | NOW | $40 | 523 OOS | -0.7%: fair, not cheap | medium |
| 33 | Intraday vol seasonality vs the 0DTE price curve | - | - | 400 live straddles | the market's k(t) rises 1.0 -> 1.5 into the close, matching realized late-day vol: already priced | high |
| 34 | End-of-day momentum (09:30->15:30 vs last 30 min) | NOW | $40 | 2019-26 | rho 0.004 / 0.006, spread -0.8 bp: dead (confirms intraday.md) | high (negative) |
| 35 | Mega-cap earnings vol mispricing (P9) | NOW | TSLA ~$70 (OTM) | none local | not testable without historical option prices; wishlist | - |
| 36 | 0DTE dealer gamma / OI positioning | NOW | $40 | none local | not testable (needs OI by strike history) | - |
| 37 | News / LLM sentiment as a trigger | NOW | - | news_trading.md | already dead as a trigger (priced by 10:30); only a veto | high (negative) |
| 38 | XSP as the vehicle for every SPY idea | NOW | 1/10th of SPY | - | makes ideas 1, 4, 10, 11 affordable at 35% sizing | high |

## 4. Model results (out-of-sample unless stated)

### 4.1 P1 replay with exit variants (`p1_exits.py`, 1-min SPY and QQQ, 2007-01..2026-03, IS < 2019 / OOS 2019+)
- Score replicated exactly from `score.py` on 5-minute bars (VWAP side, ATR distance, VWAP slope, 3-of-4 bars, range break, RVOL >= 1.3). First signal per window (A 09:40-11:00, B 14:00-15:10), fill one minute after the bar close, one contract, 12 exit rules, 2 contracts (ATM single; 0.15-delta OTM single with a spot-relative strike grid and a premium floor), 3 price levels: 720 cells, 144 pooled variants.
- Underlying (direction only, bp to 15:45): SPY S>=4 OOS +0.9 (t 0.85, 50.7%); QQQ +1.4 (t 1.06, 51.5%); |S|>=5 & RVOL: +1.4 / +1.3 (t 1.2 / 0.8). By band, OOS, |S|>=5: 16-18 -1.7 bp (46.7%), 18-20 +9.0 (57.4%), 20-25 +0.1, 25+ -0.2, <16 +1.9.
- Exit rules, ATM single, |S|>=5 & RVOL, OOS (n=5,606), mean return on premium / win rate:

| Rule | MKT | **V1D** | VRP |
|---|---|---|---|
| R0 written (-45% stop, +100% take, 30-min time stop, 12:00 A-exit) | +1.7% / 40% | **-5.9% / 36%** | -8% |
| R1 hold to 15:45 | +23.9% / 36% | -16.6% / 28% | -30% |
| R2 resting 2x + hold | +5.4% / 49% | -18.3% / 34% | -31% |
| R4 VWAP-cross exit | +6.7% / 26% | -11.3% / 20% | -18% |
| R6 -45% stop only | +20.6% / 24% | -9.6% / 21% | n/a |
| R7 -45% stop + 2x | -0.2% / 37% | -10.6% / 27% | -19% |
| R8 trail 65% of peak after +50% | +7.5% / 50% | -16.8% / 37% | n/a |
| R11 -45% stop + VWAP-cross | +6.8% / 23% | -8.7% / 19% | n/a |

- OTM 0.15-delta single, same cell, V1D: written -15%, hold -44%, 2x -44%, VWAP -31%. Stopped at -45% then finished >= +100% by 15:45: 2.4% of ATM trades (V1D), 7.4% (MKT). Stopped then finished >= 0: 6.6% (V1D).
- Real-quote replay (`oct16_replay.py`, 56 single-leg trades on 8 live days, both directions, no signal): ATM written -3%, hold +35%, 2x +1%, stop-only -6%; OTM written -6%, hold +34%, 2x -20%, stop-only -29%. The Oct-16 QQQ 715P (09:57 @0.515): written rules -7.7% at 10:28 (time stop), stop-only -69% at 10:58, resting 2x +100% at 13:15, hold +868%.
- Reading: the exits only decide how fast a coin flip bleeds. The written rules bleed slowest because the time stop ends most trades before theta and the spread do. If Trevor wants a change, the one with support is "2x resting take-profit only when VIX >= 20" (where R2 is -5% vs -18% elsewhere, V1D), but the sample is 1,092 trades across 7 years and the gain is small.

### 4.2 VIX band 16-18 (`p1_exits.py` band table): removed, see 4.1. Under V1D, ATM written rules by band OOS: <16 -6.9%, 16-18 -8.1%, 18-20 -0.3%, 20-25 -6.9%, 25+ -4.6%. The present STAND_DOWN below 18 (ROUTER) costs nothing; the PLAN.md STRICT band should be deleted so the two files agree.

### 4.3 Volatility risk premium timing (`vrp_regimes.py`, SPY 2007-26; 0DTE open->close and 5-session straddles; 444 subgroup tests + 6 walk-forwards)
- Always-long 0DTE ATM straddle OOS: MKT +31% (t 12), **V1D -17% (t -13)**, VRP -28%. 5-session: -20% (MKT) / -12% (V1D) / -23% (VRP).
- Subgroups (V1D, 0DTE, OOS; all 37 OOS subgroup means are below zero except the two below): VIX 25-30 **+4.2%** (n=199, t 0.7), VIX 30+ **+3.4%** (n=149, t 0.5), VIX9D/VIX top tercile -1.4% (n=627), VVIX/VIX bottom tercile -0.7%, RV5/VIX top tercile -6%, 5-day VIX change top tercile -4%, |gap| top tercile -7%; worst: VIX9D/VIX bottom tercile -30%, VIX 13-16 -27%, Monday -29%, pre-holiday -29%.
- Walk-forward HistGB (yearly refit from 2013, 19 features), V1D: p>0.5 n=305 +4.8% (t 0.9); p>0.6 n=138 +13.5% (t 1.5); by year 2019-26: 0%, +2%, +56%, +18%, +17%, -33%, +90%, -13%. AUC 0.62 for "straddle profitable". Under VRP: ~0. Not deployable; the term-structure tercile rule captures most of what it knows.

### 4.4 Cross-asset lead-lag (`crossasset.py`)
- Daily panel 2010-26 (ok sessions, 28 features): quintile spreads of the 09:35->close move, OOS 2019+: best |spread| 24 bp (spy_r1, t -2.5, reversal) and 20 bp (KOSPI, t -2.0); 0 of 56 OOS tests pass BH (q=0.10). Spearman |rho| <= 0.06 everywhere. Asia same-day closes (Nikkei, HSI, Shanghai, KOSPI, ASX): -8 to -20 bp spreads OOS, all t > -2.
- Walk-forward direction models (logit C=0.1, HistGB depth 3; refit yearly from 2013; 1,688 OOS days): AUC 0.504 / 0.51; accuracy 51-53% vs 53.5% base up-rate; confident subsets no better. ATM 0DTE in the predicted direction: +26-33% at MKT, -14..-18% at VRP (V1D ~ -3%).
- Hourly "true overnight" panel (17:00 ET -> 09:00 ET, 2024-05..2026-10, 591 days): ES -> SPY open->close tercile spread -16 bp (t -1.8), NQ -> QQQ -17 bp (t -1.4), crude -13 bp (t -1.5), EUR +14..+20 bp (t 1.6-1.8), gold/ZN/JPY/BTC ~0. A first version using the 09:00-labelled bar (which closes at 10:00) gave +55 bp, t 4.7: a leak, now documented in `LEARNINGS.md`.
- |feature| -> realized/implied: top-quintile gaps in HYG, TLT, QQQ, SPY raise the ratio to 1.5-1.7x (MKT) vs 1.2-1.25x bottom quintile; this is the same effect as 4.5 and feeds idea 1.

### 4.5 Overnight, 1DTE and VIX1D gap days (`overnight.py`)
- SPY 2007-26: overnight +4.6%/yr (t 1.7), intraday +3.0% (t 0.85); QQQ overnight +9.3% (t 3.1) vs +4.1%. OOS by VIX band: the overnight premium is strongest at VIX < 16 (SPY +3.6 bp/night, t 2.1; QQQ +6.0, t 2.5).
- 1DTE ATM call bought 15:55, sold 09:35 (one night of theta vs the overnight drift): SPY -2.1% (t -1.2) V1D / -7% VRP; QQQ +5.2% (t 2.2) V1D / -2.5% VRP, premium 0.43-0.49% of spot. Puts -13..-19%. Verdict: the overnight premium exists but a 1DTE call pays about all of it in theta.
- VIX1D era gap days (n=875): realized |open->close| / VIX1D-implied intraday move = 1.085 overall; by |SPY gap| quintile 1.04, 1.10, 1.05, 1.08, **1.16** (q5 t vs 1.0 = 2.1); by |TLT gap| q4 1.20, q5 1.18 (t 2.4, 2.3); by |HYG gap| q5 1.15 (t 2.1). VIX1D itself drops ~22-26% at the open on every quintile, so the market does not reprice gap days more than quiet days.

### 4.6 Prediction-market shocks (`pm_shocks.py`, `pm_shocks_decluster.py`)
- 690 markets, 205k prices, 2025-07..2026-10. Events: 1,771 (>= 5 pt / 60 min), 833 (8 pt), 512 (10 pt); only 100 / 61 / 42 inside RTH.
- Signed (risk-off impulse) results, raw: Iran -> CL +38 bp 1h (t 3.2), +82 bp 24h (t 4.2, n=448); QQQ -12 bp 1h (t 2.2), -21 bp 24h (t 3.4); 12 of 246 tests pass BH, all in this family plus Fed-odds -> VIX.
- De-clustered (one event per 60-min bucket, n=226 at 5 pt / 144 at 8 pt): CL +38 bp 1h (t 2.4), +37 bp 4h (t 2.1), **+86 bp 24h (t 3.4, 58% hit)**; QQQ +3 / +3 / +11 bp (t 0.5 / 0.4 / 1.3); SPY ~0. By year: 2025 n=29 -29 bp (t -1.2); 2026 n=197 +103 bp (t 3.6). At 8 pt: CL +64 bp 24h (t 2.2).
- Hour-before returns ~0 and 1h cross-correlations |rho| < 0.03 for the 12 most-sampled markets: the odds are not lagging the tape at hourly resolution.
- Option economics (approximate): crude daily sd ~2.5% (OVX ~40), so +86 bp is 0.35 sd. A 1-day-ahead ATM USO option at a 10% VRP and 5% spread: EV ~ +15-20% per event if the 2026 effect persists, ~ -15% if 2025 is the truth. Most events are overnight, so the entry is the next open and the first hour's +38 bp is partly lost.

### 4.7 Crypto (`crypto_funding.py`)
- Funding (Deribit BTC-PERPETUAL, 2019-04..2026-10, 65k hourly points): contrarian quintile spreads IS +30..+256 bp (t 0.7-1.7), OOS 2023-07+ -23..-128 bp (t -1.1..-2.4). Sign flip: no signal. (BTC itself is RESEARCH-ONLY anyway.)
- BTC overnight -> crypto equities (6 names, 2021-26): after the leak fix, tercile spreads -53..+78 bp, t -1.2..+1.4. Weekend -> Monday: t -1.1..+0.7 (n=85). Monday |move| larger only for MARA (+99 bp, t 2.5).
- Residual gap fade (stock gap minus 1.5 x BTC overnight, -> 09:35->close): MARA -207 bp (t -3.6, BH), RIOT -136 (t -2.5), MSTR -115 (t -2.0), CLSK -72, HOOD -60, COIN -15. Shares-only lead; refines universe.md's "miners fill gaps".
- BTC weekend reversal: Spearman(weekend move, next 1d) -0.19, (next 2d) -0.23, n=214; weekend |move| 242 bp vs weekday 170 bp. Untested as an IBIT option (1-week ATM ~$256/contract).

### 4.8 Trend / carry (`trend_carry.py`, 13 ETFs + 8 futures, 2007-26, monthly)
- 0 of 84 OOS instrument-signal tests pass BH. Pooled across ETFs, OOS: 1-month +34 bp/month (t 0.25), 3-month +31 (t 0.6), 6-1 +24 (t 0.3), 12-1 +7 (t 0.3); 1-month ATM option in the signal direction +1..+4% (OOS), -2..-11% (IS). Carry not tested (no foreign rate series fetched).

## 5. What failed and why
1. **The one-week calibration.** Fitting the 0DTE price level to Oct 8-16 made every long-option idea look +20-50% and would have reversed the exit-rule conclusion. The fix was an external anchor (VIX1D) and reporting three levels. Lesson recorded.
2. **Start-labelled hourly bars** (yfinance, Coinbase): two false discoveries at t 4.7 and 3.8. Fixed; rule added.
3. **Clustered events.** 448 "Iran events" were ~226 headlines; the QQQ/SPY effects were an artefact of counting each headline five times. De-clustering is now part of the script.
4. **Strike grids in dollars** at 2007 price levels made "ATM" options 0.4% off and OTM strikes 3 sd away; fixed with a spot-relative grid and a premium floor.
5. **Flat-vol BS for wings** overstates OTM returns; the real smile is now applied.
6. **Things not done:** FX carry (no FRED foreign rates fetched), earnings vol (no option history), gamma/OI positioning (no OI history), LLM news sentiment (no timestamped corpus), MES/ES options (broker support unknown).

## 6. What is tradeable now under the hard rule
- XSP 0DTE ATM straddle on big-gap mornings (idea 1): paper 20 signals, then probe-size. Entry 09:35 when |SPY gap| >= 0.7% or |TLT gap| >= 0.6% or |HYG gap| >= 0.4% (top quintiles), hold to 15:45, no stop (a straddle's stop is its premium). Expect +5..+15%/trade, 1-2 signals a week.
- USO weekly OTM call/put on a de-clustered Iran/oil odds shock (idea 2): P5 moves from WATCH to probe (1 contract, <= $40 premium) once the 1-minute odds feed catches an RTH event; grade against the next-day CL move.
- Term-structure gate (idea 3) on every long-premium playbook: VIX9D/VIX bottom tercile (< ~0.90) = no new long premium.
- Keep P1 as written (exits unchanged, OTM singles banned, 18+ gate), accept that it is ~-6%/trade until a signal with direction is found.

## 7. Proposals for PLAN.md / ROUTER.md (for Trevor; nothing edited)
1. PLAN.md volatility gate: delete the 16-18 "STRICT" band; nothing 0DTE below 18 (ROUTER already says this). Evidence 4.2.
2. ROUTER.md P1: keep the written exits; drop the "resting 2x after every fill" universal rule for P1 (it is -18% vs -6%), keep it for P8/P11 only if VIX >= 20. Never 0.10-0.20-delta singles (already re-tooled to ATM; make it explicit).
3. New gate for all playbooks: no long premium when VIX9D/VIX is in its bottom tercile of the last 2 years (today's threshold ~0.90), and size up only at VIX >= 25.
4. New WATCH playbook P15 "gap-day straddle" (idea 1, XSP), with the 20-signal paper rule.
5. P5 upgrade: trigger = de-clustered >= 5-pt / 60-min move in any Iran/Hormuz/oil market (not 10 pt); instrument USO weekly; probe-size; grade on CL 24h. Keep it WATCH until 20 graded RTH events.
6. Engine: replace `edge.py`'s pool-based level with the VIX1D-anchored level until 60 live sessions of `option_snaps` exist, then refit `k_spy` and the level from live data. Log VIX1D at 09:35 daily (free from Yahoo `^VIX1D`).
7. Data hygiene rule (CYCLE/LEARNINGS): any hourly bar from yfinance/Coinbase is labelled by START time; use the previous bar for anything "known at 09:30".

## 8. Data-acquisition wishlist
Free, do now: `^VIX1D` daily (done, `data/weekend_raw`), keep `option_snaps` + `vol_obs` running (60 sessions = the pricing anchor); FRED foreign short rates for FX carry (JPY/EUR/GBP/AUD 3-month); CBOE VIX1D intraday via `cdn.cboe.com` (not fetched; would give the 09:35 0DTE level back to 2022); Polymarket 1-minute feed for all iran/oil markets (now top-12 only); Deribit DVOL (BTC implied vol) for IBIT straddles; Coinbase/Kraken for ETH/SOL overnight (Binance/Bybit are geo-blocked from this machine: 451/403; Stooq is behind a JS wall).
Paid (approximate, confirm before buying): ThetaData options history ($40-80/mo; 0DTE SPX/SPY quotes back to 2012: settles the price level and lets P1 be back-tested on real option paths); Polygon options Advanced (~$199/mo, full OPRA trades/quotes, 2+ years); ORATS (~$100/mo, implied vs realized by earnings date for P9); Databento OPRA (pay-as-you-go, cents per MB, best for a one-off 0DTE pull); CBOE DataShop SPX/XSP EOD (hundreds of dollars per year of data); SpotGamma / OptionMetrics for dealer positioning and institutional IV surfaces ($100/mo, $10k+/yr). The single highest-value purchase is 0DTE SPY/SPX quote history (ThetaData or Databento): every 0DTE conclusion in this repo rests on a level we have measured for 8 days.

## 9. Methods and caveats
- Costs: option spread 4% (ATM) / 10% (OTM) with 50% of the half-spread paid each way (fill study: 37%); straddle 2-3% round trip; ETF options 6%; no commissions (Robinhood) but no fees modelled either.
- Time zones: all intraday work in America/New_York; the 1-minute matrices were checked against market.db at 0.0 bp (intraday.md); hourly bars are start-labelled (see 5.2).
- Splits: IS 2007/2010-2018, OOS 2019+ (P1, cross-asset, VRP, overnight, trend); crypto funding OOS 2023-07+; crypto equities OOS 2024-07+; prediction markets have no IS (15 months total). Walk-forward models refit yearly on expanding windows.
- Multiple testing: ~1,900 tests; BH at q=0.10 inside each family; the three positive findings in section 1 are reported with their family sizes (875-day quintiles: 15 cells; PM: 246 tests, 12 survivors in one family, ~226 effective events, one regime; VRP: 444 subgroups, 0 positive survivors). Expect roughly half of what looks like +10% to be noise.
- 0DTE expiries existed daily only from 2022 (Mon/Wed/Fri from 2016); earlier years are "as if".
- Not shown: the 1-minute set ends 2026-03-31; Apr-Oct 2026 is covered only by market.db 5-minute (Jul+) and 1-minute (Sep 29+) bars and the 8 live option days.

## 10. Files
- `research/weekend/common.py` (loaders, k_spy, smile, BS, stats), `fetch_yf.py` (64 series), `p1_exits.py`, `vrp_regimes.py`, `crossasset.py`, `overnight.py`, `pm_shocks.py`, `pm_shocks_decluster.py`, `crypto_funding.py`, `trend_carry.py`, `oct16_replay.py`; outputs `research/weekend/out/*.json|log` (`p1_trades.pkl` has every simulated trade).
- Raw data (gitignored): `data/weekend_raw/` (yfinance daily/hourly, Deribit/Kraken/OKX funding, Coinbase BTC 1h, `^VIX1D`).
