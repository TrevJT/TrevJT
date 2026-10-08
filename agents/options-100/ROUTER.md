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

## Playbooks (revised 2026-10-07 after 3-agent research sprint; evidence in research/brainstorm/ and research/SYNTHESIS.md)
Status: LIVE = may trade; WATCH = log signals + real quotes only, no money until ≥ 20 logged signals beat the baseline; RETIRED = tested, no edge.

| ID | Playbook | Status | Instrument / timing | Fires when | Evidence | Risk |
|---|---|---|---|---|---|---|
| P8 | **Bold-play ladder** | LIVE | SPY 0DTE ATM/+$3 debit spread (call or put), bought 09:35-10:00; resting sell at 2× right after fill; exit 15:00 | prior-day VIX ≥ 20. Direction: gap direction if |gap| ≥ 0.5%, else first-15-min range break | Monte Carlo 1993-2023, no edge assumed: −6% EV/bet at VIX≥20 (best of all structures), 37% win at ~2.2×; all-in ladder P($1k)≈6.9%, P($5k)≈1.2% vs fair ceiling 14%/2.9% | ALL-IN (max whole lots). Stop at $1,500 → tell Trevor to withdraw $1,000 |
| P9 | **Mega-cap earnings strangle** | LIVE | OTM call debit spread + OTM put debit spread, long strikes ≈ ±8-9%, expiry 2 days out; buy 15:30-15:55 day of AMC report; sell next day 09:45-10:30 | TSLA Oct 21 AMC, META ~Oct 28 AMC (confirm dates); skip if ATM straddle > 9% (TSLA) / > 10% (META) | Last 15 reports: TSLA avg move 9.2% vs ~6.4% implied; META 9.4% vs ~7% | TSLA ≤ $70; META funded from TSLA proceeds |
| P10 | Oct 28 triple stack | WATCH→LIVE on Oct 28 if P9 META not taken | QQQ 2-day ~1.5% OTM call + put debit spreads, $3 wide, 13:30; exit Oct 29 by 11:00 | FOMC + GOOGL/MSFT/META same day | QQQ >2.5% moves on 15.8% of FOMC days vs 7.6% base, realized/implied 0.97 | ≤ $40 |
| P11 | Gap-day QQQ breakout | WATCH | QQQ 0DTE debit spread in break direction after first 5m close outside 15-min opening range; resting sell 3× | |gap| ≥ 1% | gap ≥1% → ≥1% move with gap 25% vs 10% base; ORB replication ≈ 0 after costs | none until validated |
| P1 | 0DTE momentum score | LIVE, re-tooled | Was 0.10-0.20Δ singles → now ATM/+$3 debit spreads only (0.10Δ singles: −46…−73% EV/bet) | VIX ≥ 18 and |S| ≥ 5 and RVOL ≥ 1.3 | score itself ≈ coin flip (60 sessions); spreads cut the bleed | ≤ 35% equity |
| P5 | Iran-odds shock → oil | WATCH | USO/XLE 1-week debit spread in direction of odds move | tracked Iran/Hormuz market moves ≥ 10 pt in a day | next-day crude move 3.58% vs 2.47% (n=19, p≈0.05, not multiple-test robust) | none until validated |
| P3 | Catalyst sniper (concepts/1) | WATCH | weeklies into scheduled events | — | CPI/NFP/FOMC realized < implied for SPY (0.61-0.82×): event premium already priced | — |
| P4 | Headline/peace (concepts/4) | LIVE (swing) | Jan-2027 debit spreads | mapped odds ≥ +5 pt over 5d | thesis-driven, no backtest | ≤ 25%, swing cap |
| P12 | Midterm relief call spread | LIVE (small) | SPY Nov 6 +1%/+2% call spread, buy Nov 3 15:45, exit Nov 4-5 | Nov 3 | SPY up day-after in 7/8 midterms since 1994, avg +0.48% | ≤ $20 |
| P2 | Macro-print straddle (CPI/PPI/NFP) | RETIRED | — | — | realized/implied 0.74-0.82; CPI moves below normal days in last 12 prints | — |
| P6 | Full-Kelly momentum (concepts/3) | RETIRED | — | — | log-growth negative at forced sizing; no directional edge found | — |
| P7 | Power-hour / far-OTM lotto | RETIRED | — | — | 0.05Δ finishes ITM 1.5% vs 10% fair; Mondays 0/138; power-hour continuation 14.4% vs 15.2% reversal | — |

Universal execution rules (from the research): never buy below 0.10Δ; prefer debit spreads over singles; place a resting take-profit (2× for P8/P1, 3× for P11) immediately after every fill; sell into spikes instead of holding to expiry; trade only when the volatility gate allows.

## Broker limitation (discovered 2026-10-08)
The Robinhood Trading MCP REJECTS multi-leg orders at placement ("Multi-leg options orders aren't supported in the Robinhood Trading MCP yet"), even though review_option_order accepts them. Until that changes: SINGLE LEGS ONLY. Every playbook that specified a debit spread uses the long leg alone (P8: ATM single; P9: OTM call + OTM put singles at ~±8%; P10/P12: long legs only), with sizing cut so max premium stays inside the same risk cap. Re-check monthly with a $0.01 dry spread order.

## Decision framework v3 (2026-10-07): every trade must show a measured edge
Why: with no edge, all-in betting loses everything ~95% of the time (bankroll sims). The fix is to find edge, not to bet bigger.
Edge can only come from: (a) options priced cheaper than the move history says is coming (volatility mispricing, measurable now),
(b) information the market prices slowly (earnings history, prediction-market shocks, gaps), (c) execution (spreads, selling into spikes).

1. **EV gate (all playbooks):** before any entry run `python3 agents/options-100/bot/edge.py scan --sym <SYM> --exp <EXP> --log` on LIVE quotes.
   A trade qualifies only if its exact structure shows EV ≥ +15% and P(profit) ≥ 10% with premium ≥ $0.10. Direction-neutral forecast, so
   a playbook's directional reason must add to, never replace, the EV gate.
2. **Shadow first:** the engine logs its top 5 picks at 09:45, 11:00 and 14:00 every trading day into edge_picks (no money).
   Nightly `edge.py grade` scores them against the actual close. Engine is TRUSTED once ≥ 60 graded picks show positive realized
   return on premium and realized ≈ predicted (within 15 pts).
3. **Probe trades while untrusted:** at most 2 per day, ≤ $15 each, only on picks with EV ≥ +25%: real fills to measure slippage.
4. **Once trusted:** size by quarter-Kelly on the engine's EV estimate (edge known → Kelly beats bold play); bold-play all-in only for
   P8 days with EV ≥ +15%.
5. **Report card:** reports/research nightly shows engine predicted vs realized, per-playbook P&L, and which inputs mattered.
   Anything that stops earning is demoted automatically on Friday's review.

## Daily selection (pre-open, after context brief + odds board)
1. Gates: compute vix_gate (P8 needs prior VIX ≥ 20; P1 needs ≥ 18; nothing 0DTE below 16) (PLAN.md), regime_hist (context.py brief), pm_shock, and the event calendar for today/tomorrow.
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
