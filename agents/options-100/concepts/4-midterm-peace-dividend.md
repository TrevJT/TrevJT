# Concept 4: Midterm Miracle + Peace Dividend (drafted 2026-10-06)

## Thesis
Two scheduled/priced-low catalysts overlap in the next 90 days: the post-midterm seasonal window (Q4 midterm year → Q2 pre-election year, S&P avg +20%, 19/19 positive 12 months after election day since 1950) and a cluster of "peace" headlines that history shows move specific cheap names 6–11% in a day: a US–Iran deal / Hormuz reopening (airlines +6–10%, cruise +8–11%, oil −16% on Apr 8 2026), a US–China grand deal (NIO/XPEV/LI +6–8% on May 12 2025), a Russia–Ukraine ceasefire (12% priced by Oct 31, 55% by Jun 2027; CNH/ag-construction, EU builders up, EU defense −5–7%). We buy 70–100 DTE calls on beaten-down, high-short-interest beneficiaries so the book survives the Nov 3 vote and sells INTO the headline spike.

## Honest read on the midterm statistics
Real: best three quarters of the cycle, never down 12 months post-election (n=19), worst case +1.9%. But 2026 lacks every usual precondition: no deep midterm low (−8.9% in March vs ~19% norm), record highs, Fed hiking (3.75–4.00%), 10-yr 5.3%, CAPE near record, and the likely R-president + D-Congress combo is the weakest gridlock configuration (~5–8% avg). Treat it as a tailwind that raises the odds the peace trades have a bid, not as a standalone thesis.

## Universe (live Robinhood quotes 2026-10-06, Jan 15 2027 expiry unless noted)
| Ticker | Last | Why cheap | Headline | Contract | Bid/Ask | Δ | IV | OI | Cost |
|---|---|---|---|---|---|---|---|---|---|
| JBLU | 4.14 | P/S 0.19, short 29.5% float | Iran deal / oil crash | Jan 4C | 0.60/0.66 | 0.62 | 63% | 4.5k | $63 |
| JBLU | | | | Jan 5C | 0.23/0.25 | 0.34 | 58% | 27.6k | $24 |
| NIO | 3.43 | 52w low, P/S 0.5 | US–China deal | Jan 3.5C | 0.36/0.40 | 0.54 | 56% | 22.8k | $38 |
| NIO | | | | Jan 4C | 0.20/0.21 | 0.36 | 55% | 35.8k | $21 |
| CNH | 13.40 | Ukraine ag/rebuild proxy | Ukraine ceasefire | Jan 15C | 0.55/0.65 | 0.35 | 40% | 32.6k | $60 |
| NCLH | 15.59 | P/E 9.9, 52w −36%, short 21% | Iran deal + risk-on | Jan 17C | 1.17/1.23 | 0.44 | 51% | 11.5k | $120 (too rich single; spread only) |
| AAL | 13.14 | P/S 0.15 | Iran deal | Jan 14C | 0.97/1.01 | 0.46 | 46% | 3.5k | $99 |
| LI | 10.83 | net cash ≈ price | US–China | Jan 12C | 0.67/0.72 | 0.41 | 48% | 212 | $70 |
| CLF | 12.39 | P/S 0.36, short 14% | risk-on / rebuild | Jan 13C | 1.44/1.51 | 0.52 | 65% | 3.4k | $148 (no) |
Rejected: DHT puts (bid/ask 2.20/3.10, OI 197: spread 34%), EUAD puts (stale, 0.15/2.05), MOS puts ($118–142, over budget), ZIM (pinned by $35 cash bid), IWM/KRE calls ($185–298).

## Level 3 unlock
Agentic account is options Level 3; review_option_order accepted a 2-leg debit spread with no warnings. Debit call spreads cut cost ~40% and let the book hold 3 themes instead of 2.

## Allocation ($100), primary
| Leg | Order | Net cost | Max gain | Theme |
|---|---|---|---|---|
| A | Buy JBLU Jan 4C / sell JBLU Jan 5C (debit spread) | ~$39 | $61 (+156%) | Iran / oil |
| B | Buy NIO Jan 3.5C (single) | ~$38 | unlimited; +100% at 4.26 | US–China |
| C | Buy NIO Jan 4C (single) | ~$21 | lottery leg | US–China |
Total ≈ $98. Alternate (all-long): JBLU Jan 4C $63 + NIO Jan 4C $21 = $84, $16 reserve. CNH Jan 15C ($60) replaces NIO if a Ukraine talks date is announced before entry.

## Model (daily score, 9:40 ET)
Per theme: headline-probability proxy (Polymarket odds; store daily), 5-day momentum of the underlying, IV percentile (do not buy after IV > 70th pct), news score from `search` (agent reads ≤10 headlines, −2…+2). Enter only when IV percentile < 60 and news score ≥ 0 (buy quiet, sell loud). Re-score daily; if a theme's odds collapse (e.g. talks cancelled) and position < −40%, cut and rotate into the next-best theme.

## Entry rules
1. Enter in two tranches: 60% on approval day at 10:20 ET, 40% next day, limit at mid, reprice +1 tick after 10 min, cancel at 30 min.
2. Always review_option_order first; abort on any mismatch.
3. Never enter within 2 trading days before the underlying's earnings (JBLU Oct 27, AAL Oct 22, NCLH Nov 3). Spreads may be held through earnings; singles are closed the day before unless > +50%.

## Exit rules
- Headline spike: at the first run after a qualifying headline (Iran deal / Hormuz open / US–China deal / Ukraine ceasefire), sell 100% of that theme into the move at mid−1 tick. Do not wait for a better print; these moves fade 30–50% within 3 sessions.
- +100% on any leg without a headline: sell half.
- −60% on any leg: close.
- Hard date: close everything by Jan 8 2027 (one week before expiry), or earlier at +150% book-level.
- Nov 3–4: no selling into election-night noise; first exit window Nov 5 10:20.

## Schedule (ET)
9:40 score + news; 12:30 headline check + stops; 15:30 marks, earnings-proximity closes, journal. Extra 9:35 run on any day with a scheduled Iran/Ukraine/China summit or FOMC (Oct 28).

## Kill switches
Balance < $15; MCP order error twice; any fill ≥ 5% worse than limit; `STOP` file in repo → flatten.

## Expected path
Three uncorrelated lottery tickets with 70–100 days of life. Rough odds: Iran deal by Jan ~35% (Polymarket 32% by Dec), US–China deal headline ~30%, Ukraine ceasefire ~15%. P(at least one headline hits while positioned) ≈ 60%. A hit pays +80–150% on that theme; theta bleeds ~25% a month on the singles. P(ruin, book < $15 by Jan 8) ≈ 35%. Median ≈ $70–110. Upside: two hits ≈ $220–300 (~15%).

## What the journal teaches
Whether "buy quiet, sell loud" beats chasing; realized theta on 70-DTE sub-$5 calls; spread vs single P&L on the same headline; how much of the first-day spike survives to the next run.
