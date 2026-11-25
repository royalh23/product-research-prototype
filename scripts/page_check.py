#!/usr/bin/env python3
"""
Check whether a seller's Instagram page is still alive (Rauf's checks 2 and 3).

Input: a CSV of the page's reels with at least the columns
  reel_url, views
Optional columns: pinned (yes/blank), likes, comments, shares

What it works out:
  - post date of every reel (from the URL), outlier score (views / page median)
  - CHECK 2 "videos still get views": momentum = median views of reels aged 3-10 days
    divided by median views of reels aged 11-45 days. Reels under 3 days old are
    left out because they are still growing.
  - CHECK 3 "owner still posts": days since last post, posts in last 7 / 14 days
  - recent outliers (posted in the last 14 days with 3x+ the median)

Usage:
  python scripts/page_check.py data/pages/<account>_reels.csv
  python scripts/page_check.py data/pages/<account>_reels.csv --now 2026-11-14

Writes <input>_checked.csv next to the input and prints a summary block that
can be pasted into the report.
"""
import csv
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reel_date import code_from_url, post_datetime  # noqa: E402


def num(x):
    if x is None:
        return None
    s = str(x).strip().replace(",", "").upper()
    if not s:
        return None
    mult = 1
    if s.endswith("K"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("M"):
        mult, s = 1_000_000, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    path = Path(argv[0])
    now = datetime.now(timezone.utc)
    if "--now" in argv:
        now = datetime.strptime(argv[argv.index("--now") + 1], "%Y-%m-%d").replace(tzinfo=timezone.utc)

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    reels = []
    for r in rows:
        code = code_from_url(r.get("reel_url", ""))
        if not code:
            continue
        dt = post_datetime(code)
        r["post_date"] = dt.strftime("%Y-%m-%d")
        r["age_days"] = round((now - dt).total_seconds() / 86400, 1)
        r["_views"] = num(r.get("views"))
        r["_pinned"] = str(r.get("pinned", "") or r.get("note", "")).lower().startswith(("yes", "pinned"))
        reels.append(r)

    if not reels:
        print("No reel URLs found.")
        return 1

    base = [r for r in reels if not r["_pinned"]]
    page_median = med(r["_views"] for r in base)
    for r in reels:
        v = r["_views"]
        r["outlier_score"] = round(v / page_median, 2) if (v and page_median) else ""

    unpinned = sorted(base, key=lambda r: r["age_days"])
    last_post_age = unpinned[0]["age_days"] if unpinned else None
    posts_7 = sum(1 for r in unpinned if r["age_days"] <= 7)
    posts_14 = sum(1 for r in unpinned if r["age_days"] <= 14)
    recent = [r for r in unpinned if 3 <= r["age_days"] <= 10]
    older = [r for r in unpinned if 10 < r["age_days"] <= 45]
    m_recent, m_older = med(r["_views"] for r in recent), med(r["_views"] for r in older)
    momentum = round(m_recent / m_older, 2) if (m_recent and m_older) else None
    recent_outliers = [r for r in unpinned if r["age_days"] <= 14 and r["outlier_score"] and r["outlier_score"] >= 3]
    too_new = [r for r in unpinned if r["age_days"] < 3]

    # verdicts
    if momentum is None:
        c2 = "UNKNOWN (need reels aged 3-10 and 11-45 days)"
    elif momentum >= 1.0:
        c2 = f"PASS - rising ({momentum}x)"
    elif momentum >= 0.6:
        c2 = f"OK - steady/slight cooling ({momentum}x)"
    elif momentum >= 0.35:
        c2 = f"WARN - cooling ({momentum}x)"
    else:
        c2 = f"FAIL - views dying ({momentum}x)"
    if recent_outliers and momentum is not None and momentum < 1.0:
        c2 += f"; but {len(recent_outliers)} recent outlier(s) still hitting"

    if last_post_age is None:
        c3 = "UNKNOWN"
    elif last_post_age <= 3 and posts_14 >= 4:
        c3 = f"PASS - posted {last_post_age}d ago, {posts_14} posts in 14d"
    elif last_post_age <= 7:
        c3 = f"OK - posted {last_post_age}d ago, {posts_14} posts in 14d"
    elif last_post_age <= 14:
        c3 = f"WARN - slowing, last post {last_post_age}d ago"
    else:
        c3 = f"FAIL - stopped posting ({last_post_age}d since last post)"

    out = path.with_name(path.stem + "_checked.csv")
    fields = [k for k in rows[0].keys() if not k.startswith("_")]
    for extra in ("post_date", "age_days", "outlier_score"):
        if extra not in fields:
            fields.append(extra)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(reels)

    def fmt(x):
        return f"{x:,.0f}" if isinstance(x, (int, float)) else "n/a"

    print(f"PAGE CHECK  ({path.name}, as of {now:%Y-%m-%d})")
    print(f"  reels read: {len(reels)} (pinned excluded from medians: {len(reels) - len(base)})")
    print(f"  page median views: {fmt(page_median)}")
    print(f"  median views, reels 3-10d old: {fmt(m_recent)} (n={len(recent)})")
    print(f"  median views, reels 11-45d old: {fmt(m_older)} (n={len(older)})")
    print(f"  CHECK 2 videos still viewed: {c2}")
    print(f"  CHECK 3 owner still posting: {c3}  | posts last 7d: {posts_7}")
    if too_new:
        print(f"  note: {len(too_new)} reel(s) under 3 days old left out of momentum (still growing)")
    if recent_outliers:
        print("  recent outliers (<=14d, 3x+ median):")
        for r in sorted(recent_outliers, key=lambda r: -r["outlier_score"])[:5]:
            print(f"    {r['reel_url']}  {fmt(r['_views'])} views  {r['outlier_score']}x  posted {r['post_date']}")
    print(f"  written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
