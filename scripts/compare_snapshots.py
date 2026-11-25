#!/usr/bin/env python3
"""
Compare two page snapshots side by side (markdown table).

Two uses:
  Me vs rival (same day):   python scripts/compare_snapshots.py data/snapshots/snowbarkie/2026-11-15.json data/snapshots/<rival>/2026-11-15.json --labels Me Rival
  Me now vs me last time:   python scripts/compare_snapshots.py --progress snowbarkie
  Instagram vs Facebook:    python scripts/compare_snapshots.py --latest snowbarkie snowbarkie_fb --labels Instagram Facebook
      (picks the two newest snapshots of that account automatically)

Prints a markdown table: metric | A | B | difference | which is better.
Standard library only.
"""
import json
import sys
from pathlib import Path

METRICS = [
    # key, label, higher_is_better, kind
    ("followers", "Followers", True, "n"),
    ("median_views_all", "Median views (all reels)", True, "n"),
    ("median_views_recent_2_14d", "Median views (reels 2-14 days old)", True, "n"),
    ("views_per_follower", "Views per follower", True, "x"),
    ("best_reel_views", "Best reel views", True, "n"),
    ("outliers_last_14d", "Outlier reels in last 14 days (3x+ median)", True, "n"),
    ("momentum", "Momentum (new vs older reels)", True, "x"),
    ("posts_last_7d", "Posts in last 7 days", True, "n"),
    ("posts_last_14d", "Posts in last 14 days", True, "n"),
    ("days_since_last_post", "Days since last post", False, "x"),
    ("like_rate", "Like rate (likes / views)", True, "%"),
    ("comment_rate", "Comment rate (comments / views)", True, "%"),
    ("forward_rate", "Forward rate ((sends+shares) / likes)", True, "x"),
    ("median_reach", "Median reach per reel", True, "n"),
    ("median_avg_watch_sec", "Median average watch time (sec)", True, "x"),
    ("link_clicks_last_14d", "Link clicks, last 14 days", True, "n"),
    ("follows_last_14d", "Follows from reels, last 14 days", True, "n"),
]


def fmt(v, kind):
    if v is None:
        return "n/a"
    if kind == "%":
        return f"{v*100:.2f}%"
    if kind == "x":
        return f"{v:.2f}"
    return f"{v:,.0f}"


def compare(a, b, la, lb, progress=False):
    head_b = f"{lb} ({b['date']})" if progress else f"{lb} @{b['account']}"
    head_a = f"{la} ({a['date']})" if progress else f"{la} @{a['account']}"
    print(f"| Metric | {head_a} | {head_b} | Change | Better |")
    print("|---|---|---|---|---|")
    wins_a = wins_b = 0
    for key, label, hib, kind in METRICS:
        va, vb = a.get(key), b.get(key)
        if va is None or vb is None:
            ch, better = "n/a", "-"
        else:
            d = va - vb
            pct = f" ({d / vb * 100:+.0f}%)" if vb else ""
            ch = (f"{d*100:+.2f} pts" if kind == "%" else f"{d:+.2f}" if kind == "x" else f"{d:+,.0f}") + pct
            if va == vb:
                better = "same"
            elif (va > vb) == hib:
                better, wins_a = la, wins_a + 1
            else:
                better, wins_b = lb, wins_b + 1
        print(f"| {label} | {fmt(va, kind)} | {fmt(vb, kind)} | {ch} | {better} |")
    print()
    print(f"Score: {la} better on {wins_a}, {lb} better on {wins_b} (of metrics measured on both).")
    ba, bb = a.get("best_reel_url"), b.get("best_reel_url")
    if ba or bb:
        print(f"Best reel {la}: {ba or 'n/a'}")
        print(f"Best reel {lb}: {bb or 'n/a'}")


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "--progress":
        acc = argv[1].lstrip("@")
        snaps = sorted((Path("data/snapshots") / acc).glob("*.json"))
        if len(snaps) < 2:
            print(f"Only {len(snaps)} snapshot(s) for @{acc}. This run is the baseline; progress compare starts next time.")
            return 0
        new, old = json.loads(snaps[-1].read_text(encoding="utf-8")), json.loads(snaps[-2].read_text(encoding="utf-8"))
        print(f"PROGRESS @{acc}: {old['date']} -> {new['date']}\n")
        compare(new, old, "Now", "Last time", progress=True)
        old_urls = {r["url"] for r in old.get("reels", [])}
        fresh = [r for r in new.get("reels", []) if r["url"] not in old_urls and r.get("views")]
        if fresh:
            print("\nNew reels since last snapshot (by views):")
            for r in sorted(fresh, key=lambda r: -r["views"])[:10]:
                r["date"] = r.get("date") or "no date"
                hook = f"  hook: {r['hook']}" if r.get("hook") else ""
                print(f"  {r['date']}  {r['views']:,.0f} views  {r['url']}{hook}")
        return 0
    if argv[0] == "--latest":
        def newest(acc):
            snaps = sorted((Path("data/snapshots") / acc.lstrip("@")).glob("*.json"))
            if not snaps:
                raise SystemExit(f"No snapshots for @{acc} yet. Run page_snapshot.py first.")
            return json.loads(snaps[-1].read_text(encoding="utf-8"))
        a, b = newest(argv[1]), newest(argv[2])
        la, lb = "A", "B"
        if "--labels" in argv:
            i = argv.index("--labels")
            la, lb = argv[i + 1], argv[i + 2]
        print(f"COMPARE @{a['account']} ({a['date']}) vs @{b['account']} ({b['date']})\n")
        compare(a, b, la, lb)
        return 0
    a = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    b = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    la, lb = "A", "B"
    if "--labels" in argv:
        i = argv.index("--labels")
        la, lb = argv[i + 1], argv[i + 2]
    print(f"COMPARE @{a['account']} vs @{b['account']} ({a['date']} / {b['date']})\n")
    compare(a, b, la, lb)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
