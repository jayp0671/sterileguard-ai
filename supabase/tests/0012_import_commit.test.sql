-- SG-24 / ADR-0010: the steward commit function. Who may call it is also in the RLS matrix
-- (0010); this file checks what a commit writes: forced fields, payload fields that are
-- ignored, skipped days, one commit per job and per file, and the audit trail.
begin;
create extension if not exists pgtap with schema extensions;

select plan(16);

insert into public.organizations (id, name) values ('c0000000-0000-4000-8000-000000000001', 'Ic Org');
insert into public.facilities (id, organization_id, name)
values ('c0000000-0000-4000-8000-000000000002', 'c0000000-0000-4000-8000-000000000001', 'Ic Fac');
insert into public.departments (id, facility_id, name, slug) values
  ('c0000000-0000-4000-8000-000000000003', 'c0000000-0000-4000-8000-000000000002', 'Ic Dept', 'ic-dept'),
  ('c0000000-0000-4000-8000-000000000004', 'c0000000-0000-4000-8000-000000000002', 'Ic Other', 'ic-other');
insert into auth.users (id, email, aud, role) values
  ('c0000000-0000-4000-8000-0000000000a1', 'ic-steward@example.test', 'authenticated', 'authenticated'),
  ('c0000000-0000-4000-8000-0000000000a2', 'ic-admin@example.test', 'authenticated', 'authenticated'),
  ('c0000000-0000-4000-8000-0000000000a3', 'ic-tech@example.test', 'authenticated', 'authenticated');
insert into public.memberships (user_id, department_id, role) values
  ('c0000000-0000-4000-8000-0000000000a1', 'c0000000-0000-4000-8000-000000000003', 'data_steward'),
  ('c0000000-0000-4000-8000-0000000000a2', 'c0000000-0000-4000-8000-000000000003', 'dept_admin'),
  ('c0000000-0000-4000-8000-0000000000a3', 'c0000000-0000-4000-8000-000000000003', 'technician');
-- An existing real day (Nov 10) that a non-overwrite commit must skip.
insert into public.shift_plans (department_id, plan_date, regular_patients, morning_staff_present, source)
values ('c0000000-0000-4000-8000-000000000003', '2026-11-10', 250, 3, 'real');
insert into public.import_jobs (id, department_id, original_filename, content_hash, status, created_by) values
  ('c0000000-0000-4000-8000-0000000000b1', 'c0000000-0000-4000-8000-000000000003', 'week.csv', 'hash-1', 'validated', 'c0000000-0000-4000-8000-0000000000a1'),
  ('c0000000-0000-4000-8000-0000000000b2', 'c0000000-0000-4000-8000-000000000003', 'week-copy.csv', 'hash-1', 'validated', 'c0000000-0000-4000-8000-0000000000a1'),
  ('c0000000-0000-4000-8000-0000000000b3', 'c0000000-0000-4000-8000-000000000003', 'other.csv', 'hash-3', 'validated', 'c0000000-0000-4000-8000-0000000000a1');

set local role authenticated;
set local request.jwt.claims = '{"sub":"c0000000-0000-4000-8000-0000000000a3","role":"authenticated","aal":"aal2"}';
select throws_ok(
  $$select public.commit_import('c0000000-0000-4000-8000-0000000000b1', '[]', '[]')$$,
  'P0002', null, 'a technician cannot commit (job reads as not found)'
);

set local request.jwt.claims = '{"sub":"c0000000-0000-4000-8000-0000000000a1","role":"authenticated","aal":"aal1"}';
select throws_ok(
  $$select public.commit_import('c0000000-0000-4000-8000-0000000000b1', '[]', '[]')$$,
  '42501', null, 'aal1 sessions cannot commit'
);

set local request.jwt.claims = '{"sub":"c0000000-0000-4000-8000-0000000000a1","role":"authenticated","aal":"aal2"}';
select throws_ok(
  $$select public.commit_import('c0000000-0000-4000-8000-0000000000b1', '[]', '[]', true)$$,
  '42501', null, 'a data steward cannot overwrite existing days'
);

-- The payload tries to choose another department, source, dataset, status and author: all ignored.
create temp table out1 as
select public.commit_import(
  'c0000000-0000-4000-8000-0000000000b1',
  $j$[
    {"plan_date": "2026-11-09", "regular_patients": 392, "morning_staff_present": 3, "mf_cases": 20,
     "department_id": "c0000000-0000-4000-8000-000000000004", "source": "simulated",
     "status": "draft", "created_by": "c0000000-0000-4000-8000-0000000000a3",
     "id": "c0000000-0000-4000-8000-0000000000ff", "not_a_column": 1},
    {"plan_date": "2026-11-10", "regular_patients": 343, "morning_staff_present": 3}
  ]$j$,
  $j$[
    {"shift_date": "2026-11-09", "ot_labor_hours": 4.5, "status": "draft",
     "approved_by": "c0000000-0000-4000-8000-0000000000a3"},
    {"shift_date": "2026-11-10", "ot_labor_hours": 2.0}
  ]$j$
) as r;

select is((select (r ->> 'plans')::int from out1), 1, 'one new plan (Nov 10 already existed)');
select is((select (r ->> 'actuals')::int from out1), 1, 'one new actual');
select is((select r -> 'skipped_dates' from out1), '["2026-11-10"]'::jsonb, 'the existing day is reported as skipped');

reset role;
select results_eq(
  $$select department_id, source, status, created_by from public.shift_plans where department_id = 'c0000000-0000-4000-8000-000000000003' and plan_date = '2026-11-09'$$,
  $$values ('c0000000-0000-4000-8000-000000000003'::uuid, 'real'::text, 'final'::text, 'c0000000-0000-4000-8000-0000000000a1'::uuid)$$,
  'plan is forced to the job department, real, final and the caller'
);
select isnt(
  (select id from public.shift_plans where department_id = 'c0000000-0000-4000-8000-000000000003' and plan_date = '2026-11-09'),
  'c0000000-0000-4000-8000-0000000000ff'::uuid, 'the payload cannot choose row ids'
);
select results_eq(
  $$select status, approved_by, created_by_role from public.shift_actuals where department_id = 'c0000000-0000-4000-8000-000000000003' and shift_date = '2026-11-09'$$,
  $$values ('approved'::text, 'c0000000-0000-4000-8000-0000000000a1'::uuid, 'data_steward'::text)$$,
  'actual is approved by the caller as data steward'
);
select is(
  (select d.import_job_id from public.datasets d join public.shift_plans p on p.dataset_id = d.id
   where p.department_id = 'c0000000-0000-4000-8000-000000000003' and p.plan_date = '2026-11-09'),
  'c0000000-0000-4000-8000-0000000000b1'::uuid, 'lineage: row -> dataset -> import job'
);
select results_eq(
  $$select status, rows_committed, approved_by from public.import_jobs where id = 'c0000000-0000-4000-8000-0000000000b1'$$,
  $$values ('committed'::text, 1, 'c0000000-0000-4000-8000-0000000000a1'::uuid)$$,
  'the job is committed by the caller'
);
select is(
  (select count(*)::int from public.audit_log
   where actor_id = 'c0000000-0000-4000-8000-0000000000a1'
     and entity in ('datasets', 'shift_plans', 'shift_actuals', 'import_jobs')),
  4, 'dataset, plan, actual and job update are each audited with the steward as actor'
);

set local role authenticated;
set local request.jwt.claims = '{"sub":"c0000000-0000-4000-8000-0000000000a1","role":"authenticated","aal":"aal2"}';
select throws_ok(
  $$select public.commit_import('c0000000-0000-4000-8000-0000000000b1', '[]', '[]')$$,
  '55000', null, 'a job commits only once'
);
select is(
  (select (public.commit_import('c0000000-0000-4000-8000-0000000000b2',
    '[{"plan_date": "2026-11-11", "regular_patients": 300, "morning_staff_present": 3}]', '[]')
    ->> 'already_committed')::boolean),
  true, 'the same file in a second job changes nothing'
);

-- A dept admin may overwrite: Nov 9 gets the new count.
set local request.jwt.claims = '{"sub":"c0000000-0000-4000-8000-0000000000a2","role":"authenticated","aal":"aal2"}';
select is(
  (select (public.commit_import('c0000000-0000-4000-8000-0000000000b3',
    '[{"plan_date": "2026-11-09", "regular_patients": 401, "morning_staff_present": 3}]', '[]', true)
    ->> 'plans')::int),
  1, 'a dept admin overwrites an existing day'
);
reset role;
select is(
  (select regular_patients from public.shift_plans
   where department_id = 'c0000000-0000-4000-8000-000000000003' and plan_date = '2026-11-09' and source = 'real'),
  401, 'the overwrite replaced the value'
);

select * from finish();
rollback;
