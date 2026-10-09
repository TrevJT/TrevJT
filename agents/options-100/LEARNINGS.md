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
| 2026-10-09 | self-audit reported stalls/errors already fixed | audit read multi-day logs; quiet cycles wrote heartbeat but not cycle.log | audit scoped to current session + today's failsafe lines; EVERY cycle must append one cycle.log line | re-run showed only real items |

## Open improvement queue (work these when idle / nightly)
1. [IN PROGRESS 10-08] ID cache per day (state/ids_<SYM>_<DATE>.json). Cheapest build: per-strike get_option_instruments calls (~0.8 KB each) for ±1% strikes at pre-open, not the full listing (~30 KB/page). SPY puts cached for 10-08.
2. Grade engine picks against realized payoff; once ≥ 60 graded, recalibrate pool choice by which pool predicted better.
3. Add QQQ/IWM recent-5m pools; add VIX-regime conditioning to the recent pool when ≥ 250 sessions accumulate.
4. [DONE 10-08 12:40] 60s feed for top-12 markets (predictions.py fastsnap, launchd com.trevjt.options100.fastodds), second-stamped; shock.py reads it. ORIGINAL NOTE: PM shock 10-08 12:15-12:30: SPY spiked on the 12:15 bar BEFORE the odds jump showed in the 12:30 snapshot. 15-min odds snapshots are too slow to front-run headlines. Improvement: snapshot the ~10 highest-impact markets every 1-2 min during RTH (cheap: single gamma-api call) and timestamp precisely, to measure true lead-lag.
5. Detect intraday regime change (realized vol today vs pool) and switch pools mid-day.

- 2026-10-09 09:47 (open item): EV on OTM 0DTE calls is very spot-sensitive. A $0.24 spot change moved 779C from +57% to +41% EV. Every top call pick so far sits where the call IV (~14.5%) is below the put IV (16-19%), so the engine may just be reading normal skew as edge. Fix: take spot from get_equity_quotes in the same second as the option quotes, and grade call vs put picks separately in `edge.py grade` to see whether call-side EV comes true.
- 2026-10-09 11:10 (open hypothesis): the 11:00 scan showed +55-75% EV on calls AND puts at once, so the engine isn't just reading skew. Robinhood's IV (~11.5-14%) over the 296 minutes left, counted in calendar time, implies a sd to close of ~0.27%. The engine's recent 5m pool says 0.35%. Either 0DTE afternoon options really are cheap in this low-VIX regime, or the pool overstates the move. Possible reasons it overstates: high-vol days in the last 60 sessions, or fat-tailed days leaking in. Test: tonight's grade (call vs put split). After that, recompute the pool sd with the top 10% of days removed, and compare predicted to realized |move| from 11:00 to close over all 61 sessions.
- 2026-10-09 11:15 TESTED (SPY 5m, last 61 sessions, 11:05 open to 15:55 close):
  - Realized sd 0.349%, mean |r| 0.268%, median |r| 0.202%. The market implies sd ~0.27%, so mean |r| ~0.215%.
  - With the top 10% of days removed, sd drops to 0.257%, which is BELOW implied.
  - Verdict: the "edge" is a tail bet. On a typical day the options are fairly priced or rich. All the EV comes from ~6 big-move days in 61. It is real only if the fat-tail regime continues, and it pays as rare big wins against many small losses (P(profit) 10-24% matches this).
  - Implication: size tiny and many (probe-sized), never concentrated. Engine trust requires ≥60 graded picks for exactly this reason.
- 2026-10-09 11:34 INCIDENT: the cycles at 11:24 and 11:29 MT were skipped. The Mac went into 'Clamshell Sleep' at 11:20 when the lid closed (on AC) and woke at 11:34. caffeinate cannot block lid-close sleep, and launchd jobs don't run while asleep, so the failsafe was down too. Today was harmless (flat, STAND_DOWN). Fixes, Trevor's call, both system settings: keep the lid open during market hours, or `sudo pmset -a disablesleep 1` on market days (reverse with 0). Report in EOD; don't ping mid-day while flat.
