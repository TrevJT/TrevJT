import sqlite3, math, collections, bisect, statistics as st
DB='/Users/trevorthompson/code/TrevJT/agents/options-100/data/market.db'
con=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
def bars(sym,iv):
    d=collections.defaultdict(list)
    for ts,o,h,l,c in con.execute("select ts,open,high,low,close from bars where symbol=? and interval=? order by ts",(sym,iv)):
        d[ts[:10]].append((ts[11:],o,h,l,c))
    return d
def daily(sym):
    return {r[0]:r[1:] for r in con.execute("select ts,open,high,low,close from bars where symbol=? and interval='1d' order by ts",(sym,))}

print("=== TEST3 ORB (15-min opening range, 5m bars, 60 sessions): first break, then excursion beyond break level")
for sym in ['SPY','QQQ','IWM']:
    B=bars(sym,'5m'); res=[]
    for day,b in sorted(B.items()):
        if len(b)<70: continue
        orb=b[:3]; H=max(x[2] for x in orb); L=min(x[3] for x in orb); w=(H-L)/b[0][1]
        d=None
        for i,x in enumerate(b[3:],3):
            if x[2]>H: d=1; lvl=H; break
            if x[3]<L: d=-1; lvl=L; break
        if d is None: continue
        rest=b[i:]
        if d==1: mfe=max(x[2] for x in rest)/lvl-1; cl=rest[-1][4]/lvl-1
        else: mfe=1-min(x[3] for x in rest)/lvl; cl=1-rest[-1][4]/lvl
        fb=any((x[3]<L if d==1 else x[2]>H) for x in rest)
        res.append((w,mfe,cl,fb,x[0]))
    n=len(res)
    for thr in (0.0025,0.005,0.01):
        print(f"{sym} n={n} P(MFE>={thr*100:.2f}%)={sum(r[1]>=thr for r in res)/n:.2f}  P(close beyond+{thr*100:.2f}%)={sum(r[2]>=thr for r in res)/n:.2f}")
    print(f"{sym} median OR width={st.median(r[0] for r in res)*100:.2f}% median close-vs-break={st.median(r[2] for r in res)*100:.2f}% failed(opposite break)={sum(r[3] for r in res)/n:.2f}")

print("\n=== TEST3b ORB on 1h bars (2y): first-hour range break, approx; close beyond break level")
for sym in ['SPY','QQQ']:
    B=bars(sym,'1h'); res=[]
    for day,b in sorted(B.items()):
        if len(b)<7: continue
        H,L=b[0][2],b[0][3]; d=None
        for i,x in enumerate(b[1:],1):
            up=x[2]>H; dn=x[3]<L
            if up and dn: d=None; break
            if up: d=1; lvl=H; break
            if dn: d=-1; lvl=L; break
        if d is None: continue
        cl=(b[-1][4]/lvl-1)*d
        res.append(cl)
    n=len(res)
    print(sym, f"n={n} P(close beyond break +0.25%)={sum(r>=0.0025 for r in res)/n:.2f} +0.5%={sum(r>=0.005 for r in res)/n:.2f} +1%={sum(r>=0.01 for r in res)/n:.2f}  P(close back inside)={sum(r<0 for r in res)/n:.2f} mean={st.mean(res)*1e4:.1f}bp")

print("\n=== TEST4 overnight gap (SPY daily 2000-2026): gap>=+/-1% -> open->close continuation vs fill")
D=daily('SPY'); dd=sorted(d for d in D if d>='2000-01-01'); V=daily('^VIX')
rows=[]
for i in range(1,len(dd)):
    p,c=D[dd[i-1]],D[dd[i]]
    g=c[0]/p[3]-1; oc=c[3]/c[0]-1; hi=c[1]/c[0]-1; lo=c[2]/c[0]-1
    rows.append((g,oc,hi,lo,dd[i]))
def show(lbl,rs):
    n=len(rs)
    cont1=sum(1 for g,oc,hi,lo,_ in rs if math.copysign(1,g)*oc>=0.01)/n
    rev1=sum(1 for g,oc,hi,lo,_ in rs if -math.copysign(1,g)*oc>=0.01)/n
    fill=sum(1 for g,oc,hi,lo,_ in rs if (lo<=-g/(1+g) if g>0 else hi>=-g/(1+g)))/n
    print(f"{lbl:28s} n={n:5d} P(cont>=1% o->c)={cont1:.3f} P(reverse>=1%)={rev1:.3f} P(gap filled intraday)={fill:.2f}")
show('all days',rows)
show('gap up >=1%',[r for r in rows if r[0]>=0.01])
show('gap down <=-1%',[r for r in rows if r[0]<=-0.01])
show('gap up >=1% since 2020',[r for r in rows if r[0]>=0.01 and r[4]>='2020'])
show('gap down <=-1% since 2020',[r for r in rows if r[0]<=-0.01 and r[4]>='2020'])
show('all since 2020',[r for r in rows if r[4]>='2020'])

print("\n=== TEST5 late-day (14:30->16:00, 1h bars SPY 2y): trend into 14:30 vs final 90 min")
B=bars('SPY','1h'); Dd=daily('SPY'); ds=sorted(Dd); res=[]
for day,b in sorted(B.items()):
    m={x[0]:x for x in b}
    if '14:30' not in m or '15:30' not in m: continue
    i=bisect.bisect_left(ds,day)
    if i==0: continue
    pc=Dd[ds[i-1]][3]; p=m['14:30'][1]; tr=p/pc-1
    hi=max(m['14:30'][2],m['15:30'][2])/p-1; lo=min(m['14:30'][3],m['15:30'][3])/p-1; cl=m['15:30'][4]/p-1
    res.append((tr,hi,lo,cl))
def sh(l,rs):
    n=len(rs); s=lambda r: math.copysign(1,r[0])
    print(f"{l:24s} n={n} P(with-trend close>=0.3%)={sum(s(r)*r[3]>=0.003 for r in rs)/n:.3f} P(against>=0.3%)={sum(-s(r)*r[3]>=0.003 for r in rs)/n:.3f} P(touch with-trend>=0.5%)={sum((r[1] if s(r)>0 else -r[2])>=0.005 for r in rs)/n:.3f}")
sh('all',res); sh('|trend|>=1%',[r for r in res if abs(r[0])>=0.01]); sh('|trend|<0.3%',[r for r in res if abs(r[0])<0.003])
