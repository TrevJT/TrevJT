# PLAN: options-100 (DRAFT — awaiting Trevor's approval)

## Objective
Learn, not earn. Turn $100 into labeled trade data on long-option behavior (delta, theta, IV, spread drag) while trying not to lose it faster than the lessons arrive. $100 is treated as spent.

## Hard constraints (from Robinhood + Trevor)
- Agentic account, options only, single-leg long calls/puts (MCP does not support spreads).
- Limit orders only, regular hours only. Always `review_option_order` before `place_option_order`.
- Limited margin ON (reuse same-day proceeds, no loan). Options Level 2 on the Agentic account.
- Fully autonomous after approval. Max daily loss: entire balance.

## Capital split
- Core book: $70. Lab book: $30. Books never borrow from each other.

## Core book — swing longs on cheap, liquid names
- Universe: F (primary), SOFI, XLF. NIO only if spread ≤10% of price.
- Contract: ATM or 1 strike ITM, delta 0.50–0.70, 14–45 DTE. 1 contract. Cost ≤ $35.
- Entry: after 10:15 ET. Direction = 20-day trend + 5-day momentum agree (from `get_equity_historicals`), IV rank not elevated (from `get_option_quotes`), no earnings inside the hold window (`get_earnings_calendar`). Skip if bid-ask > 10% of mid. Limit at mid, improve by $0.01 after 10 min, cancel after 30 min.
- Exit: +50% take profit, −50% stop, or 21 DTE time stop, whichever first. Never hold past 15:30 ET on expiry day.
- Cadence: at most 1 new entry per day, at most 2 open positions.

## Lab book — short-dated data generator
- Universe: SPY/QQQ OTM 0–1 DTE singles ≤ $0.20, or F weeklies ≤ $0.15.
- Entry: after 10:15 ET, only with a stated intraday thesis (trend vs VWAP). 1 contract. 1 per day.
- Exit: +40% / −50% or flat by 15:00 ET. Never carried into the final 30 minutes.
- Stops when the $30 is gone. Not refilled from core.

## Daily schedule (ET)
- 10:20 scan + entries. 12:30 manage. 15:00 manage + lab flatten. 15:30 expiry-day flatten.
- Runs are scheduled routines on the desktop session. Each run: pull positions, check exits, then look for entries.

## Journal (every decision, JSONL)
timestamp, book, underlying, contract, side, qty, limit, fill, thesis, greeks at entry, exit rule, exit fill, pnl, fees, lesson.

## Kill switches
- Balance < $15: stop trading, write final report.
- 3 consecutive core losses: pause core 2 trading days, review journal, adjust rules, resume.
- Any MCP error placing/cancelling orders twice in a row: stop, report to Trevor.
- Auth failure: stop, report.

## What we expect to learn
Whether cheap long options with 50/50 brackets have any edge for us; how much bid-ask and theta actually cost; whether the lab book's intraday data is worth its burn rate.

## Weekly report to Trevor
P&L, trade count, win rate, avg spread paid, biggest lesson, proposed rule changes. Rule changes require Trevor's OK.
