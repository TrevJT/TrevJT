# PLAN: options-100 — Concept 2, 0DTE Momentum Scalper (APPROVED by Trevor 2026-10-06 22:30 ET)

## Hard rules (Trevor, non-negotiable)
1. Maximum possible loss is the $100 in the Agentic account. Nothing that can lose more.
2. LONG options only: buy-to-open, sell-to-close. NEVER sell-to-open, never uncovered, never credit spreads, never futures, never equities, never crypto.
3. No margin, no borrowed money, no leverage beyond the long premium itself. Order cost ≤ cash on hand at the moment of the order.
4. Every order: `review_option_order` first, then `place_option_order` only if the review has no warnings and matches symbol/side/qty/price exactly.
5. Limit orders only, regular hours only. Flat by 15:45 ET every day: never hold a 0DTE contract into expiry.
6. Tools the agent may call: robinhood-trading get_*/search/review_option_order/place_option_order/cancel_option_order. Equity and crypto order tools are forbidden.

## Volatility gate (approved by Trevor 2026-10-07 after day-1 review)
Source: SPY 1993-2026, prior-day VIX vs next-day range corr 0.74; direction ~coin flip.
- Prior-day VIX < 16 → NO 0DTE entries (stand down). Exception: a prediction-market shock (any tracked iran/fed/midterms/trump market with stable same-day |r| ≥ 0.4 to SPY/QQQ/CL=F/XLE moving ≥ 8 pts since prior close) lifts the gate for that day, entries still need |S| ≥ 5.
- Prior-day VIX 16-18 → entries need |S| ≥ 5, RVOL ≥ 1.3, ATR5 ≥ 0.06% of price.
- Prior-day VIX ≥ 18 → base rules below, plus RVOL ≥ 1.3 and ATR5 ≥ 0.06% of price.
- Standing down is a valid, logged decision ("no_trade_day" in the journal with the reason).

## Strategy (from concepts/2-0dte-momentum-scalper.md)
- Universe: SPY and QQQ 0DTE (1DTE on Tue/Thu before 14:00). IWM only if RVOL ≥ 1.5.
- Contract: delta 0.10–0.20, mid $0.15–0.40, spread ≤ 12% of mid, bid ≥ $0.05.
- Entry windows (ET): A 9:40–11:00, B 14:00–15:10. No new entries 11:00–14:00 or after 15:10.
- Score S (−6…+6) from 5-min bars: VWAP side, >0.5 ATR from VWAP, VWAP slope, 3 of 4 bars in direction, range break (opening range in A, 13:00–14:00 range in B), RVOL ≥ 1.3. S ≥ +4 call, S ≤ −4 put.
- Regime gate: VIX 13–28 (proxy if unavailable). Event days: FOMC minutes Oct 7 and FOMC Oct 28 → no entries 13:30–14:15. CPI Oct 14, PPI Oct 15, GDP/PCE Oct 29, jobs Nov 6 → no window-A entry before 10:00. Opex Oct 16 → window A only.
- Sizing: unit = 35% of equity in whole contracts; 1 unit per entry; one pyramid add at S ≥ ±5 with position ≥ +50%; exposure cap 70%; max 2 positions (SPY+QQQ same direction count as one); max 4 round trips/day.
- Exits: half at +80% (all at +100% if 1 contract); trail 65% of peak or 5-min close back through VWAP; hard stop −45%; time stop if not +25% in 30 min; window-A entries out by 12:00 unless +50%; flat by 15:45.
- News overlay (every cycle): `search` headlines; on a major headline (Fed, war/ceasefire, tariff, outage, index shock) set regime NO_NEW_ENTRIES / CALLS_ONLY / PUTS_ONLY. Never overrides exits.
- Kill switches: day −60% from open → no new entries; 3 consecutive losses → done for the day; VIX outside band, spread > 12%, stale quotes, or MCP errors → no new orders, flatten at bid if open; equity < $25 → 1 contract ≤ $0.25 no pyramids; equity < $12 → stop and report; `STOP` file in repo root → flatten and halt.

## Operations
- Executor and orchestrator are the same thing: the "robinhood" Claude Code desktop session, which has the Robinhood MCP tools loaded. An in-session cron fires the cycle every minute 7:24–14:06 MDT (9:24–16:06 ET) on weekdays; each firing runs when the session is idle, so the real cadence is 1–2 minutes. Procedure: `agents/options-100/CYCLE.md`. Math: `agents/options-100/bot/score.py`.
- Crons are session-only and expire 7 days after creation (Oct 7 → renew Oct 13). If the session dies, nothing runs; positions are long-only and can only expire worthless (max loss = premium). Leave the terminal open and idle during market hours.
- State: `agents/options-100/state/`. Journal: `journal/options-100.jsonl`, one line per decision. Daily report 16:05 ET committed to git. Weekly report Friday.
