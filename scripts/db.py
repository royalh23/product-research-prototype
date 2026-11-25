"""Supabase helper for Product Hunter (standard library only).

Reads SUPABASE_URL and SUPABASE_SERVICE_KEY from .env. The key is never
printed, logged or put in an exception message.

Every write is an upsert on a natural key, so running the same thing twice
never creates duplicate rows. Required unique keys: scripts/db_setup.sql.

CLI:
  python scripts/db.py check                 # can we read every table?
  python scripts/db.py acquire [holder]      # take the burner lease
  python scripts/db.py release [holder]
  python scripts/db.py seen                  # how many reel codes are known
  python scripts/db.py due                   # products due for a recheck
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEASE = "burner:@dayum3439"
DEFAULT_HOLDER = "product-hunter"


class DBError(Exception):
    pass


class LeaseHeld(DBError):
    """Another agent holds the burner lease: stop, do not browse."""


def _env():
    vals = {}
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    url = os.environ.get("SUPABASE_URL") or vals.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or vals.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise DBError("SUPABASE_URL / SUPABASE_SERVICE_KEY missing in .env")
    return url.rstrip("/") + "/rest/v1/", key


def _req(method, path, body=None, params=None, prefer=None):
    base, key = _env()
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"apikey": key, "Authorization": "Bearer " + key,
               "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body, default=str).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:400]
        raise DBError(f"{method} {path} -> HTTP {e.code}: {msg}") from None
    except urllib.error.URLError as e:
        raise DBError(f"{method} {path} -> network error: {e.reason}") from None


def select(table, params=None, page=1000):
    """Read all rows (paged)."""
    out, offset = [], 0
    while True:
        p = dict(params or {})
        p.setdefault("select", "*")
        p["limit"], p["offset"] = page, offset
        rows = _req("GET", table, params=p) or []
        out += rows
        if len(rows) < page:
            return out
        offset += page


def upsert(table, rows, on_conflict, ignore=False):
    """Insert or update rows, matched on on_conflict. Returns the stored rows."""
    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        return []
    res = "ignore-duplicates" if ignore else "merge-duplicates"
    groups = {}
    for r in rows:  # PostgREST bulk needs identical keys; group instead of null-filling
        groups.setdefault(tuple(sorted(r)), []).append(r)
    out = []
    for grp in groups.values():
        for i in range(0, len(grp), 200):
            out += _req("POST", table, grp[i:i + 200],
                        params={"on_conflict": on_conflict},
                        prefer=f"resolution={res},return=representation") or []
    return out


def _clean(d):
    """Drop None so an upsert never blanks a value that is already stored."""
    return {k: v for k, v in d.items() if v is not None}


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------- keys ----------
def name_key(name):
    """Lowercase, letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def db_status(status, seasonal=None):
    """App status -> database status. Returns (status, seasonal)."""
    s = (status or "new").strip()
    if s == "skip-seasonal":
        return "skip", True
    return {"niche-only": "niche_only"}.get(s, s), seasonal


def reel_code(url_or_code):
    """Reel code from an IG/FB url, or the code itself. None if not found."""
    s = (url_or_code or "").strip()
    m = re.search(r"/(?:reel|reels|p)/([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"[A-Za-z0-9_-]{6,}", s) else None


def handle_key(h):
    return (h or "").strip().lstrip("@").lower() or None


# ---------- lease ----------
def acquire_lease(holder=DEFAULT_HOLDER, minutes=90):
    ok = _req("POST", "rpc/acquire_lease",
              {"p_resource": LEASE, "p_holder": holder, "p_minutes": minutes})
    if ok is False or ok is None or (isinstance(ok, list) and not ok):
        who = ""
        try:
            rows = select("session_lease", {"resource": f"eq.{LEASE}"})
            if rows:
                who = f" (held by {rows[0]['holder']} until {rows[0]['expires_at']})"
        except DBError:
            pass
        raise LeaseHeld(f"Lease {LEASE} is taken{who}. Stop: no browsing.")
    return True


def release_lease(holder=DEFAULT_HOLDER):
    _req("POST", "rpc/release_lease", {"p_resource": LEASE, "p_holder": holder})


# ---------- reads ----------
def load_seen_codes(verified_only=False):
    """Set of reel codes already stored (for the fast 'repeat' skip)."""
    p = {"select": "reel_code"}
    if verified_only:
        p["code_verified"] = "is.true"
    return {r["reel_code"] for r in select("reels", p)}


def load_seen():
    """{reel_code: handle} for every stored reel (one read at hunt start)."""
    return {r["reel_code"]: r.get("handle") for r in
            select("reels", {"select": "reel_code,handle"})}


def classify_reel(code, handle, seen):
    """'repeat' when code AND handle match what is stored; 'handle_changed'
    when the code is known under another handle; else 'new'. No DB call."""
    c, h = reel_code(code), handle_key(handle)
    if c not in seen:
        return "new"
    return "repeat" if seen[c] == h else "handle_changed"


def flag_handle_changed(code, old_handle, new_handle):
    """Stored row no longer trusted: mark it unverified and note the mismatch."""
    _req("PATCH", "reels", {"code_verified": False, "last_seen_at": _now(),
                            "notes": f"handle mismatch: stored @{old_handle}, seen @{new_handle}"},
         params={"reel_code": f"eq.{reel_code(code)}"})


def load_product_keys():
    """{name_key: {id, name, status}} for every known product."""
    return {r["name_key"]: r for r in
            select("products", {"select": "id,name,name_key,status"})}


def due_rechecks(on=None):
    on = on or date.today().isoformat()
    return select("products", {"select": "id,name,status,recheck_on",
                               "recheck_on": f"lte.{on}", "order": "recheck_on"})


# ---------- writes ----------
def upsert_account(handle, **f):
    h = handle_key(handle)
    if not h:
        return None
    row = _clean({"handle": h, "last_seen_at": _now(), **f})
    return upsert("accounts", row, "handle")[0]


def upsert_product(name, **f):
    """Match on name_key. Returns the stored row (with id)."""
    key = name_key(name)
    if not key:
        raise DBError("product name has no letters or digits")
    if "status" in f:
        f["status"], seas = db_status(f["status"], f.get("seasonal"))
        if seas:
            f["seasonal"] = True
    row = _clean({"name": name, "name_key": key, "last_seen_at": _now(), **f})
    return upsert("products", row, "name_key")[0]


def upsert_reel(code, times_seen=None, **f):
    """f: platform, handle, product_id, post_date, code_verified, hook_text,
    first_frame, clip_type, cta, source, hunt_id, notes."""
    c = reel_code(code)
    if not c:
        raise DBError("no reel code")
    if f.get("handle"):
        f["handle"] = handle_key(f["handle"])
        upsert_account(f["handle"], platform=f.get("platform"))
    row = _clean({"reel_code": c, "last_seen_at": _now(),
                  "times_seen": times_seen, **f})
    return upsert("reels", row, "reel_code")[0]


def add_metrics(code, captured_at=None, confidence="measured", **m):
    """m: views, likes, comments, sends, shares. One row per reel per capture time."""
    row = {"reel_code": reel_code(code), "captured_at": captured_at or _now(),
           "confidence": confidence, **{k: m.get(k) for k in
                                        ("views", "likes", "comments", "sends", "shares")}}
    return upsert("reel_metrics", row, "reel_code,captured_at")[0]


def add_seller(product_id, handle, store_url=None):
    h = handle_key(handle)
    upsert_account(h)
    return upsert("product_sellers", _clean({"product_id": product_id, "handle": h,
                                             "store_url": store_url}),
                  "product_id,handle")[0]


def add_shop_check(product_id, captured_at=None, **f):
    """f: store_url, price_usd, price_raw (keep the raw currency), fx_rate,
    bought_month ('300+'), rating, reviews, notes."""
    row = _clean({"product_id": product_id, "captured_at": captured_at or _now(), **f})
    return upsert("shop_checks", row, "product_id,captured_at")[0]


def add_ad_check(product_id, captured_at=None, **f):
    """f: ad_count, advertisers, oldest_ad_date, notes."""
    row = _clean({"product_id": product_id, "captured_at": captured_at or _now(), **f})
    return upsert("ad_checks", row, "product_id,captured_at")[0]


def add_snapshot(handle, captured_at=None, **f):
    """Own-page snapshot. f: followers, median_views, median_views_2_14d,
    best_reel_views, outliers_14d, posts_7d, posts_14d, momentum, like_rate, forward_rate."""
    row = _clean({"handle": handle_key(handle), "captured_at": captured_at or _now(), **f})
    return upsert("own_snapshots", row, "handle,captured_at")[0]


def start_hunt(agent_id, source="feed", query=None, hunt_id=None, started_at=None):
    row = _clean({"id": hunt_id, "agent_id": agent_id, "source": source,
                  "query": query, "started_at": started_at or _now()})
    return upsert("hunts", row, "id")[0] if hunt_id else \
        _req("POST", "hunts", row, prefer="return=representation")[0]


def finish_hunt(hunt_id, **f):
    """f: reels_viewed, new_reels, repeats_skipped, new_products, notes, finished_at."""
    f.setdefault("finished_at", _now())
    return _req("PATCH", "hunts", _clean(f), params={"id": f"eq.{hunt_id}"},
                prefer="return=representation")


def touch_repeat(code):
    """A repeat reel seen again: bump last_seen_at (times_seen via db_setup.sql RPC)."""
    try:
        _req("POST", "rpc/touch_reel", {"p_code": reel_code(code)})
    except DBError:
        _req("PATCH", "reels", {"last_seen_at": _now()},
             params={"reel_code": f"eq.{reel_code(code)}"})


def check_access():
    tables = ["accounts", "products", "reels", "reel_metrics", "hunts", "shop_checks",
              "ad_checks", "product_sellers", "own_snapshots", "results_log",
              "lessons", "session_lease"]
    bad = []
    for t in tables:
        try:
            _req("GET", t, params={"select": "*", "limit": 1})
        except DBError as e:
            bad.append(f"{t}: {str(e).split(': ', 1)[-1][:120]}")
    return bad


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    arg = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_HOLDER
    try:
        if cmd == "check":
            bad = check_access()
            print("OK: all tables readable" if not bad else "NO ACCESS:\n  " + "\n  ".join(bad))
            sys.exit(1 if bad else 0)
        elif cmd == "acquire":
            acquire_lease(arg); print("lease acquired")
        elif cmd == "release":
            release_lease(arg); print("lease released")
        elif cmd == "seen":
            print(len(load_seen_codes()), "reel codes known")
        elif cmd == "due":
            for r in due_rechecks():
                print(r["recheck_on"], r["status"], r["name"])
    except LeaseHeld as e:
        print("STOP:", e); sys.exit(2)
    except DBError as e:
        print("DB error:", e); sys.exit(1)
