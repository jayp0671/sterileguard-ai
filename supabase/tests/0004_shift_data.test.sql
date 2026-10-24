-- pgTAP for SG-08: shift tables, unique days, audit capture and immutability, core RLS.
-- The full table x operation x actor matrix is SG-12.
begin;
create extension if not exists pgtap with schema extensions;
select plan(23);

select has_table('public', 'datasets', 'datasets exists');
select has_table('public', 'shift_plans', 'shift_plans exists');
select has_table('public', 'shift_actuals', 'shift_actuals exists');
select has_table('public', 'audit_log', 'audit_log exists');
select ok(
  (select p.prosecdef and p.proconfig @> array['search_path=""']
   from pg_proc p where p.oid = 'public.audit_row_change()'::regprocedure),
  'audit_row_change is security definer with an empty search_path'
);
select ok(
  not has_function_privilege('anon', 'public.audit_row_change()', 'execute'),
  'anon cannot run audit_row_change'
);

-- Fixtures: department A with a technician, supervisor and dept_admin
insert into public.organizations (id, name) values ('20000000-0000-4000-8000-000000000001', 'T Org');
insert into public.facilities (id, organization_id, name)
values ('20000000-0000-4000-8000-000000000002', '20000000-0000-4000-8000-000000000001', 'T Fac');
insert into public.departments (id, facility_id, name, slug)
values ('20000000-0000-4000-8000-00000000000a', '20000000-0000-4000-8000-000000000002', 'Dept A', 't8-dept-a');
insert into auth.users (id, email, aud, role) values
  ('20000000-0000-4000-8000-0000000000a1', 'tech@example.test', 'authenticated', 'authenticated'),
  ('20000000-0000-4000-8000-0000000000a2', 'sup@example.test', 'authenticated', 'authenticated'),
  ('20000000-0000-4000-8000-0000000000a3', 'admin@example.test', 'authenticated', 'authenticated');
insert into public.memberships (user_id, department_id, role) values
  ('20000000-0000-4000-8000-0000000000a1', '20000000-0000-4000-8000-00000000000a', 'technician'),
  ('20000000-0000-4000-8000-0000000000a2', '20000000-0000-4000-8000-00000000000a', 'supervisor'),
  ('20000000-0000-4000-8000-0000000000a3', '20000000-0000-4000-8000-00000000000a', 'dept_admin');

-- Unique (department, date, source)
insert into public.shift_plans (id, department_id, plan_date, regular_patients, morning_staff_present, source)
values ('20000000-0000-4000-8000-0000000000f1', '20000000-0000-4000-8000-00000000000a', '2026-10-20', 300, 4, 'real');
select throws_ok(
  $$insert into public.shift_plans (department_id, plan_date, regular_patients, morning_staff_present, source)
    values ('20000000-0000-4000-8000-00000000000a', '2026-10-20', 310, 4, 'real')$$,
  '23505', null, 'a second real plan for the same department and date is rejected'
);
select lives_ok(
  $$insert into public.shift_plans (department_id, plan_date, regular_patients, morning_staff_present, source)
    values ('20000000-0000-4000-8000-00000000000a', '2026-10-20', 310, 4, 'simulated')$$,
  'a simulated plan can share the date with a real one'
);
select throws_ok(
  $$insert into public.shift_plans (department_id, plan_date, regular_patients, morning_staff_present, ot_available_staff, source)
    values ('20000000-0000-4000-8000-00000000000a', '2026-10-21', 300, 3, 4, 'real')$$,
  '23514', null, 'ot_available_staff above morning staff is rejected'
);

-- Audit capture: insert, update, delete each write exactly one row with before/after
select set_config('request.headers', '{"x-request-id":"req-sg08"}', true);
update public.shift_plans set regular_patients = 320 where id = '20000000-0000-4000-8000-0000000000f1';
select is(
  (select count(*)::int from public.audit_log
   where entity = 'shift_plans' and entity_id = '20000000-0000-4000-8000-0000000000f1'),
  2, 'insert and update of one plan wrote two audit rows'
);
select ok(
  (select (before ->> 'regular_patients')::int = 300 and (after ->> 'regular_patients')::int = 320
          and request_id = 'req-sg08'
   from public.audit_log where entity = 'shift_plans' and action = 'update'
     and entity_id = '20000000-0000-4000-8000-0000000000f1'),
  'update audit row has before, after and the request id'
);
delete from public.shift_plans where id = '20000000-0000-4000-8000-0000000000f1';
select ok(
  (select before is not null and after is null from public.audit_log
   where entity = 'shift_plans' and action = 'delete'
     and entity_id = '20000000-0000-4000-8000-0000000000f1'),
  'delete audit row has before and no after'
);
select ok(
  exists (select 1 from public.audit_log where entity = 'memberships' and action = 'insert'
          and department_id = '20000000-0000-4000-8000-00000000000a'),
  'membership changes are audited'
);

-- Immutable even for the owner
select throws_ok($$update public.audit_log set action = 'insert'$$, '42501', null,
  'owner cannot update audit rows');
select throws_ok($$delete from public.audit_log$$, '42501', null, 'owner cannot delete audit rows');

-- Technician: cannot write plans, can file own actuals, cannot touch approved rows, no audit view
set local role authenticated;
set local request.jwt.claims = '{"sub":"20000000-0000-4000-8000-0000000000a1","role":"authenticated","aal":"aal2"}';
select throws_ok(
  $$insert into public.shift_plans (department_id, plan_date, regular_patients, morning_staff_present, source)
    values ('20000000-0000-4000-8000-00000000000a', '2026-10-22', 300, 4, 'real')$$,
  '42501', null, 'technician cannot insert a plan'
);
select lives_ok(
  $$insert into public.shift_actuals (id, department_id, shift_date, ot_labor_hours, source, created_by)
    values ('20000000-0000-4000-8000-0000000000c1', '20000000-0000-4000-8000-00000000000a', '2026-10-20', 4.5, 'real',
            '20000000-0000-4000-8000-0000000000a1')$$,
  'technician can insert their own actual'
);
select is((select count(*)::int from public.audit_log), 0, 'technician sees no audit rows');
select throws_ok($$update public.audit_log set action = 'insert'$$, '42501', null,
  'authenticated cannot update audit rows');

-- Supervisor approves; the technician can then no longer edit it
set local request.jwt.claims = '{"sub":"20000000-0000-4000-8000-0000000000a2","role":"authenticated","aal":"aal2"}';
update public.shift_actuals set status = 'approved' where id = '20000000-0000-4000-8000-0000000000c1';
select is((select status from public.shift_actuals where id = '20000000-0000-4000-8000-0000000000c1'),
  'approved', 'supervisor can approve an actual');
set local request.jwt.claims = '{"sub":"20000000-0000-4000-8000-0000000000a1","role":"authenticated","aal":"aal2"}';
update public.shift_actuals set ot_labor_hours = 1 where id = '20000000-0000-4000-8000-0000000000c1';
select is((select ot_labor_hours from public.shift_actuals where id = '20000000-0000-4000-8000-0000000000c1'),
  4.5::numeric, 'technician cannot edit an approved actual');

-- dept_admin reads the department audit trail
set local request.jwt.claims = '{"sub":"20000000-0000-4000-8000-0000000000a3","role":"authenticated","aal":"aal2"}';
select ok((select count(*)::int from public.audit_log) > 0, 'dept_admin sees the audit trail');
select throws_ok($$delete from public.audit_log$$, '42501', null, 'dept_admin cannot delete audit rows');

select * from finish();
rollback;
