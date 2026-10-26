-- SG-12: full RLS permission matrix (plan §2.2, §15.1).
-- Every table x {select, insert, update, delete} x {each department-A role, a department-B
-- technician, an aal1 user, anon}. Expected results live in the `rules` table below: each
-- (table, operation) lists the actors that are allowed, and every other actor must be denied.
-- Each attempt runs in its own subtransaction that is always rolled back, so attempts never
-- affect one another. Every later DB ticket must add its tables here.
begin;
create extension if not exists pgtap with schema extensions;

-- ---------------------------------------------------------------------------
-- Fixtures: org A (department A) and a separate org B (department B)
-- ---------------------------------------------------------------------------
insert into public.organizations (id, name) values
  ('40000000-0000-4000-8000-000000000001', 'Matrix Org A'),
  ('40000000-0000-4000-8000-000000000011', 'Matrix Org B');
insert into public.facilities (id, organization_id, name) values
  ('40000000-0000-4000-8000-000000000002', '40000000-0000-4000-8000-000000000001', 'Fac A'),
  ('40000000-0000-4000-8000-000000000012', '40000000-0000-4000-8000-000000000011', 'Fac B');
insert into public.departments (id, facility_id, name, slug) values
  ('40000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-000000000002', 'Dept A', 'mx-dept-a'),
  ('40000000-0000-4000-8000-00000000000b', '40000000-0000-4000-8000-000000000012', 'Dept B', 'mx-dept-b');

insert into auth.users (id, email, aud, role) values
  ('40000000-0000-4000-8000-0000000000a1', 'mx-tech-a@example.test', 'authenticated', 'authenticated'),
  ('40000000-0000-4000-8000-0000000000a2', 'mx-sup-a@example.test', 'authenticated', 'authenticated'),
  ('40000000-0000-4000-8000-0000000000a3', 'mx-admin-a@example.test', 'authenticated', 'authenticated'),
  ('40000000-0000-4000-8000-0000000000a4', 'mx-steward-a@example.test', 'authenticated', 'authenticated'),
  ('40000000-0000-4000-8000-0000000000a5', 'mx-platform@example.test', 'authenticated', 'authenticated'),
  ('40000000-0000-4000-8000-0000000000a6', 'mx-aal1@example.test', 'authenticated', 'authenticated'),
  ('40000000-0000-4000-8000-0000000000b1', 'mx-tech-b@example.test', 'authenticated', 'authenticated'),
  ('40000000-0000-4000-8000-0000000000c1', 'mx-spare@example.test', 'authenticated', 'authenticated');

-- The platform admin's membership is in department B, so their access to A comes only from
-- is_platform_admin(). The aal1 user is a dept_admin of A who has not completed two-factor.
insert into public.memberships (user_id, department_id, role) values
  ('40000000-0000-4000-8000-0000000000a1', '40000000-0000-4000-8000-00000000000a', 'technician'),
  ('40000000-0000-4000-8000-0000000000a2', '40000000-0000-4000-8000-00000000000a', 'supervisor'),
  ('40000000-0000-4000-8000-0000000000a3', '40000000-0000-4000-8000-00000000000a', 'dept_admin'),
  ('40000000-0000-4000-8000-0000000000a4', '40000000-0000-4000-8000-00000000000a', 'data_steward'),
  ('40000000-0000-4000-8000-0000000000a5', '40000000-0000-4000-8000-00000000000b', 'platform_admin'),
  ('40000000-0000-4000-8000-0000000000a6', '40000000-0000-4000-8000-00000000000a', 'dept_admin'),
  ('40000000-0000-4000-8000-0000000000b1', '40000000-0000-4000-8000-00000000000b', 'technician');

insert into public.invites (id, email, department_id, role, invited_by) values
  ('40000000-0000-4000-8000-0000000000e1', 'mx-invitee@example.test',
   '40000000-0000-4000-8000-00000000000a', 'technician', '40000000-0000-4000-8000-0000000000a3');
insert into public.datasets (id, department_id, source, name, row_count, content_hash) values
  ('40000000-0000-4000-8000-0000000000f3', '40000000-0000-4000-8000-00000000000a',
   'simulated', 'mx', 1, 'hash');
insert into public.shift_plans (id, department_id, plan_date, regular_patients, morning_staff_present, source)
values ('40000000-0000-4000-8000-0000000000f1', '40000000-0000-4000-8000-00000000000a',
        '2026-11-02', 300, 3, 'real');
insert into public.shift_actuals (id, department_id, shift_date, ot_labor_hours, source, created_by)
values ('40000000-0000-4000-8000-0000000000f2', '40000000-0000-4000-8000-00000000000a',
        '2026-11-02', 4.5, 'real', '40000000-0000-4000-8000-0000000000a1');
insert into public.idempotency_keys (user_id, key, method, path, body_hash, status, response)
values ('40000000-0000-4000-8000-0000000000a1', 'mx-key-1', 'PUT', '/v1/plans/x', 'h', 200, '{}');
insert into public.model_versions (id, version, feature_set, artifact_path, card, metrics, training_dataset_ids)
values ('40000000-0000-4000-8000-0000000000d1', 'mx-20261026-0000-abc1234', 'full', 'mx/artifact.joblib',
        '{}', '{}', array['40000000-0000-4000-8000-0000000000f3']::uuid[]);

-- ---------------------------------------------------------------------------
-- Actors and rules
-- ---------------------------------------------------------------------------
create temp table actors (actor text primary key, claims text, db_role text);
insert into actors values
  ('tech_a', '{"sub":"40000000-0000-4000-8000-0000000000a1","role":"authenticated","aal":"aal2"}', 'authenticated'),
  ('sup_a', '{"sub":"40000000-0000-4000-8000-0000000000a2","role":"authenticated","aal":"aal2"}', 'authenticated'),
  ('admin_a', '{"sub":"40000000-0000-4000-8000-0000000000a3","role":"authenticated","aal":"aal2"}', 'authenticated'),
  ('steward_a', '{"sub":"40000000-0000-4000-8000-0000000000a4","role":"authenticated","aal":"aal2"}', 'authenticated'),
  ('platform', '{"sub":"40000000-0000-4000-8000-0000000000a5","role":"authenticated","aal":"aal2"}', 'authenticated'),
  ('aal1_a', '{"sub":"40000000-0000-4000-8000-0000000000a6","role":"authenticated","aal":"aal1"}', 'authenticated'),
  ('tech_b', '{"sub":"40000000-0000-4000-8000-0000000000b1","role":"authenticated","aal":"aal2"}', 'authenticated'),
  ('anon', '{"role":"anon"}', 'anon');

-- stmt returns the number of department-A target rows the actor could read or change.
create temp table rules (tbl text, op text, stmt text, allowed text[]);
insert into rules values
  -- organizations: visible through a department you belong to; platform admin manages
  ('organizations', 'select', $q$select count(*) from public.organizations where id = '40000000-0000-4000-8000-000000000001'$q$,
   array['tech_a','sup_a','admin_a','steward_a','platform']),
  ('organizations', 'insert', $q$with t as (insert into public.organizations (name) values ('mx-new') returning 1) select count(*) from t$q$,
   array['platform']),
  ('organizations', 'update', $q$with t as (update public.organizations set name = 'mx-upd' where id = '40000000-0000-4000-8000-000000000001' returning 1) select count(*) from t$q$,
   array['platform']),
  ('organizations', 'delete', $q$with t as (delete from public.organizations where id = '40000000-0000-4000-8000-000000000001' returning 1) select count(*) from t$q$,
   array['platform']),
  -- facilities
  ('facilities', 'select', $q$select count(*) from public.facilities where id = '40000000-0000-4000-8000-000000000002'$q$,
   array['tech_a','sup_a','admin_a','steward_a','platform']),
  ('facilities', 'insert', $q$with t as (insert into public.facilities (organization_id, name) values ('40000000-0000-4000-8000-000000000001', 'mx-new') returning 1) select count(*) from t$q$,
   array['platform']),
  ('facilities', 'update', $q$with t as (update public.facilities set name = 'mx-upd' where id = '40000000-0000-4000-8000-000000000002' returning 1) select count(*) from t$q$,
   array['platform']),
  ('facilities', 'delete', $q$with t as (delete from public.facilities where id = '40000000-0000-4000-8000-000000000002' returning 1) select count(*) from t$q$,
   array['platform']),
  -- departments: members read; dept_admin edits settings; platform admin creates and deletes
  ('departments', 'select', $q$select count(*) from public.departments where id = '40000000-0000-4000-8000-00000000000a'$q$,
   array['tech_a','sup_a','admin_a','steward_a','platform']),
  ('departments', 'insert', $q$with t as (insert into public.departments (facility_id, name, slug) values ('40000000-0000-4000-8000-000000000002', 'mx-new', 'mx-new') returning 1) select count(*) from t$q$,
   array['platform']),
  ('departments', 'update', $q$with t as (update public.departments set name = 'mx-upd' where id = '40000000-0000-4000-8000-00000000000a' returning 1) select count(*) from t$q$,
   array['admin_a','platform']),
  ('departments', 'delete', $q$with t as (delete from public.departments where id = '40000000-0000-4000-8000-00000000000a' returning 1) select count(*) from t$q$,
   array['platform']),
  -- profiles: only your own row; rows are created by the auth trigger, never deleted by users
  ('profiles', 'select', $q$select count(*) from public.profiles where user_id = '40000000-0000-4000-8000-0000000000a1'$q$,
   array['tech_a']),
  ('profiles', 'insert', $q$with t as (insert into public.profiles (user_id) values ('40000000-0000-4000-8000-0000000000c1') returning 1) select count(*) from t$q$,
   array[]::text[]),
  ('profiles', 'update', $q$with t as (update public.profiles set theme = 'dark' where user_id = '40000000-0000-4000-8000-0000000000a1' returning 1) select count(*) from t$q$,
   array['tech_a']),
  ('profiles', 'delete', $q$with t as (delete from public.profiles where user_id = '40000000-0000-4000-8000-0000000000a1' returning 1) select count(*) from t$q$,
   array[]::text[]),
  -- memberships: own rows readable; dept_admin and platform admin manage
  ('memberships', 'select', $q$select count(*) from public.memberships where user_id = '40000000-0000-4000-8000-0000000000a1' and department_id = '40000000-0000-4000-8000-00000000000a'$q$,
   array['tech_a','admin_a','platform']),
  ('memberships', 'insert', $q$with t as (insert into public.memberships (user_id, department_id, role) values ('40000000-0000-4000-8000-0000000000c1', '40000000-0000-4000-8000-00000000000a', 'technician') returning 1) select count(*) from t$q$,
   array['admin_a','platform']),
  ('memberships', 'update', $q$with t as (update public.memberships set role = 'supervisor' where user_id = '40000000-0000-4000-8000-0000000000a1' and department_id = '40000000-0000-4000-8000-00000000000a' returning 1) select count(*) from t$q$,
   array['admin_a','platform']),
  ('memberships', 'delete', $q$with t as (delete from public.memberships where user_id = '40000000-0000-4000-8000-0000000000a1' and department_id = '40000000-0000-4000-8000-00000000000a' returning 1) select count(*) from t$q$,
   array['admin_a','platform']),
  -- invites: dept_admin and platform admin; never deleted (revoked instead)
  ('invites', 'select', $q$select count(*) from public.invites where id = '40000000-0000-4000-8000-0000000000e1'$q$,
   array['admin_a','platform']),
  ('invites', 'insert', $q$with t as (insert into public.invites (email, department_id, role, invited_by) values ('mx-new@example.test', '40000000-0000-4000-8000-00000000000a', 'technician', (select auth.uid())) returning 1) select count(*) from t$q$,
   array['admin_a','platform']),
  ('invites', 'update', $q$with t as (update public.invites set revoked_at = now() where id = '40000000-0000-4000-8000-0000000000e1' returning 1) select count(*) from t$q$,
   array['admin_a','platform']),
  ('invites', 'delete', $q$with t as (delete from public.invites where id = '40000000-0000-4000-8000-0000000000e1' returning 1) select count(*) from t$q$,
   array[]::text[]),
  -- shift_plans: members read; supervisor and dept_admin write; no deletes
  ('shift_plans', 'select', $q$select count(*) from public.shift_plans where id = '40000000-0000-4000-8000-0000000000f1'$q$,
   array['tech_a','sup_a','admin_a','steward_a','platform']),
  ('shift_plans', 'insert', $q$with t as (insert into public.shift_plans (department_id, plan_date, regular_patients, morning_staff_present, source) values ('40000000-0000-4000-8000-00000000000a', '2026-11-03', 300, 3, 'real') returning 1) select count(*) from t$q$,
   array['sup_a','admin_a']),
  ('shift_plans', 'update', $q$with t as (update public.shift_plans set regular_patients = 310 where id = '40000000-0000-4000-8000-0000000000f1' returning 1) select count(*) from t$q$,
   array['sup_a','admin_a']),
  ('shift_plans', 'delete', $q$with t as (delete from public.shift_plans where id = '40000000-0000-4000-8000-0000000000f1' returning 1) select count(*) from t$q$,
   array[]::text[]),
  -- shift_actuals: technician and above file their own; edit rules by role and approval
  ('shift_actuals', 'select', $q$select count(*) from public.shift_actuals where id = '40000000-0000-4000-8000-0000000000f2'$q$,
   array['tech_a','sup_a','admin_a','steward_a','platform']),
  ('shift_actuals', 'insert', $q$with t as (insert into public.shift_actuals (department_id, shift_date, ot_labor_hours, source, created_by) values ('40000000-0000-4000-8000-00000000000a', '2026-11-03', 2.0, 'real', (select auth.uid())) returning 1) select count(*) from t$q$,
   array['tech_a','sup_a','admin_a']),
  ('shift_actuals', 'update', $q$with t as (update public.shift_actuals set ot_labor_hours = 3 where id = '40000000-0000-4000-8000-0000000000f2' returning 1) select count(*) from t$q$,
   array['tech_a','sup_a','admin_a']),
  ('shift_actuals', 'delete', $q$with t as (delete from public.shift_actuals where id = '40000000-0000-4000-8000-0000000000f2' returning 1) select count(*) from t$q$,
   array[]::text[]),
  -- datasets: members read; data_steward and dept_admin register; immutable afterwards
  ('datasets', 'select', $q$select count(*) from public.datasets where id = '40000000-0000-4000-8000-0000000000f3'$q$,
   array['tech_a','sup_a','admin_a','steward_a','platform']),
  ('datasets', 'insert', $q$with t as (insert into public.datasets (department_id, source, name, row_count, content_hash, created_by) values ('40000000-0000-4000-8000-00000000000a', 'simulated', 'mx-new', 1, 'h', (select auth.uid())) returning 1) select count(*) from t$q$,
   array['admin_a','steward_a']),
  ('datasets', 'update', $q$with t as (update public.datasets set name = 'mx-upd' where id = '40000000-0000-4000-8000-0000000000f3' returning 1) select count(*) from t$q$,
   array[]::text[]),
  ('datasets', 'delete', $q$with t as (delete from public.datasets where id = '40000000-0000-4000-8000-0000000000f3' returning 1) select count(*) from t$q$,
   array[]::text[]),
  -- audit_log: dept_admin and platform admin read; nobody writes, edits or deletes
  ('audit_log', 'select', $q$select count(*) from public.audit_log where department_id = '40000000-0000-4000-8000-00000000000a'$q$,
   array['admin_a','platform']),
  ('audit_log', 'insert', $q$with t as (insert into public.audit_log (action, entity) values ('insert', 'mx') returning 1) select count(*) from t$q$,
   array[]::text[]),
  ('audit_log', 'update', $q$with t as (update public.audit_log set entity = 'mx' where department_id = '40000000-0000-4000-8000-00000000000a' returning 1) select count(*) from t$q$,
   array[]::text[]),
  ('audit_log', 'delete', $q$with t as (delete from public.audit_log where department_id = '40000000-0000-4000-8000-00000000000a' returning 1) select count(*) from t$q$,
   array[]::text[]),
  -- idempotency_keys: each aal2 user reads and writes only their own keys
  ('idempotency_keys', 'select', $q$select count(*) from public.idempotency_keys where user_id = '40000000-0000-4000-8000-0000000000a1' and key = 'mx-key-1'$q$,
   array['tech_a']),
  ('idempotency_keys', 'insert', $q$with t as (insert into public.idempotency_keys (user_id, key, method, path, body_hash, status, response) values ((select auth.uid()), 'mx-key-2', 'PUT', '/p', 'h', 200, '{}') returning 1) select count(*) from t$q$,
   array['tech_a','sup_a','admin_a','steward_a','platform','tech_b']),
  ('idempotency_keys', 'update', $q$with t as (update public.idempotency_keys set status = 201 where user_id = '40000000-0000-4000-8000-0000000000a1' and key = 'mx-key-1' returning 1) select count(*) from t$q$,
   array['tech_a']),
  ('idempotency_keys', 'delete', $q$with t as (delete from public.idempotency_keys where user_id = '40000000-0000-4000-8000-0000000000a1' returning 1) select count(*) from t$q$,
   array[]::text[]),
  -- model_versions (SG-14): global; supervisor and above in any department read; no direct writes
  ('model_versions', 'select', $q$select count(*) from public.model_versions where id = '40000000-0000-4000-8000-0000000000d1'$q$,
   array['sup_a','admin_a','platform']),
  ('model_versions', 'insert', $q$with t as (insert into public.model_versions (version, feature_set, artifact_path, card, metrics, training_dataset_ids) values ('mx-new', 'full', 'p', '{}', '{}', '{}') returning 1) select count(*) from t$q$,
   array[]::text[]),
  ('model_versions', 'update', $q$with t as (update public.model_versions set status = 'rejected' where id = '40000000-0000-4000-8000-0000000000d1' returning 1) select count(*) from t$q$,
   array[]::text[]),
  ('model_versions', 'delete', $q$with t as (delete from public.model_versions where id = '40000000-0000-4000-8000-0000000000d1' returning 1) select count(*) from t$q$,
   array[]::text[]);

create temp table matrix as
select r.tbl, r.op, a.actor, r.stmt, a.claims, a.db_role, a.actor = any (r.allowed) as expected
from rules r cross join actors a;

-- Run one statement as an actor. The block always raises, so its effects (and the role
-- switch) roll back; the row count travels out in the error message.
create function pg_temp.sgt_try(stmt text, claims text, db_role text)
returns boolean
language plpgsql
as $fn$
declare
  n integer;
begin
  begin
    perform set_config('request.jwt.claims', claims, true);
    execute format('set local role %I', db_role);
    execute stmt into n;
    raise exception using errcode = 'P0001', message = 'SGT:' || coalesce(n, 0);
  exception
    when sqlstate 'P0001' then
      if sqlerrm like 'SGT:%' then
        return substr(sqlerrm, 5)::integer > 0;
      end if;
      return false;
    when others then
      return false;
  end;
end;
$fn$;

-- Audited tables, for the exactly-one-audit-row checks below.
create temp table audited (tbl text, ins text, upd text, del text);
insert into audited values
  ('memberships',
   $q$insert into public.memberships (user_id, department_id, role) values ('40000000-0000-4000-8000-0000000000c1', '40000000-0000-4000-8000-00000000000a', 'supervisor')$q$,
   $q$update public.memberships set role = 'technician' where user_id = '40000000-0000-4000-8000-0000000000c1' and role = 'supervisor'$q$,
   $q$delete from public.memberships where user_id = '40000000-0000-4000-8000-0000000000c1'$q$),
  ('invites',
   $q$insert into public.invites (id, email, department_id, role, invited_by) values ('40000000-0000-4000-8000-0000000000e2', 'mx-audit@example.test', '40000000-0000-4000-8000-00000000000a', 'technician', '40000000-0000-4000-8000-0000000000a3')$q$,
   $q$update public.invites set revoked_at = now() where id = '40000000-0000-4000-8000-0000000000e2'$q$,
   $q$delete from public.invites where id = '40000000-0000-4000-8000-0000000000e2'$q$),
  ('departments',
   $q$insert into public.departments (id, facility_id, name, slug) values ('40000000-0000-4000-8000-00000000000c', '40000000-0000-4000-8000-000000000002', 'Dept C', 'mx-dept-c')$q$,
   $q$update public.departments set name = 'Dept C2' where id = '40000000-0000-4000-8000-00000000000c'$q$,
   $q$delete from public.departments where id = '40000000-0000-4000-8000-00000000000c'$q$),
  ('datasets',
   $q$insert into public.datasets (id, department_id, source, name, row_count, content_hash) values ('40000000-0000-4000-8000-0000000000f4', '40000000-0000-4000-8000-00000000000a', 'simulated', 'mx2', 1, 'h')$q$,
   $q$update public.datasets set name = 'mx3' where id = '40000000-0000-4000-8000-0000000000f4'$q$,
   $q$delete from public.datasets where id = '40000000-0000-4000-8000-0000000000f4'$q$),
  ('shift_plans',
   $q$insert into public.shift_plans (id, department_id, plan_date, regular_patients, morning_staff_present, source) values ('40000000-0000-4000-8000-0000000000f5', '40000000-0000-4000-8000-00000000000a', '2026-11-04', 300, 3, 'real')$q$,
   $q$update public.shift_plans set regular_patients = 301 where id = '40000000-0000-4000-8000-0000000000f5'$q$,
   $q$delete from public.shift_plans where id = '40000000-0000-4000-8000-0000000000f5'$q$),
  ('shift_actuals',
   $q$insert into public.shift_actuals (id, department_id, shift_date, ot_labor_hours, source) values ('40000000-0000-4000-8000-0000000000f6', '40000000-0000-4000-8000-00000000000a', '2026-11-04', 1, 'real')$q$,
   $q$update public.shift_actuals set ot_labor_hours = 2 where id = '40000000-0000-4000-8000-0000000000f6'$q$,
   $q$delete from public.shift_actuals where id = '40000000-0000-4000-8000-0000000000f6'$q$),
  ('model_versions',
   $q$insert into public.model_versions (id, version, feature_set, artifact_path, card, metrics, training_dataset_ids) values ('40000000-0000-4000-8000-0000000000d2', 'mx-audit', 'core', 'p', '{}', '{}', '{}')$q$,
   $q$update public.model_versions set status = 'rejected' where id = '40000000-0000-4000-8000-0000000000d2'$q$,
   $q$delete from public.model_versions where id = '40000000-0000-4000-8000-0000000000d2'$q$);

-- One audit row per change, with the right before/after shape.
create function pg_temp.sgt_audit_delta(stmt text, tbl text, act text)
returns text
language plpgsql
as $fn$
declare
  before_n integer;
  after_n integer;
  shape_ok boolean;
begin
  select count(*) into before_n from public.audit_log where entity = tbl and action = act;
  execute stmt;
  select count(*) into after_n from public.audit_log where entity = tbl and action = act;
  select case act
           when 'insert' then before is null and after is not null
           when 'update' then before is not null and after is not null and before <> after
           else before is not null and after is null
         end
    into shape_ok
  from public.audit_log where entity = tbl and action = act order by id desc limit 1;
  return (after_n - before_n)::text || ':' || coalesce(shape_ok, false)::text;
end;
$fn$;

-- Tables that must appear in the matrix: every table in public.
create temp table covered as select distinct tbl from rules;

select plan(
  (select count(*)::integer from matrix)
  + (select count(*)::integer from audited) * 3
  + 5
);

select is(pg_temp.sgt_try(stmt, claims, db_role), expected,
          format('%s %s by %s should be %s', tbl, op, actor, case when expected then 'allowed' else 'denied' end))
from matrix
order by tbl, op, actor;

select is(pg_temp.sgt_audit_delta(ins, tbl, 'insert'), '1:true', tbl || ' insert writes one audit row')
from audited order by tbl;
select is(pg_temp.sgt_audit_delta(upd, tbl, 'update'), '1:true', tbl || ' update writes one audit row')
from audited order by tbl;
select is(pg_temp.sgt_audit_delta(del, tbl, 'delete'), '1:true', tbl || ' delete writes one audit row')
from audited order by tbl;

-- Coverage and helpers
select is(
  (select array_agg(c.relname::text order by c.relname)
   from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind = 'r'
     and c.relname::text not in (select tbl from covered)),
  null::text[],
  'every table in public is covered by the RLS matrix'
);
select is(
  (select count(*)::integer from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity),
  0, 'RLS is enabled on every public table'
);
select is(
  (select count(*)::integer from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.prosecdef
     and not coalesce(p.proconfig @> array['search_path=""'], false)),
  0, 'every security definer function has an empty search_path'
);
select is(
  (select count(*)::integer from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.prosecdef and has_function_privilege('anon', p.oid, 'execute')),
  0, 'anon cannot execute any security definer function'
);
select throws_ok($$update public.audit_log set entity = 'mx'$$, '42501', null,
  'audit rows cannot be updated even by the table owner');

select * from finish();
rollback;
