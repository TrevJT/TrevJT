#!/usr/bin/env python3
"""Deterministic math for the options-100 0DTE scalper. No network.
Bars live in agents/options-100/state/bars_<SYM>.csv as lines: begins_at_utc,open,high,low,close,volume

  score.py ingest SYM "<lines>"      append bars (dedupe by timestamp, keep last 3 sessions)
  score.py last SYM                  print the last stored bar's begins_at (UTC) for the next incremental fetch
  score.py score SPY QQQ [--now HH:MM]
  score.py manage positions.json marks.json [--now HH:MM]
All clock times are ET (HH:MM)."""
import json, os, sys, statistics
from datetime import datetime, timezone, timedelta

from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state")


def _path(sym): return os.path.join(STATE, f"bars_{sym}.csv")


def _load(sym):
    out = []
    if not os.path.exists(_path(sym)): return out
    for line in open(_path(sym)):
        p = line.strip().split(",")
        if len(p) < 6: continue
        try:
            ts = datetime.fromisoformat(p[0].replace("Z", "+00:00")).astimezone(ET)
            out.append({"t": ts, "o": float(p[1]), "h": float(p[2]), "l": float(p[3]), "c": float(p[4]), "v": float(p[5])})
        except Exception:
            continue
    out.sort(key=lambda b: b["t"])
    return out


def ingest(sym, text):
    bars = {b["t"]: b for b in _load(sym)}
    n = 0
    for line in text.replace(";", "\n").splitlines():
        p = line.strip().split(",")
        if len(p) < 6: continue
        try:
            ts = datetime.fromisoformat(p[0].replace("Z", "+00:00")).astimezone(ET)
            bars[ts] = {"t": ts, "o": float(p[1]), "h": float(p[2]), "l": float(p[3]), "c": float(p[4]), "v": float(p[5])}; n += 1
        except Exception:
            continue
    days = sorted({t.date() for t in bars})[-3:]
    keep = sorted((b for b in bars.values() if b["t"].date() in days), key=lambda b: b["t"])
    with open(_path(sym), "w") as f:
        for b in keep:
            f.write(f"{b['t'].astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')},{b['o']},{b['h']},{b['l']},{b['c']},{int(b['v'])}\n")
    return n, len(keep)


def _session(bars, day):
    return [b for b in bars if b["t"].date() == day and (9, 30) <= (b["t"].hour, b["t"].minute) < (16, 0)]


def score_symbol(sym, now_hm, day=None):
    bars = _load(sym)
    if not bars: return {"error": "no bars"}
    hh, mm = map(int, now_hm.split(":"))
    day = day or bars[-1]["t"].date()
    bars = [b for b in bars if b["t"].date() < day or (b["t"].hour, b["t"].minute) < (hh, mm)]
    today = _session(bars, day)
    if len(today) < 3: return {"error": f"only {len(today)} session bars for {day} before {now_hm}"}
    pv = cv = 0.0; vwaps = []
    for b in today:
        tp = (b["h"] + b["l"] + b["c"]) / 3; pv += tp * b["v"]; cv += b["v"]
        vwaps.append(pv / cv if cv else b["c"])
    vwap = vwaps[-1]; slope = vwaps[-1] - vwaps[-4] if len(vwaps) >= 4 else 0.0
    trs = [max(bars[i]["h"] - bars[i]["l"], abs(bars[i]["h"] - bars[i-1]["c"]), abs(bars[i]["l"] - bars[i-1]["c"])) for i in range(1, len(bars))]
    atr = statistics.mean(trs[-14:]) if trs else 0.0
    orb = today[0]; ph = [b for b in today if 13 <= b["t"].hour < 14]; last = today[-1]; close = last["c"]
    hist = [b["v"] for b in bars if (b["t"].hour, b["t"].minute) not in ((9, 30), (9, 35), (15, 55))]
    med = statistics.median(hist) if hist else 0; rvol = last["v"] / med if med else 0.0
    window = "A" if (9, 40) <= (hh, mm) <= (11, 0) else ("B" if (14, 0) <= (hh, mm) <= (15, 10) else None)
    comp = {"vwap_side": 1 if close > vwap else -1,
            "atr_dist": 1 if close - vwap > 0.5 * atr else (-1 if vwap - close > 0.5 * atr else 0),
            "vwap_slope": 1 if slope > 0 else (-1 if slope < 0 else 0)}
    last4 = today[-4:]; ups = sum(b["c"] > b["o"] for b in last4); dns = sum(b["c"] < b["o"] for b in last4)
    comp["bars_3of4"] = 1 if ups >= 3 else (-1 if dns >= 3 else 0)
    hi, lo = (max(b["h"] for b in ph), min(b["l"] for b in ph)) if (window == "B" and ph) else (orb["h"], orb["l"])
    comp["range_break"] = 1 if close > hi else (-1 if close < lo else 0)
    base = sum(comp.values()); comp["rvol"] = ((1 if base > 0 else -1) if base else 0) if rvol >= 1.3 else 0
    S = sum(comp.values()); decision = "CALL" if S >= 4 else ("PUT" if S <= -4 else "NONE")
    if window is None: decision = "NONE (outside entry window)"
    stale = (hh * 60 + mm) - (last["t"].hour * 60 + last["t"].minute)
    return {"symbol": sym, "last_bar": last["t"].strftime("%H:%M"), "bar_age_min": stale, "now": now_hm, "window": window,
            "close": round(close, 2), "vwap": round(vwap, 2), "vwap_slope_15m": round(slope, 3), "atr5": round(atr, 3),
            "range_hi": hi, "range_lo": lo, "rvol": round(rvol, 2), "components": comp, "score": S, "decision": decision}


def manage(positions, marks, now_hm):
    hh, mm = map(int, now_hm.split(":")); t = hh * 60 + mm; out = []
    for p in positions:
        q = marks.get(p["id"], {}); bid, ask = float(q.get("bid", 0) or 0), float(q.get("ask", 0) or 0)
        mid = (bid + ask) / 2 if bid and ask else bid
        entry = float(p["entry"]); peak = max(float(p.get("peak", entry)), mid); pnl = (mid / entry - 1) if entry else 0
        eh, em = map(int, p["entered"].split(":")); held = t - (eh * 60 + em)
        sym = marks.get(p["symbol"], {}); vwap, close = sym.get("vwap"), sym.get("close")
        act, why = "HOLD", []
        stop_level = -0.0 if p.get("stop_at_entry") else -0.45
        if t >= 15 * 60 + 45: act, why = "SELL_ALL", ["15:45 flatten"]
        elif pnl <= stop_level: act, why = "SELL_ALL", [f"hard stop {pnl:+.0%} (level {stop_level:+.0%})"]
        elif p.get("scaled") and mid <= peak * 0.65: act, why = "SELL_ALL", [f"trail: {mid:.2f} <= 65% of peak {peak:.2f}"]
        elif p.get("scaled") and vwap and close and ((p["type"] == "call" and close < vwap) or (p["type"] == "put" and close > vwap)):
            act, why = "SELL_ALL", ["trail: close back through VWAP"]
        elif pnl >= 1.0 and int(p["qty"]) == 1: act, why = "SELL_ALL", [f"+100% single contract {pnl:+.0%}"]
        elif pnl >= 0.8 and int(p["qty"]) >= 2 and not p.get("scaled"): act, why = "SELL_HALF", [f"+80% scale-out {pnl:+.0%}"]
        elif held >= 30 and pnl < 0.25 and not p.get("scaled"): act, why = "SELL_ALL", [f"time stop: {held}m held, {pnl:+.0%} < +25%"]
        elif p.get("window") == "A" and t >= 12 * 60 and pnl < 0.5: act, why = "SELL_ALL", [f"window A exit by 12:00, {pnl:+.0%} < +50%"]
        elif t >= 15 * 60 + 30: why = ["15:30: work the bid; sell at bid if unfilled by 15:40"]
        out.append({"id": p["id"], "symbol": p["symbol"], "type": p["type"], "qty": p["qty"], "entry": entry, "mid": round(mid, 3),
                    "bid": bid, "pnl": round(pnl, 3), "peak": round(peak, 3), "held_min": held, "action": act, "why": why,
                    "limit": round(max(bid, mid - 0.01), 2) if t < 15 * 60 + 40 else bid})
    return out


if __name__ == "__main__":
    a = sys.argv[1:]; now = None
    if "--now" in a:
        i = a.index("--now"); now = a[i + 1]; del a[i:i + 2]
    now = now or datetime.now(ET).strftime("%H:%M")
    if a and a[0] == "ingest":
        n, k = ingest(a[1], a[2] if len(a) > 2 else sys.stdin.read()); print(f"ingested {n}, stored {k}")
    elif a and a[0] == "last":
        b = _load(a[1]); print(b[-1]["t"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if b else "")
    elif a and a[0] == "score":
        print(json.dumps({s: score_symbol(s, now) for s in a[1:]}, indent=1, default=str))
    elif a and a[0] == "manage":
        print(json.dumps(manage(json.load(open(a[1])), json.load(open(a[2])), now), indent=1))
    else:
        print(__doc__)
