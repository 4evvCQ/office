#!/usr/bin/env python3
"""Витягує графік відключень для групи офісу зі сторінки ДТЕК і пише dtek.json."""
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://www.dtek-kem.com.ua/ua/shutdowns"
GROUP = "GPV27.1"
OUT = "dtek.json"
KYIV = timezone(timedelta(hours=2))

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
}


def grab_object(text, marker):
    """Повертає JSON-об'єкт, що йде після marker, рахуючи дужки."""
    i = text.index(marker) + len(marker)
    while text[i] not in "{":
        i += 1
    depth, start, in_str, esc = 0, i, False, False
    for j in range(i, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:j + 1])
    raise ValueError("незбалансовані дужки після " + marker)


def main():
    req = urllib.request.Request(URL, headers=HEADERS)
    page = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")

    if "DisconSchedule.fact" not in page:
        print("на сторінці немає DisconSchedule.fact — ймовірно, спрацював захист", file=sys.stderr)
        return 1

    fact = grab_object(page, "DisconSchedule.fact")
    days = fact.get("data") or {}
    if not days:
        print("порожній розклад", file=sys.stderr)
        return 1

    day_ts = str(fact.get("today") or sorted(days)[0])
    hours = days.get(day_ts, {}).get(GROUP)
    if not hours:
        print("немає даних для групи " + GROUP, file=sys.stderr)
        return 1

    m = re.search(r"DisconSchedule\.updateTimestamp\s*=\s*'([^']*)'", page)
    data = {
        "group": GROUP.replace("GPV", ""),
        "date": datetime.fromtimestamp(int(day_ts), KYIV).strftime("%Y-%m-%d"),
        "schedule_updated": fact.get("update"),
        "site_updated": m.group(1) if m else None,
        "hours": {str(h): hours.get(str(h), "yes") for h in range(1, 25)},
        "fetched": datetime.now(KYIV).isoformat(timespec="seconds"),
    }

    old = None
    try:
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        pass
    if old and {k: v for k, v in old.items() if k != "fetched"} == \
               {k: v for k, v in data.items() if k != "fetched"}:
        print("без змін")
        return 0

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("оновлено:", data["date"], data["schedule_updated"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
