# ROUTER.md — options-100 strategy router (approved by Trevor 2026-10-07, capital $143.64)

Goal: an extreme, aggressive, test account built around 0DTE / short-dated options day trading. The router is not tied to one
pattern. Every pre-open it reads the research and picks the playbook(s) with the best odds today, sizes them, and journals why.
When no playbook has an edge, standing down IS the trade.

## Hard rules (unchanged, override everything)
- Long options only (single legs or DEBIT spreads). Never sell-to-open a naked/uncovered leg, never a credit spread, no margin,
  no futures, no equities, no crypto. Max possible loss = premium paid ≤ cash. review_option_order before every place.
- 0DTE contracts: flat by 15:45 ET. Any contract: closed by 15:00 ET on its expiry day (never held into expiry/exercise).
- Swing positions (DTE ≥ 2) may be held overnight; cap total swing premium at 40% of equity so the day-trading book keeps ≥ 60%.
- Daily loss stop: −50% of start-of-day equity → no new entries that day. Equity < $15 → stop and report.

## Playbooks
| ID | Playbook | Instrument | When the router may pick it | Risk per trade |
|---|---|---|---|---|
| P1 | 0DTE momentum scalper (CYCLE.md step 4) | SPY/QQQ 0DTE singles or $1-wide debit spreads | VIX gate NORMAL or STRICT (prior VIX ≥ 16) or PM shock day | ≤ 35% equity |
| P2 | Event-day straddle | 0-1DTE SPY/QQQ long call + long put (or two debit spreads) bought 14:30-15:30 the day BEFORE a scheduled print (CPI, PPI, NFP, FOMC, big-tech earnings AMC), sold next morning 09:35-10:15 | Scheduled catalyst tomorrow, VIX9D/VIX < 1 (event not fully priced) | ≤ 30% equity |
| P3 | Catalyst sniper (concepts/1) | 0.30-0.40Δ weeklies / debit spreads on the event name (BAC, XLF, SOFI, F, RIVN, TSLA-sympathy) | Event 3-7 sessions out, IV/HV < 1.3 | ≤ 25% equity, swing cap applies |
| P4 | Headline/peace dividend (concepts/4) | Jan-2027 debit spreads (JBLU 4/5C, NIO 3.5C/4C, CNH 15C) | Relevant Polymarket odds turning (≥ +5 pt 5d) toward the headline | ≤ 25% equity, swing cap applies |
| P5 | PM-shock momentum | 0DTE XLE / USO / SPY options in the direction of the stable SAME-DAY correlation (correlate.py) | A tracked iran/hormuz/fed market moves ≥ 8 pt intraday (15-min odds feed); enter within 15 min, out in ≤ 60 min | ≤ 25% equity |
| P6 | Full-Kelly momentum (concepts/3) | 7-14 DTE near-ATM on high-beta momentum names | Only if |S| ≥ 60 in concepts/3 model AND market regime TRENDY | ≤ 35% equity, swing cap applies |
| P7 | Power-hour lotto | 0DTE SPY/QQQ 0.05-0.10Δ, ≤ $0.10 | 14:30-15:15, trend day confirmed (|o-c|/range > 0.6 so far, RVOL ≥ 1.3), max 1/day | ≤ 10% equity |

## Daily selection (pre-open, after context brief + odds board)
1. Gates: compute vix_gate (PLAN.md), regime_hist (context.py brief), pm_shock, and the event calendar for today/tomorrow.
2. Score each playbook 0-3 on today's evidence:
   - P1: 3 if VIX ≥ 18 and TRENDY; 2 if VIX 16-18 or PM shock; 0 if STAND_DOWN.
   - P2: 3 if a top-tier print is tomorrow (CPI/FOMC/NFP) and VIX9D/VIX < 0.95; 2 for tier-2 (PPI, retail sales, mega-cap earnings); else 0.
   - P3: 2 if an event in its universe is 3-7 sessions out and IV/HV < 1.3; else 0.
   - P4: 2 if a mapped odds market moved ≥ +5 pt over 5d toward the payoff; 1 if flat; 0 if moving against.
   - P5: armed (score 2) every day; it fires only on an intraday odds shock.
   - P6: 2 only if the concepts/3 score clears and regime TRENDY; else 0.
   - P7: armed (1) on TRENDY/MIXED days; decided at 14:30.
3. Run every playbook scoring ≥ 2, highest first, within the risk caps. If nothing scores ≥ 2 (P5 aside), stand down.
4. Write day.json.playbooks = [{id, score, reason}] and journal {event: "router", playbooks, evidence}.

## Learning loop
- Every trade journals its playbook ID. reports/research (nightly) adds per-playbook P&L, win rate, avg winner/loser.
- Friday: re-rank. A playbook with ≥ 8 trades and negative expectancy is suspended until a backtest or new evidence supports it.
- New playbooks are added only with a backtest (context.py) or a stable correlation (correlate.py) behind them.
