#!/usr/bin/env python3
"""
Save a dated snapshot of one Instagram page's numbers, so pages can be compared
with each other (me vs rival) and with themselves over time (me now vs last time).

Input: the page's reels CSV (data/pages/<account>_reels.csv) with at least
  reel_url, views
Optional columns: pinned, likes, comments, shares, sends, hook,
  post_date (YYYY-MM-DD; needed for Facebook, whose links don't carry a date),
  reach, avg_watch_sec, link_clicks, follows (from Meta Business Suite insights)

Usage:
  python scripts/page_snapshot.py data/pages/snowbarkie_reels.csv --account snowbarkie --followers 48 [--posts 12] [--store yes|no] [--now 2026-11-15]
  python scripts/page_snapshot.py data/pages/snowbarkie_fb_reels.csv --account snowbarkie_fb --followers 120 --platform fb

Writes data/snapshots/<account>/<YYYY-MM-DD>.json (overwrites the same day) and prints a summary.
Standard library only.
"""
import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reel_date import code_from_url, post_datetime  # noqa: E402


def num(x):
    s = str(x or "").strip().replace(",", "").upper()
    if not s or s in ("N/A", "NA", "-"):
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
    return round(statistics.median(xs), 4) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--account", required=True)
    ap.add_argument("--followers", type=float)
    ap.add_argument("--posts", type=float)
    ap.add_argument("--store", choices=["yes", "no"])
    ap.add_argument("--now")
    ap.add_argument("--platform", choices=["ig", "fb"], default="ig")
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    if a.now:
        now = datetime.strptime(a.now, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    with open(a.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    reels = []
    for r in rows:
        url = (r.get("reel_url") or "").strip()
        if not url:
            continue
        code = code_from_url(url)
        dt = None
        if code:
            try:
                dt = post_datetime(code)
            except ValueError:
                dt = None
        if dt is None and (r.get("post_date") or "").strip():
            raw = r["post_date"].strip()[:16]
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    pass
        if dt is not None and dt > now:  # posted after the snapshot date (only happens with --now in the past)
            continue
        pinned = str(r.get("pinned", "") or r.get("note", "")).lower().startswith(("yes", "pinned"))
        v, lk, cm = num(r.get("views")), num(r.get("likes")), num(r.get("comments"))
        sh, sd = num(r.get("shares")), num(r.get("sends"))
        reels.append({
            "url": url, "date": dt.strftime("%Y-%m-%d") if dt else None,
            "age": round((now - dt).total_seconds() / 86400, 1) if dt else None, "pinned": pinned,
            "views": v, "likes": lk, "comments": cm, "shares": sh, "sends": sd,
            "reach": num(r.get("reach")), "avg_watch_sec": num(r.get("avg_watch_sec")),
            "link_clicks": num(r.get("link_clicks")), "follows": num(r.get("follows")),
            "hook": (r.get("hook") or "").strip(),
        })
    if not reels:
        print("No reel URLs found in", a.csv)
        return 1

    base = [r for r in reels if not r["pinned"]]
    m_all = med(r["views"] for r in base)
    dated = [r for r in base if r["age"] is not None]
    recent = [r for r in dated if 2 <= r["age"] <= 14]
    m_recent = med(r["views"] for r in recent)
    win_new = [r for r in dated if 3 <= r["age"] <= 10]
    win_old = [r for r in dated if 10 < r["age"] <= 45]
    m_new, m_old = med(r["views"] for r in win_new), med(r["views"] for r in win_old)
    momentum = round(m_new / m_old, 2) if (m_new and m_old) else None
    by_age = sorted(dated, key=lambda r: r["age"])
    best = max((r for r in base if r["views"]), key=lambda r: r["views"], default=None)
    outl = [r for r in dated if r["age"] <= 14 and r["views"] and m_all and r["views"] >= 3 * m_all]

    like_rates = [r["likes"] / r["views"] for r in base if r["likes"] and r["views"]]
    comment_rates = [r["comments"] / r["views"] for r in base if r["comments"] is not None and r["views"]]
    fwd = [((r["sends"] or 0) + (r["shares"] or 0)) / r["likes"] for r in base
           if r["likes"] and (r["sends"] is not None or r["shares"] is not None)]

    last14 = [r for r in dated if r["age"] <= 14]

    def total(key):
        vals = [r[key] for r in last14 if r[key] is not None]
        return sum(vals) if vals else None

    snap = {
        "account": a.account, "platform": a.platform, "date": now.strftime("%Y-%m-%d"),
        "followers": a.followers, "posts_total": a.posts, "store_link": a.store,
        "reels_read": len(reels),
        "median_views_all": m_all,
        "median_views_recent_2_14d": m_recent,
        "views_per_follower": round(m_all / a.followers, 2) if (m_all and a.followers) else None,
        "best_reel_views": best["views"] if best else None,
        "best_reel_url": best["url"] if best else None,
        "outliers_last_14d": len(outl),
        "momentum": momentum,
        "days_since_last_post": by_age[0]["age"] if by_age else None,
        "posts_last_7d": sum(1 for r in dated if r["age"] <= 7),
        "posts_last_14d": sum(1 for r in dated if r["age"] <= 14),
        "like_rate": med(like_rates),
        "comment_rate": med(comment_rates),
        "forward_rate": med(fwd),
        "median_reach": med(r["reach"] for r in base),
        "median_avg_watch_sec": med(r["avg_watch_sec"] for r in base),
        "link_clicks_last_14d": total("link_clicks"),
        "follows_last_14d": total("follows"),
        "undated_reels": sum(1 for r in base if r["age"] is None),
        "reels": reels,
    }

    out_dir = Path("data/snapshots") / a.account
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{snap['date']}.json"
    out.write_text(json.dumps(snap, indent=1), encoding="utf-8")

    def f(x, pct=False):
        if x is None:
            return "n/a"
        return f"{x*100:.2f}%" if pct else f"{x:,.0f}" if abs(x) >= 10 else f"{x:g}"

    print(f"SNAPSHOT @{a.account} {snap['date']}")
    print(f"  followers {f(a.followers)} | reels read {len(reels)} | store link {a.store or 'n/a'}")
    print(f"  median views: all {f(m_all)} | recent 2-14d {f(m_recent)} | best {f(snap['best_reel_views'])}")
    print(f"  momentum {f(momentum)} | outliers 14d {len(outl)} | last post {f(snap['days_since_last_post'])}d ago | posts 7d/14d {snap['posts_last_7d']}/{snap['posts_last_14d']}")
    print(f"  like rate {f(snap['like_rate'], True)} | comment rate {f(snap['comment_rate'], True)} | forward rate {f(snap['forward_rate'])}")
    extra = [("median reach", snap["median_reach"]), ("median watch sec", snap["median_avg_watch_sec"]),
             ("link clicks 14d", snap["link_clicks_last_14d"]), ("follows 14d", snap["follows_last_14d"])]
    if any(v is not None for _, v in extra):
        print("  " + " | ".join(f"{k} {f(v)}" for k, v in extra))
    if snap["undated_reels"]:
        print(f"  note: {snap['undated_reels']} reel(s) had no date (add post_date) and were left out of age-based numbers")
    print(f"  saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
