"""Nightly backup: dump every Supabase table to data/export/<table>.csv.

  python scripts/export_csv.py
Original data/*.csv files are never touched.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

TABLES = ["accounts", "products", "reels", "reel_metrics", "product_sellers", "shop_checks",
          "ad_checks", "own_snapshots", "hunts", "results_log", "lessons"]

out = os.path.join(db.ROOT, "data", "export")
os.makedirs(out, exist_ok=True)
for t in TABLES:
    rows = db.select(t)
    cols = sorted({k for r in rows for k in r}) or ["(empty)"]
    with open(os.path.join(out, f"{t}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"{t:16} {len(rows)}")
