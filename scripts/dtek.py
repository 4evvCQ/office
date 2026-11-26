#!/usr/bin/env python3
"""Витягує графік відключень для групи офісу зі сторінки ДТЕК і пише dtek.json."""
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://www.dtek-kem.com.ua/ua/shutdowns"
OFFICE = "27.1"
GROUPS = ["27.1", "25.1", "29.1", "35.1"]
OUT = "dtek.json"
KYIV = timezone(timedelta(hours=2))
ATTEMPTS = 3            # скільки разів пробувати, якщо ДТЕК віддав сторінку без графіка
PAUSE = 20              # секунд між спробами
STALE_HOURS = 6         # після скількох годин без оновлення це вже справжня проблема

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


def fetch_page():
    req = urllib.request.Request(URL, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")


def soft_fail(reason):
    """ДТЕК тимчасово не віддає графік. Сваримось лише якщо дані вже протухли."""
    age = None
    try:
        with open(OUT, encoding="utf-8") as f:
            fetched = json.load(f).get("fetched")
        if fetched:
            age = (datetime.now(KYIV) - datetime.fromisoformat(fetched)).total_seconds() / 3600
    except (OSError, ValueError, TypeError):
        pass

    if age is None:
        print(reason + "; попередніх даних немає", file=sys.stderr)
        return 1
    if age > STALE_HOURS:
        print("%s; дані не оновлювались %.1f год — це вже проблема" % (reason, age),
              file=sys.stderr)
        return 1
    print("%s; лишаємо попередні дані (їм %.1f год), спробуємо наступного разу" % (reason, age))
    return 0


def build(page):
    """Розбирає сторінку. Повертає dict або None, якщо графіка на ній немає."""
    if "DisconSchedule.fact" not in page:
        return None

    fact = grab_object(page, "DisconSchedule.fact")
    days = fact.get("data") or {}
    if not days:
        return None

    day_ts = str(fact.get("today") or sorted(days)[0])
    day = days.get(day_ts, {})

    groups = {}
    for g in GROUPS:
        raw = day.get("GPV" + g)
        if raw:
            groups[g] = {str(h): raw.get(str(h), "yes") for h in range(1, 25)}
    if OFFICE not in groups:
        return None

    m = re.search(r"DisconSchedule\.updateTimestamp\s*=\s*'([^']*)'", page)
    return {
        "group": OFFICE,
        "date": datetime.fromtimestamp(int(day_ts), KYIV).strftime("%Y-%m-%d"),
        "schedule_updated": fact.get("update"),
        "site_updated": m.group(1) if m else None,
        "hours": groups[OFFICE],
        "groups": groups,
        "fetched": datetime.now(KYIV).isoformat(timespec="seconds"),
    }


def main():
    data, last = None, "сторінка без графіка"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            data = build(fetch_page())
        except Exception as e:                      # мережа, таймаут, биті дужки
            last = "%s: %s" % (type(e).__name__, e)
            data = None
        if data:
            break
        if attempt < ATTEMPTS:
            print("спроба %d з %d невдала (%s), чекаю %d с" % (attempt, ATTEMPTS, last, PAUSE),
                  file=sys.stderr)
            time.sleep(PAUSE)

    if not data:
        return soft_fail("ДТЕК не віддав графік з %d спроб (%s)" % (ATTEMPTS, last))

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
