#!/bin/bash
# P5 trigger (ROUTER, revised 2026-10-17): any Iran/Hormuz market moving >= 5 pts within the last 60 min -> "SHOCK".
# De-cluster: only the first SHOCK per 24h counts (check journal for a p5 event today before acting).
# Also prints the day move since prior 16:00 ET; >= 8 there still lifts the PLAN.md VIX-gate exception.
DB="$(dirname "$0")/../data/market.db"; # pm_prices.ts is ET "YYYY-MM-DD HH:MM" (intraday) or "YYYY-MM-DD" (daily rows, excluded). Optional args: SINCE NOW (ET, same format).
NOW="${2:-$(TZ=America/New_York date '+%Y-%m-%d %H:%M')}"; SINCE="${1:-$(TZ=America/New_York date -v-1d '+%Y-%m-%d 16:00')}"
HOUR="$(date -j -f '%Y-%m-%d %H:%M' -v-60M "$NOW" '+%Y-%m-%d %H:%M')"
Q="(m.question like '%Iran%' or m.question like '%Hormuz%')"  # not WTI price-target markets: they just track crude (circular)
echo "60-min moves:"
sqlite3 "$DB" "with t as (select p.market_id, m.question q, p.ts, p.prob from pm_prices p join pm_markets m on m.market_id=p.market_id where length(p.ts)=16 and p.ts>='$SINCE' and p.ts<='$NOW' and $Q),
f as (select market_id, max(ts) b, (select max(ts) from t t2 where t2.market_id=t.market_id and t2.ts<='$HOUR') a from t group by market_id)
select round(100*((select prob from t where t.market_id=f.market_id and ts=f.b)-(select prob from t where t.market_id=f.market_id and ts=f.a)),1) d,
 substr((select q from t where t.market_id=f.market_id limit 1),1,60) from f where a is not null order by abs(d) desc limit 3" | awk -F'|' '{print} ($1>=5||$1<=-5){s=1} END{print (s?"SHOCK":"no_shock")}'
echo "day moves:"
sqlite3 "$DB" "with t as (select p.market_id, m.question q, p.ts, p.prob from pm_prices p join pm_markets m on m.market_id=p.market_id where length(p.ts)=16 and p.ts>='$SINCE' and p.ts<='$NOW' and $Q),
f as (select market_id, min(ts) a, max(ts) b from t group by market_id)
select round(100*((select prob from t where t.market_id=f.market_id and ts=f.b)-(select prob from t where t.market_id=f.market_id and ts=f.a)),1) d,
 substr((select q from t where t.market_id=f.market_id limit 1),1,60) from f order by abs(d) desc limit 3" | awk -F'|' '{print} ($1>=8||$1<=-8){s=1} END{print (s?"DAY_SHOCK":"no_day_shock")}'
