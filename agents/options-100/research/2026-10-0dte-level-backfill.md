# 0DTE price level, measured from real Robinhood history (2026-10-17)

Research only; no order tool was called. Script: `research/weekend/backfill_0dte_level.py` (loads `research/weekend/optfetch/*.jsonl`, writes table `option_hist` in `data/market.db`, full output in `optfetch/level_results.txt`, per-day panel in `optfetch/level_panel.csv`).

## Data actually obtained
- **Day set: 248 of 250 SPY days, 2025-10-20 .. 2026-10-16**, ATM strike K = round(SPY daily open), expired call+put resolved for every day, `day` bar (open = first print). 2 days had no non-interpolated expiry-day bar.
- **Real intraday is shorter than the brief assumed.** 5-minute bars are real only for the last ~7 trading days (2026-10-07 on; 2026-09-30 and June 17 5m are all `interpolated`). **10-minute bars are real back to 2026-06-17.** So intraday = 77 days of 10m (06-17..10-06) + 8 days of 5m. Entry = first real bar in 09:35-09:50 (09:40 for 10m; the 09:30 bar is a lone stale print). SPY spot at entry needs the SPY 5m bar, available from 2026-07-15, so the matched intraday set is **n=67** (07-15..10-16).
- `option_hist` rows: 496 day, 924 10-minute, 192 5-minute. ±$3 strikes not fetched (nothing needed them).
- Day-open straddle vs 09:40 straddle on the same 67 days: 1.03x (median 1.04), so the first day print is only slightly rich, not noisy.

## Level: realized |close - entry spot| / straddle premium (1.0 = fair; EV net of 2% cost = |close-K| / (1.02 x premium) - 1, settle at SPY close)
| Set | n | ratio mean (boot 95% CI) | median | EV mean (CI) |
|---|---|---|---|---|
| Day open (entry = first print, spot = SPY open) | 248 | **0.947** [0.852, 1.047] | 0.82 | **-7.3%** [-16.3%, +2.7%] |
| Intraday 09:40 (spot = SPY 5m) | 67 | **0.861** [0.688, 1.053] | 0.67 | **-8.7%** [-27%, +12%] |

Verdict: a long 0DTE SPY ATM straddle from the open is roughly fair before costs and about -7..-9% after 2% costs; the median day loses 20-28%. Not distinguishable from zero, not a positive-EV level.

By month (day set, ratio / EV): 2025-10 .74/-24%, 11 1.16/+12%, 12 .95/-8%, 2026-01 .76/-28%, 02 1.25/+22%, 03 .91/-12%, 04 .96/-6%, 05 .79/-22%, 06 1.17/+15%, 07 .76/-27%, 08 .93/-8%, 09 .94/-7%, 10 (12d) .99/0%. Month CIs are +-0.4 wide; no stable month effect.

By prior-close VIX tercile (day set): low .97 / -5%, mid .88 / -14%, high .99 / -3%. Intraday set: .83/-8%, .77/-7%, .99/-11%. Flat.

## Gap-day claim (realized/implied 1.16 on top-quintile |gap|) is NOT confirmed against real prices
|gap| quintile (day set, ratio / EV): q1 .90/-11%, q2 1.00/-3%, q3 1.01/-3%, q4 .92/-10%, **q5 (gap up to 2.6%) .91 [0.68,1.18] / -10%**. Intraday: q5 .95/-13%, q4 1.08/+3%. The VIX1D-based 1.16 compared realized to an index; against what Robinhood actually charges, gap days are priced up as much as they move. Drop the gap-day straddle as a TRADEABLE-NOW lead.

## Term gate VIX9D/VIX (prior close, terciles)
- Day set: bottom tercile ratio 1.12 / **EV +9.3%** [-9.5%, +30.5%] (n=83) vs others ratio .86 / **-15.6%** [-25.2%, -5.3%] (n=165).
- Intraday set: bottom tercile .68 / **-12.6%** (n=23) vs others **-6.7%** (n=44).
The sign flips between the two sets and the bottom-tercile CI includes 0 in both: no usable gate.

## Compared with the other levels
- **VIX1D**: straddle premium / (open x VIX1D/sqrt(252) x sqrt(2/pi)) = **0.73** [0.72, 0.75]; realized |open->close| / same = 0.67. In the edge.py sd form (rms of open->close move / (open x VIX1D/100/sqrt(252) x sqrt(0.69))) the constant is **0.83** (95% CI 0.74-0.93, n=250); mean|z| x sqrt(pi/2) gives 0.80. The old 0.92 sits at the upper CI edge, so it is slightly generous, not wildly off.
- **Oct 8-16 live quotes**: day-open straddle was 0.29-0.47% of spot (mean **0.36%**) vs **0.51%** for the prior 11 months (mean; median 0.45%): 1.43x cheaper in raw terms, 1.22x cheaper after normalizing by VIX (premium/(VIX/sqrt(252)) 0.364 vs 0.444). Those quotes were a cheap week, but realized/premium that week was ~1.0 (EV ~0%), so the cheapness did not become profit. Historical level is what to use: ratio ~0.9-0.95 gross.

## Recommendation
- `bot/edge.py`: replace `VIX1D_REALIZED = 0.92` with **`VIX1D_REALIZED = 0.83`** (rms basis, CI 0.74-0.93). Not edited here, as asked.
- Treat long 0DTE ATM straddles as -7..-9% EV; promote nothing on 0DTE price-level grounds.
- Caveats: day bars are trade prints (first print may be minutes after 09:30); K is an integer strike near open so payoff uses |close-K|; one year only; 10m bars were hand-transcribed by fetch agents (spot-checked, no anomalies in the panel).
