#!/usr/bin/env python3
"""
Get the exact post date of an Instagram post/reel from its URL.

Instagram's feed does not show post dates, but the code in every post URL
(e.g. /reel/DfYOAFdCRcX/) contains the creation time. Tested on 16 reels with
known dates: 16/16 matched.

Usage:
  python scripts/reel_date.py https://www.instagram.com/reel/DfYOAFdCRcX/ [more urls...]
  python scripts/reel_date.py --csv data/products.csv          # fills post_date + age_days columns in place

No extra packages needed (standard library only, Python 3.8+).
"""
import csv
import re
import sys
from datetime import datetime, timezone

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
IG_EPOCH_MS = 1314220021721  # Instagram's ID epoch
CODE_RE = re.compile(r"instagram\.com/(?:[^/]+/)?(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)")


def code_from_url(url):
    m = CODE_RE.search(url or "")
    return m.group(1) if m else None


def post_datetime(code):
    n = 0
    for ch in code[:11]:  # longer codes (private posts) carry the ID in the first 11 chars
        n = n * 64 + ALPHABET.index(ch)
    return datetime.fromtimestamp(((n >> 23) + IG_EPOCH_MS) / 1000, tz=timezone.utc)


def age_days(dt, now=None):
    now = now or datetime.now(timezone.utc)
    return round((now - dt).total_seconds() / 86400, 1)


def fill_csv(path):
    try:
        f = open(path, newline="", encoding="utf-8")
    except FileNotFoundError:
        print(f"File not found: {path}")
        return
    with f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []
    for col in ("post_date", "age_days"):
        if col not in fields:
            fields.append(col)
    filled = 0
    for r in rows:
        code = code_from_url(r.get("reel_url", ""))
        if not code:
            continue
        try:
            dt = post_datetime(code)
        except ValueError:
            continue
        r["post_date"] = dt.strftime("%Y-%m-%d %H:%M")
        r["age_days"] = age_days(dt)
        filled += 1
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Filled post_date/age_days for {filled} of {len(rows)} rows in {path}")


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "--csv":
        fill_csv(argv[1])
        return 0
    for url in argv:
        code = code_from_url(url) or url  # also accept a bare code
        try:
            dt = post_datetime(code)
            print(f"{url}\t{dt:%Y-%m-%d %H:%M} UTC\t{age_days(dt)} days old")
        except ValueError:
            print(f"{url}\tcould not read a post code")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
