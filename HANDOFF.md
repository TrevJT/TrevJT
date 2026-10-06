# Handoff: options-100 agent (continue in Claude Code desktop)

## Why desktop
Cloud session network policy blocks agent.robinhood.com and robinhood.com; no browser tools there. Desktop has local network + browser for the OAuth step.

## Setup on desktop
1. `git clone https://github.com/TrevJT/TrevJT && cd TrevJT && git checkout claude/options-agent-setup`
2. `claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading`
3. In Claude Code: `/mcp` -> robinhood-trading -> authenticate (browser OAuth).
4. In Robinhood app: Agentic account funded with $100, trade approvals OFF (fully autonomous after plan approval).

## Agreed parameters (from Trevor)
- Capital: $100. Treat as already lost. Learning/test account; the riskiest of several agents.
- Max daily loss: all of it.
- Options ONLY. No stocks, no crypto.
- Fully autonomous AFTER a written plan is articulated and Trevor approves it.
- Orchestrator runs sub-agents, answers their questions itself, never stops until the task completes.
- Keep replies extremely concise.

## First task on desktop (PLAN.md and research.md already on this branch)
1. Verify MCP tools: list accounts, confirm Agentic account id + buying power, pull an option chain.
2. Write `agents/options-100/PLAN.md` (strategy, entry/exit rules, sizing, max trades/week, what we expect to learn), present to Trevor, wait for approval.
3. Then trade autonomously; log every decision to `journal/options-100.jsonl`.

## Research in flight (cloud session)
Two agents were researching (a) Robinhood MCP tool surface + agentic options rules, (b) defined-risk options strategies for $100. Results will be appended to `agents/options-100/research.md` on this branch if they land before the cloud session ends.
