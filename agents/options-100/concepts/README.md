# options-100: three aggressive concepts (drafted 2026-10-06, awaiting Trevor's pick)

All three obey the broker box: $100, Agentic account, single-leg long calls/puts only, limit orders, regular hours, review before place, close before expiry.

| | 1. Catalyst Sniper | 2. 0DTE Momentum Scalper | 3. Full-Kelly Momentum Compounder |
|---|---|---|---|
| Edge claimed | Pre-event IV ramp (documented, small) + occasional realized > implied | 0DTE gamma on trend days, filtered ORB / power hour | Short-term continuation in high-turnover names + LLM headline score |
| Instruments | Weekly 0.30–0.40Δ on F, SOFI, RIVN, T, PFE, SNAP, XLF, SLV, GDX, BAC | SPY/QQQ 0DTE, 0.10–0.20Δ, $0.15–0.40 | 7–14 DTE 0.40–0.50Δ on SOFI, RIVN, RGTI, QS, JOBY, ACHR, SNAP, LCID, NIO, OPEN |
| Trades / 2 wks | ~4–5 events | ~15–25 round trips | ~3 |
| Concurrency | ≤2 events, ≤3 contracts | ≤2 positions, 1 pyramid | 1 position, all-in |
| Runs / day | 5–7 | every 5–15 min | 3 |
| P(ruin) 2 wks | ~30% | ~60% | ~65% |
| P(ruin) 4 wks | ~55% | ~80%+ | ~80% |
| Median at 4 wks | $45–65 | $40–55 (2 wks) | $25–45 |
| Upside case | $250–400 (~10%) | >$200 (~15%), >$500 (~4%) | $150–250 (~27%), $750 (~5%) |
| Skill the journal builds | IV ramp / implied-vs-realized calibration | Intraday regime + execution cost | Factor scoring + roll-up compounding |

Files: `1-catalyst-sniper.md`, `2-0dte-momentum-scalper.md`, `3-full-kelly-momentum-compounder.md`.

Orchestrator's take: Concept 1 has the only published edge and the slowest burn, so it generates the most trades before ruin. Concept 2 is the most aggressive in operational tempo and the only one with a credible path past $500. Concept 3 is the purest lottery. Hybrid option: run 1 as the base book and let 2 use the same-day proceeds on FOMC/CPI days.
