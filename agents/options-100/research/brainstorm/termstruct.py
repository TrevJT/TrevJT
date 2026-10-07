import sqlite3,pandas as pd,numpy as np
con=sqlite3.connect("file:/Users/trevorthompson/code/TrevJT/agents/options-100/data/market.db?mode=ro",uri=True)
g=lambda s:pd.read_sql(f"select ts,close from bars where symbol='{s}' and interval='1d'",con,parse_dates=['ts']).set_index('ts').close
r=(g('^VIX9D')/g('^VIX')).dropna(); spy=g('SPY')
print("VIX9D/VIX now %.3f pctile %.1f%%"%(r.iloc[-1],(r<r.iloc[-1]).mean()*100))
f5=(spy.shift(-5)/spy-1).reindex(r.index); a5=f5.abs()
lo=r<=r.quantile(0.05)
print("next-5d |SPY| when ratio<=5th pct: %.2f%% (n=%d) vs all %.2f%%; P(|5d|>3%%) %.1f%% vs %.1f%%"%(a5[lo].mean()*100,lo.sum(),a5.mean()*100,(a5[lo]>.03).mean()*100,(a5>.03).mean()*100))
v=g('^VIX').reindex(r.index); impl5=v/100*np.sqrt(5/252)
print("realized/implied 5d: low-ratio %.2f vs all %.2f"%((a5/impl5)[lo].mean(),(a5/impl5).mean()))
