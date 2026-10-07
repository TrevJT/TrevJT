#!/bin/bash
# options-100 failsafe. launchd runs this every 120 s. If the orchestrator session's heartbeat is stale during
# market hours, run ONE cycle through a fresh one-shot Claude Code run (same MCP tools, same rules).
REPO=$HOME/code/TrevJT; S=$REPO/agents/options-100/state; LOG=$S/failsafe.log
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH
mkdir -p "$S"
dow=$(TZ=America/New_York date +%u); hm=$(TZ=America/New_York date +%H%M); now=$(date +%s)
[ "$dow" -ge 6 ] && exit 0
[ "$((10#$hm))" -lt 924 ] && exit 0
[ "$((10#$hm))" -gt 1606 ] && exit 0
caffeinate -i -t 150 &
[ -f "$REPO/STOP" ] && exit 0
python3 -c "import json,sys,datetime;d=json.load(open('$S/day.json'));p=json.load(open('$S/positions.json'));sys.exit(0 if d.get('halted') and not p and d.get('date')==datetime.date.today().isoformat() else 1)" 2>/dev/null && exit 0   # halted + flat: nothing to protect
hb=0; [ -f "$S/heartbeat.json" ] && hb=$(stat -f %m "$S/heartbeat.json")
lk=0; [ -f "$S/cycle.lock" ] && lk=$(stat -f %m "$S/cycle.lock")
[ $((now - hb)) -lt 240 ] && exit 0      # orchestrator alive
[ $((now - lk)) -lt 300 ] && exit 0      # a cycle is running right now
echo "$(date '+%F %T') heartbeat stale $((now - hb))s -> running one-shot cycle" >> "$LOG"
touch "$S/cycle.lock"
cd "$REPO" && ( "$(command -v claude || echo $HOME/.local/bin/claude)" -p --model claude-opus-5-5 \
  --allowedTools "mcp__robinhood-trading__*,WebSearch,Read,Write,Edit,Bash(python3:*),Bash(date:*),Bash(TZ=*),Bash(cat:*),Bash(echo:*),Bash(ls:*),Bash(git:*),Bash(touch:*),Bash(rm:*),Bash(mkdir:*)" \
  "You are the options-100 FAILSAFE (the main orchestrator session is down). Read agents/options-100/PLAN.md and agents/options-100/CYCLE.md and run exactly ONE cycle now, obeying every hard rule. Write state/heartbeat.json with source=failsafe. Then stop." >> "$LOG" 2>&1 ) &
pid=$!; ( sleep 300; kill $pid 2>/dev/null ) & wait $pid; rm -f "$S/cycle.lock"
echo "$(date '+%F %T') one-shot cycle finished" >> "$LOG"
