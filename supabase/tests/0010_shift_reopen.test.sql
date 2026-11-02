-- SG-20: reopen columns. A reopen is an update, so its reason lands in the audit row.
begin;
create extension if not exists pgtap with schema extensions;

select plan(3);

insert into public.organizations (id, name) values ('a0000000-0000-4000-8000-000000000001', 'Ro Org');
insert into public.facilities (id, organization_id, name)
values ('a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000001', 'Ro Fac');
insert into public.departments (id, facility_id, name, slug)
values ('a0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000002', 'Ro Dept', 'ro-dept');
insert into public.shift_actuals (id, department_id, shift_date, ot_labor_hours, source, status, created_by_role)
values ('a0000000-0000-4000-8000-0000000000a1', 'a0000000-0000-4000-8000-000000000003',
        '2026-11-02', 4, 'real', 'approved', 'technician');

select throws_ok(
  $$update public.shift_actuals set reopen_reason = 'x' where id = 'a0000000-0000-4000-8000-0000000000a1'$$,
  '23514', null, 'a reopen reason needs at least 3 characters'
);
select throws_ok(
  $$update public.shift_actuals set created_by_role = 'owner' where id = 'a0000000-0000-4000-8000-0000000000a1'$$,
  '23514', null, 'the author role must be an app role'
);

update public.shift_actuals
set status = 'submitted', reopen_reason = 'wrong overtime total', reopened_at = now()
where id = 'a0000000-0000-4000-8000-0000000000a1';

select is(
  (select after ->> 'reopen_reason' from public.audit_log
   where entity = 'shift_actuals' and entity_id = 'a0000000-0000-4000-8000-0000000000a1'
     and action = 'update'
   order by id desc limit 1),
  'wrong overtime total', 'the audit row keeps the reopen reason'
);

select * from finish();
rollback;
