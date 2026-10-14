#!/bin/bash
# One idle orchestrator cycle (flat / stand-down): news check + cycle.log + HEARTBEAT.
# The heartbeat is the point: without it failsafe.sh (stale > 480 s) launches a full one-shot cycle every 2 min.
# 2026-10-13: idle cycles skipped the heartbeat and failsafe ran 47 redundant cycles.
cd "$(dirname "$0")/../../.." || exit 1
S=agents/options-100/state; ET=$(TZ=America/New_York date +%H:%M)
echo "$ET"
python3 - "$S" "$ET" "${1:-idle}" <<'PY'
import json, sys, time
S, et, act = sys.argv[1:]
d = json.load(open(f"{S}/day.json"))
json.dump({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "et": et, "source": "orchestrator", "equity": d.get("start_equity"),
           "cash": d.get("cash"), "positions": len(json.load(open(f"{S}/positions.json"))), "last_action": act}, open(f"{S}/heartbeat.json", "w"))
open(f"{S}/cycle.log", "a").write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {et} - - {d.get('vix')} {d.get('vix_gate')} 0 {act}\n")
PY
# news AFTER the heartbeat so a hung feed can never starve it (2026-10-14)
python3 agents/options-100/bot/news.py --hours 0.1 | grep -E "<[^>]*(shock|fed|macro)" | head -5
