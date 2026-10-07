#!/usr/bin/env python3
"""Deterministic math for the options-100 0DTE scalper. No network. Reads JSON files written by the
orchestrator from Robinhood MCP results and prints a decision block.

Usage:
  python3 score.py score  state/bars_SPY.json state/bars_QQQ.json [--now HH:MM]   -> momentum score per symbol
  python3 score.py manage state/positions.json state/marks.json [--now HH:MM]       -> exit actions per position

Bars file: the raw tool result of get_equity_historicals (5-minute bars). Keys are normalized loosely.
Marks file: {"<contract_id>": {"bid":..,"ask":..}, "SPY": {"vwap":.., "close":..}, ...}
Positions file: [{"id":..,"symbol":"SPY","type":"call","qty":1,"entry":0.25,"entered":"09:47","window":"A","peak":0.25}]
All times ET, HH:MM, from the orchestrator.
"""
import json, sys, statistics
from datetime import datetime, timezone, timedelta

ET = timezone(timedelta(hours=-4))  # EDT; set to -5 after Nov 1 2026


def _get(d, *names, default=None):
    for n in names:
        if isinstance(d, dict) and n in d and d[n] not in (None, ""):
            return d[n]
    return default


def _bars(obj):
    """Flatten whatever shape the tool returned into [{t, o, h, l, c, v}] sorted by time (ET)."""
    if isinstance(obj, dict):
        for k in ("historicals", "data_points", "bars", "results", "data", "candles"):
            if k in obj:
                obj = obj[k]; break
        else:
            for v in obj.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    obj = v; break
    if isinstance(obj, dict):
        obj = next((v for v in obj.values() if isinstance(v, list)), [])
    out = []
    for b in obj or []:
        if not isinstance(b, dict):
            continue
        t = _get(b, "begins_at", "timestamp", "time", "t", "datetime", "start")
        try:
            ts = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts = ts.astimezone(ET)
        except Exception:
            continue
        o = float(_get(b, "open_price", "open", "o", default=0) or 0)
        h = float(_get(b, "high_price", "high", "h", default=o) or o)
        l = float(_get(b, "low_price", "low", "l", default=o) or o)
        c = float(_get(b, "close_price", "close", "c", default=o) or o)
        v = float(_get(b, "volume", "v", default=0) or 0)
        if c > 0:
            out.append({"t": ts, "o": o, "h": h, "l": l, "c": c, "v": v})
    out.sort(key=lambda x: x["t"])
    return out


def _session(bars, day):
    return [b for b in bars if b["t"].date() == day and (b["t"].hour, b["t"].minute) >= (9, 30)
            and (b["t"].hour, b["t"].minute) < (16, 0)]


def score_symbol(bars, now_hm):
    if not bars:
        return {"error": "no bars"}
    day = bars[-1]["t"].date()
    today = _session(bars, day)
    if len(today) < 3:
        return {"error": f"only {len(today)} session bars for {day}"}
    # VWAP
    pv = cv = 0.0; vwaps = []
    for b in today:
        tp = (b["h"] + b["l"] + b["c"]) / 3
        pv += tp * b["v"]; cv += b["v"]
        vwaps.append(pv / cv if cv else b["c"])
    vwap = vwaps[-1]
    slope = vwaps[-1] - vwaps[-4] if len(vwaps) >= 4 else 0.0
    # ATR(14) on 5-min bars over all history
    trs = []
    for i in range(1, len(bars)):
        p = bars[i - 1]["c"]; b = bars[i]
        trs.append(max(b["h"] - b["l"], abs(b["h"] - p), abs(b["l"] - p)))
    atr = statistics.mean(trs[-14:]) if trs else 0.0
    # Opening range = first 5-min bar; power-hour range = 13:00-14:00
    orb = today[0]
    ph = [b for b in today if 13 <= b["t"].hour < 14]
    last = today[-1]
    close = last["c"]
    # Relative volume: last bar vs median of history excluding first two bars of each day
    hist = [b["v"] for b in bars if not ((b["t"].hour, b["t"].minute) in ((9, 30), (9, 35)))]
    med = statistics.median(hist) if hist else 0
    rvol = last["v"] / med if med else 0.0
    now = now_hm or last["t"].strftime("%H:%M")
    hh, mm = map(int, now.split(":"))
    window = "A" if (9, 40) <= (hh, mm) <= (11, 0) else ("B" if (14, 0) <= (hh, mm) <= (15, 10) else None)
    # Components
    comp = {}
    comp["vwap_side"] = 1 if close > vwap else -1
    comp["atr_dist"] = (1 if close - vwap > 0.5 * atr else (-1 if vwap - close > 0.5 * atr else 0))
    comp["vwap_slope"] = 1 if slope > 0 else (-1 if slope < 0 else 0)
    last4 = today[-4:]
    ups = sum(1 for b in last4 if b["c"] > b["o"]); dns = sum(1 for b in last4 if b["c"] < b["o"])
    comp["bars_3of4"] = 1 if ups >= 3 else (-1 if dns >= 3 else 0)
    if window == "B" and ph:
        hi, lo = max(b["h"] for b in ph), min(b["l"] for b in ph)
    else:
        hi, lo = orb["h"], orb["l"]
    comp["range_break"] = 1 if close > hi else (-1 if close < lo else 0)
    base = sum(comp.values())
    comp["rvol"] = (1 if base > 0 else -1 if base < 0 else 0) if rvol >= 1.3 else 0
    S = sum(comp.values())
    decision = "CALL" if S >= 4 else ("PUT" if S <= -4 else "NONE")
    if window is None:
        decision = "NONE (outside entry window)"
    return {"as_of": last["t"].strftime("%Y-%m-%d %H:%M ET"), "now": now, "window": window, "close": round(close, 2),
            "vwap": round(vwap, 2), "vwap_slope_15m": round(slope, 3), "atr5": round(atr, 3),
            "or_high": orb["h"], "or_low": orb["l"], "range_hi": hi, "range_lo": lo, "rvol": round(rvol, 2),
            "components": comp, "score": S, "decision": decision}


def manage(positions, marks, now_hm):
    hh, mm = map(int, now_hm.split(":"))
    t = hh * 60 + mm
    out = []
    for p in positions:
        q = marks.get(p["id"], {})
        bid, ask = float(q.get("bid", 0) or 0), float(q.get("ask", 0) or 0)
        mid = (bid + ask) / 2 if bid and ask else bid
        entry = float(p["entry"]); peak = max(float(p.get("peak", entry)), mid)
        pnl = (mid / entry - 1) if entry else 0
        eh, em = map(int, p["entered"].split(":")); held = t - (eh * 60 + em)
        sym = marks.get(p["symbol"], {})
        vwap, close = sym.get("vwap"), sym.get("close")
        act, why = "HOLD", []
        if t >= 15 * 60 + 45:
            act, why = "SELL_ALL", ["15:45 flatten"]
        elif pnl <= -0.45:
            act, why = "SELL_ALL", [f"hard stop {pnl:+.0%}"]
        elif p.get("scaled") and (mid <= peak * 0.65):
            act, why = "SELL_ALL", [f"trail: {mid:.2f} <= 65% of peak {peak:.2f}"]
        elif p.get("scaled") and vwap and close and ((p["type"] == "call" and close < vwap) or (p["type"] == "put" and close > vwap)):
            act, why = "SELL_ALL", ["trail: close back through VWAP"]
        elif pnl >= 1.0 and int(p["qty"]) == 1:
            act, why = "SELL_ALL", [f"+100% single contract {pnl:+.0%}"]
        elif pnl >= 0.8 and int(p["qty"]) >= 2 and not p.get("scaled"):
            act, why = "SELL_HALF", [f"+80% scale-out {pnl:+.0%}"]
        elif held >= 30 and pnl < 0.25 and not p.get("scaled"):
            act, why = "SELL_ALL", [f"time stop: {held}m held, {pnl:+.0%} < +25%"]
        elif p.get("window") == "A" and t >= 12 * 60 and pnl < 0.5:
            act, why = "SELL_ALL", [f"window A exit by 12:00, {pnl:+.0%} < +50%"]
        elif t >= 15 * 60 + 30:
            why = ["15:30: start working the bid; sell at bid if not filled by 15:40"]
        out.append({"id": p["id"], "symbol": p["symbol"], "type": p["type"], "qty": p["qty"], "entry": entry,
                    "mid": round(mid, 3), "bid": bid, "pnl": round(pnl, 3), "peak": round(peak, 3), "held_min": held,
                    "action": act, "why": why})
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    now = None
    if "--now" in args:
        i = args.index("--now"); now = args[i + 1]; del args[i:i + 2]
    if not now:
        now = datetime.now(ET).strftime("%H:%M")
    if args and args[0] == "score":
        res = {}
        for f in args[1:]:
            sym = f.split("bars_")[-1].split(".")[0]
            res[sym] = score_symbol(_bars(json.load(open(f))), now)
        print(json.dumps(res, indent=1, default=str))
    elif args and args[0] == "manage":
        pos = json.load(open(args[1])); marks = json.load(open(args[2]))
        print(json.dumps(manage(pos, marks, now), indent=1))
    else:
        print(__doc__)
