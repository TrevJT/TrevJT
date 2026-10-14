#!/usr/bin/env python3
"""Where do option trades actually print inside the quoted spread? (owner, 2026-10-14: "if a spread is $1-$2 but fills happen at $1.20, it's worth grabbing")

For each ticker: 30-400 DTE contracts within ±25% of spot that traded TODAY (yfinance lastTradeDate).
  position = (last - bid) / (ask - bid)   0 = printed at bid, 0.5 = mid, 1 = ask
  eff_cost = |last - mid| / mid           one-way cost actually paid vs mid (the quoted half-spread is (ask-bid)/2/mid)
  capture  = eff_cost / quoted half-spread   <1 means trades print inside the quote
Caveats: last-trade side unknown (buy vs sell prints mixed); after-hours bid/ask may be the closing quote, not the quote at the trade.
  python3 agents/options-100/bot/research_fills.py TICKER [TICKER ...]
"""
import socket, sys, json, statistics, math
_gai = socket.getaddrinfo
socket.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, socket.AF_INET, *a, **k)
from datetime import datetime, timezone, date
import yfinance as yf

def scan(t):
    tk = yf.Ticker(t)
    try:
        spot = tk.fast_info["last_price"]
        exps = tk.options
    except Exception as e:
        return {"t": t, "err": type(e).__name__}
    rows = []
    today = date.today()
    for e in exps:
        dte = (date.fromisoformat(e) - today).days
        if not 30 <= dte <= 400: continue
        try: ch = tk.option_chain(e)
        except Exception: continue
        for typ, df in (("call", ch.calls), ("put", ch.puts)):
            for r in df.itertuples():
                if not (0.75 * spot <= r.strike <= 1.25 * spot): continue
                b, a, l = r.bid, r.ask, r.lastPrice
                if not (b > 0 and a > b and l > 0): continue
                ltd = r.lastTradeDate
                if ltd is None or ltd.date() != today: continue
                mid = (a + b) / 2; half = (a - b) / 2 / mid
                pos = (l - b) / (a - b)
                rows.append(dict(e=e, dte=dte, typ=typ, k=r.strike, bid=b, ask=a, last=l, vol=int(r.volume or 0),
                                 qspread=(a - b) / mid, pos=pos, eff=abs(l - mid) / mid, cap=abs(l - mid) / mid / half if half else None))
    if not rows: return {"t": t, "spot": spot, "n": 0}
    inside = [r for r in rows if 0 <= r["pos"] <= 1]
    w = lambda k: statistics.median(r[k] for r in rows)
    return {"t": t, "spot": round(spot, 2), "n": len(rows), "contracts_vol": sum(r["vol"] for r in rows),
            "med_quoted_spread": round(w("qspread"), 3), "med_pos": round(w("pos"), 2),
            "share_inside_quote": round(len(inside) / len(rows), 2),
            "med_eff_cost_oneway": round(w("eff"), 3), "med_capture_of_half_spread": round(statistics.median(r["cap"] for r in rows if r["cap"] is not None), 2),
            "samples": sorted(rows, key=lambda r: -r["vol"])[:3]}

if __name__ == "__main__":
    out = [scan(t) for t in sys.argv[1:]]
    for o in out:
        if o.get("n"):
            print(f"{o['t']:6s} n={o['n']:3d} vol={o['contracts_vol']:6d} quoted spread {o['med_quoted_spread']*100:5.1f}%  last@ {o['med_pos']:.2f} of spread  inside {o['share_inside_quote']*100:3.0f}%  eff one-way cost {o['med_eff_cost_oneway']*100:5.1f}% (= {o['med_capture_of_half_spread']:.2f}x quoted half-spread)")
        else: print(f"{o['t']:6s} no contracts traded today in 30-400 DTE ±25%" + (f" ({o.get('err')})" if o.get("err") else ""))
    json.dump(out, open(sys.argv[0].replace("bot/research_fills.py", "data/research_fills_2026-10-14.json"), "w"), indent=1, default=str)
