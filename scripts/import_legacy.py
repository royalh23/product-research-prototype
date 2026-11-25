"""One-time import of all CSV + report history into Supabase.

  python scripts/import_legacy.py            # dry run: parse everything, print summary
  python scripts/import_legacy.py --apply    # write (idempotent: every write is an upsert)

Rules: imported reels get code_verified=false, source='import'. No codes or
numbers are invented: anything unverified / hidden is stored with
confidence 'unverified' and empty numbers.
"""
import csv
import glob
import json
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

ROOT = db.ROOT
D = lambda *p: os.path.join(ROOT, *p)  # noqa: E731
OWN = "snowbarkie"
STATUSES = {"new", "noise", "candidate", "watch", "winner", "niche-only", "skip",
            "skip-seasonal", "testing", "unverified"}
PRIO = {s: i for i, s in enumerate(["noise", "new", "unverified", "skip", "skip-seasonal",
                                    "watch", "candidate", "niche-only", "winner", "testing"])}
NS = uuid.UUID("6f1c2a4e-9b7d-4c3e-8a11-0d5e7f9a2b10")

products, reels, accounts = {}, {}, {}
metrics, shops, ads, snaps, hunts = {}, {}, {}, {}, []
sellers = set()
skipped = Counter()
skip_examples = defaultdict(list)
notes_log = []


def skip(reason, example=""):
    skipped[reason] += 1
    if example and len(skip_examples[reason]) < 3:
        skip_examples[reason].append(example[:70])


# ---------- parsing helpers ----------
def num(s):
    """'1.5M' -> 1500000, '42,800' -> 42800, 'n/a'/'' -> None. Never guesses."""
    s = (s or "").strip().replace(",", "").replace("*", "").lstrip("~")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KkMm]?)\+?", s)
    if not m:
        return None
    v = float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()]
    return int(round(v))


def fnum(s):
    try:
        return float(str(s).strip().rstrip("x").replace(",", ""))
    except (ValueError, AttributeError):
        return None


def usd(raw):
    """Only a plain $ price becomes price_usd; anything else stays raw only."""
    m = re.search(r"\$\s*(\d+(?:\.\d+)?)", raw or "")
    if m and not re.search(r"€|EUR|₩|KRW|£|AZN|₼", raw):
        return float(m.group(1))
    return None


def badge(s):
    m = re.search(r"(\d[\d,]*\+?)\s*(?:bought|\b)", (s or "").replace("*", ""))
    if m and re.search(r"\d+\+", m.group(1)):
        return m.group(1)
    m = re.fullmatch(r"\**\s*(\d+\+)\s*\**", (s or "").strip())
    return m.group(1) if m else None


def ts(day, hhmm=None):
    t = f"{hhmm[:2]}:{hhmm[2:]}" if hhmm else "00:00"
    return f"{day}T{t}:00+00:00"


def date_part(s):
    m = re.search(r"\d{4}-\d{2}-\d{2}", s or "")
    return m.group(0) if m else None


def ip_text(t):
    return bool(re.search(r"\bIP\b|trademark|licen[cs]|disney|nintendo|marvel|look-alike|"
                          r"celebrity|minion|grinch|call of duty|mario|mickey|olaf|bmw",
                          t or "", re.I))


def recheck_date(t, base=None):
    d = re.search(r"recheck\D{0,12}(\d{4}-\d{2}-\d{2})", t or "", re.I)
    if d:
        return d.group(1)
    m = re.search(r"recheck in (\d+) days?", t or "", re.I)
    if m and base:
        return (date.fromisoformat(base) + timedelta(days=int(m.group(1)))).isoformat()
    return None


# ---------- model updates ----------
def product(name, day, status=None, **f):
    key = db.name_key(name)
    if not key:
        return None
    p = products.setdefault(key, {"name": name.strip(), "first_seen_at": ts(day),
                                  "_sday": "0000", "notes": []})
    if ts(day) < p["first_seen_at"]:
        p["first_seen_at"] = ts(day)
    p["last_seen_at"] = max(p.get("last_seen_at", ""), ts(day))
    if status in STATUSES:
        newer = day > p["_sday"] or (day == p["_sday"] and
                                     PRIO[status] > PRIO.get(p.get("status"), -1))
        if newer:
            p["status"], p["_sday"] = status, day
            if status in ("skip", "skip-seasonal", "noise") and f.get("skip_reason"):
                p["skip_reason"] = f["skip_reason"]
    for k in ("category", "score", "recheck_on", "window_closes"):
        if f.get(k) is not None:
            p[k] = f[k]
    if f.get("ip_flag"):
        p["ip_flag"] = True
    if f.get("seasonal"):
        p["seasonal"] = True
    if f.get("note") and f["note"] not in p["notes"]:
        p["notes"].append(f["note"])
    return key


def account(h, **f):
    h = db.handle_key(h)
    if not h or not re.fullmatch(r"[a-z0-9._]{2,30}", h):
        return None
    a = accounts.setdefault(h, {"handle": h})
    a.update({k: v for k, v in f.items() if v not in (None, "")})
    return h


def reel(code, day, **f):
    r = reels.setdefault(code, {"reel_code": code, "code_verified": False,
                                "source": "import", "first_seen_at": ts(day),
                                "last_seen_at": ts(day), "times_seen": 0})
    r["times_seen"] = max(r["times_seen"], 0)
    if f.pop("_sighting", False):
        r["times_seen"] += 1
    r["first_seen_at"] = min(r["first_seen_at"], ts(day))
    r["last_seen_at"] = max(r["last_seen_at"], ts(day))
    for k, v in f.items():
        if v not in (None, "") and not r.get(k):
            r[k] = v
    return r


def metric(code, at, confidence="measured", **m):
    if confidence == "unverified":
        m = {}
    vals = {k: m.get(k) for k in ("views", "likes", "comments", "sends", "shares")}
    if confidence == "measured" and all(v is None for v in vals.values()):
        return
    metrics[(code, at)] = {"reel_code": code, "captured_at": at,
                           "confidence": confidence, **vals}


def shop(pkey, at, **f):
    f = {k: v for k, v in f.items() if v not in (None, "")}
    if not any(k in f for k in ("price_raw", "bought_month", "store_url")):
        return
    cur = shops.setdefault((pkey, at), {"_p": pkey, "captured_at": at})
    for k, v in f.items():
        cur.setdefault(k, v)


def split_hook(h):
    """'"hook" | first frame | CTA comment dog | no price' -> parts."""
    parts = [x.strip() for x in (h or "").split(" | ")]
    out = {"hook_text": parts[0].strip('"') if parts and parts[0] else None}
    rest = parts[1:]
    cta = [x for x in rest if re.match(r"CTA\b", x, re.I)]
    out["cta"] = re.sub(r"^CTA:?\s*", "", cta[0], flags=re.I) if cta else None
    other = [x for x in rest if x not in cta and not re.match(r"(no )?price", x, re.I)]
    out["first_frame"] = other[0] if other else None
    return out


# ---------- 1. data/products.csv ----------
def import_products_csv():
    for r in csv.DictReader(open(D("data", "products.csv"), encoding="utf-8-sig")):
        day = r["found_date"] or "2026-11-14"
        code = db.reel_code(r["reel_url"])
        status = (r["status"] or "").strip()
        text = " ".join([r.get("verdict_reason", ""), r.get("notes", "")])
        h = account(r["account"])
        pkey = None
        if h == OWN:
            skip("own-page @snowbarkie row: reel kept, not scored as a product", r["product"])
        elif (r["product"] or "").strip():
            pkey = product(
                r["product"], day, status, category=r["category"] or None,
                score=num(r["score"]), skip_reason=r["verdict_reason"] or None,
                ip_flag=status == "niche-only" or ip_text(text),
                seasonal=status == "skip-seasonal" or "seasonal" in text.lower(),
                recheck_on=recheck_date(text, day))
            if h and pkey and status not in ("noise",):
                sellers.add((pkey, h))
        else:
            skip("products.csv row with no product name (reel kept)", r["reel_url"])
        if not code:
            skip("products.csv row with no reel code", r["product"])
            continue
        unver = status == "unverified" or "unverified" in text.lower()
        reel(code, day, platform="facebook" if "facebook.com" in r["reel_url"] else "instagram",
             handle=h, _pkey=pkey, post_date=date_part(r["post_date"]), cta=r["cta"] or None,
             _sighting=True, _source_csv=r["source"], notes=r["notes"] or None)
        metric(code, ts(day), "unverified" if unver else "measured",
               views=num(r["views"]), likes=num(r["likes"]), comments=num(r["comments"]),
               sends=num(r["sends"]), shares=num(r["shares"]))
        if pkey:
            shop(pkey, ts(day), store_url=r["store_url"] or r["product_url"] or None,
                 price_raw=r["price"] or None, price_usd=usd(r["price"]),
                 bought_month=badge(r["shop_bought_month"]) or r["shop_bought_month"] or None,
                 notes=r["shop_status"] or None)


# ---------- 2. data/pages.csv + data/pages/* ----------
page_product = {}


def import_pages():
    for r in csv.DictReader(open(D("data", "pages.csv"), encoding="utf-8-sig")):
        h = account(r["account"], role="own" if r["status"] == "own" else "rival",
                    followers=num(r["followers"]), store_url=r["store_url"],
                    notes=r["notes"], last_checked_at=ts(r["last_checked"]) if r["last_checked"] else None)
        day = r["last_checked"] or r["first_seen"]
        if h == OWN or r["status"] == "own":
            continue  # own page is never a product
        if r["product"]:
            st = r["status"] if r["status"] in STATUSES else None
            pk = product(r["product"], day, st, ip_flag=ip_text(r["product"] + r["notes"]),
                         recheck_on=recheck_date(r["notes"], day))
            page_product[h] = pk
            sellers.add((pk, h))
            m = re.search(r"(\d+)\+?\s*(?:active\s+|FB\s+|facebook\s+)?ads", r["notes"], re.I)
            if m:
                ads[(pk, ts(day))] = {"_p": pk, "captured_at": ts(day), "ad_count": int(m.group(1)),
                                      "notes": "pages.csv: " + r["notes"][:200]}

    for f in sorted(glob.glob(D("data", "pages", "*.csv"))):
        base = os.path.basename(f)
        if base.startswith("_"):
            continue
        h_raw = re.sub(r"_(reels|reels_checked|outliers)\.csv$", "", base)
        platform = "instagram"
        if h_raw.endswith("_fb"):
            h_raw, platform = h_raw[:-3], "facebook"
        h = account(h_raw)
        day = datetime.fromtimestamp(os.path.getmtime(f)).date().isoformat()
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            code = db.reel_code(r.get("reel_url"))
            if not code:
                skip("page csv row with no reel code", f"{base}")
                continue
            if base.endswith("_outliers.csv"):
                hk = r.get("hook", "")
                ff = re.search(r"0-3s:\s*(.+)", hk)
                hook = {"hook_text": re.sub(r"\s*0-3s:.*", "", hk).strip() or None,
                        "first_frame": ff.group(1).strip() if ff else None,
                        "cta": r.get("cta") or None, "clip_type": r.get("video_style") or None}
            else:
                hook = split_hook(r.get("hook"))
            reel(code, day, platform=platform, handle=h, _pkey=page_product.get(h),
                 post_date=date_part(r.get("post_date")), **hook)
            metric(code, ts(day), views=num(r.get("views")), likes=num(r.get("likes")),
                   comments=num(r.get("comments")), sends=num(r.get("sends")),
                   shares=num(r.get("shares")))


# ---------- 3. snapshots ----------
SNAP_MAP = {"followers": "followers", "median_views_all": "median_views",
            "median_views_recent_2_14d": "median_views_2_14d", "best_reel_views": "best_reel_views",
            "outliers_last_14d": "outliers_14d", "posts_last_7d": "posts_7d",
            "posts_last_14d": "posts_14d", "momentum": "momentum", "like_rate": "like_rate",
            "forward_rate": "forward_rate"}
INTS = {"followers", "median_views", "median_views_2_14d", "best_reel_views", "outliers_14d",
        "posts_7d", "posts_14d"}


def put_snap(handle, at, vals, src):
    row = snaps.setdefault((handle, at), {"handle": handle, "captured_at": at, "_src": src})
    for k, v in vals.items():
        if v is not None and row.get(k) is None:
            row[k] = int(round(v)) if k in INTS else v


def import_snapshots():
    for f in sorted(glob.glob(D("data", "snapshots", "*", "*.json"))):
        j = json.load(open(f, encoding="utf-8"))
        handle = os.path.basename(os.path.dirname(f))
        at = ts(j.get("date") or os.path.basename(f)[:10])
        put_snap(handle, at, {dst: (j.get(src) if isinstance(j.get(src), (int, float)) else None)
                              for src, dst in SNAP_MAP.items()}, "json")


ROW_MAP = [(r"^Followers$", "followers"), (r"^Median views \(all", "median_views"),
           (r"^Median views \(reels 2", "median_views_2_14d"), (r"^Best reel views", "best_reel_views"),
           (r"^Outlier reels", "outliers_14d"), (r"^Momentum", "momentum"),
           (r"^Posts in last 7", "posts_7d"), (r"^Posts in last 14", "posts_14d"),
           (r"^Like rate", "like_rate"), (r"^Forward rate", "forward_rate")]


def table_rows(lines):
    """Yield (header_cells, row_cells) for markdown tables."""
    head = None
    for ln in lines:
        if not ln.startswith("|"):
            head = None
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if head is None:
            head = cells
        elif set("".join(cells)) <= set("-: "):
            continue
        else:
            yield head, cells


def import_progress_reports():
    files = sorted(glob.glob(D("reports", "progress", "progress_*.md")))
    for f in files:
        m = re.search(r"progress_(\d{4}-\d{2}-\d{2})(?:_(\d{4}))?_(\w+?)\.md", os.path.basename(f))
        day, hhmm, handle = m.groups()
        vals = {}
        for head, cells in table_rows(open(f, encoding="utf-8").read().splitlines()):
            if head[0] != "Metric" or len(cells) < 2:
                continue
            for pat, key in ROW_MAP:
                if re.search(pat, cells[0], re.I):
                    raw = cells[1].replace("*", "")
                    if "%" in raw:
                        v = fnum(raw.replace("%", ""))
                        vals[key] = v / 100 if v is not None else None
                    else:
                        vals[key] = fnum(raw) if key in ("momentum", "forward_rate") else num(raw)
        put_snap(handle, ts(day, hhmm), vals, "progress report")
    # Nov 19 exists only as prose in the track report; values copied from that report.
    f = D("reports", "track", "track_2026-11-19_snowbarkie.md")
    if os.path.exists(f):
        t = open(f, encoding="utf-8").read()
        g = lambda p: (re.search(p, t) or [None, None])[1]  # noqa: E731
        put_snap(OWN, ts("2026-11-19"), {
            "followers": num(g(r"→ \*\*(\d+)\*\*")), "median_views": num(g(r"Page median: ([\d,]+)")),
            "momentum": fnum(g(r"→ \*\*([\d.]+)x")), "posts_14d": num(g(r"There are (\d+) reels in 14")),
            "posts_7d": num(g(r"(\d+) of them in the last 7")),
            "best_reel_views": num(g(r"All outliers[^:]*: ([\d.]+K)"))}, "track report")


# ---------- 4. hooks in progress / compare / ig_vs_fb ----------
def import_report_hooks():
    files = (glob.glob(D("reports", "progress", "*.md")) + glob.glob(D("reports", "compare", "*.md"))
             + glob.glob(D("reports", "facebook", "ig_vs_fb_*.md")))
    for f in sorted(files):
        day = date_part(os.path.basename(f))
        hhmm = (re.search(r"_(\d{4})_", os.path.basename(f)) or [None, None])[1]
        for head, cells in table_rows(open(f, encoding="utf-8").read().splitlines()):
            hcol = next((i for i, h in enumerate(head) if re.search(r"hook", h, re.I)), None)
            if hcol is None or hcol >= len(cells):
                continue
            row = " ".join(cells)
            codes = [c for c in re.findall(r"/reel/([A-Za-z0-9_-]+)|\b(D[A-Za-z0-9_-]{10})\b", row)]
            codes = [a or b for a, b in codes]
            hook = cells[hcol].strip().strip('"').strip("*")
            if not hook or hook.lower() in ("not viewed", "n/a"):
                continue
            if not codes:
                skip("report hook with no reel code (kept only in the report)",
                     f"{os.path.basename(f)}: {hook}")
                continue
            vcol = next((i for i, h in enumerate(head) if re.fullmatch(r"(IG )?views", h, re.I)), None)
            for c in codes:
                reel(c, day, hook_text=hook)
                if vcol is not None and vcol < len(cells):
                    metric(c, ts(day, hhmm), views=num(cells[vcol]))


# ---------- 5. hunt reports ----------
acct_products = defaultdict(set)


def match_product(handle, name, day, table=False):
    """Report item -> existing product via the account; else a new product.
    Bullet items (table=False) must name an account already known from data."""
    h = db.handle_key(handle)
    if table:
        h = account(h)
    elif h not in accounts:
        skip("report bullet whose first word is not a known account", f"{handle} {name}")
        return None
    cands = sorted(acct_products.get(h, set()))
    if len(cands) == 1:
        return cands[0]
    if cands:
        words = set(re.findall(r"[a-z]{3,}", name.lower()))
        best = max(cands, key=lambda k: len(words & set(re.findall(r"[a-z]{3,}",
                                                                   products[k]["name"].lower()))))
        if words & set(re.findall(r"[a-z]{3,}", products[best]["name"].lower())):
            return best
    if re.search(r"\(n/a\)|unclear|not identified", name, re.I):
        return None
    k = product(name, day)
    if k and h:
        sellers.add((k, h))
        acct_products[h].add(k)
    return k


def import_hunts():
    for (pk, h) in sorted(sellers):
        acct_products[h].add(pk)
    for r in reels.values():
        if r.get("handle") and r.get("_pkey"):
            acct_products[r["handle"]].add(r["_pkey"])
    for f in sorted(glob.glob(D("reports", "hunt", "hunt_*.md"))):
        base = os.path.basename(f)
        text = open(f, encoding="utf-8").read()
        title = text.splitlines()[0].lstrip("# ").strip()
        day = date_part(base)
        hhmm = (re.search(r"\d{4}-\d{2}-\d{2}_(\d{4})_", base) or [None, None])[1]
        is_all = base.startswith("hunt_ALL")
        src = "feed" if "feed" in base else ("search" if "search" in title else "hashtag")
        q = (re.search(r'search "([^"]+)"', title) or [None, None])[1]
        rv = num((re.search(r"~?(\d+) reels viewed", title) or [None, ""])[1])
        npd = num((re.search(r"~?(\d+) products", title) or [None, ""])[1])
        note = [title]
        if "rebuilt" in title:
            note.append("REBUILT from data/products.csv on 2026-11-15; original prose and "
                        "reels-viewed count lost (report says batch 1, not batch 2).")
        if is_all:
            note.append("Master report merging the per-batch reports; its items were imported "
                        "from those batch files, not twice.")
        hid = str(uuid.uuid5(NS, base))
        hunts.append({"id": hid, "agent_id": "import", "source": src, "query": q,
                      "started_at": ts(day, hhmm), "finished_at": ts(day, hhmm),
                      "reels_viewed": rv, "new_products": npd, "notes": " ".join(note)})
        if is_all:
            continue
        sections = re.split(r"^##+\s+", text, flags=re.M)[1:]
        for sec in sections:
            head, _, body = sec.partition("\n")
            hl = head.lower()
            lines = body.splitlines()
            if hl.startswith("candidates") or hl.startswith("proven"):
                for hd, cells in table_rows(lines):
                    cols = {h.lower(): i for i, h in enumerate(hd)}
                    if "product" not in cols or "account" not in cols:
                        continue
                    get = lambda c: cells[cols[c]] if c in cols and cols[c] < len(cells) else ""  # noqa
                    name, acc = get("product").replace("*", ""), get("account")
                    pk = match_product(acc, name, day, table=True)
                    if not pk:
                        skip("hunt item with no identified product", f"{base}: {acc}")
                        continue
                    why = get("why") + " " + get("badge")
                    if hl.startswith("candidates"):
                        product(products[pk]["name"], day, "candidate",
                                ip_flag=ip_text(why),
                                seasonal="SEASONAL" in why,
                                note=f"{day} hunt: {why.strip()[:120]}")
                    price = get("price")
                    b = badge(get("badge") or get("bought/mo"))
                    url = get("product_url") or get("product url") or get("url")
                    shop(pk, ts(day, hhmm), price_raw=price if price and price != "n/a" else None,
                         price_usd=usd(price), bought_month=b,
                         store_url=url if url.startswith("http") else None,
                         notes=("badge: " + get("badge")) if get("badge") else None)
            elif hl.startswith("watch"):
                rc = recheck_date(head, day)
                for ln in lines:
                    m = re.match(r"\s*[-*]\s+@?([A-Za-z0-9._]+)\s+(.+)", ln)
                    if m:
                        pk = match_product(m.group(1), re.sub(r"\(.*", "", m.group(2)), day)
                        if pk:
                            product(products[pk]["name"], day, "watch", recheck_on=rc)
            elif "niche-only" in hl:
                for item in re.split(r"\s+·\s+|\n[-*]\s+", body.strip()):
                    m = re.match(r"[-*\s]*@?([A-Za-z0-9._]+)\s+(.+)", item.strip())
                    if m:
                        pk = match_product(m.group(1), re.sub(r"\(.*", "", m.group(2)), day)
                        if pk:
                            product(products[pk]["name"], day, "niche-only", ip_flag=True)
            elif hl.startswith("crowded"):
                for ln in lines:
                    m = re.match(r"\s*[-*]\s+([^:]+):\s*(.+)", ln)
                    if m:
                        for h in re.findall(r"([a-z0-9._]{3,})", m.group(2).split("→")[0]):
                            for pk in sorted(acct_products.get(h, ())):
                                product(products[pk]["name"], day,
                                        note=f"CROWDED {day}: {m.group(1).strip()}")
            elif hl.startswith("skipped"):
                for ln in lines:
                    ln = ln.strip()
                    mu = re.match(r"[-*]\s*unverified[^:]*:\s*(.+)", ln, re.I)
                    if mu:
                        for h in re.findall(r"[a-z0-9._]{3,}", mu.group(1)):
                            for pk in sorted(acct_products.get(h, ())):
                                product(products[pk]["name"], day, "unverified")
                        continue
                    m = re.match(r"[-*]\s+@?([A-Za-z0-9._]+)\s+([^:]+):\s*(.+)", ln)
                    if m and not re.match(r"\d", m.group(1)):
                        pk = match_product(m.group(1), m.group(2), day)
                        if pk:
                            reason = m.group(3).strip()
                            product(products[pk]["name"], day, "skip", skip_reason=reason,
                                    ip_flag=ip_text(reason))
                    elif ln.startswith(("-", "*")) and re.search(r"noise", ln, re.I):
                        skip("hunt 'noise' summary line (rows already in products.csv)", base)


# ---------- 6. check / compare / fb reports ----------
def import_checks():
    for f in sorted(glob.glob(D("reports", "check", "check_*.md"))):
        base = os.path.basename(f)
        m = re.match(r"check_(\d{4}-\d{2}-\d{2})_(.+)\.md", base)
        day, h = m.group(1), db.handle_key(m.group(2))
        text = open(f, encoding="utf-8").read()
        if h == OWN or "WITHDRAWN" in text[:400]:
            skip("check report of own page @snowbarkie (never a product)", base)
            continue
        title = next(ln for ln in text.splitlines() if ln.startswith("# "))[2:]
        name = title.split(", @")[0].strip()
        verdict = title.split(":", 1)[1] if ":" in title else ""
        score = num((re.search(r"score (\d+)/100", title) or [None, ""])[1])
        st = ("winner" if "WINNER" in verdict else "niche-only" if "NICHE" in verdict
              else "watch" if "WATCH" in verdict else "skip" if "SKIP" in verdict else None)
        pk = page_product.get(h) or match_product(h, name, day, table=True)
        product(products[pk]["name"], day, st, score=score,
                ip_flag="NICHE-ONLY" in verdict, note=f"check {day}: {verdict.strip()[:150]}")
        sellers.add((pk, h))
        b = re.search(r'"?(\d+\+) bought in (?:the )?past month', text)
        if b:
            shop(pk, ts(day, "1200"), bought_month=b.group(1), notes=f"from {base}")
        a = re.search(r"~?(\d+)\+? (?:active )?(?:FB |facebook )?ads\b[^\n]{0,60}", text, re.I)
        if a:
            adv = re.search(r"(\d+)\+? advertisers", a.group(0))
            ads[(pk, ts(day, "1200"))] = {"_p": pk, "captured_at": ts(day, "1200"),
                                          "ad_count": int(a.group(1)),
                                          "advertisers": int(adv.group(1)) if adv else None,
                                          "notes": f"{base}: {a.group(0).strip()[:150]}"}


# ---------- 7. results_log ----------
results = []


def import_results():
    for r in csv.DictReader(open(D("data", "results_log.csv"), encoding="utf-8-sig")):
        pk = product(r["product"], r["date"]) if r["product"] else None
        results.append({"logged_on": r["date"], "_p": pk, "link_clicks": num(r["link_clicks"]),
                        "orders": num(r["orders"]), "revenue_usd": fnum(r["revenue"]),
                        "notes": " | ".join(x for x in [r["niche_angle"], r["outcome"], r["notes"]] if x)})


# ---------- write ----------
def apply():
    bad = db.check_access()
    if bad:
        print("\nCannot write: no table access. Run scripts/db_setup.sql first.\n  " + "\n  ".join(bad[:3]))
        sys.exit(1)
    acc_rows = [{**a, "role": a.get("role", "seen")} for a in accounts.values()]
    for r in reels.values():
        if r.get("handle") and r["handle"] not in accounts:
            acc_rows.append({"handle": r["handle"], "role": "seen"})
    if not TEST:
        db.upsert("accounts", acc_rows, "handle")
    prow = []
    for k, p in products.items():
        st, seas = db.db_status(p.get("status", "new"), p.get("seasonal", False))
        prow.append({"name": p["name"], "name_key": k, "status": st,
                     "category": p.get("category"), "skip_reason": p.get("skip_reason"),
                     "ip_flag": p.get("ip_flag", False), "seasonal": bool(seas),
                     "window_closes": p.get("window_closes"), "score": p.get("score"),
                     "recheck_on": p.get("recheck_on"), "first_seen_at": p["first_seen_at"],
                     "last_seen_at": p["last_seen_at"], "notes": "\n".join(p["notes"]) or None})
    if TEST:
        got = db.upsert("products", prow[:TEST], "name_key")
        print(f"\nTEST write: {len(got)} products stored, read back:")
        for r in db.select("products", {"select": "name,name_key,status,seasonal,ip_flag,score,recheck_on",
                                        "name_key": "in.(" + ",".join(x["name_key"] for x in got) + ")"}):
            print("  ", r)
        print("Run again with --apply for the rest (the 5 are upserted, not duplicated).")
        return
    ids = {r["name_key"]: r["id"] for r in db.upsert("products", prow, "name_key")}
    db.upsert("hunts", hunts, "id")
    hunt_by_day = defaultdict(list)
    for h in hunts:
        if not h["notes"].startswith("All Hunts"):
            hunt_by_day[h["started_at"][:10]].append(h["id"])
    rrows = []
    for r in reels.values():
        row = {k: v for k, v in r.items() if not k.startswith("_")}
        row["product_id"] = ids.get(r.get("_pkey"))
        day_h = hunt_by_day.get(r["first_seen_at"][:10], [])
        if len(day_h) == 1:
            row["hunt_id"] = day_h[0]
        rrows.append(row)
    # same keys in every row (PostgREST bulk insert requirement)
    keys = set().union(*rrows)
    db.upsert("reels", [{k: r.get(k) for k in keys} for r in rrows], "reel_code")
    db.upsert("reel_metrics", list(metrics.values()), "reel_code,captured_at")
    db.upsert("product_sellers", [{"product_id": ids[p], "handle": h} for p, h in sellers
                                  if p in ids], "product_id,handle")
    sk = ["product_id", "captured_at", "store_url", "price_usd", "price_raw", "bought_month", "notes"]
    db.upsert("shop_checks", [{k: ({**s, "product_id": ids[s["_p"]]}).get(k) for k in sk}
                              for s in shops.values()], "product_id,captured_at")
    ak = ["product_id", "captured_at", "ad_count", "advertisers", "notes"]
    db.upsert("ad_checks", [{k: ({**a, "product_id": ids[a["_p"]]}).get(k) for k in ak}
                            for a in ads.values()], "product_id,captured_at")
    snk = ["handle", "captured_at"] + sorted(set(SNAP_MAP.values()))
    db.upsert("own_snapshots", [{k: s.get(k) for k in snk} for s in snaps.values()],
              "handle,captured_at")
    if results:
        db.upsert("results_log", [{**{k: v for k, v in r.items() if k != "_p"},
                                   "product_id": ids.get(r["_p"])} for r in results],
                  "logged_on,product_id,handle")
    print("\nWritten.")


def summary():
    print("=== IMPORT SUMMARY", "(DRY RUN)" if "--apply" not in sys.argv else "", "===")
    tbl = [("accounts", len(accounts | {r['handle']: 1 for r in reels.values() if r.get('handle')})),
           ("products", len(products)), ("reels", len(reels)), ("reel_metrics", len(metrics)),
           ("product_sellers", len(sellers)), ("shop_checks", len(shops)), ("ad_checks", len(ads)),
           ("own_snapshots", len(snaps)), ("hunts", len(hunts)), ("results_log", len(results))]
    for t, n in tbl:
        print(f"  {t:16} {n}")
    print("\nProducts by status:")
    for s, n in Counter(p.get("status", "new") for p in products.values()).most_common():
        print(f"  {s:14} {n}")
    print(f"  (ip_flag: {sum(1 for p in products.values() if p.get('ip_flag'))}, "
          f"seasonal: {sum(1 for p in products.values() if p.get('seasonal'))}, "
          f"recheck_on set: {sum(1 for p in products.values() if p.get('recheck_on'))})")
    unver = sum(1 for m in metrics.values() if m["confidence"] == "unverified")
    linked = sum(1 for r in reels.values() if r.get("_pkey"))
    print(f"\nReels: {len(reels)} with codes (all code_verified=false, source=import); "
          f"{linked} linked to a product; {sum(1 for r in reels.values() if r.get('hook_text'))} with hook text; "
          f"{unver} metric rows 'unverified' with empty numbers.")
    print("Snapshots:", ", ".join(sorted(f"{h} {a[:10]}{'' if a[11:16]=='00:00' else ' '+a[11:16]}"
                                         for h, a in snaps)))
    print("\nSkipped / not importable:")
    for r, n in skipped.most_common():
        print(f"  {n:4}  {r}" + (f"   e.g. {skip_examples[r][0]}" if skip_examples[r] else ""))


TEST = int(sys.argv[sys.argv.index("--test") + 1]) if "--test" in sys.argv else 0

if __name__ == "__main__":
    if TEST and "--apply" not in sys.argv:
        sys.argv.append("--apply")
    import_products_csv()
    import_pages()
    import_snapshots()
    import_progress_reports()
    import_report_hooks()
    import_hunts()
    import_checks()
    import_results()
    summary()
    if "--apply" in sys.argv:
        apply()
