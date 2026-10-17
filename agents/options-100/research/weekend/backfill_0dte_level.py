"""Load optfetch/out*.jsonl (Robinhood MCP 0DTE ATM call/put bars) into market.db option_hist,
then measure the 0DTE price level. Run: python3 backfill_0dte_level.py"""
import json, glob, sqlite3, math, os, sys
import numpy as np, pandas as pd
H = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(H, '../../data/market.db')
c = sqlite3.connect(DB)
c.execute("""create table if not exists option_hist(occ text, symbol text, expiry text, strike real, type text,
 interval text, ts text, open real, high real, low real, close real, primary key(occ,interval,ts))""")
rows = []; days = {}
for f in sorted(glob.glob(os.path.join(H, 'optfetch/out*.jsonl'))):
    for l in open(f):
        d = json.loads(l); days[d['date']] = d
        for t in ('call','put'): d['day'][t] = [b for b in d['day'][t] if b['begins_at'][:10] == d['date']]
for f in sorted(glob.glob(os.path.join(H, 'optfetch/iout*.jsonl'))):  # 10minute intraday (5m is only real for ~7 trading days)
    for l in open(f):
        i = json.loads(l)
        if i['date'] in days: days[i['date']]['intra10'] = {'call': i['call'], 'put': i['put']}
for d in days.values():
    for typ in ('call', 'put'):
        oid = d[typ + '_id']
        if not oid: continue
        for iv, key in (('day', 'day'), ('5minute', 'intra'), ('10minute', 'intra10')):
            for b in d.get(key, {}).get(typ, []):
                if b.get('interpolated'): continue
                rows.append((oid, 'SPY', d['date'], float(d['K']), typ, iv, b['begins_at'],
                             *(float(b[k + '_price']) for k in ('open', 'high', 'low', 'close'))))
c.executemany("insert or replace into option_hist values(?,?,?,?,?,?,?,?,?,?,?)", rows); c.commit()

def bars(sym, iv):
    return pd.read_sql(f"select ts,open,close from bars where symbol='{sym}' and interval='{iv}'", c)
spy = bars('SPY', '1d').set_index('ts'); spy.index = spy.index.astype(str).str[:10]
spy['prev'] = spy.close.shift(1); spy['gap'] = (spy.open / spy.prev - 1).abs()
def prevclose(sym):
    s = bars(sym, '1d').set_index('ts').close; s.index = s.index.astype(str).str[:10]; return s.shift(1)
vix, v9, v1 = prevclose('^VIX'), prevclose('^VIX9D'), prevclose('^VIX1D')
s5 = bars('SPY', '5m').set_index('ts').open
recs = []
for dt, d in days.items():
    if dt not in spy.index: continue
    cb, pb = d['day']['call'], d['day']['put']
    r = dict(date=dt, K=d['K'], O=spy.open[dt], C=spy.close[dt], gap=spy.gap[dt], vix=vix.get(dt), v9=v9.get(dt), v1=v1.get(dt))
    if cb and pb:
        r['prem_open'] = float(cb[0]['open_price']) + float(pb[0]['open_price'])
        r['call_close'] = float(cb[0]['close_price']); r['put_close'] = float(pb[0]['close_price'])
    # intraday entry: first bar >= 13:35Z with both legs, within 15 min
    src = d['intra'] if d['intra']['call'] else d.get('intra10', {'call': [], 'put': []})
    ic = {b['begins_at']: float(b['open_price']) for b in src['call']}
    ip = {b['begins_at']: float(b['open_price']) for b in src['put']}
    ts = sorted(t for t in ic if t in ip and t[11:16] >= '13:35' and t[11:16] <= '13:50')
    if ts:
        t = ts[0]; et = dt + ' ' + t[11:16].replace('13:', '09:').replace('14:', '10:')
        r['prem_intra'] = ic[t] + ip[t]; r['t_in'] = t[11:16]
        r['S_in'] = s5.get(dt + ' 09:' + t[14:16])
    recs.append(r)
df = pd.DataFrame(recs).sort_values('date').reset_index(drop=True)
df['month'] = df.date.str[:7]
df['impl1d'] = df.O * df.v1 / 100 / math.sqrt(252) * math.sqrt(2 / math.pi)  # expected |full-day move| ex-VRP
rng = np.random.default_rng(0)
def boot(x, n=5000):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    if len(x) < 3: return (np.nan, np.nan)
    m = rng.choice(x, (n, len(x))).mean(1); return tuple(np.percentile(m, [2.5, 97.5]))
def summ(x):
    x = pd.Series(x).dropna()
    lo, hi = boot(x); return f"n={len(x)} mean={x.mean():.3f} med={x.median():.3f} CI[{lo:.3f},{hi:.3f}]"
COST = 0.02
def build(prem_col, spot_col):
    d = df.dropna(subset=[prem_col]).copy()
    d = d[d[prem_col] > 0.3]  # drop broken prints
    if spot_col == 'S_in': d = d.dropna(subset=['S_in'])
    d['move'] = (d.C - d[spot_col]).abs()
    d['ratio'] = d.move / d[prem_col]
    d['payoff'] = (d.C - d.K).abs()  # settles at close
    d['ret'] = d.payoff / (d[prem_col] * (1 + COST)) - 1
    d['prem_pct'] = d[prem_col] / d[spot_col] * 100
    return d
out = []
def P(s=''): print(s); out.append(s)
def groups(d, label):
    P(f"\n### {label}\nALL: ratio {summ(d.ratio)} | EV net {summ(d.ret)} | prem%spot mean {d.prem_pct.mean():.3f}")
    P("by month:"); [P(f"  {m}: ratio {summ(g.ratio)} | EV {g.ret.mean():+.3f}") for m, g in d.groupby('month')]
    d = d.copy()
    d['vb'] = pd.qcut(d.vix, 3, labels=['VIX lo', 'VIX mid', 'VIX hi'], duplicates='drop')
    P("by prior-close VIX tercile:"); [P(f"  {m}: ratio {summ(g.ratio)} | EV {g.ret.mean():+.3f} | prem% {g.prem_pct.mean():.3f}") for m, g in d.groupby('vb', observed=True)]
    d['gq'] = pd.qcut(d.gap, 5, labels=['q1', 'q2', 'q3', 'q4', 'q5'], duplicates='drop')
    P("by |gap| quintile:"); [P(f"  {m}: ratio {summ(g.ratio)} | EV {g.ret.mean():+.3f} | gap<={g.gap.max()*100:.2f}%") for m, g in d.groupby('gq', observed=True)]
    d['term'] = d.v9 / d.vix; d['tb'] = pd.qcut(d.term, 3, labels=['term lo', 'term mid', 'term hi'], duplicates='drop')
    P("by VIX9D/VIX tercile:"); [P(f"  {m}: ratio {summ(g.ratio)} | EV {g.ret.mean():+.3f}") for m, g in d.groupby('tb', observed=True)]
    lo, rest = d[d.tb == 'term lo'], d[d.tb != 'term lo']
    P(f"gate: bottom tercile EV {lo.ret.mean():+.3f} (n={len(lo)}) vs others {rest.ret.mean():+.3f} (n={len(rest)}); boot CI lo {boot(lo.ret)}, others {boot(rest.ret)}")
    P(f"EV boot CI overall {boot(d.ret)}")
    return d
d1 = build('prem_open', 'O'); d1 = groups(d1, "DAY-OPEN set (entry = first day print, spot = SPY open)")
P(f"premium / VIX1D-implied |move| (price level): {summ(d1.prem_open / d1.impl1d)}")
P(f"realized |C-O| / VIX1D-implied |move|: {summ((d1.C-d1.O).abs()/d1.impl1d)}")
d2 = build('prem_intra', 'S_in') if 'prem_intra' in df else None
if d2 is not None and len(d2):
    d2 = groups(d2, "INTRADAY set (entry = first real 5m bar at 09:35-09:50, spot = SPY 5m open)")
    P(f"entry times: {d2.t_in.value_counts().to_dict()}")
    P(f"premium / VIX1D-implied |move| (day-implied, understates remaining-day): {summ(d2.prem_intra / d2.impl1d)}")
    P(f"realized |C-S_in| / VIX1D-implied: {summ(d2.move/d2.impl1d)}")
df.to_csv(os.path.join(H, 'optfetch/level_panel.csv'), index=False)
open(os.path.join(H, 'optfetch/level_results.txt'), 'w').write('\n'.join(out))

# ---- edge.py-comparable constant: rms(open->close move) / (VIX1D sigma_day * sqrt(0.69)), the form used in edge.py sd_rem
P("\n### VIX1D_REALIZED-comparable constant (sd form, full day from the open)")
dd = df.dropna(subset=['v1']).copy()
sig = dd.O * dd.v1 / 100 / math.sqrt(252) * math.sqrt(0.69)
z = (dd.C - dd.O) / sig
def bs(f, n=3000):
    return np.percentile([f(rng.choice(z.values, len(z))) for _ in range(n)], [2.5, 97.5])
P(f"all days n={len(z)}: rms z = {math.sqrt((z**2).mean()):.3f} CI {bs(lambda a: math.sqrt((a**2).mean())).round(3)}; mean|z|*sqrt(pi/2) = {z.abs().mean()*math.sqrt(math.pi/2):.3f}")
dm = d1.merge(dd[['date']], on='date'); zs = ((dm.C-dm.O)/(dm.O*dm.v1/100/math.sqrt(252)*math.sqrt(0.69)))
P(f"straddle-backfill days n={len(zs)}: rms z = {math.sqrt((zs**2).mean()):.3f}")
# day-open print vs first real intraday bar (is the first day print noisy / stale?)
if d2 is not None and len(d2):
    m = d2.copy()
    P(f"day-open premium vs intraday-entry premium (same days, n={len(m)}): mean ratio open/intra = {(m.prem_open/m.prem_intra).mean():.3f}, median {(m.prem_open/m.prem_intra).median():.3f}")
open(os.path.join(H, 'optfetch/level_results.txt'), 'w').write('\n'.join(out))
