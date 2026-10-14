# Does any index, sector, commodity or single stock fit the models better than SPY?

2026-10-14. Owner's question: "SPY is the most traded and speculated piece. Expand the concept to different indexes, or maybe an even more hidden gem: individual stocks. Do any individual stocks hold up to the model better than SPY?"

- Code: `bot/research_universe.py` (`fetch | chains | run | all`). `run` takes about 30 seconds.
- Cache: `data/research_universe_cache.pkl` (gitignored; checked with `git check-ignore`). It holds the bars, earnings dates, today's option chains and all result tables (`results.run`, `results.trades`).
- Builds on `direction.md`, which found that only the oversold dip-buy on SPY/QQQ survives. Nothing here repeats that study's SPY/QQQ indicator scan.

## Verdict (short)

1. **No individual stock is a "hidden gem" for the dip-buy, and the evidence that would be needed is absent.**
   - Ticker-level dip-buy performance does not persist from 2010–18 to 2019–26. The Spearman correlation of in-sample vs out-of-sample excess across ~260 tickers is 0.01–0.09 for the four oversold triggers, and none is significant.
   - The top decile picked in-sample does no better out of sample than the whole universe: RSI2 −8.5% vs −4.9% EV per trade; 3-down −1.9% vs −4.1%.
   - Across 3,186 ticker×model tests there were 114 nominal underlying hits, against 159 expected by chance. **BH passes 1** (PBR PEAD, n=8, in-sample sign opposite; noise).
   - On option P&L, 67 tests pass BH, and **every one of them is a significant loser.**
2. **The oversold effect itself is real and universal on the underlying, but too small to pay for single-stock options.**
   - Pooled out of sample (2019+), 299 tickers: RSI2<10 → +0.2% excess over the ticker's own random 5-day return (week-clustered t 3.6; in-sample t 3.6). 3-down: +0.1% (t 2.6 / 3.3).
   - It shows up in every asset class except volatility ETPs and macro (rates, commodities, FX).
   - As a 21-day ATM call, the same trades return **−5% EV (RSI2) and −5% (3-down) on single stocks and ETFs pooled**, against **+15% and +9% on SPY**.
   - Index ETFs as a class come in around +2%. QQQ, RSP and IWM are flat to negative on RSI2.
3. **SPY (via XSP) is still the best vehicle.** Indexes have the smallest options spreads (≈2%) and the cleanest mean reversion. Single names add idiosyncratic noise, which you pay for in IV, plus 10–25% quoted spreads on cheap contracts.
4. **Overbought → put:** the underlying does mean-revert. Overbought names lag their own drift by +0.2% per 5 days (t 3.1 OOS, 5.3 IS). Even so, puts lose in every class (pooled −9%, SPY −18%).
   - The exception is VXX/UVXY puts (+7%), which is structural decay plus post-spike reversion. Real IV and borrow on those are extreme, so do not trade them.
5. **Trend, PEAD and ticker-specific gap rules are dead out of sample.**
   - The one **new lead** is *gap fill in crypto-linked names* (MARA, RIOT, CLSK, COIN, MSTR, HOOD): **+2.3% per event open→close, hit rate 64%, t 3.0, n=305, positive in 6 of 8 years.**
   - It was spotted after the fact, executes at the opening print, and has no clean option implementation. Paper-test it on shares; do not trade it.
6. **Affordability works against single names.** 43 of 254 optionable tickers have an ATM ~23-day call with ask ≤ $85 today. Their pooled out-of-sample dip-buy is **−9% EV**, worse than the universe, because cheap contracts carry 10–25% quoted spreads (tick size). The affordable SPY exposure is still XSP (≈$84–123 for 14–30d ATM; see `direction.md`).

**Recommendation:** keep the dip-buy on **XSP only**. Do not add single stocks or sector ETFs to the bot. Do not add an "affordable cheap-stock" sleeve either: the data say it is worse, not better. Two things are worth paper-tracking without trading: crypto-miner gap fill (shares), and mean-reverting ETFs as a secondary dip-buy list (rule 4 under Recommendations).

## Method

- **Universe.** 305 requested, **299 with data**.
  - 6 index, 12 international, 30 sector/industry, 14 macro (GLD SLV USO UNG TLT IEF HYG LQD UUP FXE FXY DBA DBC EMB) and 2 vol (VXX UVXY) ETFs.
  - 34 mega-caps, 49 retail favorites (PLTR COIN MSTR SOFI GME AMC MARA …), and 152 large caps across sectors, including fallen names (INTC WBA→missing, BA PFE T VZ MMM CCL AAL KSS M NKE BABA LUMN CHGG BYND PTON VFC NWL XRX …).
  - Daily yfinance bars from 2007. Earnings dates come from yfinance (235/235 stocks).
- **Periods.** In-sample 2010-01 to 2018-12. **Out-of-sample 2019-01 to 2026-10-13.** Ticker selection and gap direction are learned in-sample and frozen.
- **Models.** Signal at the close, entry at the close; positions per ticker never overlap.

  | model | trigger | structure |
  |---|---|---|
  | dip_rsi2 / dip_3down / dip_bb / dip_atr | RSI(2)<10 / 3+ down closes / close < 20d lower BB / 1-day drop > 2×ATR14 | 21d ATM call, hold 5 |
  | dip_vix / dip_vixts | market VIX>25 / VIX/VIX3M>1 | 30d ATM call, hold 10 |
  | ob_put | RSI(2)>90 | 21d ATM put, hold 5 |
  | trend_call / trend_put | above SMA200 and 12-1m momentum>0 (or both negative), checked every 20 sessions | 30d ATM call/put, hold 20 |
  | gap | \|overnight gap\| > 1.5 daily σ; fill vs continue learned in-sample | open→close; 7d ATM option |
  | pead | earnings reaction \|excess vs SPY\| > max(2%, 1.5σ) | 14d ATM in the reaction direction, hold 5 |

- **Excess.** Every trade is measured against **the same ticker's unconditional same-structure return in the same period** (entered every day). A dip-buy on a 10× stock only scores if its dips beat its random days. SPY's row is the benchmark.
- **Option pricing.** Black-Scholes with sticky-moneyness skew 3 and an IV floor of 8%.
  - **Primary IV = RV20 × clip(0.9·VIX / RV20_SPY, 0.8, 2.5)**: each ticker's realized vol scaled by the market's live implied/realized ratio. For SPY this reproduces `direction.md`'s 0.9×VIX.
  - Why not a flat k×RV20: SPY's implied/realized is 1.18 on a median day but **1.35 on RSI2<10 days**. A flat k underprices exactly the dip entries and inflates dip-buy EV by 5–8 points.
  - Sensitivity: flat k = 1.1 / 1.2 / 1.3.
  - Today's chains (yfinance, 254 tickers) show median IV/RV20 of 1.58 for index ETFs, 1.30–1.43 for stocks without earnings before expiry, and 1.62–1.69 with earnings inside the window.
- **Costs.** Round trip = 0.6 × **today's quoted ATM spread for that ticker**, with a 2% floor and 30% cap. Tickers without a chain use their class median.
  - Median quoted spreads: index 2%, macro 5%, mega 6–7%, large and retail 10–15%, sector and intl 16–19%. The tick size makes cheap contracts' percentage spreads wide.
- **Statistics.**
  - t-stats on non-overlapping trades.
  - Pooled results are **week-clustered** (trades averaged within each calendar week first), because 300 tickers dip on the same days.
  - BH across all ticker×model OOS tests with n≥8.

## 1. Pooled out-of-sample results by model and asset class (2019+, dynamic IV, real spreads)

EV = mean net return on premium per trade. "und x" = underlying excess over the ticker's unconditional same-horizon return. t = week-clustered.

| model | ALL tickers EV | und x (t) | index ETFs EV | mega EV | retail EV | large EV | sector EV | macro EV | **SPY EV** (n) |
|---|---|---|---|---|---|---|---|---|---|
| dip_rsi2 | −5.3% | +0.18% (3.6) | +2.0% | +0.7% | −7.8% | −4.6% | −9.8% | −7.3% | **+15.2%** (95) |
| dip_3down | −4.9% | +0.13% (2.6) | +0.2% | +2.6% | −8.1% | −4.4% | −9.2% | −6.0% | **+9.4%** (97) |
| dip_bb | −8.9% | −0.2% (3.0*) | −12.6% | +2.0% | −10.2% | −9.0% | −17.5% | −8.2% | +6.0% (46) |
| dip_atr | −15.0% | −0.5% (1.3) | −15.9% | −8.5% | −9.9% | −15.2% | −24.9% | −16.9% | +4.5% (26) |
| dip_vix | −0.7% | +1.2% (1.6) | +9.0% | +4.4% | +8.3% | −2.8% | −3.7% | −12.3% | **+10.5%** (52) |
| dip_vixts | −6.5% | +1.0% (1.0) | +11.4% | +5.2% | −0.6% | −9.7% | −5.6% | −16.0% | **+21.3%** (31) |
| ob_put | −8.7% | +0.2% (3.1) | −15.0% | −7.4% | −2.8% | −8.7% | −16.5% | −7.0% | −18.3% (153) |
| trend_call | −2.9% | −0.3% (−0.2) | +0.5% | +16.4% | +11.2% | −8.0% | −11.3% | −7.4% | +16.7% (75) |
| trend_put | −13.9% | −0.3% | −27.5% | −22.0% | −4.1% | −14.1% | −28.0% | −18.2% | −21.9% (11) |
| pead | −13.9% | 0.0% (−0.3) | | −7.6% | −16.5% | −14.6% | | | |
| gap (direction-only) | +0.8%† (t 2.4) | +0.1% (3.5) | −1.2% | +3.3% | +1.8% | +0.3% | +1.3% | +0.5% | −3.6% (66) |

\* The trade-weighted mean is negative while the week-clustered mean is positive: the March-2020 cluster dominates the trade count.

† Gap EV is the chosen side minus the same-day straddle average. Raw gap-option EV (+5%) is a gamma artifact of pricing a gap day with a calm-day IV.

Read-across:
- **Every dip trigger beats its own random-day baseline on the underlying, in every equity class, in both periods.** It is the most universal effect in the study.
- **But only SPY-like indexes turn it into positive option EV.** Single stocks pay more for IV relative to the tiny excess (+0.1–0.2% per 5 days against a 21d premium of ~4–6% of spot) and pay 3–8× the spread.
- Trend_call "wins" in mega/retail on raw EV (+16%/+11%) only because those names rose. **Excess over their own random-day calls is +2%/+1% and not significant.**
- Macro (TLT, GLD, USO, HYG …) never works for dip-buys: there is no mean reversion to harvest.
- In-sample (2010–18) the same pooled numbers were: RSI2 EV −7%, 3-down −5%, underlying t 3.6/3.3, ob_put underlying t 5.3. The **underlying effect replicated; the option loss replicated too.**

## 2. Ticker selection out of sample (the "gem by chance" test)

Rank tickers on 2010–18, take the top decile, then evaluate that same list on 2019–26.

| model | Spearman ρ IS→OOS (underlying excess) | p | top-decile OOS EV | all OOS EV | bottom-decile OOS EV |
|---|---|---|---|---|---|
| dip_rsi2 | 0.045 | 0.46 | −8.5% | −4.9% | −6.2% |
| dip_3down | 0.014 | 0.83 | −1.9% | −4.1% | +0.2% |
| dip_bb | 0.093 | 0.14 | −8.1% | −9.1% | −12.9% |
| dip_atr | 0.025 | 0.70 | −15.8% | −15.4% | −14.9% |
| dip_vix | −0.018 | 0.78 | −8.2% | −1.4% | +2.2% |
| dip_vixts | −0.101 | 0.10 | −8.6% | −6.6% | −7.4% |
| ob_put | 0.073 | 0.24 | −10.9% | −9.1% | −7.7% |
| trend_call | **0.201** | **0.001** | +2.0% | −3.6% | −7.8% |
| gap | 0.043 | 0.48 | +6.6% | +5.1% | +7.3% |
| pead | −0.135 | 0.07 | −20.7% | −13.2% | −13.1% |

- **Which tickers dip-buy well is not a stable property.** Past winners are no better than past losers.
- The only persistent ranking is trend (ρ 0.20): trending names keep trending. Even so, its top decile's option *excess* is −0.7%.
- Ranking on in-sample option excess instead of the t-stat gives the same picture.
- Sign persistence across all 2,693 ticker×model cells with n≥8 on both sides: P(OOS excess > 0 | IS > 0) = 48%, against 38% when IS ≤ 0. Most of that comes from some models being systematically better, not from ticker skill.

## 3. Ticker "character" (transferable insight)

The study measured variance ratio VR(5), VR(20), lag-1 autocorrelation, Hurst (from aggregated variance) and realized vol, all in-sample.
- **Character persists:** IS→OOS ρ = 0.46 for VR5, 0.34 for AC1, 0.32 for Hurst, 0.89 for realized vol. Weekly AC5 does not persist (−0.06).
- **Mean-reverting character predicts better dip-buy results out of sample** for three of the four stock-level triggers. Spearman of IS character vs OOS underlying excess:

  | | AC1 | VR5 | Hurst |
  |---|---|---|---|
  | dip_3down | | | −0.21 (p 0.001) |
  | dip_bb | −0.19 (p 0.002) | −0.21 (p 0.001) | |
  | dip_atr | −0.20 (p 0.001) | −0.21 (p 0.001) | |

  RSI2 shows no relation (ρ ≈ 0).
- **VIX-triggered dip-buys favor high-vol, high-beta names** (ρ with RV = +0.53). That is beta into a market rebound, not character.
- Practical size: picking the most mean-reverting decile (lowest IS VR5) improves dip_3down OOS option excess from −0.1% to +2.0% and EV from −4.1% to −2.7%.
  - That is a real tilt, but **it does not turn single-stock dip-buys positive.**
  - The decile: CLSK MARA BRK-B NKE AMT SNAP V MA CHGG DG TXN TMO CL MDT HL SPG MCD KHC EFA TLT TSM XLF UVXY SO WFC ADBE.
- Trend models show no character link (|ρ| ≤ 0.05).

## 4. Survivorship check

| dip_rsi2 OOS, grouped by the ticker's own 2019–26 buy-and-hold | tickers | EV | excess | und x |
|---|---|---|---|---|
| fell (CAGR<0) | 56 | −11.1% | −3.0% | +0.1% |
| rose 0–15%/yr | 145 | −5.4% | +0.2% | +0.2% |
| rose >15%/yr | 98 | −1.5% | −2.1% | +0.2% |

- **The excess over random days is the same in fallen and winning names.** The dip effect is not a survivorship artifact.
- **The raw option EV is survivorship:** today's winners make the dip-buy look ~10 points better than a fallen name.
- WBD, WOLF, QRVO and ET (plus fully delisted names like BBBY) have no yfinance data. The universe is still winner-tilted, which makes the negative single-stock verdict conservative.

## 5. Sensitivity

| dip OOS, all tickers | dyn IV (primary) | flat k=1.1 | k=1.2 | k=1.3 | excess at 14d / 21d / 30d tenor (dyn) |
|---|---|---|---|---|---|
| dip_rsi2 | −5.3% | +1.8% | −1.1% | −3.5% | −0.6 / −1.1 / −1.4% |
| dip_3down | −4.9% | +0.8% | −2.1% | −4.4% | −0.4 / −0.7 / −0.9% |
| dip_bb | −8.9% | +3.9% | +1.0% | −1.4% | −3.9 / −4.5 / −4.8% |

- Under the most generous IV assumption (k=1.1, below today's measured ratios) pooled single-name dip-buys reach about +2%: break-even, not an edge. Tenor does not matter.
- SPY's dip_rsi2 was **−4% EV in 2010–18 and +15% in 2019–26.** Even the benchmark depends on regime (see `direction.md`).

## 6. Affordable + edge candidates

**Affordable today** (yfinance chain, ATM call at the expiry nearest 21d within 14–30d, ask ≤ $85; 43 of 254): CGC PLUG TLRY NIO LCID OPEN AMC AAL LUMN VALE BB BAC HYG RIG SNAP PTON UNG NOK JETS CLSK RUN AG MARA SOFI F KGC HL CDE CCL IEF JD XLU FXI CLF GAP KWEB RIVN XLF T SLV LQD RIOT DKNG.

| affordable set, OOS pooled | EV | excess | und x (t) | vs SPY EV |
|---|---|---|---|---|
| dip_rsi2 | −8.8% | −3.1% | 0.0% (3.1) | +15.2% |
| dip_3down | −8.5% | −2.8% | 0.0% (2.2) | +9.4% |
| dip_vix | −1.2% | +0.3% | +1.6% (1.1) | +10.5% |
| gap (direction-only) | +2.9% | | +0.3% (3.2) | −3.6% |

Cells positive in **both** periods among affordable tickers: 53 of 271. P(OOS excess > 0 | IS > 0) = 50%, against 44% otherwise, so this is mostly chance. The best of them, all with in-sample t < 2 except the miners:

| ticker | model | ask | quoted spread | IS t | OOS t | OOS EV | comment |
|---|---|---|---|---|---|---|---|
| MARA / RIOT / CLSK | gap (fill) | $52 / $81 / $50 | 4% / 12% / 17% | 3.5 / 3.1 / 3.1 | 1.8 / 1.8 / 2.1 | +31% / +19% / +54% | see lead below; in-sample data are penny-stock years |
| F | dip_vix | $54 | 14% | 1.1 | 1.4 | +12.5% | 52 clustered entries ≈ 4 episodes |
| KWEB | dip_vix | $72 | 9% | 1.8 | 0.9 | +7.8% | same caveat |
| JD | dip_bb | $67 | 13% | 0.6 | 1.3 | +23% | n=37 |
| XLF | dip_3down | $75 | 10% | 1.7 | 0.1 | +2.1% | flat |
| RUN | dip_rsi2 | $50 | 15% | 1.4 | 1.6 | +7.4% | solar, high-vol |

None of these passes a correction or beats SPY's dip-buy. **The "cheap underlying + edge" gem does not exist in this data.** The cheap contracts are cheap because the stocks are low-priced and high-vol, and the spread then eats the small mean-reversion premium.

### Lead worth tracking: crypto-linked gap fill

- In-sample, MARA, RIOT and CLSK all learned *fade the gap*. COIN, MSTR and HOOD have no in-sample period, and they also faded out of sample.
- Pooled OOS, fading |gap| > 1.5σ from open to close: **+2.3% per event, hit rate 64%, week-clustered t 3.0, n=305.**
- By year:

  | year | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
  |---|---|---|---|---|---|---|---|---|
  | mean per event | +4.9% | −0.5% | +2.2% | +7.0% | +3.2% | +1.5% | +3.2% | −0.2% |

- Plausible mechanism: these names gap on overnight BTC moves and the open overshoots. That fits `news_trading.md`, where the STX/WDC lows printed at 09:25 and 60% reverted by 10:38.
- Caveats:
  - It was found by looking across 300 tickers.
  - The fill is measured from the official open print, which a retail order cannot reliably get.
  - Options at 09:30 have their widest spreads.
- Next step if pursued: replay with 5-minute bars (entry 09:35 and 09:45) and paper-trade 1 share. Do not trade options on it.

## Recommendations

1. **Answer to the owner: no.** No index, sector, commodity or individual stock holds up better than SPY in a way that survives out-of-sample selection.
   - The oversold mean-reversion effect is *everywhere* on the underlying (t ≈ 3.6 pooled, replicated across both periods and every equity class).
   - But it is a +0.1–0.2% nudge. Only SPY-class options (≈2% spreads, IV marked off VIX) are cheap enough for that nudge to show up as option profit.
2. **Keep the dip-buy on XSP; do not widen it to single names.** That includes the cheap ones: affordable names are *worse* (−9% EV OOS).
3. **Never buy puts for direction**; that now holds across 299 tickers. Overbought names do underperform (t 3.1), but long puts still lose everywhere except vol ETPs.
4. **Secondary-list idea (paper only):** if a second dip vehicle is wanted while XSP is flat, use **index-like, mean-reverting ETFs** (DIA, MDY, IWM on VIX triggers; XLF) at the VIX>25 / VIX/VIX3M>1 triggers.
   - Their OOS EV was +5% to +22% on n≈31–52 clustered entries (≈4–6 independent episodes).
   - Too few episodes to call an edge.
5. **Paper-track crypto-miner gap fill on shares** with intraday bars before any capital.
6. **Retired by this study:** single-stock PEAD (pooled −14%, underlying excess 0.0% OOS); trend/TSMOM calls and puts; ATR-shock dip-buys (−15%); ticker-selected dip lists.

## Caveats

- Option prices are modeled, not historical quotes. Spreads are today's quotes applied backward; spreads were wider before 2020 for most single names, which makes the history optimistic.
- The dynamic IV transfers the *market's* implied/realized ratio to each ticker. An idiosyncratic dip in a calm market (stock IV jumps, VIX doesn't) is therefore still underpriced in the model, which flatters single-stock dip-buys. The single-stock verdict is conservative.
- yfinance opens for thin names (and the pre-2017 penny-stock years of MARA, RIOT and CLSK) are noisy. The gap results inherit that.
- VIX-triggered results are pooled across tickers on the same ~50 dates, so their effective sample is the number of episodes, not trades.
- Universe and today's prices are survivorship-biased (see section 4). Earnings dates come from yfinance and may miss some early-2000s reports.
