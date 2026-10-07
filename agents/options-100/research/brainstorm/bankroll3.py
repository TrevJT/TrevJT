import sqlite3, math, numpy as np
from math import log, sqrt, exp, erf
DB="/Users/trevorthompson/code/TrevJT/agents/options-100/data/market.db"
N=lambda x:0.5*(1+erf(x/sqrt(2)))
def Ninv(p):
    lo,hi=-10,10
    for _ in range(80):
        m=(lo+hi)/2
        if N(m)<p: lo=m
        else: hi=m
    return (lo+hi)/2
def bs_call(S,K,T,v):
    if T<=0: return max(S-K,0)
    d1=(log(S/K)+0.5*v*v*T)/(v*sqrt(T)); d2=d1-v*sqrt(T)
    return S*N(d1)-K*N(d2)
def strike_for_delta(S,T,v,delta):  # call side, r=0
    d1=Ninv(delta); return S*exp(-(d1*v*sqrt(T)-0.5*v*v*T))
TDAY=1/252
FEE=0.04/100  # per share per side
def ask(m): return math.ceil(max(m,0.01)*100+0.5-1e-9)/100   # mid + half of $0.01 spread, tick-rounded
def bid(m): return max(0.0, math.floor(m*100-0.5+1e-9)/100) if m>=0.015 else 0.0

# ---------- BS tables ----------
print("== 0DTE call, S=775, bought at open (T=1 trading day), r=0 ==")
for iv in (0.15,0.20,0.25):
    print(f"\nIV {iv:.0%}  (1-day sd = {iv*sqrt(TDAY)*100:.2f}%)")
    print("delta  strike  %OTM   mid    ask   theta/hr(1st hr) | close value & multiple of ask for SPY +0.5% +1% +1.5% +2%  | P(ITM)")
    S=775
    for d in (0.50,0.25,0.10,0.05,0.02):
        K=strike_for_delta(S,TDAY,iv,d); K=round(K)
        m=bs_call(S,K,TDAY,iv); a=ask(m)
        th=(m-bs_call(S,K,TDAY*(5.5/6.5),iv))
        outs=[]
        for mv in (0.005,0.01,0.015,0.02):
            val=max(S*(1+mv)-K,0); outs.append(f"{val:5.2f}({val/a:5.1f}x)")
        z=(log(S/K))/(iv*sqrt(TDAY))
        print(f"{d:4.2f}  {K:5d}  {100*(K/S-1):4.2f}%  {m:5.2f}  {a:5.2f}  {th:5.2f}  | "+"  ".join(outs)+f" | {N(z):.3f}")
    # debit spread ATM / +5
    for w in (3,5):
        K1=775;K2=775+w
        m=bs_call(S,K1,TDAY,iv)-bs_call(S,K2,TDAY,iv); a=ask(bs_call(S,K1,TDAY,iv))-bid(bs_call(S,K2,TDAY,iv))
        outs=[f"{min(max(S*(1+mv)-K1,0),w):5.2f}({min(max(S*(1+mv)-K1,0),w)/a:4.1f}x)" for mv in (0.005,0.01,0.015,0.02)]
        print(f"ATM/+{w} call debit spread mid {m:.2f} cost {a:.2f} max {w}: "+"  ".join(outs))

# ---------- data ----------
con=sqlite3.connect(f"file:{DB}?mode=ro",uri=True)
spy=dict((r[0],(r[1],r[2])) for r in con.execute("select ts,open,close from bars where symbol='SPY' and interval='1d' and open>0"))
vix=dict(con.execute("select ts,close from bars where symbol='^VIX' and interval='1d'"))
vd=sorted(vix)
import bisect
rows=[]
for ts in sorted(spy):
    i=bisect.bisect_left(vd,ts)-1
    if i<0: continue
    o,c=spy[ts]; rows.append((ts,vix[vd[i]],c/o-1))
V=np.array([r[1] for r in rows]); R=np.array([r[2] for r in rows])
print(f"\n{len(rows)} SPY days {rows[0][0]}..{rows[-1][0]}")
for lo,hi in ((0,13),(13,16),(16,20),(20,25),(25,35),(35,99)):
    m=(V>=lo)&(V<hi)
    print(f"prior VIX {lo}-{hi}: {m.mean():5.1%} of days, sd(o->c)={R[m].std()*100:.2f}%, |move|>1%: {(abs(R[m])>0.01).mean():.1%}, >1.5%: {(abs(R[m])>0.015).mean():.1%}, >2%: {(abs(R[m])>0.02).mean():.1%}")

# ---------- one-day trade P&L per $ of premium ----------
def trade(equity, frac, delta, v, r, rng, spreadw=None, fractional=False, minone=False):
    """returns new equity. direction random; uses symmetric BS (call on up bet, put on down bet via symmetry)"""
    S=100.0*7.75  # scale irrelevant except tick effects; use S=775
    iv=v/100*0.9
    up = rng.random()<0.5
    move = r if up else -r          # favourable move in bet direction (put = mirror; ignores skew)
    if spreadw is None:
        K=round(strike_for_delta(S,TDAY,iv,delta))
        m=bs_call(S,K,TDAY,iv); px=ask(m)+FEE
        exitv=max(S*(1+move)-K,0)
        proceeds = (bid(exitv) - FEE) if exitv>=0.015 else 0.0
    else:
        K1=round(S); K2=K1+spreadw
        px=ask(bs_call(S,K1,TDAY,iv))-bid(bs_call(S,K2,TDAY,iv))+2*FEE
        exitv=min(max(S*(1+move)-K1,0),spreadw)
        proceeds = max(exitv-0.01-2*FEE,0) if exitv>0.02 else 0.0
    cost=px*100
    budget=equity*frac
    n = budget/cost if fractional else math.floor(budget/cost)
    if n<=0 and minone and equity>=cost: n=1
    if n<=0: return equity, False
    return equity - n*cost + n*proceeds*100, True

def sim(name, frac, delta, vixmin=0, stop=None, spreadw=None, fractional=False, minone=False, paths=10000, horizon=756, start=143.64, seed=1):
    rng=np.random.default_rng(seed)
    n=len(R); hit1=hit5=ruin=0; t1=[];tend=[];final=[];trades=[]
    for p in range(paths):
        i=rng.integers(0,n-horizon); e=start; reached1=False; out=None; ntr=0
        for t in range(horizon):
            v=V[i+t]; r=R[i+t]
            if v<vixmin: continue
            e2,traded=trade(e,frac,delta,v,r,rng,spreadw,fractional,minone)
            if not traded:
                continue   # unaffordable today -> skip
            e=e2; ntr+=1
            if e>=1000 and not reached1: reached1=True; t1.append(t)
            if stop and e>=stop: out='stop'; break
            if e>=5000: out='5k'; break
            if e<20: out='ruin'; break
        if reached1: hit1+=1
        if out=='5k': hit5+=1
        if out=='ruin': ruin+=1
        tend.append(t); final.append(e); trades.append(ntr)
    final=np.array(final)
    print(f"{name:52s} P($1k)={hit1/paths:6.2%}  P($5k)={hit5/paths:6.2%}  P(ruin)={ruin/paths:6.1%}  "
          f"alive@3y={1-(hit5+ruin)/paths-(0 if not stop else 0):5.1%} med trades={np.median(trades):4.0f} med days to end={np.median(tend):5.0f}  med days to $1k={np.median(t1) if t1 else float('nan'):5.0f}  P(final<$30)={(final<30).mean():5.1%} P(final>=$143)={(final>=143.6).mean():5.1%} mean final=${final.mean():6.0f} med final=${np.median(final):6.1f}")


sim("(a') ATM 0DTE 35% FRACTIONAL daily", 0.35, 0.50, fractional=True)
sim("(a'') ATM/+3 debit spr 35% (min 1 lot) daily", 0.35, None, spreadw=3, minone=True)
sim("(a3) ATM/+3 debit spr ALL-IN VIX>=20 stop1500", 1.0, None, spreadw=3, vixmin=20, stop=1500)
sim("(a4) ATM/+3 debit spr ALL-IN VIX>=20 stop5000", 1.0, None, spreadw=3, vixmin=20, stop=5000)
sim("(b) 0.05d all-in VIX>=20", 1.0, 0.05, vixmin=20)
sim("(c) 0.10d all-in daily stop1500", 1.0, 0.10, stop=1500)
sim("(c2) 0.10d all-in VIX>=20 stop1500", 1.0, 0.10, vixmin=20, stop=1500)
sim("(c4) 0.10d all-in VIX>=25 stop1500", 1.0, 0.10, vixmin=25, stop=1500)
sim("(c5) 0.25d all-in VIX>=20 stop1500", 1.0, 0.25, vixmin=20, stop=1500, minone=True)
sim("(d) 0.10d 35% VIX>=20", 0.35, 0.10, vixmin=20, minone=True)
