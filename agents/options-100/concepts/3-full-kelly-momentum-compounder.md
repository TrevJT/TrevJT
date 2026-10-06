# Concept 3: Full-Kelly Momentum Compounder

## Thesis (why this is the aggressive edge)
Short-horizon continuation is real but conditional: Medhat & Schmeling show one-month returns *continue* in high-turnover stocks and *reverse* in low-turnover ones, and the effect is strongest in volatile names. Lopez-Lira & Tang show LLM headline scores predict next-day returns, most strongly in small caps and after negative news. We combine both: buy 7–21 DTE options only on names that are already moving, on surging volume, with headline confirmation, and let convexity do the work. Honest framing: with $100, the minimum ticket forces sizing far above true Kelly, so this is a lottery with a slightly better ticket-picking rule, not a positive-growth system.

## Model
Score each ticker at 9:40 ET from MCP data; all factors z-scored across the universe, clipped to ±2.
| Factor | Computation | Wt |
|---|---|---|
| Momentum | 0.5·(5d return) + 0.5·(20d return), signed | 20% |
| Relative strength | 10d return minus sector ETF (ARKK/KWEB/XLK/XLF/IPAY) from equity historicals | 15% |
| Volume surge | Today's projected volume ÷ 20d ADV; hard gate ≥1.5× (turnover = continuation regime) | 15% |
| LLM news | Agent reads ≤10 headlines (48h), scores each −2…+2 as "good/bad/irrelevant for price," averages | 20% |
| IV percentile | 30d IV from option Greeks vs. 60d realized vol from historicals; IV/HV <1.2 = +, >1.6 = − | 15% |
| Short interest | From news search / last snapshot; >15% float plus positive momentum = +, else 0 | 15% |

Composite S ∈ [−100, 100]. **Trade only if |S| ≥ 60 and momentum, RS and news agree in sign.** S>0 → call; S<0 → put. Contract: nearest weekly with 7–14 DTE, delta 0.40–0.50, mid $25–$90, spread ≤12% of mid. **Roll-up rule:** when P&L ≥ +80% and S ≥ 60 at a check, sell to close, buy to open the next strike up (delta ~0.40–0.45) in the following weekly with all proceeds; max 3 rolls per trend, then take profit entirely.

## Universe (approx. prices Oct 2–5 2026; premium = ATM 10–14 DTE est.)
| Ticker | Price | IV / beta | Est. premium | Next earnings |
|---|---|---|---|---|
| SOFI | $18.0 | ~55% / 1.9 | $65–80 | Oct 27 |
| RIVN | $14.6 | ~70% / 2.0 | $70–85 | Oct 22 |
| RGTI | $14.9 | ~100% / 2.8 | $85–115 (go 5% OTM) | ~Nov 10 |
| QBTS | ~$21 | ~100% / 2.7 | $80–100 (10% OTM) | Nov 5 |
| QS | $7.05 | ~95% / 2.3 | $45–55 | Oct 28 |
| JOBY | $5.75 | ~80% / 2.1 | $30–40 | ~Nov 4 |
| ACHR | $5.05 | ~85% / 2.4 | $30–38 | ~Nov 5 |
| SNAP | ~$5.3 | ~70% / 1.5 | $25–32 | Nov 4 |
| LCID | $4.17 | ~80% / 1.6 | $22–30 | Nov 9 |
| NIO | $3.68 | ~75% / 1.4 | $18–25 | Nov 11 |
| OPEN | ~$3.5 | ~110% / 2.9 | $25–35 | Nov 5 |
| PLUG | ~$2.2 | ~100% / 2.6 | $12–20 (marginal) | early Nov |
Excluded: IONQ (~$35), SMCI (~$30), INTC (ran past $30), F/BAC/PFE/T (beta too low). Sub-$5 names carry 15–25% spreads on $0.25 contracts; the spread gate will often skip them.

## Entry rules
1. 9:40 run only; never buy in the first 10 minutes or after 15:00.
2. Pass all gates: |S|≥60, sign agreement, volume ≥1.5×ADV, spread ≤12%, DTE 7–14, earnings not inside the hold window + 1 day.
3. Limit at mid (step to mid+1 tick after 5 min; cancel at 15 min unfilled).
4. Always `review_option_order` first; abort on any mismatch in symbol, side, quantity, or price.
5. One position at a time; if flat and no ticker qualifies, stay in cash.

## Exit rules
- **Take-profit/roll:** +80% → roll up per rule above; +150% without roll conditions → sell entirely.
- **Stop:** −50% of premium (checked 12:30 and 15:30 only; intraday noise is ignored on purpose). If a stop cannot fill at ≤12% below mid, ride.
- **Time stop:** close at 15:30 on day 7 of the hold or at 3 DTE, whichever first; never hold into expiry day (auto-exercise risk).
- **Earnings:** close by 15:30 the session before any earnings date.

## Sizing & compounding
Kelly for p≈0.38, win +120%, loss −50%: f* = 0.38/0.5 − 0.62/1.2 ≈ 0.24 of bankroll. The cheapest viable ticket ($25–90) is 50–90% of a $100 balance, i.e. 2–4× Kelly—the zone where expected log-growth is **negative** (g(0.8) ≈ 0.38·ln1.96 + 0.62·ln0.6 ≈ −0.06/trade). We accept this. Rule: buy the largest whole contract count ≤ 90% of balance (initially 1 contract). On a win, 100% of proceeds redeploy into the roll or the next signal. Max open positions: 1 (2 only when balance > $300 and both have |S|≥70, opposite sectors).

## Schedule (ET)
- **9:40** – Pull historicals, chains, news; score universe; place entry or roll; log.
- **12:30** – Check stop/roll; re-score held name only; cancel stale orders.
- **15:30** – Final stop/roll/time-stop/earnings/expiry checks; Friday: close anything expiring that day; write journal.

## Kill switches
- Balance < $20 → halt (nothing buyable).
- 3 consecutive losses → 2-trading-day cooldown.
- SPY −2% intraday at run time → no new calls; SPY +2% → no new puts.
- Spread > 12% of mid or option volume < 100 → skip.
- Any `place_option_order` rejection or review mismatch → halt until owner reviews.
- `STOP` file in repo → flatten at next run.

## Expected path
Approx. 3 trades per 2 weeks, 6 per 4 weeks, p(win)≈0.38, loss ≈45% of balance, ruin ≡ balance < ticket. Ruin by 2 weeks ≈ P(≥2 losses in 3) = 3·0.62²·0.38 + 0.62³ ≈ **65%**; by 4 weeks ≈ **80%**. Median outcome: ~$25–45 remaining, then stuck. Upside: 3 straight wins (p≈5.5%) ≈ $100→$750; 2 wins/1 loss sequences (p≈27%) ≈ $150–250. Rough P(≥$300 at 4 weeks) ≈ 8–12%.

## What the journal will teach us
Per trade: S and each factor, LLM headline scores and the headlines, fill vs mid (true spread cost), IV at entry/exit, outcome. After 20 trades we learn which factor predicts fills that reach +80%, whether news score adds to momentum alone, realized slippage per price tier, and whether the roll rule or a flat +100% exit compounds better.

## Sources
- https://alphaarchitect.com/short-term-momentum/
- https://cepr.org/publications/dp15857
- https://arxiv.org/abs/2304.07619
- https://en.wikipedia.org/wiki/Kelly_criterion
- https://www.marketbeat.com/earnings/reports/2026-10-27-sofi-technologies-inc-stock/
- https://247wallst.com/investing/2026/10/02/rivian-jumps-4-after-delivering-19248-vehicles-and-reaffirming-full-year-guidance-tesla-rises-2/
- https://www.heygotrade.com/en/us-stock/rgti/
- https://www.tradingview.com/news/tradingview:d60ebf8ce5813:0-lucid-reports-q3-2026-production-2-954-and-deliveries-3-806-sets-nov-9-earnings-date/
- https://www.marketbeat.com/earnings/reports/2026-10-28-ford-motor-stock/
- https://www.tipranks.com/stocks/qs/earnings
- https://marketchameleon.com/Overview/RGTI/Earnings/Earnings-Dates/
- https://flashalpha.com/stock/rgti/iv
- https://www.everhint.com/stock-market-news-october-05-2026-evening-update-last-12-hours-pacific-time/
