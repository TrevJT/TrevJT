# Concept 1: Catalyst Sniper

## Thesis (why this is the aggressive edge)
Scheduled binary events are the one place where a $100 long-options account has a documented, repeatable tailwind. Gao/Xing/Zhang (JFQA 2018) find ATM straddles bought 3 days before earnings and sold at the announcement return +3.34% on average, versus structurally negative straddle returns otherwise, and the effect is strongest in small, volatile, thinly traded names: exactly the $2–$16 stocks we can afford. The edge comes from IV expansion into the print (vega) plus occasional pre-print drift; we are not paid to hold through IV crush unless the realized move clearly beats the implied move. Implied-move beat rates are stock-specific (25%–88%), so "hold vs. sell before" is a per-ticker scoring decision, not a rule. Macro prints (CPI, FOMC, jobs) give the same setup on XLF/SLV/GDX with tighter spreads.

## Model (inputs, scoring, decision rule)
Inputs per candidate (pulled at each run): (1) days-to-event; (2) IV of target contract vs 30-day realized vol from daily historicals (IV/HV ratio); (3) implied move = ATM straddle price / spot vs. median absolute post-event move over last 8 events (IM/RM ratio); (4) 5-day price momentum and distance to 20-day high/low; (5) news sentiment score −1..+1 from news search (last 72h, headline count-weighted); (6) spread/mid of the target contract.

Score S = 2·[IV/HV < 1.3] + 2·[IM/RM < 0.9] + 1·[days-to-event 3–7] + 1·[|sentiment| > 0.4] + 1·[spread ≤ 10% mid] − 3·[spread > 15% mid].
Trade only S ≥ 4. Direction: sentiment > +0.4 and momentum up → call; < −0.4 and momentum down → put; otherwise both (synthetic strangle, two single-leg orders, 1 contract each at ~0.35 delta). Hold-through flag = IM/RM < 0.8 AND ticker's historical implied-move beat rate ≥ 55%; else sell before the print.

## Universe & calendar (Oct 6 – Nov 6, 2026)
Prices ~Oct 5 close. Est. premium = target weekly contract, ~0.30–0.40 delta, 3–7 days out, at pre-event IV.

| Ticker | Catalyst | Date / time ET | Spot | Target contract | Est. premium |
|---|---|---|---|---|---|
| XLF | CPI | Oct 14 08:30 | ~$59 | Oct 17 ±$1 OTM | $35–55 |
| BAC | Q3 earnings | Oct 14 06:45 BMO | $53.75 | Oct 17 ±$1.5 OTM | $45–70 |
| SLV / GDX | CPI + PPI | Oct 14–15 08:30 | check | weekly ±2% OTM | $40–80 |
| T | Q3 earnings | Oct 21 BMO | $24.30 | Oct 24 ±$0.5 OTM | $20–35 |
| RIVN | TSLA print (sympathy) | Oct 21 AMC | $14.60 | Oct 24 ±$1 OTM | $30–45 |
| INTC | Q3 earnings | Oct 22 AMC | $116 | skip, too expensive | n/a |
| F | Q3 earnings | Oct 27 AMC (verify; some say Oct 23) | $12.10 | Oct 30 ±$0.5 OTM | $15–28 |
| SOFI | Q3 earnings (IM ~8.6–12.5%) | Oct 27 BMO | $15.92 | Oct 30 ±$1 OTM | $35–60 |
| XLF / SLV | FOMC | Oct 28 14:00 | — | Oct 31 weekly | $35–70 |
| RIVN | Q3 earnings | Oct 29 AMC | $14.60 | Oct 31 ±$1 OTM | $35–55 |
| PFE | Q3 earnings (est.) | Nov 3 BMO | $28.52 | Nov 6 ±$1 OTM | $25–40 |
| XLF / GDX | Midterms + JOLTS | Nov 3 | — | Nov 6 weekly | $35–70 |
| XLF / SLV | Oct jobs report | Nov 6 08:30 | — | Nov 13 weekly (close Nov 6) | $40–80 |
| SNAP | Q3 earnings, date unconfirmed | late Oct / early Nov | $5.58 | weekly ±$0.5 OTM | $15–30 |

Out of window: LCID and PLUG (Nov 9), NIO (late Nov). Agent re-verifies every date via the earnings calendar before entry.

## Entry rules
1. Enter 3–7 calendar days before the event, only during 9:30–16:00 ET, only via limit at mid or mid+1 tick after review_option_order dry-run.
2. Contract: expiry 1–4 days after the event, delta 0.30–0.40, open interest ≥ 500, spread ≤ 10% of mid (hard skip > 15%).
3. Per-trade cost ≤ 45% of equity; two-sided (call+put) combined ≤ 60%.
4. Never enter on event day; never enter in the final 30 minutes.
5. If the limit does not fill within one run, cancel and reprice once; then abandon.

## Exit rules
1. Sell-before mode (default): close by 15:45 ET the session before the print (AMC) or at 15:45 the prior day (BMO/8:30 macro).
2. Hold-through mode (flag set): close at 9:35–10:20 ET post-event; no later than 12:30.
3. Profit take: +60% on either leg, close that leg; +150% close all.
4. Pre-event stop: −45% on a leg with 2+ days left, close it.
5. Hard close of everything by 15:00 ET on expiry day. No ITM contracts ever held into close on expiry.

## Sizing & compounding
Start $100. Max 2 open catalysts (≤ 3 contracts total). Deploy up to 90% of equity across them; keep ~$8 cash for fees/repricing. Winnings compound: position size is recomputed from current equity at each entry (45% rule), so a run to $250 means $110 tickets. Below $40, drop to one $15–30 contract per event (SNAP/F/T/PFE tier). Sale proceeds are reusable same day.

## Schedule (ET)
- 9:35: Scan calendar for events 3–7 days out; score; close hold-through positions post-event; check fills.
- 10:20: Second entry window (post-opening spread compression); reprice unfilled orders.
- 12:30: Mark positions, update IV/HV, news sentiment refresh; enforce stops.
- 15:00: Mandatory expiry-day close; evaluate sell-before exits.
- 15:45: Final pre-event sells; cancel all open orders.
- Extra runs at 8:35 and 14:05 on macro-print days.

## Kill switches
- Equity < $15: stop; nothing is affordable with acceptable spread.
- Three consecutive full-loss events: 5 trading-day pause, owner review.
- Any order not dry-run first, any fill ≥ 5% worse than limit, or MCP data stale > 15 min: halt until manual reset.
- Position open at 15:30 on expiry day: close at market-equivalent limit immediately.
- Owner can revoke agent approval in-app at any time.

## Expected path
With ~8–10 events in the window and ~45% win rate on sell-before vega trades (avg +40%) vs. −45% losers, expectancy per trade is roughly −2% after spread drag; the fat right tail comes from the 1–2 hold-through trades where realized move ≥ 1.5× implied (SOFI Apr-26 moved 17.6% on a 9.7% implied). Probability of ruin (< $15): ~30% by 2 weeks, ~55% by 4 weeks. Median outcome at Nov 6: ~$45–65. Upside case (two hold-through hits, e.g., SOFI/RIVN moving 15%+): $250–400, maybe 10% probability.

## What the journal will teach us
Per trade: entry IV, HV, IM/RM, sentiment score, spread at fill, mode (sell-before/hold), P&L by leg, event outcome vs. implied. After 10 events we can answer: does IV actually ramp for sub-$20 names in the last 3–7 days; what IM/RM threshold predicts implied-move beats; whether sentiment-directed single legs beat two-sided strangles; and true spread drag per $1 of premium.

## Sources
- https://www.federalreserve.gov/newsevents/2026-october.htm
- https://fedratecalc.com/fomc-meeting-schedule/october-2026/
- https://www.bls.gov/schedule/2026/10_sched_list.htm
- https://www.bls.gov/schedule/2026/11_sched_list.htm
- https://newsroom.bankofamerica.com/content/newsroom/press-releases/2026/09/bank-of-america-to-report-third-quarter-2026-financial-results-a.html
- https://www.marketbeat.com/earnings/reports/2026-10-22-intel-co-stock/
- https://finance.yahoo.com/markets/stocks/articles/ts-q3-2026-earnings-expect-091739043.html
- https://www.aol.com/articles/sofi-edges-higher-earnings-weeks-194312000.html
- https://www.investing.com/news/stock-market-news/sofi-technologies-stock-may-move-87-on-upcoming-earnings-93CH-4806316
- https://rivian.com/investors
- https://nextearningsdate.com/ford-motor.html
- https://www.marketbeat.com/stocks/NYSE/PFE/earnings/
- https://www.sec.gov/Archives/edgar/data/0001318605/000162828026064366/exhibit991111111.htm
- https://www.washingtonexaminer.com/news/4462055/dates-to-know-2026-midterm-elections/
- https://resolve.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/anticipating-uncertainty-straddles-around-earnings-announcements/7B34877AD5E06304BA3C55FBA3219FDD
- https://alphaarchitect.com/2013/02/straddle-earnings-announcements-and-win/
- https://earnings-watcher.com/wiki/earnings-expected-moves
- https://medium.com/@EarningsWatcher/how-to-profit-from-iv-ush-before-earnings-575574d9db98
- https://robinhood.com/us/en/support/articles/trading-with-your-agent/
- https://nexustrade.io/blog/robinhood-agentic-trading-mcp-review-20260708
- https://www.finder.com/stock-trading/robinhood-agentic-accounts
