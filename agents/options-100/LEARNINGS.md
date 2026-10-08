# LEARNINGS.md — the bot's self-improvement log (read at every pre-open; append whenever something is learned)

## Core operating principle (Trevor, 2026-10-08)
This agent is a recursive self-improver. When an input, model or process is unreliable, it does NOT explain the flaw
away or trade around it — it builds a better source/method, verifies it, and records the change here.
Loop for every anomaly: OBSERVE → HYPOTHESIZE root cause → TEST against data → FIX (code/data/process) → VERIFY → LOG.
Never act on a number it has reason to distrust. "Probably stale" means "go get the real one."

## Entries
| Date | Observed | Root cause (verified) | Fix | Verified by |
|---|---|---|---|---|
| 2026-10-07 | 0DTE momentum score lost 4/4 | score ≈ coin flip on 60 sessions; low-VIX chop | VIX gate; EV gate | context.py backtest |
| 2026-10-07 | session stalled 2h18m, failsafe crashed | cron queue blocked while user typed; undefined $CL | fixed path; 5-min cadence; don't type during RTH | failsafe log |
| 2026-10-08 | spreads rejected at placement | Robinhood MCP: multi-leg unsupported (review passes, place fails) | single legs only; re-test monthly | 400 error text |
| 2026-10-08 | EV engine showed +100…+415% | (a) Yahoo option quotes delayed ~15 min (0.20 vs live 0.14); (b) forecast scaled full-day tails by √t | edge.py --quotes reads LIVE Robinhood quotes; forecast = real clock-time→close returns, conservative of 730-session 1h pool vs recent-60 5m pool | 772P live: EV fell +117% → +2…8%; direct 5m backtest payoff $0.255 vs $0.19 |
| 2026-10-08 | self-audit: failsafe.log 'Input must be provided … --print' | --allowedTools is variadic and swallowed the prompt arg → failsafe never ran a cycle (yesterday's stall was unprotected) | prompt piped via stdin | `echo … | claude -p --allowedTools …` returned FAILSAFE-OK |

## Open improvement queue (work these when idle / nightly)
1. [IN PROGRESS 10-08] ID cache per day (state/ids_<SYM>_<DATE>.json). Cheapest build: per-strike get_option_instruments calls (~0.8 KB each) for ±1% strikes at pre-open, not the full listing (~30 KB/page). SPY puts cached for 10-08.
2. Grade engine picks against realized payoff; once ≥ 60 graded, recalibrate pool choice by which pool predicted better.
3. Add QQQ/IWM recent-5m pools; add VIX-regime conditioning to the recent pool when ≥ 250 sessions accumulate.
4. [DONE 10-08 12:40] 60s feed for top-12 markets (predictions.py fastsnap, launchd com.trevjt.options100.fastodds), second-stamped; shock.py reads it. ORIGINAL NOTE: PM shock 10-08 12:15-12:30: SPY spiked on the 12:15 bar BEFORE the odds jump showed in the 12:30 snapshot. 15-min odds snapshots are too slow to front-run headlines. Improvement: snapshot the ~10 highest-impact markets every 1-2 min during RTH (cheap: single gamma-api call) and timestamp precisely, to measure true lead-lag.
5. Detect intraday regime change (realized vol today vs pool) and switch pools mid-day.
