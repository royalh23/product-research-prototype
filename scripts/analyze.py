"""/analyze-hunt: build one frozen, evidence-backed analysis from the database.

Reads only from the database (never browses). Every number written into the
analysis has an analysis_evidence row with refs + a recompute recipe that
scripts/verify_analysis.py re-checks.

  python scripts/analyze.py hunt <hunt_id> [--backfilled]
  python scripts/analyze.py latest                 # newest hunt
  python scripts/analyze.py all [--backfilled]     # all hunts together
  python scripts/analyze.py backfill               # one per imported hunt + all
  python scripts/analyze.py check "<product name>" | track | weekly
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

BRAND_WORDS = ("velvaire", "pupack", "snowbarkie")
OWN = "snowbarkie"
KRW_PER_USD = 1400  # rough planning rate; every converted price is shown with "~"
NM = "not measured"


def r2(x):
    return None if x is None else round(x, 2)


def fmt(n):
    if n is None:
        return NM
    if abs(n) >= 1e6:
        return f"{n / 1e6:.1f}M"
    if abs(n) >= 1e3:
        return f"{n / 1e3:.1f}K"
    return f"{n:g}" if isinstance(n, float) else str(n)


def price_view(raw, usd):
    """Plain $ → '$49.99'. KRW → '₩54,000 (~$39)'. Unknown currency → raw as seen."""
    if usd is not None:
        return f"${usd:.2f}"
    if not raw:
        return NM
    m = re.search(r"₩\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*KRW", raw)
    if m:
        krw = float((m.group(1) or m.group(2)).replace(",", ""))
        return f"{raw.split('(')[0].strip()} (~${krw / KRW_PER_USD:.0f})"
    return raw


class Builder:
    def __init__(self, kind, title, hunt_id=None, subject=None, backfilled=False):
        self.a = {"kind": kind, "title": title, "hunt_id": hunt_id, "subject": subject or "",
                  "backfilled": backfilled}
        self.sections, self.evidence, self.actions = [], [], []

    # --- evidence helpers -------------------------------------------------
    def data(self, sec, claim, value, refs, method, recipe, tol=0.01):
        self.evidence.append({"section_key": sec, "claim": claim, "basis": "data",
                              "value": value, "refs": refs, "method": method,
                              "recompute": recipe, "tolerance": tol})
        return value

    def infer(self, sec, claim, reasoning, confidence):
        self.evidence.append({"section_key": sec, "claim": claim, "basis": "inference",
                              "reasoning": reasoning, "confidence": confidence})

    def section(self, key, title, body, chart=None, table=None):
        self.sections.append({"position": len(self.sections) + 1, "slug": key, "heading": title,
                              "body_md": body, "chart": chart, "table_data": table})

    KINDS = {"prompt": "agent_prompt", "manual": "manual_todo", "recheck": "recheck"}

    def action(self, kind, text, title=None):
        self.actions.append({"position": len(self.actions) + 1, "kind": self.KINDS[kind],
                             "title": title or ("Agent prompt" if kind == "prompt" else "To do"),
                             "body": text})

    # --- write (an analysis is written once and never changed) -------------
    def save(self):
        verdict = next((x["body_md"] for x in self.sections if x["slug"] == "verdict"), "")
        self.a["verdict"] = verdict.split(chr(10))[0]
        self.a["summary_md"] = verdict
        self.a["data_claims"] = sum(1 for e in self.evidence if e["basis"] == "data")
        q = {"kind": f"eq.{self.a['kind']}", "subject": f"eq.{self.a['subject']}",
             "hunt_id": f"eq.{self.a['hunt_id']}" if self.a["hunt_id"] else "is.null"}
        existing = db.select("analyses", q)
        if existing:
            print(f"exists, unchanged: {existing[0]['id']} ({self.a['title']})")
            return existing[0]["id"]
        aid = db._req("POST", "analyses", {k: v for k, v in self.a.items() if v is not None},
                      prefer="return=representation")[0]["id"]
        try:
            self._write_children(aid)
        except Exception:
            for t in ("analysis_evidence", "analysis_actions", "analysis_sections", "analyses"):
                db._req("DELETE", t, params={("id" if t == "analyses" else "analysis_id"): f"eq.{aid}"})
            raise
        print(f"analysis {aid}: {len(self.sections)} sections, {len(self.evidence)} claims "
              f"({self.a['data_claims']} data) | {self.a['title']}")
        return aid

    def _write_children(self, aid):
        sec_ids = {}
        if self.sections:
            for r in db._req("POST", "analysis_sections", [{**x, "analysis_id": aid} for x in self.sections],
                             prefer="return=representation"):
                sec_ids[r["slug"]] = r["id"]
        if self.actions:
            db._req("POST", "analysis_actions", [{**x, "analysis_id": aid} for x in self.actions],
                    prefer="return=minimal")
        keys = ["claim", "basis", "value", "refs", "method", "recompute", "tolerance",
                "reasoning", "confidence", "source_url"]
        if self.evidence:
            rows = [{**{k: e.get(k) for k in keys}, "analysis_id": aid,
                     "section_id": sec_ids.get(e["section_key"])} for e in self.evidence]
            for r in rows:
                if r["basis"] == "data":
                    r["confidence"] = "high"
                if r["refs"] is None:
                    r["refs"] = []  # column is NOT NULL; inference/external claims have no table refs
            for i in range(0, len(rows), 200):
                db._req("POST", "analysis_evidence", rows[i:i + 200], prefer="return=minimal")


# ---------------- data loading ----------------
class Data:
    def __init__(self):
        self.hunts = sorted(db.select("hunts"), key=lambda h: h["started_at"])
        self.products = {p["id"]: p for p in db.select("products")}
        self.reels = db.select("reels")
        self.metrics = defaultdict(list)
        for m in db.select("reel_metrics", {"order": "captured_at"}):
            self.metrics[m["reel_code"]].append(m)
        self.shops = defaultdict(list)
        for s in db.select("shop_checks", {"order": "captured_at"}):
            self.shops[s["product_id"]].append(s)
        self.sellers = defaultdict(set)
        for s in db.select("product_sellers"):
            self.sellers[s["product_id"]].add(s["handle"])
        self.accounts = {a["handle"]: a for a in db.select("accounts")}

    def hunt_reels(self, hunt):
        """Reels of one hunt: linked by hunt_id; imported reels (no hunt_id) by
        first-seen date. Returns (reels, shared_day) where shared_day means the
        date had several hunts so imported reels can't be split between them."""
        day = hunt["started_at"][:10]
        same_day = [h for h in self.hunts if h["started_at"][:10] == day
                    and not (h["notes"] or "").startswith("All Hunts")]
        out = [r for r in self.reels if r.get("hunt_id") == hunt["id"]]
        if hunt["agent_id"] == "import":
            out += [r for r in self.reels if not r.get("hunt_id") and r["source"] == "import"
                    and r["first_seen_at"][:10] == day]
        return out, len(same_day) > 1 and hunt["agent_id"] == "import"

    def latest_metric(self, code, before=None):
        ms = [m for m in self.metrics.get(code, []) if not before or m["captured_at"] <= before]
        return ms[-1] if ms else None


def skip_group(p):
    """Skip group of a product, or None. Order: IP > seasonal > regulated > status."""
    if not (p["status"] in ("skip", "noise", "niche_only", "unverified") or p.get("ip_flag") or p.get("seasonal")):
        return None
    if p.get("ip_flag"):
        return "IP"
    if p.get("seasonal"):
        return "seasonal"
    if re.search(r"medic|supplement|vape|weapon|knife|drug", (p.get("skip_reason") or "") + p["name"], re.I):
        return "regulated"
    return p["status"]


def fwd(m):
    if not m or not m.get("likes"):
        return None
    return ((m.get("sends") or 0) + (m.get("shares") or 0)) / m["likes"]


# ---------------- the hunt analysis ----------------
def analyze_scope(D, B, reels, label, prev_hunt=None, hunt=None, shared_day=False):
    now = datetime.now(timezone.utc)
    pids = {r["product_id"] for r in reels if r.get("product_id")}
    prods = [D.products[p] for p in pids if p in D.products]
    rows = []
    for r in reels:
        p = D.products.get(r.get("product_id"))
        m = D.latest_metric(r["reel_code"])
        rows.append((r, p, m))

    def mref(r, m, field):
        return {"table": "reel_metrics", "key": {"reel_code": r["reel_code"], "captured_at": m["captured_at"]},
                "field": field, "value": m.get(field)}

    # candidates (best reel per product)
    cand = {}
    for r, p, m in rows:
        if p and p["status"] in ("candidate", "winner") and m and m.get("likes"):
            f = fwd(m)
            if p["id"] not in cand or (f or 0) > (cand[p["id"]][3] or 0):
                cand[p["id"]] = (r, p, m, f)
    ranked = sorted(cand.values(), key=lambda x: -(x[3] or 0))

    # ---- 1. verdict
    if ranked:
        r, p, m, f = ranked[0]
        B.data("verdict", f"Top forward rate: {p['name']}", r2(f),
               [mref(r, m, "likes"), mref(r, m, "sends"), mref(r, m, "shares")],
               "(sends + shares) / likes on the reel's latest metric row",
               {"op": "ratio", "reel_code": r["reel_code"], "captured_at": m["captured_at"]})
        reasons = [f"- **{p['name']}** (@{r['handle']}): forward rate **{r2(f)}**, {fmt(m['likes'])} likes, "
                   f"{fmt(m.get('sends'))} sends."]
        B.data("verdict", "Candidate count", len(ranked),
               [{"table": "products", "key": {"id": x[1]["id"]}, "field": "status", "value": x[1]["status"]}
                for x in ranked][:20],
               "number of products in this scope with status candidate/winner and a metric row",
               {"op": "count_status", "product_ids": [x[1]["id"] for x in ranked],
                "statuses": ["candidate", "winner"]}, tol=0)
        reasons.append(f"- {len(ranked)} candidates in total from {len(reels)} reels.")
        proven = [(p2, s) for p2 in prods for s in D.shops.get(p2["id"], [])
                  if s.get("bought_month") and re.match(r"\d+\+", s["bought_month"])]
        if proven:
            best = max(proven, key=lambda x: int(x[1]["bought_month"].rstrip("+")))
            B.data("verdict", f"Best Shop badge {best[1]['bought_month']}",
                   int(best[1]["bought_month"].rstrip("+")),
                   [{"table": "shop_checks", "key": {"id": best[1]["id"]}, "field": "bought_month",
                     "value": best[1]["bought_month"]}],
                   "highest 'bought in past month' badge among this scope's products",
                   {"op": "badge", "shop_check_id": best[1]["id"]}, tol=0)
            reasons.append(f"- Strongest sales proof: **{best[0]['name']}**, "
                           f"{best[1]['bought_month']} bought in past month.")
        else:
            reasons.append("- Shop sales proof: not measured in this scope.")
        verdict = f"Check **{p['name']}** first."
    else:
        verdict, reasons = "No candidate in this scope.", ["- No product reached candidate status."]
    B.section("verdict", "Verdict", verdict + "\n\n" + "\n".join(reasons[:3]))

    # ---- 2. what changed
    if hunt and prev_hunt:
        lines = []
        for f, lab in (("reels_viewed", "Reels viewed"), ("new_reels", "New reels"),
                       ("repeats_skipped", "Repeats skipped"), ("new_products", "New products")):
            a, b = prev_hunt.get(f), hunt.get(f)
            for h, v in ((prev_hunt, a), (hunt, b)):
                if v is not None:
                    B.data("changed", f"{lab} in hunt {h['started_at'][:16]}", v,
                           [{"table": "hunts", "key": {"id": h["id"]}, "field": f, "value": v}],
                           f"hunts.{f} as recorded", {"op": "field", "table": "hunts",
                                                      "key": {"id": h["id"]}, "field": f}, tol=0)
            lines.append(f"| {lab} | {fmt(a)} | {fmt(b)} |")
        body = (f"Compared with the previous hunt ({prev_hunt['started_at'][:16]} UTC).\n\n"
                "| Metric | Previous | This hunt |\n|---|---|---|\n" + "\n".join(lines))
        if hunt["agent_id"] == "import":
            body += "\n\nImported hunts didn't record new/repeat counts; those show as not measured."
    else:
        body = "No previous hunt to compare with." if hunt else "Roll-up across all hunts."
    B.section("changed", "What changed since the previous hunt", body)

    # ---- 3. candidates ranked
    tbl, chart = [], []
    for i, (r, p, m, f) in enumerate(ranked[:25], 1):
        B.data("candidates", f"{p['name']} forward rate", r2(f),
               [mref(r, m, "likes"), mref(r, m, "sends"), mref(r, m, "shares")],
               "(sends + shares) / likes", {"op": "ratio", "reel_code": r["reel_code"],
                                            "captured_at": m["captured_at"]})
        B.data("candidates", f"{p['name']} likes", m["likes"], [mref(r, m, "likes")],
               "likes on latest metric row", {"op": "metric", "reel_code": r["reel_code"],
                                              "captured_at": m["captured_at"], "field": "likes"}, tol=0)
        tbl.append({"rank": i, "product": p["name"], "handle": r["handle"], "reel_code": r["reel_code"],
                    "likes": m["likes"], "sends": m.get("sends"), "shares": m.get("shares"),
                    "forward_rate": r2(f), "post_date": r.get("post_date"), "status": p["status"]})
        chart.append({"label": p["name"][:28], "forward_rate": r2(f)})
    B.section("candidates", "Candidates ranked",
              f"{len(ranked)} candidates, ranked by forward rate ((sends + shares) / likes)."
              if ranked else "No candidates.",
              chart={"type": "bar", "x": "label", "y": "forward_rate", "unit": "ratio", "data": chart},
              table={"columns": ["rank", "product", "handle", "likes", "sends", "forward_rate",
                                 "post_date", "status"], "rows": tbl})

    # ---- 4. proven sellers
    ptbl = []
    for p in prods:
        for s in D.shops.get(p["id"], []):
            if s.get("bought_month") and re.match(r"\d+\+", s["bought_month"]):
                B.data("proven", f"{p['name']} badge", int(s["bought_month"].rstrip("+")),
                       [{"table": "shop_checks", "key": {"id": s["id"]}, "field": "bought_month",
                         "value": s["bought_month"]}], "Shop cart badge text as recorded",
                       {"op": "badge", "shop_check_id": s["id"]}, tol=0)
                ptbl.append({"product": p["name"], "badge": s["bought_month"] + " bought in past month",
                             "price": price_view(s.get("price_raw"), s.get("price_usd")),
                             "price_estimated": s.get("price_usd") is None and bool(s.get("price_raw")),
                             "store_url": s.get("store_url"), "checked": s["captured_at"][:10]})
    ptbl.sort(key=lambda x: -int(x["badge"].split("+")[0]))
    note = "\n\nPrices marked ~ are converted from KRW at a rough rate and are estimates." \
        if any(x["price_estimated"] for x in ptbl) else ""
    if any(x["price_estimated"] for x in ptbl):
        B.infer("proven", "KRW prices converted to USD", f"Converted at {KRW_PER_USD} KRW per USD, a rough "
                "planning rate; stores geolocate the browser and show KRW.", "low")
    B.section("proven", "Proven sellers (Shop badge)",
              (f"{len(ptbl)} badge rows." if ptbl else "No Shop badges in this scope.") + note,
              table={"columns": ["product", "badge", "price", "checked", "store_url"], "rows": ptbl})

    # ---- 5. candidates with no Shop check
    nos = []
    for r, p, m, f in ranked:
        sc = D.shops.get(p["id"], [])
        if not any(s.get("bought_month") or s.get("price_raw") for s in sc):
            reason = next((s.get("shop_status") for s in sc if s.get("shop_status")), None) or \
                next((n for s in sc for n in ["blocked", "not-shop", "no-link"]
                      if n in (s.get("notes") or "")), None)
            if not reason and r.get("post_date") and r["post_date"] >= (now - timedelta(days=1)).date().isoformat():
                reason = "too-new"
            nos.append({"product": p["name"], "handle": r["handle"],
                        "reason": reason or "not recorded (hunt ran before the reason rule)"})
    B.section("no_shop_check", "Candidates with no Shop check",
              f"{len(nos)} of {len(ranked)} candidates have no Shop check." if ranked else "No candidates.",
              table={"columns": ["product", "handle", "reason"], "rows": nos})

    # ---- 6. crowded themes (distinct seller handles over time)
    crowd = []
    for p in prods:
        hs = {r["handle"] for r in D.reels if r.get("product_id") == p["id"] and r.get("handle")}
        hs |= D.sellers.get(p["id"], set())
        if len(hs) >= 3:
            B.data("crowded", f"{p['name']} seller count", len(hs),
                   [{"table": "product_sellers", "key": {"product_id": p["id"]}, "field": "handle",
                     "value": sorted(hs)[:10]}],
                   "distinct handles in product_sellers plus reels linked to the product",
                   {"op": "sellers", "product_id": p["id"]}, tol=0)
            by_day = defaultdict(set)
            for r in D.reels:
                if r.get("product_id") == p["id"] and r.get("handle"):
                    by_day[r["first_seen_at"][:10]].add(r["handle"])
            seen, series = set(), []
            for d in sorted(by_day):
                seen |= by_day[d]
                series.append({"date": d, "sellers": len(seen)})
            crowd.append({"product": p["name"], "sellers": len(hs), "series": series})
    crowd.sort(key=lambda x: -x["sellers"])
    B.section("crowded", "Crowded themes",
              f"{len(crowd)} products seen from 3+ accounts." if crowd else "No product seen from 3+ accounts.",
              chart={"type": "line", "x": "date", "y": "sellers", "series": crowd[:5]},
              table={"columns": ["product", "sellers"], "rows": [{k: c[k] for k in ("product", "sellers")}
                                                                for c in crowd]})

    # ---- 7. fit for my pages
    fit = []
    for r, p, m, f in ranked:
        txt = (p["name"] + " " + (p.get("category") or "")).lower()
        if p.get("category") == "pet" or re.search(r"\bdog|puppy|pup\b", txt):
            fit.append(f"- **{p['name']}** → Pupack dog audience (pet product)")
            B.infer("fit", f"{p['name']} fits the Pupack audience",
                    "category is pet / name mentions dogs; Pupack buyers are dog owners", "medium")
        elif re.search(r"hair|bonnet|dryer|beauty", txt) or p.get("category") == "beauty":
            fit.append(f"- **{p['name']}** → Velvaire (hair/beauty)")
            B.infer("fit", f"{p['name']} fits Velvaire", "hair/beauty product; Velvaire is a hair-dryer "
                    "bonnet brand", "low")
    B.section("fit", "Fit for my pages", "\n".join(fit) if fit else
              "No candidate in this scope fits the Pupack dog audience or Velvaire.")

    # ---- 8. hook and clip insights
    by_clip = defaultdict(list)
    hooks = []
    for r, p, m in rows:
        f = fwd(m)
        if f is not None and r.get("clip_type"):
            by_clip[r["clip_type"].split("/")[0].strip().lower()].append(f)
        if r.get("hook_text") and m and m.get("likes"):
            hooks.append((m["likes"], r, m))
    clip_rows = [{"clip_type": k, "reels": len(v), "median_forward_rate": r2(sorted(v)[len(v) // 2])}
                 for k, v in by_clip.items() if len(v) >= 2]
    clip_rows.sort(key=lambda x: -x["median_forward_rate"])
    hooks.sort(key=lambda x: -x[0])
    hl = []
    for likes, r, m in hooks[:5]:
        B.data("hooks", f"Hook likes {r['reel_code']}", likes, [mref(r, m, "likes")], "likes on latest metric",
               {"op": "metric", "reel_code": r["reel_code"], "captured_at": m["captured_at"],
                "field": "likes"}, tol=0)
        hl.append({"hook": r["hook_text"], "clip_type": r.get("clip_type") or NM, "likes": likes,
                   "reel_code": r["reel_code"]})
    B.section("hooks", "Hook and clip insights",
              "Median forward rate by clip type (types with 2+ reels), and the most-liked hooks."
              if clip_rows or hl else "Hooks and clip types: not measured in this scope (imported data rarely has them).",
              chart={"type": "bar", "x": "clip_type", "y": "median_forward_rate", "data": clip_rows},
              table={"columns": ["hook", "clip_type", "likes"], "rows": hl})

    # ---- 9. watch list and rechecks
    watch = [{"product": p["name"], "status": p["status"], "recheck_on": p.get("recheck_on") or NM,
              "overdue": bool(p.get("recheck_on") and p["recheck_on"] < now.date().isoformat())}
             for p in prods if p["status"] == "watch" or p.get("recheck_on")]
    watch.sort(key=lambda x: x["recheck_on"])
    B.section("watch", "Watch list and rechecks",
              f"{len(watch)} products to watch; {sum(w['overdue'] for w in watch)} rechecks overdue.",
              table={"columns": ["product", "status", "recheck_on", "overdue"], "rows": watch})

    # ---- 10. skipped and why
    cnt, members = Counter(), defaultdict(list)
    for p in prods:
        key = skip_group(p)
        if key:
            cnt[key] += 1
            members[key].append(p["id"])
    for k, v in cnt.items():
        B.data("skipped", f"Skipped: {k}", v,
               [{"table": "products", "key": {"id": i}, "field": "status", "value": D.products[i]["status"]}
                for i in members[k][:20]],
               "count of this scope's products in this skip group (IP > seasonal > regulated > status)",
               {"op": "count_skip", "product_ids": members[k], "group": k}, tol=0)
    B.section("skipped", "Skipped and why",
              "\n".join(f"- {k}: {v}" for k, v in cnt.most_common()) or "Nothing skipped.")

    # ---- 11. risks and data quality
    total_m = [m for _, _, m in rows if m]
    unver = sum(1 for m in total_m if m["confidence"] == "unverified")
    no_handle = sum(1 for r, _, _ in rows if not r.get("handle"))
    est = sum(1 for p in prods for s in D.shops.get(p["id"], []) if s.get("price_raw") and s.get("price_usd") is None)
    q = [f"- Unverified metric rows: **{unver} of {len(total_m)}**",
         f"- Reels with no handle: **{no_handle}**",
         f"- Prices without a USD value (estimated with ~ or currency unknown): **{est}**",
         f"- Imported reels are code_verified = false until a hunt sees them again."]
    if shared_day:
        q.append("- This date had several hunts. Imported reels can't be split between them, so "
                 "this analysis covers **all reels first seen that day**.")
    if hunt and "REBUILT" in (hunt.get("notes") or ""):
        q.append("- This hunt's report was **rebuilt from the CSV**; its reels-viewed count is not measured.")
    B.section("risks", "Risks and data quality", "\n".join(q))

    # ---- 12. brand watch
    hits = []
    for r in reels:
        blob = " ".join(str(r.get(k) or "") for k in ("handle", "hook_text", "notes", "first_frame")).lower()
        p = D.products.get(r.get("product_id"))
        if p:
            blob += " " + p["name"].lower()
        for w in BRAND_WORDS:
            if w in blob and r.get("handle") != OWN:
                hits.append({"word": w, "reel_code": r["reel_code"], "handle": r.get("handle")})
    B.section("brand_watch", "Brand watch",
              f"{len(hits)} reels mention velvaire / pupack / snowbarkie (outside @snowbarkie)."
              if hits else "No reel outside @snowbarkie mentions velvaire, pupack or snowbarkie.",
              table={"columns": ["word", "handle", "reel_code"], "rows": hits})

    # ---- 13. next actions
    for r, p, m, f in ranked[:3]:
        B.action("prompt", f"/check-product https://www.instagram.com/reel/{r['reel_code']}/")
    for n in nos[:3]:
        B.action("prompt", f"Run a Shop check only for \"{n['product']}\" (@{n['handle']}) and save it "
                 "with dbcli.py shop. Read only; quantity 1; remove from the Shop cart after.")
    for w in [w for w in watch if w["overdue"]][:3]:
        B.action("recheck", f"**Recheck {w['product']}** (due {w['recheck_on']}).")
    if hits:
        B.action("manual", "**Look at the brand-watch hits: is anyone using your brand names?**")
    B.section("next_actions", "Next actions", "Ready-to-paste prompts and to-dos below.")


def run_hunt(D, hunt, backfilled=False):
    hs = [h for h in D.hunts if not (h["notes"] or "").startswith("All Hunts")]
    i = next(i for i, h in enumerate(hs) if h["id"] == hunt["id"])
    prev = hs[i - 1] if i > 0 else None
    reels, shared = D.hunt_reels(hunt)
    title = f"Hunt {hunt['started_at'][:16].replace('T', ' ')} UTC · {hunt['source']}"
    B = Builder("hunt", title, hunt_id=hunt["id"], backfilled=backfilled)
    analyze_scope(D, B, reels, title, prev, hunt, shared)
    return B.save()


def run_all(D, backfilled=False):
    B = Builder("all", "All hunts together", subject="all", backfilled=backfilled)
    analyze_scope(D, B, [r for r in D.reels if r.get("handle") != OWN], "all")
    return B.save()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "latest"
    bf = "--backfilled" in sys.argv
    D = Data()
    if cmd == "hunt":
        run_hunt(D, next(h for h in D.hunts if h["id"] == sys.argv[2]), bf)
    elif cmd == "latest":
        run_hunt(D, [h for h in D.hunts if h.get("finished_at")][-1])
    elif cmd == "all":
        run_all(D, bf)
    elif cmd == "backfill":
        for h in D.hunts:
            if h["agent_id"] == "import" and not (h["notes"] or "").startswith("All Hunts"):
                run_hunt(D, h, True)
        run_all(D, True)
    elif cmd in ("check", "track", "weekly"):
        sub = sys.argv[2] if len(sys.argv) > 2 else datetime.now(timezone.utc).strftime("%G-W%V")
        B = Builder(cmd, f"{cmd.title()} · {sub}", subject=sub)
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        scope = [r for r in D.reels if r["last_seen_at"] >= since and r.get("handle") != OWN] \
            if cmd != "check" else [r for r in D.reels if r.get("product_id") in
                                    {p["id"] for p in D.products.values() if sub.lower() in p["name"].lower()}]
        analyze_scope(D, B, scope, sub)
        B.save()
    else:
        print(__doc__)
