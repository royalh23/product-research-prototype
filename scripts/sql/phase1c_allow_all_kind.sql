-- PHASE 1c: allow the "all hunts together" roll-up (kind = 'all').
-- The existing check only allows hunt / check / track / weekly. Safe to re-run.
do $$
declare c text;
begin
  for c in select conname from pg_constraint
           where conrelid = 'public.analyses'::regclass and contype = 'c'
             and pg_get_constraintdef(oid) ilike '%kind%' loop
    execute format('alter table public.analyses drop constraint %I', c);
  end loop;
end $$;
alter table public.analyses add constraint analyses_kind_check
  check (kind in ('hunt','check','track','weekly','all'));
