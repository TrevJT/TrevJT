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
