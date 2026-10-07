import sqlite3, numpy as np, pandas as pd
con=sqlite3.connect("file:/Users/trevorthompson/code/TrevJT/agents/options-100/data/market.db?mode=ro",uri=True)
def px(s): return pd.read_sql(f"select ts,open,close from bars where symbol='{s}' and interval='1d' order by ts",con,parse_dates=['ts']).set_index('ts')
E={'TSLA':"2023-01-25 2023-04-19 2023-07-19 2023-10-18 2024-01-24 2024-04-23 2024-07-23 2024-10-23 2025-01-29 2025-04-22 2025-07-23 2025-10-22 2026-01-28 2026-04-22 2026-07-22",
'META':"2023-02-01 2023-04-26 2023-07-26 2023-10-25 2024-02-01 2024-04-24 2024-07-31 2024-10-30 2025-01-29 2025-04-30 2025-07-30 2025-10-29 2026-01-28 2026-04-29 2026-07-29",
'GOOGL':"2023-02-02 2023-04-25 2023-07-25 2023-10-24 2024-01-30 2024-04-25 2024-07-23 2024-10-29 2025-02-04 2025-04-24 2025-07-23 2025-10-29 2026-02-04 2026-04-29 2026-07-22",
'MSFT':"2023-01-24 2023-04-25 2023-07-25 2023-10-24 2024-01-30 2024-04-25 2024-07-30 2024-10-30 2025-01-29 2025-04-30 2025-07-30 2025-10-29 2026-01-28 2026-04-29 2026-07-29",
'AMZN':"2023-02-02 2023-04-27 2023-08-03 2023-10-26 2024-02-01 2024-04-30 2024-08-01 2024-10-31 2025-02-06 2025-05-01 2025-07-31 2025-10-30 2026-02-05 2026-04-29 2026-07-30",
'AAPL':"2023-02-02 2023-05-04 2023-08-03 2023-11-02 2024-02-01 2024-05-02 2024-08-01 2024-10-31 2025-01-30 2025-05-01 2025-07-31 2025-10-30 2026-01-29 2026-04-30 2026-07-30"}
IMPL={'TSLA':7.0,'META':7.0,'GOOGL':5.5,'MSFT':4.5,'AMZN':6.5,'AAPL':4.0}  # typical straddle-implied % (approx, public history)
print("== Earnings reactions (pm report; close t -> close t+1), PEAD = signed ret t+1 close -> t+6 close")
allp=[]
for s,ds in E.items():
    d=px(s); r=[];pe=[];big=0;rec=[]
    for t in ds.split():
        t=pd.Timestamp(t)
        if t not in d.index: print('missing',s,t); continue
        i=d.index.get_loc(t)
        if i+6>=len(d): continue
        re=d.close.iloc[i+1]/d.close.iloc[i]-1; r.append(re)
        p=np.sign(re)*(d.close.iloc[i+6]/d.close.iloc[i+1]-1); pe.append(p); allp.append(p)
        rec.append(f"{re*100:+.1f}")
    a=np.abs(r)*100
    print(f"{s:5s} n={len(r)} mean|move|={a.mean():.1f}% med={np.median(a):.1f}% max={a.max():.1f}% typical-impl~{IMPL[s]}% P(>1.5x impl)={(a>1.5*IMPL[s]).mean()*100:.0f}% PEAD mean={np.mean(pe)*100:+.2f}% hit={np.mean(np.array(pe)>0)*100:.0f}% last5={rec[-5:]}")
allp=np.array(allp); print(f"PEAD pooled n={len(allp)} mean={allp.mean()*100:+.2f}% t={allp.mean()/allp.std(ddof=1)*np.sqrt(len(allp)):.2f}")

print("\n== Midterm elections: SPY day after (close E -> close E+1), VIX change Fri-before -> E+1")
spy=px('SPY'); vix=px('^VIX'); base=spy.close.pct_change().abs()
for t in "1994-11-08 1998-11-03 2002-11-05 2006-11-07 2010-11-02 2014-11-04 2018-11-06 2022-11-08".split():
    t=pd.Timestamp(t); i=spy.index.get_loc(t)
    r1=spy.close.iloc[i+1]/spy.close.iloc[i]-1; r5=spy.close.iloc[i+5]/spy.close.iloc[i]-1
    vi=vix.index.get_loc(t); vch=vix.close.iloc[vi+1]-vix.close.iloc[vi-2]
    print(f"{t.date()} E+1={r1*100:+.2f}% E+5={r5*100:+.2f}% VIX(E-2->E+1)={vch:+.1f} pts (VIX={vix.close.iloc[vi-2]:.1f})")
print(f"SPY all-days mean|r| since 1994 = {base[base.index>='1994'].mean()*100:.2f}%")

print("\n== Polymarket Iran shock days -> |XLE|,|CL|,|SPY| same day & next day, VIX next-day change")
pm=pd.read_sql("select p.market_id, substr(p.ts,1,10) d, p.prob from pm_prices p join pm_markets m using(source,market_id) where m.source='poly' and m.topic in ('iran','oil') and m.volume>1e6",con)
pm=pm.groupby(['d','market_id']).prob.last().unstack().sort_index(); pm.index=pd.to_datetime(pm.index)
dp=pm.diff().abs().max(axis=1)
mk={k:px(k).close.pct_change() for k in ['XLE','CL=F','SPY']}; vx=px('^VIX').close.diff()
df=pd.DataFrame({k:v for k,v in mk.items()}).join(vx.rename('dVIX'))
df=df[df.index>=pm.index.min()]
# map calendar shock to the trading day on/after it
sh=dp.reindex(pd.date_range(dp.index.min(),dp.index.max())).fillna(0)
# aggregate weekend/holiday shocks forward onto next trading day
sh_td=sh.groupby(df.index[df.index.searchsorted(sh.index).clip(0,len(df)-1)]).max()
df['shock']=sh_td.reindex(df.index).fillna(0)
for thr in [0.05,0.10,0.15]:
    S=df.shock>=thr
    nx=S.shift(1,fill_value=False)
    for k in ['XLE','CL=F','SPY']:
        print(f"thr={thr:.2f} {k:5s} same: n={S.sum():3d} |r|={df.loc[S,k].abs().mean()*100:.2f}% vs {df.loc[~S,k].abs().mean()*100:.2f}% | next: |r|={df.loc[nx,k].abs().mean()*100:.2f}% vs {df.loc[~nx,k].abs().mean()*100:.2f}%")
    print(f"   next-day dVIX mean {df.loc[nx,'dVIX'].mean():+.2f} vs {df.loc[~nx,'dVIX'].mean():+.2f}")
print("\n== control for vol clustering: next|CL| ~ a + b*|CL_today| + c*shock10 (OLS), and permutation p")
d=df[['CL=F','XLE','shock']].dropna().copy()
for k in ['CL=F','XLE']:
    y=d[k].abs().shift(-1); x1=d[k].abs(); x2=(d.shock>=0.10).astype(float)
    m=y.notna(); X=np.column_stack([np.ones(m.sum()),x1[m],x2[m]]); Y=y[m].values
    b,res,_,_=np.linalg.lstsq(X,Y,rcond=None); e=Y-X@b; s2=e@e/(len(Y)-3); se=np.sqrt(np.diag(s2*np.linalg.inv(X.T@X)))
    print(k,"coef shock=%.4f t=%.2f ; coef |today|=%.3f t=%.2f n=%d"%(b[2],b[2]/se[2],b[1],b[1]/se[1],len(Y)))
    rng=np.random.default_rng(0); obs=Y[x2[m].values==1].mean()-Y[x2[m].values==0].mean(); cnt=0
    for _ in range(5000):
        p=rng.permutation(x2[m].values); cnt+= (Y[p==1].mean()-Y[p==0].mean())>=obs
    print("  perm p(next-day |%s| diff)=%.3f"%(k,cnt/5000))
