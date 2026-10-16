#!/bin/bash
# P5 trigger check: largest Iran/Hormuz odds move (pts) since prior 16:00 ET. "SHOCK" if any |move| >= 8 (PLAN.md VIX-gate exception); ROUTER P5 itself needs >= 10.
DB="$(dirname "$0")/../data/market.db"; SINCE="${1:-$(date -u -v-1d +%Y-%m-%dT20)}"
sqlite3 "$DB" "with t as (select p.market_id, m.question q, p.ts, p.prob from pm_prices p join pm_markets m on m.market_id=p.market_id where p.ts>='$SINCE' and (m.question like '%Iran%' or m.question like '%Hormuz%')),
f as (select market_id, min(ts) a, max(ts) b from t group by market_id)
select round(100*((select prob from t where t.market_id=f.market_id and ts=f.b)-(select prob from t where t.market_id=f.market_id and ts=f.a)),1) d,
 substr((select q from t where t.market_id=f.market_id limit 1),1,60) from f order by abs(d) desc limit 3" | awk -F'|' '{print} ($1>=8||$1<=-8){s=1} END{print (s?"SHOCK":"no_shock")}'
