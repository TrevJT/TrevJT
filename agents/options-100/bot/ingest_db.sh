#!/bin/bash
# Feed score.py 5m bars from market.db (yfinance, ts = naive ET) instead of pasting MCP bars. Usage: ingest_db.sh SYM SINCE("YYYY-MM-DD HH:MM" ET)
# Skip the in-progress bar: yfinance reports cumulative DAY volume on it (QQQ 14:45 bar = 27.6M -> RVOL 82.8, 2026-10-19).
CUT="$(TZ=America/New_York date -v-5M '+%Y-%m-%d %H:%M')"
D="$(dirname "$0")"; OFF=$(TZ=America/New_York date +%z | sed 's/\(..\)$/:\1/')
sqlite3 -separator , "$D/../data/market.db" "select replace(ts,' ','T')||':00$OFF',open,high,low,close,cast(volume as int) from bars where symbol='$1' and interval='5m' and ts>'$2' and ts<='$CUT' order by ts" \
 | python3 "$D/score.py" ingest "$1" "$(cat)"
