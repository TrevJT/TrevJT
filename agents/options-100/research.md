# Research: options-100 agent

## A. Robinhood Trading MCP — options via external agent (as of 2026-10-06)
Source notes: robinhood.com not fetchable from cloud; support-article facts are search extracts. Items marked UNVERIFIED need confirmation on desktop.

### Tools that matter for this agent
- Account: `get_accounts`, `get_portfolio`, `get_option_positions`, `get_realized_pnl`
- Data: `get_option_chains`, `get_option_instruments`, `get_option_quotes` (full Greeks), `get_option_historicals`, `get_equity_quotes`, `get_equity_historicals`, `get_earnings_calendar`, `search`
- Orders: `review_option_order` (dry-run, collateral validation, warnings) -> `place_option_order` -> `cancel_option_order`; `get_option_orders`
- Maybe present: `exercise_option`, `cancel_option_exercise` (UNVERIFIED)
- Old names (`get_account`, `place_order`) do NOT exist.

### Hard constraints on Agentic account options
- Long-only. Single-leg calls/puts bought to open. NO spreads/multi-leg via MCP (as of Jul 2026; UNVERIFIED for Oct).
- Agentic account needs its own Options Level 2+ (separate from main account).
- `place_option_order`: limit and stop_limit only, regular hours only. Market orders rejected. (introspected, UNVERIFIED)
- Limited margin available on Agentic account: reuse unsettled option proceeds same day, no loan/leverage. Cash-type account = T+1 settlement + good-faith-violation risk. => Enable limited margin.
- PDT rule eliminated 2026-06-04; any residual day-trade limit on limited-margin Agentic accounts UNVERIFIED.
- Auto-exercise of ITM longs at expiry if buying power allows; else DNE. Close before expiry to avoid.
- Rate limit ~4 calls/s account-wide (~240/min); back off on RATE_LIMITED.
- No paper trading / sandbox.
- Trade-approvals toggle in Robinhood Agent Settings: ON = agent proposes only; OFF = agent places directly (some trades may still prompt). Default for external MCP agents is disputed -> check in app.
- `review_*` before `place_*` is convention, not enforced. Our rule: always review first.

### OAuth / Claude Code
- `claude mcp add --transport http robinhood-trading https://agent.robinhood.com/mcp/trading`, then `/mcp` -> authenticate in browser (PKCE, no client secret). Access token ~4 days; refresh single-use.
- Authorize step may trigger selfie + ID check (>40 s); callback may fire early. Retry if auth fails.
- Known bug (Claude Code 2.1.167): empty accessToken persisted after successful authorize (anthropics/claude-code#65895). Workaround: manual token in ~/.claude/.credentials.json under mcpOAuth. Status on current version UNVERIFIED.
- `claude mcp login robinhood-trading --no-browser` exists for headless.
- Cloud/remote sessions cannot reach agent.robinhood.com -> local desktop session required.

### Sources
- https://github.com/Codejrangel/robinhood-mcp-client/blob/main/TOOLS.md
- https://github.com/kevin1chun/robinhood-for-agents/blob/main/docs/official-mcp-tools.md
- https://robinhood.com/us/en/support/articles/onboarding-an-external-agent/
- https://robinhood.com/us/en/support/articles/setting-up-an-agent/
- https://robinhood.com/us/en/support/articles/trading-with-your-agent/
- https://robinhood.com/us/en/support/articles/pattern-day-trading/
- https://github.com/anthropics/claude-code/issues/65895
- https://nexustrade.io/blog/robinhood-agentic-trading-mcp-review-20260708
- https://medium.com/p/33d3725a23e0

## B. Defined-risk options with $100 (as of Oct 2026)

### Gating facts
- Spreads need Level 3 + margin-type account; Agentic MCP is single-leg long only anyway. => Long calls/puts ONLY.
- Fees ≈ $0.09/contract round trip. Negligible vs bid-ask drag.
- PDT repealed 2026-06-04. Cash-type account: T+1 settlement, good-faith-violation risk => one round trip/day on settled cash unless limited margin is enabled.
- No paper trading.

### Feasible underlyings (approx Oct 2026)
- F ~$14: 500k+ contracts/day, ATM spread ~$0.01, weekly ATM $0.20–0.35, 14–45 DTE ATM ~$0.30–0.60. Best fit.
- SOFI ~$18: IV 50–70%, weekly ATM $0.50–0.90. More movement per dollar, wider spreads.
- NIO ~$5: contracts $0.05–0.25, spreads often 20% of premium. Marginal.
- XLF ~$57, SLV ~$59: OTM singles $0.15–0.50; ATM $0.50–1.50 (one contract, often over budget).
- SPY/QQQ/IWM: singles unaffordable except far-OTM 0DTE lottos $0.05–0.30 (worst learning vehicle).
- Excluded: PLTR (~$190), GDX, SPX/XSP, CSPs, covered calls, credit structures.

### Strategy stats
- Long ATM/ITM single, 14–45 DTE, +50%/−50%/time-stop: win rate ~35–50%, expectancy ~0 before skill. Survives ~6–10 losses.
- 0DTE long OTM singles: win rate 25–40%; retail 0DTE buyers lose on aggregate, ~60% of losses are transaction costs. Survives 5–10 trades.
- Theta: ATM loses 5–10%/week in final 30 days; <7 DTE = max decay.
- Earnings: F Oct 22, SOFI Oct 27. IV crush 30–50% overnight.
- Rule: never trade a contract whose bid-ask > 10% of its price; limit at mid.
- Realistic cadence: 3–5 trades/week, shrinking with balance.

### Sources
- https://robinhood.com/support/articles/options-investing/
- https://robinhood.com/support/articles/trading-fees-on-robinhood/
- https://robinhood.com/support/articles/360001214723/expiration-exercise-and-assignment/
- https://apexvol.com/options/f
- https://fintel.io/siv/us/sofi
- https://optionalpha.com/blog/0dte-options-strategy-performance
- https://neudata.co/literature-reviews/zero-day-to-expiry-options-a-losing-bet-for-retail-traders
- https://ryanoconnellfinance.com/option-theta/
- https://crosstrade.io/learn/risk-management/risk-of-ruin
- https://www.quantinsti.com/articles/finra-pdt-rule-removal-2026/
