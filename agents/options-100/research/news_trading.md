# Trading single-stock news with long options: is it priced in by the time we see it?

2026-10-13. Prompted by today's MU/STX/WDC chip sell-off. Code: `bot/research_news.py` (`fetch | events [--excess] [--with-earnings] | contagion [--excess] | latency`).
Data: Yahoo 1h bars (2023-11-14..2026-10-08, 730 sessions), 3y daily bars, and earnings dates, for 81 liquid optionable names in 12 sector groups. Cache: `data/research_news_cache.pkl` (gitignored).

## Verdict

**Yes, it is priced in.** By the time a 5-minute RSS poller sees a single-stock news shock, the move has already happened.
- At the median shock, **97% of the prev-close -> 3-day-close move is done by 10:30 ET**.
- After a >=4% non-earnings shock (n=4,220), the **market-adjusted drift is about 0** at every horizon: +0.03% to the close, +0.07% at 3 days, |t| < 1.
- Buying an ATM option after the shock loses about **-33% to -53% of premium** (proxy; IV assumed = 1.5x 20-day realized vol), in *either* direction.

The algos do not even need to be fast here: today's MU/STX/WDC move **happened overnight / pre-market, before any US headline**.

**Tradable with long options:** nothing robust. The one candidate is a *vol-scaled* shock (|10:30 move| >= 3x the stock's 20-day daily RV) during a *sector-wide* move.
- It continued **+0.49% (SPY-excess) to the same-day close**, with a 59% hit rate and a day-clustered t of 2.1 (n=269 over 123 dates).
- That t is what you'd expect by chance after about 90 subgroup x horizon tests.
- Over the full vol-scaled set, the effect halved from the first half to the second half: +0.57% -> +0.19% excess to close.
- The option-ROI proxy falls from about +48% in the first half to **-4% in the second half**, before 2–5% bid/ask on single-stock weeklies.

**Do not build a news-chasing strategy.** At most, log vol-scaled sector shocks and paper-track them.

**Second-order contagion** (when a leader shocks, do unmoved peers catch up?): **no**.
- Laggard peers drift +0.04% excess to the close (day-clustered t 1.4).
- In the second half: +0.01% to the close, +0.03% at 3 days. It is dead.
- In today's case, STX/WDC moved *more* than MU, and all three were rebounding by the time the headlines landed.

**Realtime feed recommendation:**
- **Alpaca News websocket** (Benzinga-sourced, free with a paper account) is the best upgrade. **Trevor must create the account and supply the key/secret.**
- The **SEC EDGAR 8-K Atom feed** needs no account; poll it every 15–30s with a User-Agent that includes an email.
- A faster feed would not have saved today. Its real value is *avoiding* stale entries, e.g. "don't buy puts at 10:38 on a move that bottomed at 09:25." It does not create alpha for a long-premium buyer.
- The most useful realtime signal we already have is **price itself**: a Robinhood scan or live quotes for gap/z-score, which beat every headline.

## 1. Today's latency check (5m bars incl. pre-market, Yahoo; snapshot at 10:45 ET)

| | prev close | 04:00 (pre-mkt open) | extreme (time) | 09:13 CNBC "Micron drops 5%" | 09:51 CNBC "...sink as sell-off deepens" | 10:38 StockStory "...Plummet" | 10:45 |
|---|---|---|---|---|---|---|---|
| MU | 989.04 | -2.9% | -6.3% (09:30) | -5.3% | -4.7% | -4.4% | -4.8% |
| STX | 753.25 | -3.5% | -9.1% (09:25) | -8.2% | -5.2% | -3.4% | -3.2% |
| WDC | 386.94 | -3.8% | -8.9% (09:25) | -7.8% | -5.3% | -3.5% | -3.0% |
| SNDK | 1487.33 | n/a | -5.8% (09:25) | -4.6% | -3.9% | -2.4% | -2.7% |
| SMH | 590.99 | n/a | -2.8% (09:30) | -2.0% | -1.5% | -1.5% | -1.5% |
| SOXX | 544.85 | n/a | -3.3% (09:30) | -2.3% | -1.6% | -1.7% | -1.7% |

- **When it happened:** STX/WDC were already -3.5% to -3.8% at the *first* pre-market print (04:00 ET), with no after-hours prints on 10-12. So the catalyst hit overnight, most likely in the Asia session, and slid to the lows by 09:25 ET.
- **09:13 headline:** the move was 85–90% done relative to the extreme.
- **09:51 headline:** STX/WDC had already retraced about 40% of the drop.
- **10:38 headline:** "Plummet" printed after **more than 60% of the STX/WDC drop had reversed**. Buying puts on it would have bought the bounce's IV at the worst price.
- **Vol context:** these names run 2.8–4.3% daily 20-day RV, so a 4% move is only **0.7–1.5 sigma** for them (z at 10:30: MU 1.5, STX 0.8, WDC 0.9). Today is not a "vol-scaled" shock at all.

## 2. Event study: >=4% shocks (gap or 10:30 vs prev close), earnings excluded

- **Sample:** 4,787 shocks, of which 567 are earnings-tagged. A tag means an earnings date on day d (pre-market) or d-1 (after close); unknown times tag both days.
- **Sign convention:** returns are signed in the shock direction as seen at 10:30, so + = continuation.
- **Two t-stats:** "t" treats events as independent. **"t-cl" is day-clustered** (averaged by date first) and is the honest one, because shocks cluster on macro days.
- **Excess:** stock log return minus SPY over the same window (beta 1).

### Raw vs SPY-excess, 10:30 entry

| subset | n | ->close raw | ->close excess (t-cl) | ->next close excess (t-cl) | ->3d close excess (t-cl) |
|---|---|---|---|---|---|
| Control: non-shock days, first hour up | 27,787 | -0.00% | -0.01% (-0.9) | -0.01% (-0.6) | +0.02% (+0.3) |
| Control: non-shock, first hour down | 25,333 | -0.02% | +0.02% (+1.7) | -0.01% (-0.9) | -0.04% (-0.9) |
| **All shocks** | 4,220 | +0.02% | +0.03% (+1.1) | +0.07% (+0.2) | +0.07% (+0.7) |
| first half (<2025-04-28) | 1,831 | -0.02% | +0.03% (+2.3) | +0.09% (+2.1) | +0.06% (+1.3) |
| second half | 2,389 | +0.05% | +0.03% (-0.2) | +0.05% (+0.3) | +0.08% (+1.2) |
| DOWN shocks | 1,896 | +0.01% | -0.04% (-0.8) | -0.22% (-2.4) | -0.50% (-2.4) |
| UP shocks | 2,324 | +0.03% | +0.08% (+1.6) | +0.31% (+2.7) | +0.54% (+2.4) |
| Sector contagion (>=2 peers moved >=2.5% same way) | 3,211 | +0.01% | +0.01% (+2.4) | +0.10% (+1.5) | +0.14% (+2.4) |
| Idiosyncratic | 1,009 | +0.06% | +0.07% (+0.8) | -0.02% (+0.2) | -0.13% (-0.2) |
| SPY up at 10:30 | 2,341 | +0.04% | +0.10% (+1.5) | +0.29% (+1.9) | +0.49% (+1.4) |
| SPY down at 10:30 | 1,877 | -0.00% | -0.06% (-0.4) | -0.21% (-0.7) | -0.45% (-0.7) |
| DOWN shock & SPY down | 1,499 | -0.05% | -0.11% (-0.3) | -0.34% (-0.9) | -0.71% (-0.2) |
| semis + memory | 2,029 | +0.19% | +0.16% (+1.8) | +0.26% (+1.3) | +0.27% (+1.8) |
| BIG (>=8%) | 531 | +0.12% | +0.00% (+0.5) | -0.29% (-0.2) | -0.46% (+0.3) |
| **Vol-scaled (>=3x RV20)** | 386 | +0.59% | +0.39% (+1.6) | +0.30% (+0.6) | +0.39% (+0.5) |
| vol-scaled, first half | 201 | +0.84% | +0.57% (+1.1) | +0.32% (0.0) | +0.17% (-0.7) |
| vol-scaled, second half | 185 | +0.33% | +0.19% (+1.2) | +0.27% (+0.9) | +0.63% (+1.6) |
| **vol-scaled + sector contagion** | 269 | +0.77% | **+0.49% (+2.1)** | +0.46% (+1.5) | +0.79% (+1.7) |
| vol-scaled, idiosyncratic | 117 | +0.19% | +0.16% (+0.8) | -0.07% (0.0) | -0.55% (-0.9) |
| (ref) earnings shocks | 567 | +0.17% | +0.15% (+0.6) | +0.26% (+1.8) | +0.33% (+1.1) |

Entries at 11:30 look the same: slightly smaller same-day numbers and the same multi-day pattern. Medians and hit rates are in the script output; hit rates are 47–55% everywhere except the vol-scaled subset (56–64%).

**Reading:**
- **Up/down asymmetry:** in excess terms, down shocks keep falling (-0.5% over 3 days) and up shocks keep rising (+0.5%). That is consistent with high-beta names in a 2023–26 bull market: a beta-1 adjustment under-corrects for MSTR/COIN/SMCI-type names.
- **Not tradable:** a 0.5% three-day drift is about 0.1 sigma for these names, which is nothing against option premium.
- **"Sector contagion" and "SPY regime" splits:** neither produces a stable edge.

### Option proxy: can a long option bought after the shock beat its premium?

**Assumptions:**
- No historical single-stock IV here, so post-shock IV = **BUMP x pre-shock 20-day close-to-close RV**, with BUMP = 1.5 (also shown at 1.25 and 2.0).
- Real post-shock IV on a name like STX after a gap is often 1.3–2x its prior RV.
- Intraday variance share uses 75% of daily variance during RTH.
- ATM straddle E|move| = 0.798·sigma·sqrt(t); a single ATM call/put costs about 0.399·sigma·sqrt(t).
- Continuation ROI = mean(max(signed move, 0)) / premium - 1. It ignores spread, skew, theta path and early exit.
- **Calibration:** on non-shock days, realized/RV20 is 0.65 to the close and 0.96 at 3 days, so the scaling is sane. A normal day's afternoon realizes less than RV20 implies, which matches the earlier SPY VRP finding.

| subset (10:30 entry) | realized/RV20 (->close / ->next / ->3d) | realized/implied @1.25x / 1.5x / 2.0x (->next close) | continuation ROI @1.5x (->close / ->next / ->3d) | fade ROI @1.5x (->3d) |
|---|---|---|---|---|
| all shocks | ~0.65–0.8 | 0.73 / 0.61 / 0.46 | -48% / -34% / -33% | -37% |
| DOWN shocks | — | 0.76 / 0.63 / 0.48 | -47% / -37% / -40% | -25% |
| UP shocks | 0.76 / 0.89 / 0.94 | 0.71 / 0.59 / 0.44 | -48% / -32% / -27% | -47% |
| vol-scaled, all | 1.38 / 1.60 / 1.48 | 1.28 / 1.07 / 0.80 | +22% / +38% / +23% | -25% |
| vol-scaled, first half | 1.56 / 1.85 / 1.78 | 1.48 / 1.24 / 0.93 | +48% / +72% / +50% | -12% |
| **vol-scaled, second half** | 1.22 / 1.37 / 1.20 | 1.09 / 0.91 / 0.68 | **-4% / +6% / -2%** | -38% |
| calibration: non-shock days | 0.65 / 0.85 / 0.96 | 0.68 / 0.56 / 0.42 | -56% / -43% / -34% | -38% |

**Interpretation:**
- **Ordinary >=4% shocks:** these are mostly ~1-sigma moves in volatile names. Afterwards they realize *less* than their own normal vol, so options bought after them are expensive.
- **Genuine >=3-sigma shocks:** these keep realizing 1.2–1.9x RV20 for days. That roughly equals the 1.5x IV bump the market charges, i.e. it's priced. The first-half profit did not survive into the second half.
- **No edge:** the second-half number is about break-even *before* spreads and depends entirely on the IV assumption. With the real IV bump at 2x, every row is negative.

## 3. Second-order contagion: leader shock -> unmoved peers

- **Leader:** a name with a >=4% move by 10:30 (non-earnings).
- **Laggard:** a same-group peer whose own 10:30 move in the leader's direction is less than 1/3 of the leader's.
- **Sign:** returns are signed in the leader's direction and SPY-excess.

| subset | n (dates) | 10:30->close (t-cl) | 11:30->close | ->next close (t-cl) | ->3d close (t-cl) |
|---|---|---|---|---|---|
| all laggards | 8,966 (634) | +0.04% (+1.4) | -0.01% | +0.08% (+1.1) | +0.13% (+0.3) |
| first half | 4,227 (314) | +0.08% (+1.5) | +0.04% | +0.13% (+1.0) | +0.24% (+0.9) |
| **second half** | 4,739 (320) | **+0.01% (+0.5)** | -0.06% | +0.03% (+0.5) | +0.03% (-0.6) |
| leader DOWN | 3,727 (380) | +0.05% (+1.4) | -0.01% | +0.03% (+0.6) | +0.05% (+0.1) |
| leader UP | 5,239 (482) | +0.04% (+0.7) | -0.01% | +0.11% (+2.1) | +0.18% (+2.0) |
| semis/memory leaders | 5,288 (479) | +0.07% (+1.6) | -0.01% | +0.04% (+0.8) | +0.07% (+0.8) |
| control: peers that already moved | 5,916 (604) | +0.02% (+1.6) | +0.03% | +0.03% (+1.0) | +0.01% (+1.1) |

**No catch-up.** Peers that haven't moved by 10:30 have decided the news isn't about them, and the market agrees. The memory-group anecdotes run both ways: STX down on 08-03 led MU -9% the next day, while STX down on 10-06 saw MU rise. Anecdotes are not a signal.

## 4. Realtime news sources (web research 2026-10-13; some prices come from third-party pages and are marked "?")

| source | push? | latency | cost | account needed (Trevor) | notes |
|---|---|---|---|---|---|
| **Alpaca News** `wss://stream.data.alpaca.markets/v1beta1/news` | websocket (+REST history) | seconds (Benzinga wire) | **free** on the Basic plan with a paper account; REST 200/min | **yes**: free account + key/secret | tickers on every item, subscribe to `*`; some forum reports of sudden 403s |
| SEC EDGAR `browse-edgar?action=getcurrent&type=8-K&output=atom` | poll | about 1 min after acceptance | free | **no** (User-Agent with name+email, 10 req/s) | primary source; map CIK to ticker; filings accepted 06:00–22:00 ET |
| Finnhub | REST poll (websocket news premium?) | minutes | free 60/min | yes | free websocket reportedly flaky |
| Massive (ex-Polygon) news | REST | **updated hourly** | $0–$199 | yes | too slow |
| Benzinga Pro / API | websocket/webhook | fastest | Pro about $99–457/mo?, API quote-only | yes | overkill; Alpaca already relays Benzinga |
| Tiingo News | REST | unknown | free starter / about $30? | yes | no push |
| PR Newswire / BusinessWire / GlobeNewswire RSS | poll | minutes | free | no | primary press releases, usually without tickers |
| X API (@DeItaone, @FirstSquawk) | poll | seconds | pay-per-use about $0.005/read? (a few $/mo for 2 accounts) | yes (developer account + credits) | Nitter/RSS bridges are mostly dead since Aug 2026 |
| Nasdaq / Seeking Alpha / Yahoo per-ticker RSS | poll | minutes | free | no | same tier as the current RSS feeds |
| **Robinhood MCP** | none for news | — | — | already set up | no news tool. Has `get_sec_filing_index` (8-K by symbol), price/indicator **alerts** (log must be polled, not pushed), and live **scans** (a top-movers or gap scan is the fastest "news" signal available) |

**Recommendation:**
1. Add EDGAR 8-K polling now; it needs no account.
2. Ask Trevor whether he wants a free Alpaca paper account for the Benzinga websocket.
3. Use both as **risk filters / staleness guards**, not entry triggers. Before any entry, the rule is: if the headline's ticker has already moved >=1.5 sigma since the prior close, the news is in the price.

## Caveats
- **Window:** 2 years of hourly data covering one regime (an AI/semis bull market). Repeated 4% shocks in MSTR/COIN/SMCI-type names dominate the counts.
- **Multiple testing:** about 15 subsets x 6 horizons x 2 (raw/excess) = about 180 numbers. A few |t| > 2 are expected by chance. Only the day-clustered t is meaningful, and none survives a Bonferroni-ish bar (~3.3).
- **Implied vol:** this is a proxy (RV x bump), not observed IV. Single-stock option spreads (2–10% of premium on weeklies) are not modeled and make every number worse for a buyer.
- **News flag:** "shock" means a price move, not a news headline. Moves with no news (flows, macro) are mixed in. Earnings dates come from Yahoo; misses would leak earnings days into the sample.
- **Data checks:** yfinance hourly bars are split-adjusted, and split days produce no false shocks (checked NVDA 2024-06-10, AVGO 2024-07-15, SMCI 2024-10-01, LRCX 2024-10-03). The pre-market 5m prints for latency are thin (Yahoo shows 0 volume pre-market).
