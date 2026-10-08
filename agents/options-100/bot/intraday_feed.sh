#!/bin/bash
# launchd every 15 min: prediction-market odds snapshot during US market hours (09:00-16:30 ET, weekdays).
dow=$(TZ=America/New_York date +%u); hm=$(TZ=America/New_York date +%H%M)
[ "$dow" -ge 6 ] && exit 0; [ "$((10#$hm))" -lt 900 ] && exit 0; [ "$((10#$hm))" -gt 1630 ] && exit 0
/usr/bin/env python3 "$HOME/code/TrevJT/agents/options-100/bot/predictions.py" snap
/usr/bin/env python3 "$HOME/code/TrevJT/agents/options-100/bot/edge.py" snap SPY QQQ IWM
