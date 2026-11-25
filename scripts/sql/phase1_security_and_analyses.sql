-- PHASE 1: run in Supabase > SQL Editor (one go). Safe to re-run.
-- Owner: the only user allowed to read anything through the website.
-- 46430da4-5073-4b08-aaaa-a41ecb1e648d

begin;

-- ========== 1. Small migrations ==========
alter table public.reels       add column if not exists hook_pattern text;
alter table public.products    add column if not exists supplier_cost_usd numeric,
                               add column if not exists landed_cost_usd  numeric,
                               add column if not exists target_price_usd numeric;
alter table public.shop_checks add column if not exists shop_status text;   -- ok | not-shop | no-link | blocked | ...

create table if not exists public.niche_ideas (
  id          bigint generated always as identity primary key,
  product_id  uuid not null references public.products(id) on delete cascade,
  idea        text not null,
  lever       text,            -- buyer / problem / design / bundle ...
  evidence    text,
  risk        text,
  status      text not null default 'idea' check (status in ('idea','picked','testing','dropped')),
  created_at  timestamptz not null default now(),
  unique (product_id, idea)
);

-- ========== 2. Analyses (frozen snapshots; old reports never change) ==========
create table if not exists public.analyses (
  id               uuid primary key default gen_random_uuid(),
  kind             text not null check (kind in ('hunt','check','track','weekly','all')),
  hunt_id          uuid references public.hunts(id) on delete set null,
  subject          text,                       -- product / page / week label
  title            text not null,
  verdict          text,
  backfilled       boolean not null default false,
  data_claims      int not null default 0,
  verified_claims  int not null default 0,
  failed_claims    int not null default 0,
  verified_at      timestamptz,
  created_at       timestamptz not null default now(),
  unique (kind, hunt_id, subject)
);

create table if not exists public.analysis_sections (
  id           bigint generated always as identity primary key,
  analysis_id  uuid not null references public.analyses(id) on delete cascade,
  ord          int not null,
  key          text not null,                 -- verdict, changed, candidates, proven, no_shop_check, crowded, fit, hooks, watch, skipped, risks, brand_watch, next_actions
  title        text not null,
  body_md      text,                          -- rendered WITHOUT raw HTML
  chart        jsonb,                         -- frozen chart data
  table_data   jsonb,                         -- frozen table rows
  unique (analysis_id, key)
);

create table if not exists public.analysis_evidence (
  id           bigint generated always as identity primary key,
  analysis_id  uuid not null references public.analyses(id) on delete cascade,
  section_key  text not null,
  claim        text not null,
  basis        text not null check (basis in ('data','inference','external')),
  refs         jsonb,                         -- [{table, key, field, value}]
  method       text,                          -- plain-language how the number was made
  value        numeric,                       -- the number claimed (data)
  tolerance    numeric default 0.01,          -- relative rounding tolerance
  recompute    jsonb,                         -- machine recipe for verify_analysis.py
  reasoning    text,
  confidence   text check (confidence in ('high','medium','low')),
  source_url   text,
  verified     boolean,
  verified_at  timestamptz,
  verify_note  text,
  constraint data_needs_refs      check (basis <> 'data'      or (refs is not null and method is not null)),
  constraint inference_needs_why  check (basis <> 'inference' or (reasoning is not null and confidence is not null)),
  constraint external_needs_url   check (basis <> 'external'  or source_url is not null)
);
create index if not exists analysis_evidence_analysis_idx on public.analysis_evidence (analysis_id);

create table if not exists public.analysis_actions (
  id           bigint generated always as identity primary key,
  analysis_id  uuid not null references public.analyses(id) on delete cascade,
  ord          int not null,
  kind         text not null check (kind in ('prompt','manual')),
  text         text not null,
  unique (analysis_id, ord)
);

-- ========== 3. Lock down: RLS on every table, owner-only read, nothing for anon ==========
do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
    execute format('grant select on public.%I to authenticated', t);
    execute format('drop policy if exists owner_read on public.%I', t);
    execute format($p$create policy owner_read on public.%I for select to authenticated
                     using (auth.uid() = '46430da4-5073-4b08-aaaa-a41ecb1e648d'::uuid)$p$, t);
  end loop;
end $$;

-- Views run with the caller's rights, so RLS of the base tables applies.
do $$
declare v text;
begin
  for v in select viewname from pg_views where schemaname = 'public' loop
    execute format('alter view public.%I set (security_invoker = true)', v);
    execute format('revoke all on public.%I from anon, authenticated', v);
    execute format('grant select on public.%I to authenticated', v);
  end loop;
end $$;

-- Lease / helper functions: agents only (service role), never the website.
do $$
declare f regprocedure;
begin
  for f in select p.oid::regprocedure from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'public' and p.proname in ('acquire_lease','release_lease','touch_reel') loop
    execute format('revoke execute on function %s from public, anon, authenticated', f);
    execute format('grant execute on function %s to service_role', f);
  end loop;
end $$;

-- New tables created later must not be readable by default.
alter default privileges in schema public revoke all on tables from anon, authenticated;

-- ========== 4. Realtime for the analyses feed (RLS applies to realtime too) ==========
do $$ begin
  alter publication supabase_realtime add table public.analyses;
exception when duplicate_object then null; end $$;

commit;

-- ========== Check after running (should list every table with rls = true) ==========
select c.relname, c.relrowsecurity as rls,
       has_table_privilege('anon', c.oid, 'select') as anon_can_select
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r','v') order by 1;
