import yfinance as yf, pandas as pd, warnings, time, os; warnings.filterwarnings("ignore")
os.makedirs("raw", exist_ok=True)
daily = ["^N225","^GDAXI","^STOXX50E","^FTSE","^HSI","000001.SS","^KS11","^AXJO","EURUSD=X","JPY=X","GBPUSD=X","AUDUSD=X","ES=F","NQ=F","YM=F","RTY=F","CL=F","GC=F","SI=F","HG=F","NG=F","ZN=F","ZB=F","6E=F","6J=F","BTC-USD","ETH-USD","FXE","FXY","UUP","EWJ","FXI","EWZ","EFA","EEM","GLD","SLV","USO","TLT","IEF","HYG","IBIT","COIN","MSTR","SPY","QQQ","IWM","^VIX","^VIX9D","^VIX3M","^VVIX","^OVX","^GVZ","^MOVE","^SKEW","^VXN","^RVX","^VXTLT","DX-Y.NYB","XSP","^XSP"]
for s in daily:
    try:
        d = yf.download(s, period="max", interval="1d", progress=False, auto_adjust=False, threads=False)
        if len(d)==0: print("EMPTY", s); continue
        d.columns = [c[0] if isinstance(c, tuple) else c for c in d.columns]
        d.to_csv(f"raw/yf_{s.replace('^','_').replace('=','_')}_1d.csv")
        print(s, len(d), d.index.min().date(), d.index.max().date(), flush=True)
    except Exception as e: print("ERR", s, e)
    time.sleep(0.6)
for s in ["ES=F","NQ=F","CL=F","BTC-USD","^VIX","SPY","QQQ","GC=F","6J=F","6E=F","ZN=F"]:
    try:
        d = yf.download(s, period="730d", interval="1h", progress=False, auto_adjust=False, threads=False)
        d.columns = [c[0] if isinstance(c, tuple) else c for c in d.columns]
        d.to_csv(f"raw/yf_{s.replace('^','_').replace('=','_')}_1h.csv"); print(s, "1h", len(d), d.index.min(), d.index.max(), flush=True)
    except Exception as e: print("ERR1h", s, e)
    time.sleep(0.6)
