# Concept 2: 0DTE Momentum Scalper

## Thesis (why this is the aggressive edge)
On a trend day, a 0.12-delta SPY 0DTE option bought for $0.25 at 9:45 can print $1.00+ by noon: ATM 0DTE gamma is 50–100x a 30-DTE option's, and it goes parabolic after 14:00. That convexity is the only thing that can turn $100 into $500. The research says most retail 0DTE buyers lose (single-leg debit trades lose ≈$8/contract; ≈$90M of aggregate losses are pure transaction cost; outright long calls/puts win ~35–40%). The failure modes are known and avoidable: buying wide-spread lottery strikes, holding through the 12:00–14:00 chop, and letting theta run past 15:30. Filtered ORB backtests on SPY long ATM options show 41–47% win rate with ~2:1 payoff (PF 1.4); a VIX-15–25 + M/W/F + event-exclusion filter lifts simulated win rate to 65%. We take only those windows, cut losers fast, and let winners run with trailing stops.

## Model
Inputs from 5-min bars (SPY, QQQ, IWM), refreshed every run:
- **VWAP** (session, volume-weighted) and its 15-min slope.
- **Opening range (OR)** = 9:30–9:35 high/low (5-min OR nearly doubled returns vs 15-min).
- **ATR(14, 5-min)** = noise unit.
- **RVOL** = current 5-min volume / 20-day average for that time slot.
- **VIX** spot (from VIXY/UVXY intraday proxy if VIX quote unavailable) and intraday change.
- **Day regime**: VIX 13–28 only; event calendar; day of week (M/W/F preferred).

**Momentum score S (−6…+6):** +1 close above VWAP (−1 below); +1 distance from VWAP > 0.5 ATR in trend direction; +1 VWAP slope sign agrees; +1 last 3 of 4 bars closed in direction; +1 close beyond OR high/low (power-hour window: beyond 13:00–14:00 range); +1 RVOL ≥ 1.3. Negative components mirror for puts.
**Decision:** S ≥ +4 → long call; S ≤ −4 → long put; otherwise no trade. Pyramid only if S ≥ +5 (or ≤ −5) *and* existing position is ≥ +50%.

## Universe & contract selection
- Primary SPY (~$775, $1 strikes), QQQ (~$750); IWM (~$279) only if RVOL ≥ 1.5. Opportunistic NVDA/AAPL/AMD on Mon/Wed/Fri (daily expiries since Jan 2026), max 1 unit, only with a same-day news catalyst.
- 0DTE on M/W/F; 1 DTE Tue/Thu before 14:00, 0DTE after.
- Price $0.15–$0.40, delta 0.10–0.20. At VIX 15.5 that is ≈$5–8 OTM at 9:45, ≈$2–4 OTM at 14:30. Skip if (ask−bid)/mid > 12% or bid < $0.05.
- Entry windows: **A** 9:40–11:00 (ORB); **B** 14:00–15:10 (power hour). No new entries 11:00–14:00 or after 15:10.

## Entry rules
1. Window and regime filters pass; S hits threshold on a *closed* 5-min bar.
2. Pick strike with delta 0.10–0.20, mid ≤ $0.40; review_option_order, then limit at mid (retry once at mid + $0.01; otherwise skip).
3. Max 2 open positions, never same direction on correlated tickers (SPY+QQQ counts as one).
4. Event days: CPI (Oct 14), PPI/retail sales (Oct 15), GDP/PCE (Oct 29), NFP (Nov 6): no Window A entry before 10:00. FOMC minutes (Oct 7) and decision (Oct 28, 14:00): no entries 13:30–14:15, then Window B targets the post-Fed break. Monthly opex Oct 16: Window A only (pinning risk).

## Exit rules
- **Scale-out:** sell half at +80% (or all if only 1 contract and ≥ +100%).
- **Trail for runners:** stop = max(peak premium × 0.65, 5-min close back through VWAP).
- **Hard stop:** −45% from entry mid.
- **Time stop:** not ≥ +25% within 30 min → exit; Window A entries exit by 12:00 unless +50%.
- **Flat by 15:45** no exceptions (auto-exercise risk); 15:30 start working the bid.

## Sizing & compounding
- Unit = 35% of current equity, whole contracts ($100 → 1 contract ≤ $0.35, or 2 ≤ $0.17).
- Initial entry 1 unit; pyramid +1 unit (max 1 add) when position ≥ +50% and S escalates; then raise stop on the whole position to original entry price. Total exposure cap 70% of equity.
- Sale proceeds are reusable same day; recalculate unit from live equity each run. Max 4 round trips/day (≈$0.36 fees + spread ≈ $8–12 drag).

## Schedule
- 9:25 pre-market: compute ATR, VIX regime, event flags, 20-day RVOL table.
- 9:35: lock OR. 9:40–11:00 every 5 min: score, enter/manage.
- 11:00–14:00 every 15 min: manage exits only.
- 14:00–15:10 every 5 min: Window B scoring, entries, pyramids.
- 15:10–15:45 every 5 min: exits only; 15:45 flatten everything.
- 16:05: journal every signal (taken or not), fills, slippage, S, regime.

## Kill switches
- Daily equity −60% from open → no new entries.
- 3 consecutive losses → done for the day.
- VIX < 12 or > 28, spread > 12% of mid, or stale quotes/MCP errors → no new orders; flatten at bid if positions open.
- Equity < $25: 1 contract ≤ $0.25, no pyramids. Equity < $12: stop and report.
- Two unfilled limit retries → cancel, skip.

## Expected path
Per-trade expectancy near zero after drag (40% × +100% − 60% × 45% − 10% ≈ +3%); profit comes from the 10–15% of trades that trail to +200–400%. Ruin (< $12) within 1 week ≈ 35%; within 2 weeks ≈ 60%. Median after 2 weeks ≈ $40–55. Upside: ~15% chance > $200, ~4% chance > $500 (two or three trend days with pyramided runners).

## What the journal will teach us
Real spread/slippage per fill vs quoted mid; whether S ≥ +4 beats +3; Window A vs B win rate; M/W/F vs Tue/Thu; VIX bucket performance; stop (−45%) vs time-stop exit frequency; how often +80% scale-out leaves money on the table.

## Sources
- https://stockanalysis.com/etf/spy/history/
- https://finance.yahoo.com/quotes/SPY,QQQ,IWM/
- https://www.cnbc.com/2026/08/17/stock-market-volatility-vix-wall-street.html
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6355218
- https://options.cafe/blog/0dte-opening-range-breakout-strategy-spy-backtested-results/
- https://blog.quantish.io/2025/09/24/refining-the-0dte-spx-breakout-strategy/
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4404704
- https://optionscout.ai/blog/retail-options-trader-report-2026
- https://spotgamma.com/0dte-options-strategy/
- https://www.gexmetrix.com/blog/zero-dte
- https://optionalpha.com/blog/0dte-options-time-decay
- https://my0dteoptions.com/blog/stocks-with-0dte-options/
- https://www.cboe.com/insights/posts/the-state-of-the-options-industry-q-1-2026
- https://fedratecalc.com/us-economic-calendar/october-2026/
- https://therighttrader.com/economic-calendar
