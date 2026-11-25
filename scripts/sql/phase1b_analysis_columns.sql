-- PHASE 1b: the analysis tables already existed with another design, so the
-- phase-1 CREATE TABLEs were skipped. This only ADDS columns and rules; it
-- drops nothing. Safe to re-run.
begin;

alter table public.analyses
  add column if not exists subject          text not null default '',
  add column if not exists backfilled       boolean not null default false,
  add column if not exists data_claims      int not null default 0,
  add column if not exists verified_claims  int not null default 0,
  add column if not exists failed_claims    int not null default 0,
  add column if not exists verified_at      timestamptz;

alter table public.analysis_evidence
  add column if not exists value        numeric,
  add column if not exists tolerance    numeric default 0.01,
  add column if not exists recompute    jsonb,
  add column if not exists reasoning    text,
  add column if not exists verify_note  text;

-- Proof rules, enforced by the database
alter table public.analysis_evidence drop constraint if exists basis_values;
alter table public.analysis_evidence add constraint basis_values check (basis in ('data','inference','external'));
alter table public.analysis_evidence drop constraint if exists data_needs_refs;
alter table public.analysis_evidence add constraint data_needs_refs check (basis <> 'data' or (refs is not null and method is not null));
alter table public.analysis_evidence drop constraint if exists inference_needs_why;
alter table public.analysis_evidence add constraint inference_needs_why check (basis <> 'inference' or (reasoning is not null and confidence is not null));
alter table public.analysis_evidence drop constraint if exists external_needs_url;
alter table public.analysis_evidence add constraint external_needs_url check (basis <> 'external' or source_url is not null);

-- One frozen analysis per hunt / subject
create unique index if not exists analyses_one_per_subject
  on public.analyses (kind, coalesce(hunt_id, '00000000-0000-0000-0000-000000000000'::uuid), subject);
create index if not exists analysis_sections_analysis_idx on public.analysis_sections (analysis_id, position);
create index if not exists analysis_evidence_analysis_idx on public.analysis_evidence (analysis_id);
create index if not exists analysis_actions_analysis_idx  on public.analysis_actions (analysis_id, position);

commit;

-- Check: should list the new columns
select table_name, column_name from information_schema.columns
where table_schema = 'public' and table_name like 'analys%'
  and column_name in ('subject','backfilled','data_claims','verified_claims','failed_claims','value','recompute','reasoning','verify_note')
order by 1, 2;
