"""Command line for the skills (/hunt, /check-product, /track-pages).

Hunt:
  python scripts/dbcli.py hunt-start --source feed [--query "x"] [--agent hunt]
      take lease, create hunt row, cache seen codes+handles and product names
      in data/.hunt_state.json. Exit 2 = lease held by someone else: STOP.
  python scripts/dbcli.py seen <code> <handle>
      instant local lookup: prints new | repeat | handle_changed.
      repeat -> counted, reel marked verified (written at next save).
  python scripts/dbcli.py hunt-save <batch.json>
      batch = list of reels (save every 10): {code, handle, product, category,
      status, skip_reason, hook_text, first_frame, clip_type, cta, post_date,
      views, likes, comments, sends, shares, confidence, sponsored,
      shop: {store_url, price_raw, bought_month, notes}}
  python scripts/dbcli.py hunt-end [--notes "..."] [--error "..."]
      flush repeats, write hunt summary, release lease. Always run it (also on errors).

Products / pages:
  python scripts/dbcli.py product <name or @handle>      stored product(s), sellers, shop/ad checks
  python scripts/dbcli.py page <handle>                  stored reels with latest views -> CSV on stdout
  python scripts/dbcli.py save-page <handle> <reels.csv> [--product "name"]
  python scripts/dbcli.py set-product "<name>" key=value ...   (status, score, recheck_on, notes, ip_flag, ...)
  python scripts/dbcli.py shop "<name>" key=value ...    (store_url, price_raw, bought_month, rating, reviews, notes)
  python scripts/dbcli.py ad "<name>" key=value ...      (ad_count, advertisers, oldest_ad_date, notes)
  python scripts/dbcli.py seller "<name>" <handle> [store_url]
  python scripts/dbcli.py account <handle> key=value ... (role, followers, store_url, notes, last_checked_at=now)
  python scripts/dbcli.py snapshot <handle> <snapshot.json>
  python scripts/dbcli.py shop-due "<name>"           CHECK/SKIP for a Shop check (7-day rule)
  python scripts/dbcli.py watched                        pages to track + products due for recheck
  python scripts/dbcli.py lease acquire|release [holder]
"""
import csv
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

STATE = os.path.join(db.ROOT, "data", ".hunt_state.json")
METRIC_KEYS = ("views", "likes", "comments", "sends", "shares")
REEL_KEYS = ("hook_text", "first_frame", "clip_type", "cta", "post_date", "notes")


def now():
    return datetime.now(timezone.utc).isoformat()


def load_state():
    if not os.path.exists(STATE):
        sys.exit("No hunt running (run hunt-start first).")
    return json.load(open(STATE, encoding="utf-8"))


def save_state(s):
    json.dump(s, open(STATE, "w", encoding="utf-8"))


def kv(args):
    out = {}
    for a in args:
        k, _, v = a.partition("=")
        v = v.strip()
        if v.lower() in ("true", "false"):
            v = v.lower() == "true"
        elif v.lower() in ("", "n/a", "null", "none"):
            v = None
        elif k in ("score", "ad_count", "advertisers", "reviews", "followers") and v.isdigit():
            v = int(v)
        elif k in ("price_usd", "rating", "fx_rate"):
            v = float(v)
        elif v == "now":
            v = now()
        out[k] = v
    return out


def num(v):
    if v in (None, "", "n/a"):
        return None
    s = str(v).replace(",", "").strip().upper()
    mult = 1
    if s.endswith("K"):
        mult, s = 1000, s[:-1]
    elif s.endswith("M"):
        mult, s = 1000000, s[:-1]
    try:
        return int(round(float(s) * mult))
    except ValueError:
        return None


def product_id(name, create=True, **f):
    key = db.name_key(name)
    rows = db.select("products", {"select": "id", "name_key": f"eq.{key}"})
    if rows and not f:
        return rows[0]["id"]
    if not rows and not create:
        return None
    return db.upsert_product(name, **f)["id"]


# ---------------- hunt ----------------
def hunt_start(a):
    o = kv(x.lstrip("-") for x in pair(a))
    agent = o.get("agent", "hunt")
    try:
        db.acquire_lease(agent)
    except db.LeaseHeld as e:
        print("STOP:", e)
        sys.exit(2)
    try:
        h = db.start_hunt(agent, source=o.get("source", "feed"), query=o.get("query"))
        seen = db.load_seen()
        names = {k: v["name"] for k, v in db.load_product_keys().items()}
    except Exception:
        db.release_lease(agent)
        raise
    save_state({"hunt_id": h["id"], "agent": agent, "seen": seen, "names": names,
                "repeats": [], "changed": {}, "viewed": 0, "new_reels": 0, "new_products": 0})
    print(f"hunt {h['id']} started | {len(seen)} known reels | {len(names)} known products")


def pair(a):
    out, i = [], 0
    while i < len(a):
        if a[i].startswith("--") and i + 1 < len(a) and not a[i + 1].startswith("--"):
            out.append(f"{a[i]}={a[i + 1]}")
            i += 2
        else:
            out.append(a[i] + "=true" if a[i].startswith("--") else a[i])
            i += 1
    return out


def seen_cmd(a):
    s = load_state()
    code, handle = db.reel_code(a[0]), db.handle_key(a[1] if len(a) > 1 else "")
    s["viewed"] += 1
    kind = db.classify_reel(code, handle, s["seen"])
    if kind == "repeat":
        s["repeats"].append(code)
    elif kind == "handle_changed":
        s["changed"][code] = s["seen"][code]
    save_state(s)
    print(kind)


def hunt_save(a):
    s = load_state()
    batch = json.load(open(a[0], encoding="utf-8"))
    hid = s["hunt_id"]
    for r in batch:
        code, handle = db.reel_code(r["code"]), db.handle_key(r.get("handle"))
        pid = None
        if r.get("product"):
            key = db.name_key(r["product"])
            if key not in s["names"]:
                s["new_products"] += 1
            f = {k: r[k] for k in ("category", "status", "skip_reason", "ip_flag", "seasonal",
                                   "recheck_on") if r.get(k) is not None}
            pid = db.upsert_product(r["product"], **f)["id"]
            s["names"][key] = r["product"]
            if handle:
                db.add_seller(pid, handle, (r.get("shop") or {}).get("store_url"))
        fields = {k: r[k] for k in REEL_KEYS if r.get(k)}
        if code in s["changed"]:
            old = s["changed"].pop(code)
            fields["notes"] = ((fields.get("notes") or "") +
                               f" | handle changed: was @{old}, now @{handle}").strip(" |")
            db.upsert_reel(code, handle=handle, product_id=pid, code_verified=False,
                           source=r.get("source", "feed"), hunt_id=hid, **fields)
        else:
            if code not in s["seen"]:
                s["new_reels"] += 1
            db.upsert_reel(code, handle=handle, product_id=pid, code_verified=True,
                           source=r.get("source", "feed"), hunt_id=hid, times_seen=1, **fields)
        s["seen"][code] = handle
        m = {k: num(r.get(k)) for k in METRIC_KEYS}
        conf = r.get("confidence") or ("measured" if any(v is not None for v in m.values())
                                       else "unverified")
        db.add_metrics(code, confidence=conf, **(m if conf != "unverified" else {}))
        if pid and r.get("shop"):
            sh = dict(r["shop"])
            if sh.get("price_raw") and "price_usd" not in sh:
                sh["price_usd"] = usd(sh["price_raw"])
            db.add_shop_check(pid, **sh)
    save_state(s)
    print(f"saved {len(batch)} reels | hunt totals: viewed {s['viewed']}, new {s['new_reels']}, "
          f"repeats {len(s['repeats'])}, new products {s['new_products']}")


def usd(raw):
    import re
    m = re.search(r"\$\s*(\d+(?:\.\d+)?)", raw or "")
    return float(m.group(1)) if m and not re.search(r"€|EUR|₩|KRW|£|₼|AZN", raw) else None


def flush_repeats(s):
    for code in set(s["repeats"]):
        db.touch_repeat(code)
        db._req("PATCH", "reels", {"code_verified": True},
                params={"reel_code": f"eq.{code}"})


def hunt_end(a):
    o = kv(x.lstrip("-") for x in pair(a))
    s = load_state()
    err = None
    try:
        flush_repeats(s)
        notes = o.get("notes") or ""
        if o.get("error"):
            notes = (notes + " | ERROR: " + str(o["error"])).strip(" |")
        db.finish_hunt(s["hunt_id"], reels_viewed=s["viewed"], new_reels=s["new_reels"],
                       repeats_skipped=len(set(s["repeats"])), new_products=s["new_products"],
                       notes=notes or None)
    except Exception as e:  # still release the lease
        err = e
    finally:
        db.release_lease(s["agent"])
        os.replace(STATE, STATE + ".last")
    print(f"hunt ended, lease released | viewed {s['viewed']}, new {s['new_reels']}, "
          f"repeats {len(set(s['repeats']))}, new products {s['new_products']}")
    if err:
        raise err


# ---------------- products / pages ----------------
def product_cmd(a):
    q = a[0]
    if q.startswith("@"):
        ids = [r["product_id"] for r in db.select("product_sellers",
                                                  {"handle": f"eq.{db.handle_key(q)}"})]
        rows = db.select("products", {"id": f"in.({','.join(ids)})"}) if ids else []
    else:
        rows = db.select("products", {"name_key": f"eq.{db.name_key(q)}"}) or \
            db.select("products", {"name": f"ilike.*{q}*"})
    for p in rows:
        pid = p["id"]
        p["sellers"] = [r["handle"] for r in db.select("product_sellers", {"product_id": f"eq.{pid}"})]
        p["shop_checks"] = db.select("shop_checks", {"product_id": f"eq.{pid}", "order": "captured_at"})
        p["ad_checks"] = db.select("ad_checks", {"product_id": f"eq.{pid}", "order": "captured_at"})
    print(json.dumps(rows, indent=1, default=str) if rows else "not in database")


def page_cmd(a):
    h = db.handle_key(a[0])
    rows = db.select("reel_latest", {"handle": f"eq.{h}"})
    w = csv.writer(sys.stdout)
    w.writerow(["reel_url", "views", "likes", "comments", "shares", "sends", "post_date",
                "captured_at", "hook"])
    for r in rows:
        w.writerow([f"https://www.instagram.com/reel/{r['reel_code']}/", r["views"], r["likes"],
                    r["comments"], r["shares"], r["sends"], r["post_date"], r["captured_at"],
                    r["hook_text"]])


def save_page(a):
    h, path = db.handle_key(a[0]), a[1]
    o = kv(x.lstrip("-") for x in pair(a[2:]))
    pid = product_id(o["product"]) if o.get("product") else None
    if pid:
        db.add_seller(pid, h)
    seen = db.load_seen()
    n = new = changed = 0
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        code = db.reel_code(r.get("reel_url"))
        if not code:
            continue
        kind = db.classify_reel(code, h, seen)
        f = {"hook_text": r.get("hook") or None, "post_date": r.get("post_date") or None}
        if kind == "handle_changed":
            changed += 1
            f["notes"] = f"handle changed: was @{seen[code]}, now @{h}"
            f["code_verified"] = False
        else:
            f["code_verified"] = True
            new += kind == "new"
        db.upsert_reel(code, handle=h, product_id=pid, source="page", **f)
        m = {k: num(r.get(k)) for k in METRIC_KEYS}
        if any(v is not None for v in m.values()):
            db.add_metrics(code, **m)
        n += 1
    db.upsert_account(h, last_checked_at=now())
    print(f"@{h}: {n} reels saved ({new} new, {changed} handle changed)")


def set_product(a):
    f = kv(a[1:])
    print(json.dumps(db.upsert_product(a[0], **f), default=str))


def shop_cmd(a):
    f = kv(a[1:])
    if f.get("price_raw") and "price_usd" not in f:
        f["price_usd"] = usd(f["price_raw"])
    print(json.dumps(db.add_shop_check(product_id(a[0]), **f), default=str))


def ad_cmd(a):
    print(json.dumps(db.add_ad_check(product_id(a[0]), **kv(a[1:])), default=str))


def seller_cmd(a):
    print(json.dumps(db.add_seller(product_id(a[0]), a[1], a[2] if len(a) > 2 else None)))


def account_cmd(a):
    print(json.dumps(db.upsert_account(a[0], **kv(a[1:])), default=str))


def snapshot_cmd(a):
    j = json.load(open(a[1], encoding="utf-8"))
    mp = {"followers": "followers", "median_views_all": "median_views",
          "median_views_recent_2_14d": "median_views_2_14d", "best_reel_views": "best_reel_views",
          "outliers_last_14d": "outliers_14d", "posts_last_7d": "posts_7d",
          "posts_last_14d": "posts_14d", "momentum": "momentum", "like_rate": "like_rate",
          "forward_rate": "forward_rate"}
    ints = {"followers", "median_views", "median_views_2_14d", "best_reel_views",
            "outliers_14d", "posts_7d", "posts_14d"}
    f = {dst: (int(round(j[src])) if dst in ints else j[src]) for src, dst in mp.items()
         if isinstance(j.get(src), (int, float))}
    print(json.dumps(db.add_snapshot(a[0], **f), default=str))


def shop_due(a):
    """Should /hunt Shop-check this product? Prints CHECK or SKIP + reason.
    SKIP when the latest shop_check is < 7 days old, unless it was 'blocked'."""
    from datetime import timedelta
    pid = product_id(a[0], create=False)
    if not pid:
        print("CHECK never-checked (new product)")
        return
    rows = db.select("shop_checks", {"product_id": f"eq.{pid}", "order": "captured_at.desc",
                                     "limit": 1})
    if not rows:
        print("CHECK never-checked")
        return
    r = rows[0]
    status = (r.get("shop_status") or "")
    blocked = status == "blocked" or "blocked" in (r.get("notes") or "").lower()
    when = datetime.fromisoformat(r["captured_at"].replace("Z", "+00:00"))
    age = datetime.now(timezone.utc) - when
    if blocked:
        print(f"CHECK last-was-blocked ({when.date()})")
    elif age < timedelta(days=7):
        print(f"SKIP checked {age.days}d ago ({when.date()}): badge {r.get('bought_month') or 'n/a'}, "
              f"price {r.get('price_raw') or 'n/a'}")
    else:
        print(f"CHECK stale ({age.days}d old)")


def watched(_a):
    acc = db.select("accounts", {"select": "handle,role,followers,last_checked_at,notes",
                                 "role": "in.(own,rival)", "order": "last_checked_at.nullsfirst"})
    st = {}
    for s in db.select("product_sellers", {"select": "handle,products(name,status)"}):
        if s.get("products"):
            st.setdefault(s["handle"], []).append(f"{s['products']['name'][:40]} [{s['products']['status']}]")
    print("PAGES (own + rival):")
    for r in acc:
        print(f"  @{r['handle']:22} {r['role']:6} checked {str(r['last_checked_at'])[:10]}  "
              f"{'; '.join(st.get(r['handle'], []))}")
    print("PRODUCTS DUE FOR RECHECK:")
    for r in db.due_rechecks():
        print(f"  {r['recheck_on']}  {r['status']:11} {r['name']}")


def lease_cmd(a):
    holder = a[1] if len(a) > 1 else "hunt"
    try:
        (db.acquire_lease if a[0] == "acquire" else db.release_lease)(holder)
        print(f"lease {a[0]}d")
    except db.LeaseHeld as e:
        print("STOP:", e)
        sys.exit(2)


CMDS = {"hunt-start": hunt_start, "seen": seen_cmd, "hunt-save": hunt_save, "hunt-end": hunt_end,
        "product": product_cmd, "page": page_cmd, "save-page": save_page,
        "set-product": set_product, "shop": shop_cmd, "ad": ad_cmd, "seller": seller_cmd,
        "account": account_cmd, "shop-due": shop_due, "snapshot": snapshot_cmd, "watched": watched, "lease": lease_cmd}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        sys.exit(1)
    try:
        CMDS[sys.argv[1]](sys.argv[2:])
    except db.DBError as e:
        print("DB error:", e)
        sys.exit(1)
