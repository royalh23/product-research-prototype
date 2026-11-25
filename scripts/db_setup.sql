-- Run once in Supabase > SQL Editor. Safe to re-run.
-- 1) The service key currently gets "permission denied" on every table.
grant usage on schema public to service_role;
grant all on all tables in schema public to service_role;
grant all on all sequences in schema public to service_role;
grant execute on all functions in schema public to service_role;
alter default privileges in schema public grant all on tables to service_role;
alter default privileges in schema public grant all on sequences to service_role;

-- 2) Natural keys so every write is an upsert (two runs never duplicate).
create unique index if not exists products_name_key_uq   on public.products (name_key);
create unique index if not exists reel_metrics_uq        on public.reel_metrics (reel_code, captured_at);
create unique index if not exists shop_checks_uq         on public.shop_checks (product_id, captured_at);
create unique index if not exists ad_checks_uq           on public.ad_checks (product_id, captured_at);
create unique index if not exists own_snapshots_uq       on public.own_snapshots (handle, captured_at);
create unique index if not exists results_log_uq         on public.results_log (logged_on, product_id, handle);

-- 3) Repeat counter for /hunt (bumps times_seen without a read).
create or replace function public.touch_reel(p_code text) returns void
language sql as $$
  update public.reels set times_seen = times_seen + 1, last_seen_at = now()
  where reel_code = p_code;
$$;
grant execute on function public.touch_reel(text) to service_role;
