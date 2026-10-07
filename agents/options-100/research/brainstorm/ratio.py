exec(open('micro_tests.py').read().split("def stat")[0].split("# ---------- TEST 1")[0])
import statistics as st
exec("\n".join(open('micro_tests.py').read().split("# ---------- TEST 2")[1].split("def stat")[0].splitlines()[1:]))
z=[r['zc'] for r in recs]; print('stdev z (realized/VIX-implied)=',round(st.pstdev(z),3),'kurt',round(sum(x**4 for x in z)/len(z)/st.pvariance(z)**2,2))
g=[r for r in recs if abs(r['gap'])>=1]; print('gap days stdev',round(st.pstdev([r['zc'] for r in g]),3), len(g))
