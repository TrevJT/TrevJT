---
name: market-history
description: Historical market data and context for the options-100 trading agent. Use before any trading decision, plan change, rule change, or strategy question about SPY/QQQ/IWM/VIX or the big-tech names — it holds every daily bar since the 1990s (S&P since 1927), 2 years of hourly bars, a growing archive of 5-minute and 1-minute bars, and every option quote the bot has seen. Also use to backtest a proposed rule before recommending it.
---

# Market history for options-100

Database: `agents/options-100/data/market.db` (SQLite, git-ignored). Source: Yahoo Finance via yfinance, no credentials.
Scripts live in `agents/options-100/bot/`. Run them from the repo root (`~/code/TrevJT`).

## What is in it

| Table / interval | Symbols | Depth |
|---|---|---|
| `bars` 1d | SPY QQQ IWM DIA ^GSPC ^NDX ^RUT ^VIX ^VIX9D ^VIX3M ^VVIX ^SKEW ^TNX ^IRX TLT DX-Y.NYB CL=F GC=F BTC-USD XLK XLF XLE XLY XLV XLI XLC SMH NVDA AAPL MSFT AMZN GOOGL META AVGO TSLA | full history (S&P 1927, VIX 1990, SPY 1993) |
| `bars` 1h | SPY QQQ IWM ^VIX | 730 days, archived daily |
| `bars` 5m | SPY QQQ IWM ^VIX | 60-day source window, archived daily so it grows permanently from 2026-07-15 |
| `bars` 1m | SPY QQQ | 7-day source window, archived daily from 2026-09-29 |
| `option_snaps` | every 0DTE quote the bot fetched (bid/ask/greeks/IV/OI) | from 2026-10-07 |

Timestamps are ET strings: daily `YYYY-MM-DD`, intraday `YYYY-MM-DD HH:MM` (bar start). Robinhood intraday history before ~2026 is placeholder data, so do not use it for history.

## Commands

```
python3 agents/options-100/bot/history.py update     # refresh + archive (pre-open and after close; ~30 s)
python3 agents/options-100/bot/history.py status     # coverage per symbol/interval
python3 agents/options-100/bot/context.py brief      # pre-open regime brief: VIX/RV percentiles, term structure,
                                                     # 30 nearest analog days since 1993, expected range, regime call
python3 agents/options-100/bot/context.py backtest --sym SPY [--score 4] [--rvol 1.3] [--atr 0] \
        [--hold 30] [--target 1.0] [--stop 0.6]      # replays the live score model (bot/score.py) on every 5m session
python3 agents/options-100/bot/context.py tod --sym SPY   # time-of-day volatility profile
echo '<json line>' | python3 agents/options-100/bot/history.py snap   # archive option quotes
sqlite3 agents/options-100/data/market.db "SELECT ..."               # ad-hoc queries
```

## Prediction markets (Polymarket + Kalshi, public APIs)

Tables `pm_markets`, `pm_prices` in the same DB. Topics: iran (incl. Hormuz, Israel, nuclear deal), midterms, trump, fed, macro, china, ukraine, oil.
Polymarket: ~200 markets ≥ $150k volume with full daily odds history. Kalshi: ~430 Fed/CPI/jobs/recession/oil markets (snapshots).
A launchd job snapshots every tracked market every 15 min in market hours, so an intraday odds history accumulates from 2026-10-07.

```
python3 agents/options-100/bot/predictions.py update   # rediscover markets + backfill history (daily job does this)
python3 agents/options-100/bot/predictions.py now      # odds board by topic with 1d/5d changes
python3 agents/options-100/bot/predictions.py movers   # biggest odds moves
python3 agents/options-100/bot/correlate.py scan       # odds-change vs asset-return correlations, split-half + Bonferroni
python3 agents/options-100/bot/correlate.py pair <market_id> <ASSET>   # biggest odds days and what the asset did
```

Findings 2026-10-07 (3,848 tests): Iran odds co-move with oil/XLE the same day (r ≈ ±0.6, significant after Bonferroni): leadership change ↑ → oil ↑; nuclear deal / Hormuz normal ↑ → oil and XLE ↓; uranium-cap deal odds ↑ → SMH ↑. No next-day lead signal survives correction yet (best: Hormuz-normal odds ↑ → crude next day ↓, r −0.24, p 0.01). Treat odds moves as a real-time read of oil/energy/semis, not a forecast, until a lead survives on fresh data.

## How to use it

- **Every pre-open:** `update`, then `brief > state/context_today.md`. The regime call (TRENDY / MIXED / CHOPPY) gates entries per CYCLE.md.
- **Before proposing any rule change:** backtest it, report signals/day, win %, stop %, and compare against the random baseline: a target/stop of T/S ATR has a no-edge win rate of about S/(T+S). A rule only has an edge if it beats that by a clear margin after option spread and theta (assume ~10% of premium round-trip).
- **When Trevor asks "what happened last time X":** query analogs from the daily table (gap, VIX level, prior-day move, drawdown), not memory.
- **Never** treat 60 days of 5m data as proof. Say how many sessions and signals a number rests on.

## Findings so far (2026-10-07, 60 sessions, ~430 signals)

- The live momentum score (S ≥ 4) has **no edge** on the underlying. With symmetric 0.6/0.6 ATR, win rate is 45–46% against a 50% random baseline. With 1.0 target / 0.6 stop it is 32–33% against 37.5%.
- Requiring |S| ≥ 5 and RVOL ≥ 1.3 lifts it to 50–54% at 0.6/0.6, which is a coin flip before costs.
- Puts did worse than calls (30% vs 34–37% at 1.0/0.6) in this up-trending 60-day window.
- Today (2026-10-07): VIX 31st percentile, realized vol 30th percentile, analog days split 15/30 up. Low-vol regime, where cheap 0DTE momentum entries bleed theta.
