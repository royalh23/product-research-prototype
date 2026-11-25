"""Recompute every 'data' claim of an analysis from the database and mark it.

  python scripts/verify_analysis.py <analysis_id>
  python scripts/verify_analysis.py --all          # every analysis with unverified claims
  python scripts/verify_analysis.py --all --force  # re-verify everything

Sets analysis_evidence.verified / verified_at / verify_note and
analyses.verified_claims / failed_claims / verified_at.
Note: claims are checked against the CURRENT database. A later status change
(e.g. a product moved from candidate to skip) makes an old claim fail; the
note says so, the frozen report itself never changes.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402
from analyze import skip_group  # noqa: E402


def one(table, **eq):
    rows = db.select(table, {k: f"eq.{v}" for k, v in eq.items()})
    return rows[0] if rows else None


def recompute(rc):
    op = rc.get("op")
    if op in ("metric", "ratio"):
        m = one("reel_metrics", reel_code=rc["reel_code"], captured_at=rc["captured_at"])
        if not m:
            return None, "metric row missing"
        if op == "metric":
            return m.get(rc["field"]), None
        if not m.get("likes"):
            return None, "likes missing"
        return ((m.get("sends") or 0) + (m.get("shares") or 0)) / m["likes"], None
    if op == "field":
        r = one(rc["table"], **rc["key"])
        return (r.get(rc["field"]) if r else None), (None if r else "row missing")
    if op == "badge":
        s = one("shop_checks", id=rc["shop_check_id"])
        b = (s or {}).get("bought_month") or ""
        return (int(b.rstrip("+")) if b[:1].isdigit() else None), (None if s else "row missing")
    if op == "sellers":
        hs = {r["handle"] for r in db.select("product_sellers", {"product_id": f"eq.{rc['product_id']}"})}
        hs |= {r["handle"] for r in db.select("reels", {"product_id": f"eq.{rc['product_id']}",
                                                         "select": "handle"}) if r.get("handle")}
        return len(hs), None
    if op in ("count_status", "count_skip"):
        ids = rc["product_ids"]
        if not ids:
            return 0, None
        ps = db.select("products", {"id": f"in.({','.join(ids)})"})
        if op == "count_status":
            return sum(1 for p in ps if p["status"] in rc["statuses"]), None
        return sum(1 for p in ps if skip_group(p) == rc["group"]), None
    return None, f"unknown recipe {op}"


def verify(aid, force=False):
    now = datetime.now(timezone.utc).isoformat()
    ev = db.select("analysis_evidence", {"analysis_id": f"eq.{aid}", "basis": "eq.data"})
    ok = bad = 0
    for e in ev:
        if e.get("verified") is not None and not force:
            ok += e["verified"]
            bad += not e["verified"]
            continue
        got, err = recompute(e.get("recompute") or {})
        want, tol = e.get("value"), float(e.get("tolerance") or 0)
        if err or got is None or want is None:
            passed, note = False, err or "value not recomputable"
        else:
            got, want = float(got), float(want)
            passed = abs(got - want) <= (max(tol * abs(want), 0.005 + 1e-9) if tol else 1e-9)  # 2-dp rounding
            note = None if passed else f"recomputed {round(got, 4)} vs claimed {want}"
        db._req("PATCH", "analysis_evidence", {"verified": passed, "verified_at": now,
                                               "verify_note": note},
                params={"id": f"eq.{e['id']}"}, prefer="return=minimal")
        ok += passed
        bad += not passed
    db._req("PATCH", "analyses", {"verified_claims": ok, "failed_claims": bad, "verified_at": now,
                                  "data_claims": len(ev)},
            params={"id": f"eq.{aid}"}, prefer="return=minimal")
    print(f"{aid}: {ok} of {len(ev)} data claims verified" + (f", {bad} FAILED" if bad else ""))
    return ok, bad


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    force = "--force" in sys.argv
    if "--all" in sys.argv:
        for a in db.select("analyses", {"select": "id,verified_at"}):
            if force or not a.get("verified_at"):
                verify(a["id"], force)
    else:
        verify(sys.argv[1], force)
