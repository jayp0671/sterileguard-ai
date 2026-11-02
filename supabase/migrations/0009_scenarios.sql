-- SG-19: staffing scenario runs (plan §6.2, §12.6). The ticket names this file
-- 0008_scenarios.sql; 0008 is the SG-15 forecasts table, so scenarios are 0009.
--
-- Members of a department read its runs; supervisors and department admins create them through
-- the API with their own token (RLS applies). Applying an option to tomorrow's plan marks the
-- run applied: that is the only edit, limited to the applied_* columns (the ticket lists select
-- and insert only; apply needs this update, see ADR-0008). Runs are never deleted by users.
-- Every recommendation is a model estimate, not a guarantee.

create table public.scenarios (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references public.departments (id) on delete cascade,
  target_date date not null,
  forecast_id uuid references public.forecasts (id) on delete set null,
  model_version text not null,
  request jsonb not null,
  result jsonb not null,
  applied boolean not null default false,
  applied_option_id text,
  applied_at timestamptz,
  applied_by uuid references auth.users (id) on delete set null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  check (applied = (applied_option_id is not null))
);
comment on table public.scenarios is
  'Staffing scenario runs (SG-19). Model estimate, not a guarantee.';

create index scenarios_department_target_created_idx
  on public.scenarios (department_id, target_date desc, created_at desc);
create index scenarios_forecast_id_idx on public.scenarios (forecast_id);
create index scenarios_created_by_idx on public.scenarios (created_by);
create index scenarios_applied_by_idx on public.scenarios (applied_by);

alter table public.scenarios enable row level security;
revoke update, delete, truncate on public.scenarios from anon, authenticated;
grant update (applied, applied_option_id, applied_at, applied_by) on public.scenarios
  to authenticated;

create policy scenarios_select on public.scenarios
for select to authenticated
using (
  (select public.is_aal2())
  and (public.is_member(department_id) or (select public.is_platform_admin()))
);

create policy scenarios_insert on public.scenarios
for insert to authenticated
with check (
  (select public.is_aal2())
  and public.has_role(department_id, array['supervisor', 'dept_admin']::public.app_role[])
  and created_by = (select auth.uid())
  and not applied
);

create policy scenarios_update on public.scenarios
for update to authenticated
using (
  (select public.is_aal2())
  and public.has_role(department_id, array['supervisor', 'dept_admin']::public.app_role[])
)
with check (
  (select public.is_aal2())
  and public.has_role(department_id, array['supervisor', 'dept_admin']::public.app_role[])
  and applied_by = (select auth.uid())
);

-- Audit without the result payload (every option of the grid, about 100 KB): the audit row
-- keeps the request, the chosen option and who applied it.
create function public.audit_scenario_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  old_row jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) - 'result' end;
  new_row jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) - 'result' end;
  row_data jsonb := coalesce(new_row, old_row);
  claims jsonb := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
  headers jsonb := nullif(current_setting('request.headers', true), '')::jsonb;
begin
  insert into public.audit_log
    (actor_id, actor_role, department_id, action, entity, entity_id, before, after, request_id)
  values (
    (select auth.uid()),
    claims ->> 'role',
    (row_data ->> 'department_id')::uuid,
    lower(tg_op),
    tg_table_name,
    row_data ->> 'id',
    old_row,
    new_row,
    headers ->> 'x-request-id'
  );
  return null;
end;
$$;
revoke execute on function public.audit_scenario_change() from anon, authenticated, public;

create trigger scenarios_audit
after insert or update or delete on public.scenarios
for each row execute function public.audit_scenario_change();
