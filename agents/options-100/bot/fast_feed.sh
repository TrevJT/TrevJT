#!/bin/bash
dow=$(TZ=America/New_York date +%u); hm=$(TZ=America/New_York date +%H%M)
[ "$dow" -ge 6 ] && exit 0; [ "$((10#$hm))" -lt 930 ] && exit 0; [ "$((10#$hm))" -gt 1600 ] && exit 0
/usr/bin/env python3 "$HOME/code/TrevJT/agents/options-100/bot/predictions.py" fastsnap
