-- SG-15: forecasts and their SHAP drivers (plan §6.2, §7.2, §12). The ticket names this file
-- 0007_forecasts.sql; 0007 is the SG-14 model registry, so forecasts are 0008.
--
-- Members of a department read its forecasts; supervisors and department admins create them
-- through the API with their own token (RLS applies). The evening job (SG-30) uses the service
-- role. Forecasts are never edited or deleted by users: a recompute adds a new row.

create table public.forecasts (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references public.departments (id) on delete cascade,
  target_date date not null,
  plan_id uuid references public.shift_plans (id) on delete set null,
  model_version text not null,
  feature_set text not null check (feature_set in ('full', 'core')),
  ot_p10 numeric(5, 2),
  ot_p50 numeric(5, 2),
  ot_p90 numeric(5, 2),
  burden_class text check (burden_class in ('low', 'moderate', 'high')),
  burden_probs jsonb,
  thresholds jsonb,
  trigger text not null check (trigger in ('manual', 'scheduled', 'scenario')),
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  check (ot_p10 <= ot_p50 and ot_p50 <= ot_p90)
);
comment on table public.forecasts is
  'Next-day overtime forecasts (SG-15). Model estimate, not a guarantee.';

create index forecasts_department_target_created_idx
  on public.forecasts (department_id, target_date desc, created_at desc);
create index forecasts_plan_id_idx on public.forecasts (plan_id);
create index forecasts_created_by_idx on public.forecasts (created_by);

create table public.forecast_drivers (
  forecast_id uuid not null references public.forecasts (id) on delete cascade,
  rank int not null check (rank between 1 and 20),
  feature text not null,
  value text,
  contribution_hours numeric(6, 3) not null,
  text_key text not null,
  text_params jsonb not null default '{}',
  default_text text not null,
  primary key (forecast_id, rank)
);

alter table public.forecasts enable row level security;
alter table public.forecast_drivers enable row level security;
revoke update, delete, truncate on public.forecasts from anon, authenticated;
revoke update, delete, truncate on public.forecast_drivers from anon, authenticated;

create policy forecasts_select on public.forecasts
for select to authenticated
using (
  (select public.is_aal2())
  and (public.is_member(department_id) or (select public.is_platform_admin()))
);

create policy forecasts_insert on public.forecasts
for insert to authenticated
with check (
  (select public.is_aal2())
  and public.has_role(department_id, array['supervisor', 'dept_admin']::public.app_role[])
  and created_by = (select auth.uid())
);

create policy forecast_drivers_select on public.forecast_drivers
for select to authenticated
using (
  (select public.is_aal2())
  and exists (
    select 1 from public.forecasts f
    where f.id = forecast_id
      and (public.is_member(f.department_id) or (select public.is_platform_admin()))
  )
);

create policy forecast_drivers_insert on public.forecast_drivers
for insert to authenticated
with check (
  (select public.is_aal2())
  and exists (
    select 1 from public.forecasts f
    where f.id = forecast_id
      and f.created_by = (select auth.uid())
      and public.has_role(f.department_id, array['supervisor', 'dept_admin']::public.app_role[])
  )
);

create trigger forecasts_audit
after insert or update or delete on public.forecasts
for each row execute function public.audit_row_change();
