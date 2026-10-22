-- SG-08: append-only audit log. Every insert, update and delete on audited tables writes one
-- row with before and after JSON. Nobody can edit or remove audit rows: there are no write
-- policies, write grants are revoked, and a trigger rejects update, delete and truncate even
-- for the table owner.

create table public.audit_log (
  id bigint generated always as identity primary key,
  occurred_at timestamptz not null default now(),
  actor_id uuid,
  actor_role text,
  department_id uuid,
  action text not null check (action in ('insert', 'update', 'delete')),
  entity text not null,
  entity_id text,
  before jsonb,
  after jsonb,
  request_id text,
  ip_hash text
);
create index audit_log_department_occurred_idx on public.audit_log (department_id, occurred_at desc);
create index audit_log_entity_idx on public.audit_log (entity, entity_id);

alter table public.audit_log enable row level security;
revoke all on public.audit_log from anon;
revoke insert, update, delete, truncate on public.audit_log from authenticated, service_role;

create policy audit_log_select on public.audit_log
for select to authenticated
using (
  (select public.is_aal2()) and (
    (select public.is_platform_admin())
    or (department_id is not null
        and public.has_role(department_id, array['dept_admin']::public.app_role[]))
  )
);

create function public.audit_log_immutable()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'audit_log is append-only (% blocked)', lower(tg_op)
    using errcode = 'insufficient_privilege';
end;
$$;
revoke execute on function public.audit_log_immutable() from anon, authenticated, public;

create trigger audit_log_no_update_delete
before update or delete on public.audit_log
for each row execute function public.audit_log_immutable();
create trigger audit_log_no_truncate
before truncate on public.audit_log
for each statement execute function public.audit_log_immutable();

create function public.audit_row_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  old_row jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end;
  new_row jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end;
  row_data jsonb := coalesce(new_row, old_row);
  claims jsonb := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
  headers jsonb := nullif(current_setting('request.headers', true), '')::jsonb;
  dept uuid;
  ent_id text;
begin
  dept := case
    when tg_table_name = 'departments' then (row_data ->> 'id')::uuid
    else (row_data ->> 'department_id')::uuid
  end;
  ent_id := coalesce(
    row_data ->> 'id',
    concat_ws(':', row_data ->> 'user_id', row_data ->> 'department_id', row_data ->> 'role')
  );

  insert into public.audit_log
    (actor_id, actor_role, department_id, action, entity, entity_id, before, after, request_id)
  values (
    (select auth.uid()),
    claims ->> 'role',
    dept,
    lower(tg_op),
    tg_table_name,
    ent_id,
    old_row,
    new_row,
    headers ->> 'x-request-id'
  );
  return null;
end;
$$;
revoke execute on function public.audit_row_change() from anon, authenticated, public;

create trigger shift_plans_audit
after insert or update or delete on public.shift_plans
for each row execute function public.audit_row_change();
create trigger shift_actuals_audit
after insert or update or delete on public.shift_actuals
for each row execute function public.audit_row_change();
create trigger memberships_audit
after insert or update or delete on public.memberships
for each row execute function public.audit_row_change();
create trigger invites_audit
after insert or update or delete on public.invites
for each row execute function public.audit_row_change();
create trigger departments_audit
after insert or update or delete on public.departments
for each row execute function public.audit_row_change();
create trigger datasets_audit
after insert or update or delete on public.datasets
for each row execute function public.audit_row_change();
