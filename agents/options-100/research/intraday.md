# Can the first minutes or hours of the session predict the rest of the day?

2026-10-14. Owner's question: "Can we predict direction by the first few trading hours or minutes of the day? Do certain times predict later movement if no major news upset happens midday?"

Code: `bot/research_intraday.py` (`fetch_hf | fetch_yf | check | build | tests | options | all`).
- `build`, `tests` and `options` run in about 2 minutes.
- Results: `data/research_intraday_results.json` (all tests, integrity, option economics) and `data/research_intraday_trades.pkl` (OOS trades per test).
- Caches: `data/research_intraday_hf/` (1-min bars, 647 MB), `data/research_intraday_yf/`, `data/research_intraday_sessions.pkl`.

## Verdict (short)

1. **No timing signal survives at a tradable 0DTE scale.**
   - 323 out-of-sample tests produced 27 nominal p<0.05 hits; about 16 are expected by chance.
   - Benjamini–Hochberg at q=0.10 passes 3 tests:
     - two are the same 5-minute micro-reversal (+0.0014% per 5 minutes; options EV −2.3% per trade);
     - one is an ex-post "no shock happened" subset that you cannot know at entry.
   - No morning, first-hour, ORB, VWAP, lunch or power-hour signal survives.
2. **Market intraday momentum (Gao et al.) was real and is now gone.**
   - In 2007–2018 the first half-hour predicted the last half-hour in SPY, QQQ and IWM, with in-sample t 3.1–4.0. That is a clean replication of the paper.
   - From 2019 to 2026-03 it is flat or reversed: SPY t −0.26, QQQ −0.52, IWM −2.0.
   - Conditioning on high volume, high VIX, big moves, event days or shock days does not revive it.
   - This confirms the earlier 726-session hourly test with 4,800 one-minute sessions. It is post-publication decay.
3. **"If no news upset happens midday, the morning direction holds" is weakly true but not usable.**
   - On days with no 4σ 5-minute shock after 10:30, the QQQ first-hour direction carries to the close: +0.071%, hit 55.5%, t 3.4, n=1,563.
   - You only know there was no shock after the fact.
   - The tradable version (exit on the first shock) keeps +0.051% (t 2.35, fails BH). Priced fairly, that is +1.4% EV per trade, which is nothing.
4. **The owner's crypto gap-fade lead partly replicates in the underlying, but not as an options edge.**
   - Fading a ≥3% gap from 09:35 to the close in MARA/RIOT/CLSK/COIN/MSTR/HOOD makes **+0.47% per event (hit 52.5%, t 2.0, n=2,263)**, not +2.3% / 64%.
   - It is negative in 2017–2020, positive in 2021–2025, and **−1.15% (t −2.4) in 2026 Q1**.
   - As 0DTE options it is +15% EV under fair vol and −15% under rich vol. As weeklies, which are what most of these names actually list, it is −2.4%.
   - **Verdict: undetermined.** It needs real gap-morning option quotes.
5. **The decision-relevant unknown is option pricing, not direction.**
   - The brief's pricing (0DTE IV = VIX on calendar minutes) gives about a 0.30% E|move| at VIX 15, which matches the repo's live `vol_obs`.
   - Under that pricing, realized moves are **1.28× implied at 10:30 and 1.65× at 15:30** (2019–2026; 1.09–1.45× at VIX<16). Always-call and always-put both come out **+27%**.
   - That contradicts direction.md's −28% for 0DTE, which priced 0DTE at VIX/√252×0.8 per session, about 2.3× more expensive.
   - Both cannot be right. Until real historical 0DTE quotes settle it, I rank signals under **fair** pricing: IV set so implied E|move| equals realized on those same days, which leaves only the value of the direction call.

**Bottom line:** the first minutes and hours of the day do not predict the rest of the day's direction well enough to pay for a 0DTE option. The best candidates are directionally right 55–60% of the time with +0.05–0.13% mean moves. That is +10–20% EV per trade under fair pricing, −10–20% under rich pricing, and negative median bankroll growth at 15–25% sizing either way. Nothing goes on a "ready when funded" list. Three things go on a paper-only watch list (see the end).

## Data

| source | what | span | integrity |
|---|---|---|---|
| HuggingFace `Rrishab/OHLCV-1m` (Finnhub-sourced monthly parquet, public, no key) | 1-min bars for 30 tickers: SPY QQQ(+QQQQ pre-2011) IWM DIA SMH NVDA TLT UUP USO GLD HYG, sector ETFs, mega-caps, MARA RIOT CLSK COIN MSTR HOOD | 2007-01-03 → 2026-03-31, **4,841 sessions** | see below |
| yfinance | 5m (60d), 1h (730d), 1d (max) for the same tickers | 2023-11 → 2026-10-14 | used for daily split/dividend fallback and recent tail |
| market.db | 1d bars (splits/dividends, VIX, 50dMA), 1h bars (alignment check), vol_obs (0DTE implied) | | |

Integrity checks (`check`):
- **Alignment.** The HF price at minute 60 matches market.db's 09:30 1h bar close to a **0.0 bp** median for SPY, QQQ and IWM (59 or 61 minutes gives 1.8–4.3 bp). Bars are labeled by their start, as assumed.
- **Closes and missing sessions.**
  - The HF 15:59 close is a 1.1–1.7 bp median from the official daily close.
  - 0 missing SPY/QQQ sessions against market.db (IWM is missing 3).
  - 14–34 half or short days are excluded.
- **Splits and dividends.** The HF data is unadjusted. Overnight gaps are corrected with market.db or yfinance daily bars. Split days are detected when HF and daily close-to-close returns disagree by more than 3%; for example, the NVDA 3:2 split on 2007-09-11 is fixed. Dividends are corrected with the adj_close/close ratio.
- **Ticker reuse.** COIN and HOOD were other companies before listing, so crypto names start at listing or their pivot date (MARA 2018, RIOT 2017-10, CLSK 2020-01, COIN 2021-04, MSTR 2020-08, HOOD 2021-07).
- **Thin series.** UUP is too thin before about 2015 (1,860 usable sessions), and HYG is sparse early on. Lead tests use only sessions where both series are complete.
- **Rejected source.** Dukascopy minute CFDs (a reputable Swiss bank, no account needed) were probed and rejected: 5–100 s per request with 503s, so 20k+ requests were impractical. Kaggle needs a login. FirstRateData's free sample is 2 weeks.
- **Trust.** The HF set is a personal mirror. It was trusted only after the alignment and close checks above, and parsed as parquet numbers only.

## Method

- **Split.** Train is 2007-01 → 2018-12 (about 2,990 sessions). Test (OOS) is 2019-01 → 2026-03 (about 1,795 sessions). The OOS period starts after Gao et al. (2018) was published.
- **Direction.** Each signal's direction ("as-is" vs "faded") is learned on train as the sign of mean(signal × return) and then frozen. The crypto fade and the ridge model use a fixed direction.
- **Statistics.**
  - "hit" is P(right | nonzero move). "mean" is the signed move of the underlying in % of price, from signal time to exit.
  - t is the plain t-stat. It is clustered by day for multi-window tests (H7).
  - BH and Bonferroni are applied across all 323 OOS p-values.
- **Entry and exit.**
  - ORB entry is the close of the first 1-minute bar that closes outside the range, before 12:00.
  - VWAP is cumulative typical price × volume.
  - A "shock" is a 5-minute move larger than 4σ of the prior 20 sessions' 5-minute returns.
  - Event days are FOMC, CPI (2015+ only) and NFP (approximated as the first Friday before 2015).
- **Options.**
  - Black-Scholes 0DTE: buy a 0.40Δ call or put at signal time and hold to the close (intrinsic value), or sell at the exit time with the same IV.
  - T = calendar minutes to 16:00 / 525,600.
  - Base σ: VIX for SPY, 1.2×VIX for QQQ, 1.3×VIX for IWM, 20-day realized vol for single names.
  - Three IV regimes:
    - **brief** = base × 1.0 (×1.2 in sensitivity);
    - **fair** = base × k, with k chosen so implied E|move| equals the realized mean |move| on that test's own trade days (direction-free, so no look-ahead on the signal);
    - **rich** = fair / 0.8, per the repo's 33-year evidence that realized ≈ 0.8× implied.
  - Spread cost: 2–4% of premium for ETFs and 4–8% for single names; the base uses the midpoint.
- **Bankroll.**
  - Each path draws one year of OOS trades at the observed frequency, with 5,000 paths.
  - Sizing is **whole contracts** with 15% or 25% of equity, priced at today's underlying level (SPY trades as XSP). A trade is skipped if one contract is unaffordable.
  - Starting capital: $170, $1,000 and $5,000. The fractional-sizing median is also reported.
  - **Min capital** = contract cost ÷ sizing fraction.

## Results by hypothesis

All "OOS" figures are 2019-01 → 2026-03. "IS" is 2007–2018.

### H1. Market intraday momentum (Gao, Han, Li & Zhou 2018): **doesn't work (decayed after publication)**

| signal → target | sym | IS hit / t | OOS n | OOS hit | OOS mean | OOS t | last 3y t |
|---|---|---|---|---|---|---|---|
| prev close→10:00 ⇒ last 30m | SPY | 52.6% / **3.26** | 1798 | 49.1% | −0.002% | −0.26 | −0.51 |
| | QQQ | 53.1% / **3.11** | 1792 | 49.7% | −0.005% | −0.52 | −1.18 |
| | IWM | 53.4% / **3.95** | 1785 | 48.3% | −0.018% | **−2.00** | −0.84 |
| ⇒ last hour | SPY | 52.3% / 3.20 | 1798 | 49.9% | +0.002% | 0.18 | 0.20 |
| 12th half-hour (15:00–15:30) ⇒ last 30m | SPY | 50.2% / 1.55 | 1782 | 50.7% | +0.009% | 1.13 | −0.55 |
| first & 12th agree ⇒ last 30m | SPY | 52.8% / 3.29 | 916 | 49.9% | +0.007% | 0.57 | −0.68 |
| … high-volume open (top tercile) | SPY | 54.8% / 3.33 | 583 | 47.7% | −0.020% | −1.00 | |
| … high-VIX tercile | SPY | 54.8% / 2.80 | 677 | 47.3% | −0.002% | −0.12 | |
| … |first half-hour| top tercile | SPY | 57.3% / **3.99** | 667 | 49.2% | −0.015% | −0.82 | −1.49 |
| … FOMC/CPI/NFP days | SPY | 53.6% / 0.83 | 211 | 47.9% | −0.024% | −0.98 | |
| … shock days | SPY | 54.9% / 2.00 | 381 | 45.4% | −0.028% | −1.00 | |

All 27 H1 variants (3 ETFs × 9) have OOS |t| ≤ 2.0, and the only "significant" one has the reversed sign. The paper's conditioning (volume, volatility, news) was strongest in-sample and weakest out of sample.

### H2. Opening-range breakout, gap-and-go vs fill: **doesn't work**

| signal | IS t | OOS n | OOS hit | OOS mean | OOS t |
|---|---|---|---|---|---|
| SPY ORB-5 ⇒ close | 1.48 | 1799 | 51.9% | +0.014% | 0.70 |
| SPY ORB-15 (faded) | 0.18 | 1785 | 47.5% | −0.016% | −0.77 |
| SPY ORB-30 (faded) | 0.01 | 1732 | 47.7% | −0.008% | −0.41 |
| SPY ORB-5 agrees with gap | **3.41** | 851 | 52.6% | +0.013% | 0.44 |
| SPY ORB-15 agrees with gap | 2.93 | 904 | 52.8% | +0.009% | 0.32 |
| SPY gap 0.1–0.3%: open ⇒ close (go) | 0.53 | 521 | 46.6% | −0.010% | −0.35 |
| SPY gap 0.3–0.6% (go) | 0.12 | 490 | 50.6% | −0.051% | −1.35 |
| SPY gap 0.6–1.0%, confirmed by 10:00 ⇒ close | **3.33** | 141 | 55.3% | +0.032% | 0.49 |
| SPY gap ≥1.0%, confirmed by 10:00 ⇒ close | **3.02** | 110 | 59.1% | +0.052% | 0.41 |
| SPY gap ≥1.0%, unfilled by 10:00 ⇒ close | 2.39 | 200 | 55.8% | +0.080% | 0.82 |

The QQQ and IWM ORB and gap tables look the same: OOS t ranges from −1.34 to +1.81. Large confirmed gaps keep the right sign (55–59% hit), but the mean has collapsed from +0.24–0.43% in-sample to +0.03–0.08%. That is "gap-and-go" decay, not a fill edge. Small gaps neither go nor fill reliably.

### H3. First hour ⇒ rest of day, conditioned: **doesn't work broadly; low-VIX continuation is undetermined**

| signal (open→10:30 ⇒ 10:30→close) | IS t | OOS n | OOS hit | OOS mean | OOS t | last 3y t |
|---|---|---|---|---|---|---|
| SPY unconditional | 1.16 | 1793 | 53.1% | +0.016% | 0.84 | 1.68 |
| QQQ unconditional | 0.52 | 1791 | 54.6% | +0.046% | 1.98 | 2.31 |
| SPY first hour agrees with gap | **3.55** | 877 | 53.4% | +0.006% | 0.25 | −0.40 |
| SPY range/ATR top tercile | 0.09 | 601 | 51.3% | −0.023% | −0.59 | |
| SPY **low-VIX tercile** | 0.35 | 310 | 55.7% | +0.059% | **2.67** | 2.36 |
| QQQ **low-VIX tercile** | 0.12 | 313 | 55.0% | +0.082% | **2.72** | 1.90 |
| SPY high-VIX tercile | 1.04 | 675 | 53.8% | +0.005% | 0.11 | |
| QQQ Friday | 0.46 | 353 | 60.2% | +0.129% | 2.52 | 1.23 |
| SPY above / below 50dMA | 0.45 / 1.08 | 1292 / 501 | 52.3 / 55.3% | +0.021 / +0.002% | 1.30 / 0.04 | |
| SPY first 5 / 15 / 30 / 90 / 120 min ⇒ rest | 3.04 / 1.13 / 1.45 / 0.93 / 2.36 | ~1790 | 50–52% | −0.009…+0.025% | −0.47…1.46 | |
| SPY walk-forward ridge, 10 morning features | — | 1799 | 51.1% | +0.007% | 0.38 | −0.94 |

- Gap/first-hour agreement, range/ATR, day of week and trend do not condition the first hour into a signal.
- In low-VIX regimes, both SPY and QQQ first-hour moves continue OOS (t 2.7). It is consistent across the two ETFs and the last 3 years, but it was absent in-sample and fails BH. It is the best paper-trade candidate in this sprint.

### H4. VWAP: **doesn't work**

| signal | IS t | OOS n | OOS hit | OOS mean | OOS t |
|---|---|---|---|---|---|
| SPY above/below VWAP at 10:30 (faded) | 0.19 | 1799 | 47.4% | −0.027% | −1.44 |
| SPY vs VWAP at 11:30 | **3.23** | 1799 | 51.8% | +0.012% | 0.72 |
| SPY vs VWAP at 13:00, far from VWAP | 2.98 | 620 | 53.4% | +0.015% | 0.45 |
| SPY first VWAP reclaim/loss 10:30–13:00 | 0.95 | 1157 | 49.1% | +0.023% | 1.07 |

The in-sample VWAP effects at 11:30 and 13:00 (t 2.5–3.2) did not carry out of sample.

### H5. Lunch reversal and power hour (extending the earlier 14.4% / 15.2% count): **doesn't work**

| signal | IS t | OOS n | OOS hit | OOS mean | OOS t |
|---|---|---|---|---|---|
| SPY open→11:30 ⇒ 11:30–13:30 | 1.41 | 1798 | 52.0% | +0.006% | 0.66 |
| SPY lunch move 11:30–13:30 ⇒ 13:30–close | 2.33 | 1793 | 51.3% | +0.006% | 0.47 |
| SPY open→15:00 ⇒ 15:00–close | 1.60 | 1795 | 50.9% | +0.008% | 0.78 |
| SPY 14:00–15:00 ⇒ power hour | 2.27 | 1793 | 50.0% | −0.006% | −0.63 |
| … |x| top tercile | 1.87 | 666 | 52.4% | +0.019% | 0.88 |
| … high VIX / low VIX | 1.28 / 0.26 | 678 / 312 | 53.2 / 52.1% | +0.010 / +0.011% | 0.42 / 1.04 |
| … quiet (no event, no shock before 15:00) | 1.90 | 1290 | 52.8% | +0.010% | 1.07 |
| … gap agrees | **4.00** | 872 | 50.6% | +0.006% | 0.39 |
| IWM open→15:00 in uptrend | 0.61 | 1289 | 52.7% | +0.029% | 2.76 (fails BH) |

### H6. "No major news midday" filter: **weakly true, not tradable**

| signal ⇒ close | non-event (ex-ante) t | event days t | no shock after signal (EX-POST) | exit on first shock (tradable) |
|---|---|---|---|---|
| SPY first hour (10:30) | 0.67 | −0.56 | +0.036%, hit 53.7%, t 2.24 | +0.021%, t 1.23 |
| QQQ first hour (10:30) | 2.09 | | **+0.071%, hit 55.5%, t 3.40 (passes BH)** | +0.051%, t 2.35 |
| SPY VWAP 10:30 | −1.36 | 0.49 | −2.13 (faded) | −1.18 |
| SPY first half-hour (10:00) | 0.68 | 0.99 | +0.028%, t 1.56 | 0.24 |

- Calendar events (FOMC/CPI/NFP) do not separate good days from bad days for these signals.
- The real separator is an *unscheduled* shock *after* entry, which you cannot know in advance.
- The owner's intuition ("if nothing upsets it, the morning trend holds") is directionally right for QQQ but worth only about 0.05–0.07% of price, versus an E|move| of about 0.40% priced into the option.

### H7. Cross-asset leads (non-overlapping 5/15/30-minute windows, 10:00–15:30): **doesn't work at a tradable scale**

| lead (last k min) ⇒ SPY next k min | OOS n | hit | mean | t | note |
|---|---|---|---|---|---|
| SPY 5m (faded = reversal) | 114,978 | 51.0% | +0.0014% | **5.32** | Bonferroni pass; IS t 9.0 |
| QQQ 5m (faded) | 114,578 | 50.8% | +0.0012% | **4.25** | Bonferroni pass; the same reversal |
| SMH 5m (faded) | 114,427 | 50.7% | +0.0008% | 2.98 | |
| TLT 5m (as-is: bonds up ⇒ SPY up) | 109,954 | 50.4% | +0.0008% | 2.78 | last 3y t 2.65; fails BH |
| QQQ−SPY / SMH−SPY / NVDA−SPY 5m | ~116k | 49.7–50.0% | ~0 | 0.3–1.0 | tech does not lead SPY |
| SMH−SPY 15m | 37,728 | 50.4% | +0.002% | 2.78 | last 3y −0.61 |
| UUP / USO / HYG / GLD (5–30m) | 5k–110k | 49.8–50.9% | ~0 | \|t\| ≤ 1.8 | |
| any lead at 30m | ~17.8k | 49.9–50.8% | | \|t\| ≤ 1.8 | |

The only statistically robust intraday effect is a 5-minute mean reversion worth about 0.1 bp. Bought as 0DTE options, it loses **−2.3% per trade** (t −26). QQQ, semis and NVDA do not lead SPY at 5–30 minutes once SPY's own move is netted out, and neither do rates, the dollar or oil.

### H8. Relative strength, QQQ vs IWM first hour: **undetermined (spread), doesn't work (direction)**

| signal | IS t | OOS n | OOS hit | OOS mean | OOS t |
|---|---|---|---|---|---|
| (QQQ−IWM) first hour ⇒ (QQQ−IWM) 10:30–close | 1.94 | 1786 | 52.6% | +0.016% | 1.15 |
| … top tercile of spread | 0.94 | 983 | 54.6% | +0.044% | 2.19 (fails BH) |
| ⇒ QQQ / SPY / IWM direction | 0.74 / 0.28 / 0.35 | 1786 | 50.8–51.4% | | 1.42 / 1.16 / −0.71 |

Leadership persists slightly as a spread, which you cannot express with one long option. It says nothing about the index's direction.

### Owner lead: crypto-linked names fade their opening gap: **undetermined, leaning no for options**

Signed move = fade direction, entry at the given time, exit at the 15:59 close. Pooled over MARA, RIOT, CLSK, COIN, MSTR and HOOD.

| gap | entry | OOS n | hit | mean | t | last 3y t |
|---|---|---|---|---|---|---|
| ≥3% | open print | 2,270 | 53.3% | +0.51% | 2.18 | 1.94 |
| ≥3% | **09:35** | 2,270 | 52.7% | **+0.46%** | **2.04** | 2.06 |
| ≥3% | 10:00 | 2,270 | 52.4% | +0.21% | 1.09 | 1.56 |
| ≥3% | 10:30 | 2,270 | 52.1% | +0.18% | 1.05 | 1.44 |
| ≥5% | 09:35 | 979 | 54.8% | +0.51% | 1.32 | 1.89 |
| by name, ≥3% from 09:35 | CLSK +0.92% (t 2.5), RIOT +0.52% (1.9), COIN +0.52% (1.5), HOOD +0.46% (1.15), MARA +0.25% (0.8), MSTR +0.05% (0.15) | | | | | |

By year, from 09:35: 2017 −2.9%, 2018 −0.5%, 2019 +0.7%, 2020 −0.2%, 2021 +0.45%, 2022 +0.59%, 2023 +0.29%, 2024 +0.88% (t 2.7), 2025 +0.86% (t 3.1), **2026 Q1 −1.15% (t −2.4)**.
- Down-gaps fade better than up-gaps: +0.47% vs +0.34%.
- Fridays, the only day these names reliably have true 0DTE, give +0.29% (t 1.0).
- Most of the fade happens in the first 30 minutes: from 10:00 only +0.21% (t 1.1) is left.
- The daily-bar "+2.3%, 64% hit" does not reproduce with real intraday entries. The effect is about 5× smaller and regime-dependent.

## Option economics (0.40Δ, base spread, OOS trades)

The EV columns are the mean return on premium. The **fair** column is the honest one for ranking.

| signal | n/yr | und. mean | hit | EV brief | EV **fair** (t) | EV rich | PoP fair | fair-EV range (Δ0.3–0.5, IV ×1–1.2, cost) | 1 contract | min capital @15% / 25% |
|---|---|---|---|---|---|---|---|---|---|---|
| BASELINE SPY always call 10:30 | 248 | +0.012% | 54.7% | +27.4% | **−8.9%** (−2.2) | −34.3% | 28% | −40…−4% | $132 | $882 / $529 |
| BASELINE SPY always put 10:30 | 248 | −0.012% | 45.1% | +27.7% | **−7.0%** (−1.5) | −31.3% | 24% | −29…−1% | $133 | $888 / $533 |
| SPY 5m reversal (BH survivor) | 15k* | +0.0014% | 51.0% | −1.1% | **−2.3%** (−26) | −3.3% | 40% | −4…−1% | $94 | $627 / $376 |
| QQQ 5m ⇒ SPY (BH survivor) | 15k* | +0.0012% | 50.8% | −1.2% | **−2.4%** (−27) | −3.4% | 40% | −4…−1% | $94 | $627 / $376 |
| SPY first hour, low VIX | 43 | +0.059% | 55.5% | +36.2% | **+20.9%** (1.7) | −10.2% | 30% | −6…+32% | $82 | $549 / $330 |
| QQQ first hour, low VIX | 43 | +0.082% | 55.0% | +62.8% | **+18.7%** (1.6) | −12.4% | 32% | −10…+27% | $110 | $732 / $439 |
| QQQ first hour, Friday | 49 | +0.129% | 60.1% | +66.9% | +9.8% (1.0) | −20.2% | 35% | −26…+14% | $160 | $1,066 / $640 |
| QQQ first hour, non-event, exit on shock | 218 | +0.051% | 54.1% | +48.1% | +1.4% (0.3) | −24.8% | 32% | −29…+3% | $160 | $1,066 / $639 |
| IWM open→15:00 in uptrend ⇒ power hour | 178 | +0.029% | 52.4% | +49.2% | +8.0% (1.3) | −20.5% | 29% | −20…+13% | $24 | $159 / $96 |
| crypto ≥3% gap fade from 09:35 (0DTE) | 312 | +0.47% | 52.5% | +174% | **+15.0%** (3.2) | −14.8% | 30% | −12…+26% | $26 | $176 / $106 |
| … same, weekly (≈2.5d to expiry), 8% spread | 312 | | | | **−2.4%** | | | | | |
| crypto ≥5% gap fade from 09:35 (0DTE) | 134 | +0.53% | 54.5% | +212% | +18.4% (2.6) | −12.1% | 30% | −9…+30% | $30 | $201 / $121 |
| HOOD ≥3% fade from 09:35 | 22 | +0.62% | 50.3% | +232% | +35.1% (1.7) | +0.7% | 30% | +3…+52% | $129 | $862 / $517 |
| COIN ≥3% fade from 09:35 | 36 | +0.50% | 53.1% | +190% | +19.1% (1.4) | −11.4% | 28% | −8…+34% | $248 | $1,652 / $991 |

\* 5-minute windows; the bankroll uses one draw per window.

- "EV brief" is not credible: under that pricing both baselines are +27%, so any 0DTE purchase "wins".
- Fair-vol multipliers k are 1.1–1.4 for the ETFs and **2.0–2.4 for crypto gap days**. Gap mornings realize about twice the trailing-RV-implied move, so their real IV must be far above RV, and the fair column assumes the market prices that correctly.

### Bankroll: one year, whole contracts, fair pricing (median end; P(grow); share of paths losing ≥90%)

| signal | $170 @15% | $170 @25% | $1,000 @15% | $1,000 @25% | $5,000 @15% | $5,000 @25% |
|---|---|---|---|---|---|---|
| SPY first hour, low VIX | $170 (no trades: 1 contract > 15–25% of $170) | $170 (no trades) | $498; 35%; 0% | $281; 20%; 0% | $3,639; 42%; 7% | $867; 25%; 41% |
| QQQ first hour, low VIX | $170 (no trades) | $170 (no trades) | $645; 27%; 0% | $370; 19%; 0% | $3,793; 43%; 0% | $974; 26%; 39% |
| crypto ≥3% fade 09:35 (0DTE) | $67; 27%; 0% | $30; 4%; 0% | $143; 22%; 42% | $32; 3%; 90% | $314; 18%; 57% | $33; 2%; 95% |
| crypto ≥5% fade 09:35 (0DTE) | $126; 40%; 0% | $47; 14%; 0% | $327; 29%; 14% | $58; 10%; 65% | $1,226; 31%; 34% | $91; 9%; 77% |
| HOOD ≥3% fade | $170 (no trades) | $170 (no trades) | $1,153; 57%; 0% | $756; 42%; 0% | $5,423; 53%; 0% | $3,134; 39%; 8% |
| BASELINE always call 10:30 | $170 (no trades) | $170 (no trades) | $545; 0%; 0% | $309; 0%; 0% | $547; 0%; 2% | $310; 0%; 100% |

Even with a +15–20% EV per trade, a 28–32% PoP at 15–25% sizing gives negative median log-growth. Volatility drag eats the edge. Only HOOD at 15% (n=161, t 1.7) has a median above start, and under rich pricing its EV is +0.7%.

## Survivors and the "ready when funded" list

- **BH survivors (q=0.10): 3.** All are untradable: two 5-minute micro-reversals (options EV −2.3%) and one ex-post subset.
- **Ready when funded:** none. No strategy here has a positive fair-priced EV that is both statistically solid and positive under rich pricing.
- **Paper-only watch list** (log live, no money):
  1. **SPY/QQQ first-hour continuation when prior VIX is in the bottom tercile** (VIX ≲ 14).
     - OOS t 2.7 for both; about 43 days a year; fair EV +19–21%.
     - Min capital: $330–$549 for SPY/XSP and $439–$732 for QQQ.
  2. **Crypto ≥5% gap fade from 09:35 on Fridays (true 0DTE).**
     - Underlying +0.5%; fair EV +18%; min capital about $120–$200.
     - The 2026 Q1 reversal is a warning.
  3. **QQQ first-hour direction held until a 4σ shock** (exit rule): t 2.35, about 218 trades a year, fair EV only +1.4%.

## What more data would resolve

1. **Historical 0DTE option quotes** (SPX/XSP/SPY intraday chains, and single-name weeklies on gap mornings). This matters more than any extra price history.
   - The sign of every EV above flips between "fair" and "rich".
   - Direction.md's pricing (≈2.3× this sprint's brief pricing) and the live `vol_obs` (≈0.8× brief, n=6) disagree by about 3×.
   - Sources: CBOE DataShop and ThetaData (paid, cheap tier); otherwise keep growing `vol_obs` (it needs 20+ days), and also log XSP 0.40Δ mid and IV at 10:30 and 15:00, plus gap-morning IV for the crypto names.
2. **April–October 2026 minute bars** (not in the HF mirror). These would add about 135 OOS sessions. That is not enough to move any t-stat by more than about 0.3, and it would mainly test whether the 2026 Q1 crypto reversal persists.
3. **Robinhood historicals** would not change conclusions. Coverage is already 4,841 one-minute sessions, and the integrity checks against market.db pass. What is missing is option prices, not underlying bars.
4. **News timestamps** (Benzinga or Alpaca news) would let H6 replace the price-shock proxy with real headlines. The ex-post test already shows the ceiling: +0.07% on QQQ, which is too small for options.

## Caveats

- Option prices are modeled, not quoted; see the pricing discussion above. The fair regime uses the realized |move| on the trade days themselves, which is direction-free but optimistic about how well the market prices gap-day vol.
- Bankroll results use whole contracts at today's prices for historical returns, and a 1-year horizon.
- The HF dataset is a third-party mirror of Finnhub data. It is validated against market.db, but its 15:59 bar is used as the close (1–2 bp from the official close).
- CPI dates exist for 2015+ only, and NFP before 2015 is approximated. Event-day tests have n≈210 OOS.
- In H7, hit rates count zero-move windows as excluded. 5-minute options trades assume a mid ±1.5% spread, which is generous for 5-minute round trips.
