# Handoff: Product Hunter database + research dashboard

_Last updated 2026-11-25. No secrets in this file: keys live only in local `.env` (git-ignored)._

## Repos
| Repo | Branch | What |
|---|---|---|
| `ily41/research-agent` (this one) | `main` | Agent skills, Python scripts, SQL, reports, CSV backups |
| `ily41/research-dashboard` (private) | `master` | Next.js dashboard, auto-deployed by Vercel: https://research-dashboard-bice.vercel.app |

## Done
**Database (Supabase)**
- `scripts/db.py` (lease, upserts, all helpers) and `scripts/dbcli.py` (the CLI the skills call).
- Import of all previous work: 513 products, 973 reels, 933 metric rows, 139 shop checks, 11 snapshots, 13 hunts (`scripts/import_legacy.py`, idempotent).
- Nightly CSV backup script `scripts/export_csv.py` → `data/export/` (not scheduled yet).
- Row-level security: owner-only read for user `46430da4-5073-4b08-aaaa-a41ecb1e648d`; anon gets nothing; views use `security_invoker`.
  Tested: logged out = 401 on all 20 tables and views; a throwaway signed-in user = 0 rows everywhere and writes/RPC blocked (user deleted afterwards).

**Skills**
- `/hunt`: lease, repeat skip (code + handle), saves every 10 reels, 7-day Shop-check reuse (`dbcli.py shop-due`), reasons for unchecked candidates.
- `/check-product`, `/track-pages`: read and write the database.
- `/analyze-hunt` (new): `scripts/analyze.py` + `scripts/verify_analysis.py`. Database only, every number is an evidence row with refs and a recompute recipe; runs at the end of the three skills above.
- Analyses: 13 written (12 backfilled imports and the live hunt of 2026-11-25), **596 of 596 data claims verified**.

**Dashboard**
- Email + password login for the owner only (no sign-up, magic link or reset flow), with a generic error.
- Security headers, a strict CSP with nonces, noindex, no trackers. Markdown is rendered without HTML; links are http(s) only with `noopener noreferrer`.
- Pages: Analyses feed (Realtime + toast) and the report page (charts, tables, proof chips, expandable proofs, copy buttons, print, Markdown export, "Discuss with Claude").
- Vercel has only the public URL and the publishable key.

## Unfinished / broken
1. **Empty dashboard after login: not diagnosed yet.** 13 analyses exist and the owner policy is in place, so the page should list them. Check first: (a) the session cookie after `/auth/login` (`sb-…-auth-token`); (b) `select auth.uid()` from the browser session equals the owner ID; (c) the `/analyses` server query error (the page shows "Couldn't load" on error but "No analyses yet" on 0 rows, so the message tells you which); (d) the Vercel runtime logs right after a page load.
2. **Login rate limit doesn't work across Vercel instances** (in-memory limiter). Decision pending: a Vercel Firewall rule (recommended) or a database limiter.
3. **Sign-ups are still enabled** in Supabase Auth (`disable_signup: false`). Data stays safe through RLS, but turn this off: Authentication → Sign In / Providers.
4. The "all hunts together" roll-up isn't written yet; it needs `phase1c` (below).
5. Phone and desktop screenshots of the logged-in pages aren't done (they need the owner signed in in Chrome).
6. The nightly CSV export and the weekly `/analyze-hunt weekly` roll-up aren't scheduled.
7. Imported hunt times come from report filenames: local Baku time stored as UTC (about 4 h off). Live hunts are correct.
8. Some products are duplicated under different wording (e.g. 3 rows for the bck_2_ftr hoodie). Not merged.

## SQL files (`scripts/` and `scripts/sql/`)
| File | Run? | What |
|---|---|---|
| `db_setup.sql` | ✅ run | service-role grants, unique keys for upserts, `touch_reel` |
| `sql/phase1_security_and_analyses.sql` | ✅ run | RLS lockdown, new columns, `niche_ideas`, Realtime (its analysis tables were skipped: they already existed) |
| `sql/phase1b_analysis_columns.sql` | ✅ run | adds analysis columns, proof-rule checks, indexes |
| `sql/phase1c_allow_all_kind.sql` | ❌ **not run** | allows `analyses.kind = 'all'` for the all-hunts roll-up |

Existing constraints to remember: `analysis_actions.kind` ∈ agent_prompt / manual_todo / recheck; `accounts.role` allows own / rival / seen; `analysis_evidence.refs` is NOT NULL.

## Phase 2 next steps
0. Fix the empty-dashboard bug (item 1) and take the logged-in screenshots before building more.
1. Overview command center with alerts: closing seasonal windows (`window_closes` countdown), overdue rechecks, a stuck lease, zero repeats across the last 3 hunts, and brand watch (velvaire / pupack / snowbarkie).
2. Products explorer: facets, search, CSV export, compare 2–4. Product page: timeline, reel growth curves, score A–E, margin calculator (price, landed cost, 3× threshold), IP/seasonal flags, niche ideas, notes.
3. Sellers page (cadence, followers over time, outliers). Reels and hook library with a hook-pattern × clip-type heatmap and links to `https://www.instagram.com/reel/<code>/`.
4. Server-side pagination plus indexes for 10,000+ reels (an index migration will need a new SQL file).
5. Before each deploy: typecheck, lint, build, smoke test every page, and screenshots at phone and desktop widths.
