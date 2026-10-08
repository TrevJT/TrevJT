#!/bin/bash
# Nightly research job (launchd, after close): refresh all data, re-run correlation scan, save dated findings.
cd "$HOME/code/TrevJT/agents/options-100" || exit 1
d=$(TZ=America/New_York date +%F)
python3 bot/history.py update
python3 bot/predictions.py update
python3 bot/edge.py grade > state/edge_grade.txt
{ echo "# Research log $d"; echo; echo '## Correlation scan'; python3 bot/correlate.py scan --top 20;
  echo '## Edge engine report card'; cat state/edge_grade.txt; echo; echo '## SPY score-model backtest'; python3 bot/context.py backtest --sym SPY --target 0.6 --stop 0.6;
  python3 bot/context.py backtest --sym SPY --target 0.6 --stop 0.6 --score 5 --rvol 1.3;
  echo; echo '## Coverage'; python3 bot/history.py status | tail -20; } > "reports/research/$d.md" 2>&1
cd "$HOME/code/TrevJT" && git add agents/options-100/reports/research && git -c user.name="Trevor Thompson" -c user.email="trevorchico@gmail.com" commit -qm "research log $d" >/dev/null 2>&1
