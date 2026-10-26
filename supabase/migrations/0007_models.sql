-- SG-14: model registry (plan §12.7). The ticket names this file 0006_models.sql; 0006 is the
-- SG-11 idempotency migration, so the registry is 0007 and SG-15's forecasts become 0008.
--
-- Versions are global (not per department). Supervisors and above in any department can read
-- them; nobody writes directly. The API and `sg ml` write with the service role, and status
-- changes go through activate_model_version / rollback_model_version so the swap of the active
-- row is one transaction. Every change is in audit_log.

-- Holds a role in any department (models are global, so there is no department to check).
create function public.has_any_role(roles public.app_role[])
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.memberships m
    where m.user_id = (select auth.uid()) and m.role = any (roles)
  );
$$;
revoke execute on function public.has_any_role(public.app_role[]) from anon, public;

create table public.model_versions (
  id uuid primary key default gen_random_uuid(),
  version text not null unique,
  feature_set text not null check (feature_set in ('full', 'core')),
  artifact_path text not null,
  card jsonb not null,
  metrics jsonb not null,
  training_dataset_ids uuid[] not null,
  data_hash text,
  code_sha text,
  gates_passed boolean not null default false,
  status text not null default 'candidate'
    check (status in ('candidate', 'active', 'retired', 'rejected')),
  created_at timestamptz not null default now(),
  activated_at timestamptz,
  activated_by uuid references auth.users (id) on delete set null
);
comment on table public.model_versions is
  'Model registry (SG-14). Version format YYYYMMDD-HHMM-<short git sha>.';

-- Only one active version per feature set.
create unique index model_versions_one_active_idx
  on public.model_versions (feature_set) where status = 'active';
create index model_versions_feature_set_created_idx
  on public.model_versions (feature_set, created_at desc);
create index model_versions_activated_by_idx on public.model_versions (activated_by);

alter table public.model_versions enable row level security;
revoke insert, update, delete, truncate on public.model_versions from anon, authenticated;

create policy model_versions_select on public.model_versions
for select to authenticated
using (
  (select public.is_aal2())
  and (select public.has_any_role(array['supervisor', 'dept_admin', 'platform_admin']::public.app_role[]))
);

create trigger model_versions_audit
after insert or update or delete on public.model_versions
for each row execute function public.audit_row_change();

-- Activate a version: refuses unless gates passed; the previous active version of the same
-- feature set is retired in the same transaction.
create function public.activate_model_version(p_version text, p_actor uuid)
returns public.model_versions
language plpgsql
security definer
set search_path = ''
as $$
declare
  target public.model_versions;
begin
  select * into target from public.model_versions where version = p_version for update;
  if not found then
    raise exception 'model version % not found', p_version using errcode = 'no_data_found';
  end if;
  if not target.gates_passed then
    raise exception 'model version % has not passed its activation gates', p_version
      using errcode = 'check_violation';
  end if;
  if target.status = 'active' then
    return target;
  end if;
  update public.model_versions set status = 'retired'
  where feature_set = target.feature_set and status = 'active';
  update public.model_versions
  set status = 'active', activated_at = now(), activated_by = p_actor
  where id = target.id
  returning * into target;
  return target;
end;
$$;

-- Roll back: re-activate the most recently activated retired version of a feature set.
create function public.rollback_model_version(p_feature_set text, p_actor uuid)
returns public.model_versions
language plpgsql
security definer
set search_path = ''
as $$
declare
  target public.model_versions;
begin
  select * into target from public.model_versions
  where feature_set = p_feature_set and status = 'retired' and gates_passed
  order by activated_at desc nulls last, created_at desc
  limit 1
  for update;
  if not found then
    raise exception 'no retired % version to roll back to', p_feature_set
      using errcode = 'no_data_found';
  end if;
  update public.model_versions set status = 'retired'
  where feature_set = p_feature_set and status = 'active';
  update public.model_versions
  set status = 'active', activated_at = now(), activated_by = p_actor
  where id = target.id
  returning * into target;
  return target;
end;
$$;

revoke execute on function public.activate_model_version(text, uuid) from anon, authenticated, public;
revoke execute on function public.rollback_model_version(text, uuid) from anon, authenticated, public;
grant execute on function public.activate_model_version(text, uuid) to service_role;
grant execute on function public.rollback_model_version(text, uuid) to service_role;

-- Private Storage bucket for artifacts: <version>/artifact.joblib and <version>/model_card.json.
-- Guarded because CI starts Postgres without the storage service (no storage schema).
do $$
begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public)
    values ('models', 'models', false)
    on conflict (id) do nothing;
  end if;
end;
$$;
