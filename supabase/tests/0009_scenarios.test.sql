-- SG-19: scenario runs. Who may read and write is in the RLS matrix (0010); this file checks
-- the table rules the matrix does not: column-limited updates, the applied consistency check,
-- and audit rows that leave out the result payload.
begin;
create extension if not exists pgtap with schema extensions;

select plan(6);

insert into public.organizations (id, name) values ('90000000-0000-4000-8000-000000000001', 'Sc Org');
insert into public.facilities (id, organization_id, name)
values ('90000000-0000-4000-8000-000000000002', '90000000-0000-4000-8000-000000000001', 'Sc Fac');
insert into public.departments (id, facility_id, name, slug)
values ('90000000-0000-4000-8000-000000000003', '90000000-0000-4000-8000-000000000002', 'Sc Dept', 'sc-dept');

insert into public.scenarios (id, department_id, target_date, model_version, request, result)
values ('90000000-0000-4000-8000-0000000000a1', '90000000-0000-4000-8000-000000000003',
        '2026-11-03', 'v', '{"target": null}', '{"options": [{"id": "m+0"}]}');

select ok(
  not has_column_privilege('authenticated', 'public.scenarios', 'result', 'UPDATE'),
  'signed-in users cannot update a run''s result'
);
select ok(
  has_column_privilege('authenticated', 'public.scenarios', 'applied_option_id', 'UPDATE'),
  'signed-in users may update the applied columns (RLS decides who)'
);
select throws_ok(
  $$update public.scenarios set applied = true where id = '90000000-0000-4000-8000-0000000000a1'$$,
  '23514', null, 'applied needs the applied option'
);

update public.scenarios set applied = true, applied_option_id = 'm+0', applied_at = now()
where id = '90000000-0000-4000-8000-0000000000a1';

select is(
  (select count(*)::integer from public.audit_log
   where entity = 'scenarios' and entity_id = '90000000-0000-4000-8000-0000000000a1'),
  2, 'insert and apply each write an audit row'
);
select ok(
  (select bool_and(not (coalesce(after, '{}') ? 'result') and not (coalesce(before, '{}') ? 'result'))
   from public.audit_log
   where entity = 'scenarios' and entity_id = '90000000-0000-4000-8000-0000000000a1'),
  'audit rows leave out the result payload'
);
select is(
  (select after ->> 'applied_option_id' from public.audit_log
   where entity = 'scenarios' and entity_id = '90000000-0000-4000-8000-0000000000a1'
     and action = 'update'),
  'm+0', 'the apply audit row records the chosen option'
);

select * from finish();
rollback;
