#!/usr/bin/env python3
"""Fresh market headlines from public RSS feeds (no credentials). Replaces WebSearch for news, which returned stale pages.

  python3 agents/options-100/bot/news.py            # last 12h, newest first, flags market-moving keywords
  python3 agents/options-100/bot/news.py --hours 1  # just the last hour (per-cycle check)

Writes state/news.json {ts, items:[{t, src, title, flag}]}. Flag = matched keyword group (fed, war, tariff, oil, macro, shock).
"""
import json, re, sys, time, urllib.request, email.utils, xml.etree.ElementTree as ET
from pathlib import Path

FEEDS = {
    "cnbc": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "cnbc-mkts": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    "marketwatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "gnews-markets": "https://news.google.com/rss/search?q=stock+market+when:1d&hl=en-US&gl=US&ceid=US:en",
    "gnews-oil-iran": "https://news.google.com/rss/search?q=oil+OR+Iran+OR+Hormuz+when:1d&hl=en-US&gl=US&ceid=US:en",
    "gnews-fed": "https://news.google.com/rss/search?q=Federal+Reserve+OR+Powell+OR+CPI+when:1d&hl=en-US&gl=US&ceid=US:en",
}
FLAGS = {
    "fed": r"\b(fed|fomc|powell|rate cut|rate hike|warsh)\b",
    "war": r"\b(strike[sd]?|missile|attack|ceasefire|invasion|hormuz|iran|israel)\b",
    "tariff": r"\b(tariff|trade war|sanction)\b",
    "oil": r"\b(oil|crude|opec|brent|wti)\b",
    "macro": r"\b(cpi|inflation|jobs report|payroll|gdp|ppi|retail sales)\b",
    "shock": r"\b(plunge|plummet|crash|soar|surge|halt|outage|record (high|low)|selloff|sell-off)\b",
}
OUT = Path(__file__).resolve().parents[1] / "state" / "news.json"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 options-100-news"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read()


def main():
    import signal  # hard cap: a feed that drips bytes can defeat the per-socket timeout and hang the trading cycle
    signal.signal(signal.SIGALRM, lambda *a: (_ for _ in ()).throw(TimeoutError("news.py 25s cap")))
    signal.alarm(25)
    hours = float(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 12
    cutoff = time.time() - hours * 3600
    items, seen, errs = [], set(), []
    for src, url in FEEDS.items():
        try:
            root = ET.fromstring(fetch(url))
        except TimeoutError:
            errs.append(f"{src}: total-cap"); break
        except Exception as e:
            errs.append(f"{src}: {type(e).__name__}"); continue
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            pub = it.findtext("pubDate")
            try:
                t = email.utils.parsedate_to_datetime(pub).timestamp()
            except Exception:
                continue
            key = re.sub(r"\W+", "", title.lower())[:60]
            if t < cutoff or not title or key in seen:
                continue
            seen.add(key)
            flag = ",".join(k for k, p in FLAGS.items() if re.search(p, title, re.I))
            items.append({"t": t, "src": src, "title": title, "flag": flag})
    items.sort(key=lambda x: -x["t"])
    OUT.write_text(json.dumps({"ts": time.time(), "hours": hours, "errors": errs, "items": items}, indent=1))
    print(f"{len(items)} headlines in last {hours:g}h from {len(FEEDS) - len(errs)}/{len(FEEDS)} feeds" + (f" (failed: {', '.join(errs)})" if errs else ""))
    for x in items[:25]:
        print(f"  {time.strftime('%m-%d %H:%M', time.localtime(x['t']))} [{x['src']}] {x['title'][:110]}" + (f"  <{x['flag']}>" if x["flag"] else ""))


if __name__ == "__main__":
    main()
