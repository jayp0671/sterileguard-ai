-- pgTAP smoke test for SG-03. The full permission matrix is SG-12.
begin;
create extension if not exists pgtap with schema extensions;
select plan(17);

-- Tables exist
select has_table('public', 'organizations', 'organizations exists');
select has_table('public', 'facilities', 'facilities exists');
select has_table('public', 'departments', 'departments exists');
select has_table('public', 'profiles', 'profiles exists');
select has_table('public', 'memberships', 'memberships exists');

-- RLS enabled on every public table
select is(
  (select count(*)::int from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity),
  0,
  'RLS is enabled on every table in public'
);

-- Helpers: empty search_path and not executable by anon
select is(
  (select count(*)::int from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public'
     and p.proname in ('is_aal2', 'is_member', 'has_role', 'is_platform_admin')
     and p.prosecdef and p.proconfig @> array['search_path=""']),
  4,
  'all four helpers are security definer with an empty search_path'
);
select ok(not has_function_privilege('anon', 'public.is_aal2()', 'execute'), 'anon cannot run is_aal2');
select ok(not has_function_privilege('anon', 'public.is_member(uuid)', 'execute'), 'anon cannot run is_member');
select ok(
  not has_function_privilege('anon', 'public.has_role(uuid, public.app_role[])', 'execute'),
  'anon cannot run has_role'
);
select ok(not has_function_privilege('anon', 'public.is_platform_admin()', 'execute'), 'anon cannot run is_platform_admin');

-- Fixtures: two departments, one member of the first
insert into public.organizations (id, name) values ('10000000-0000-4000-8000-000000000001', 'T Org');
insert into public.facilities (id, organization_id, name)
values ('10000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', 'T Fac');
insert into public.departments (id, facility_id, name, slug) values
  ('10000000-0000-4000-8000-00000000000a', '10000000-0000-4000-8000-000000000002', 'Dept A', 't-dept-a'),
  ('10000000-0000-4000-8000-00000000000b', '10000000-0000-4000-8000-000000000002', 'Dept B', 't-dept-b');
insert into auth.users (id, email, aud, role)
values ('10000000-0000-4000-8000-0000000000aa', 'member@example.test', 'authenticated', 'authenticated');
insert into public.memberships (user_id, department_id, role)
values ('10000000-0000-4000-8000-0000000000aa', '10000000-0000-4000-8000-00000000000a', 'dept_admin');

select ok(
  exists (select 1 from public.profiles where user_id = '10000000-0000-4000-8000-0000000000aa'),
  'profile row is created by the auth.users trigger'
);

-- aal1 token: sees nothing even with a membership
set local role authenticated;
set local request.jwt.claims = '{"sub":"10000000-0000-4000-8000-0000000000aa","role":"authenticated","aal":"aal1"}';
select is((select count(*)::int from public.departments where slug like 't-dept-%'), 0, 'aal1 sees 0 departments');

-- aal2 token: sees only its own department
set local request.jwt.claims = '{"sub":"10000000-0000-4000-8000-0000000000aa","role":"authenticated","aal":"aal2"}';
select results_eq(
  $$select slug from public.departments where slug like 't-dept-%'$$,
  array['t-dept-a'],
  'aal2 member sees only their department'
);
select is((select count(*)::int from public.organizations where name = 'T Org'), 1, 'org visible through membership');

-- dept_admin cannot grant platform_admin
select throws_ok(
  $$insert into public.memberships (user_id, department_id, role)
    values ('10000000-0000-4000-8000-0000000000aa', '10000000-0000-4000-8000-00000000000a', 'platform_admin')$$,
  '42501',
  null,
  'dept_admin cannot grant platform_admin'
);

-- and cannot add members to another department
select throws_ok(
  $$insert into public.memberships (user_id, department_id, role)
    values ('10000000-0000-4000-8000-0000000000aa', '10000000-0000-4000-8000-00000000000b', 'technician')$$,
  '42501',
  null,
  'dept_admin cannot manage another department'
);

select * from finish();
rollback;
