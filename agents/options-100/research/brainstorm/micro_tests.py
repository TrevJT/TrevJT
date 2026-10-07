import sqlite3, math, collections
DB='/Users/trevorthompson/code/TrevJT/agents/options-100/data/market.db'
con=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
def daily(sym):
    return {r[0]:r[1:] for r in con.execute("select ts,open,high,low,close from bars where symbol=? and interval='1d' order by ts",(sym,))}
def hourly(sym):
    d=collections.defaultdict(dict)
    for ts,o,h,l,c in con.execute("select ts,open,high,low,close from bars where symbol=? and interval='1h' order by ts",(sym,)):
        d[ts[:10]][ts[11:]]=(o,h,l,c)
    return d
vix=daily('^VIX'); v9=daily('^VIX9D'); v3=daily('^VIX3M')
vdates=sorted(vix)
def prev(dates,d):
    import bisect
    i=bisect.bisect_left(dates,d); return dates[i-1] if i>0 else None

# ---------- TEST 1: intraday momentum (1h bars, 2y) ----------
print("=== TEST1 intraday momentum: first hour (9:30-10:30) and prevclose->15:30 vs last 30m (15:30-16:00)")
for sym in ['SPY','QQQ','IWM']:
    H=hourly(sym); D=daily(sym); dd=sorted(D)
    rows=[]
    for day,b in sorted(H.items()):
        if '09:30' not in b or '15:30' not in b: continue
        p=prev(dd,day)
        if not p: continue
        pc=D[p][3]
        r1=b['09:30'][3]/pc-1           # prev close -> 10:30 (Gao uses prevclose->10:00)
        r_day=b['15:30'][0]/pc-1         # prev close -> 15:30
        rl=b['15:30'][3]/b['15:30'][0]-1 # last 30m
        rows.append((r1,r_day,rl))
    n=len(rows)
    for name,idx in [('first-hour',0),('prevclose->15:30',1)]:
        agree=sum(1 for r in rows if r[idx]*r[2]>0)/n
        # big days: |signal| top quintile
        th=sorted(abs(r[idx]) for r in rows)[int(n*0.8)]
        big=[r for r in rows if abs(r[idx])>=th]
        agb=sum(1 for r in big if r[idx]*r[2]>0)/len(big)
        mean_signed=sum(math.copysign(1,r[idx])*r[2] for r in big)/len(big)*1e4
        # large last-30 continuation >=0.25%
        cont=sum(1 for r in big if math.copysign(1,r[idx])*r[2]>=0.0025)/len(big)
        base=sum(1 for r in rows if abs(r[2])>=0.0025)/n/2
        print(f"{sym} {name:18s} n={n} sign-agree={agree:.3f} | top20% |sig|>={th*100:.2f}% n={len(big)} agree={agb:.3f} avg signed last30={mean_signed:.1f}bp  P(cont>=0.25%)={cont:.3f} vs base one-side {base:.3f}")

# ---------- TEST 2: lotto hit rates SPY: from 10:30 price, P(close beyond z*sigma) ----------
print("\n=== TEST2 SPY 0DTE lotto: P(close >= z sigma from 10:30 price, in direction) sigma=prevVIX/sqrt252*sqrt(5.5/6.5)")
H=hourly('SPY'); D=daily('SPY'); dd=sorted(D)
recs=[]
for day,b in sorted(H.items()):
    if '10:30' not in b or '15:30' not in b or day not in D: continue
    p=prev(dd,day); pv=prev(vdates,day)
    if not p or not pv: continue
    pc=D[p][3]; o=D[day][0]
    px=b['10:30'][0]; cl=b['15:30'][3]
    hi=max(b[k][1] for k in b if k>='10:30'); lo=min(b[k][2] for k in b if k>='10:30')
    sig=vix[pv][3]/100/math.sqrt(252)*math.sqrt(5.5/6.5)
    zc=(cl/px-1)/sig; zh=(hi/px-1)/sig; zl=(lo/px-1)/sig
    fh=b['09:30']; fhr=(fh[1]-fh[2])/pc/ (vix[pv][3]/100/math.sqrt(252))  # first-hour range in daily sigmas
    term=v9[pv][3]/vix[pv][3] if pv in v9 else None
    gap=(o/pc-1)/(vix[pv][3]/100/math.sqrt(252))
    trend=(px/pc-1)
    dow=__import__('datetime').date.fromisoformat(day).weekday()
    recs.append(dict(day=day,zc=zc,zh=zh,zl=zl,fhr=fhr,term=term,gap=gap,trend=trend,dow=dow,vix=vix[pv][3]))
def stat(rs,label):
    n=len(rs)
    if n==0: return
    # two-sided: either call or put lotto pays (strangle) at z>=1.645 close
    c=lambda z: sum(1 for r in rs if abs(r['zc'])>=z)/n
    t=lambda z: sum(1 for r in rs if r['zh']>=z or r['zl']<=-z)/n
    # directional: trade WITH morning trend (prevclose->10:30)
    wd=sum(1 for r in rs if math.copysign(1,r['trend'])*r['zc']>=1.645)/n
    ag=sum(1 for r in rs if -math.copysign(1,r['trend'])*r['zc']>=1.645)/n
    print(f"{label:34s} n={n:4d} P|zclose|>=1.645={c(1.645):.3f} (fair 0.100) >=2.33={c(2.326):.3f} (fair .020) | touch|z|>=1.645={t(1.645):.3f} | with-trend close>=1.645={wd:.3f} against={ag:.3f} (fair .05)")
stat(recs,'ALL')
fq=sorted(r['fhr'] for r in recs); th=fq[int(len(fq)*0.8)]
stat([r for r in recs if r['fhr']>=th],f'first-hr range top20% (>={th:.2f}sd)')
stat([r for r in recs if r['fhr']<sorted(r['fhr'] for r in recs)[int(len(recs)*0.2)]],'first-hr range bottom20%')
stat([r for r in recs if r['term'] and r['term']>1.0],'VIX9D/VIX>1 (backwardation)')
stat([r for r in recs if r['term'] and r['term']<0.9],'VIX9D/VIX<0.9 (steep contango)')
stat([r for r in recs if abs(r['gap'])>=1.0],'|gap|>=1 daily sd')
stat([r for r in recs if r['vix']>=20],'VIX>=20')
stat([r for r in recs if r['vix']<15],'VIX<15')
for d,nm in enumerate(['Mon','Tue','Wed','Thu','Fri']): stat([r for r in recs if r['dow']==d],nm)
# trend-day: |prevclose->10:30| >=0.75 sd AND first hour range top 40%
