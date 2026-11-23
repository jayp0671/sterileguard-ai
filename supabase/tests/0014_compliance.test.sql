-- SG-25: acceptances and admin actions are audited; consents carry a user or an anonymous id.
-- Who may read and write is in the RLS matrix (0010).
begin;
create extension if not exists pgtap with schema extensions;

select plan(5);

insert into public.organizations (id, name) values ('d0000000-0000-4000-8000-000000000001', 'Cp Org');
insert into public.facilities (id, organization_id, name)
values ('d0000000-0000-4000-8000-000000000002', 'd0000000-0000-4000-8000-000000000001', 'Cp Fac');
insert into public.departments (id, facility_id, name, slug)
values ('d0000000-0000-4000-8000-000000000003', 'd0000000-0000-4000-8000-000000000002', 'Cp Dept', 'cp-dept');
insert into auth.users (id, email, aud, role) values
  ('d0000000-0000-4000-8000-0000000000a1', 'cp-admin@example.test', 'authenticated', 'authenticated'),
  ('d0000000-0000-4000-8000-0000000000a2', 'cp-tech@example.test', 'authenticated', 'authenticated');
insert into public.memberships (user_id, department_id, role) values
  ('d0000000-0000-4000-8000-0000000000a1', 'd0000000-0000-4000-8000-000000000003', 'dept_admin');

set local role authenticated;
set local request.jwt.claims = '{"sub":"d0000000-0000-4000-8000-0000000000a1","role":"authenticated","aal":"aal2"}';
insert into public.admin_actions (department_id, actor_id, action, target_user_id)
values ('d0000000-0000-4000-8000-000000000003', 'd0000000-0000-4000-8000-0000000000a1', 'mfa_reset',
        'd0000000-0000-4000-8000-0000000000a2');
insert into public.policy_acceptances (user_id, policy, version)
values ('d0000000-0000-4000-8000-0000000000a1', 'terms', '1.0.0');
reset role;

select is(
  (select count(*)::int from public.audit_log
   where entity = 'admin_actions' and actor_id = 'd0000000-0000-4000-8000-0000000000a1'
     and department_id = 'd0000000-0000-4000-8000-000000000003'),
  1, 'an MFA reset lands in the department audit log with the admin as actor'
);
select is(
  (select after ->> 'target_user_id' from public.audit_log
   where entity = 'admin_actions' and actor_id = 'd0000000-0000-4000-8000-0000000000a1'),
  'd0000000-0000-4000-8000-0000000000a2', 'the audit row names the affected user'
);
select is(
  (select count(*)::int from public.audit_log
   where entity = 'policy_acceptances' and actor_id = 'd0000000-0000-4000-8000-0000000000a1'),
  1, 'accepting a policy is audited'
);
select throws_ok(
  $$insert into public.consents (version) values ('1.0.0')$$,
  '23514', null, 'a consent needs a user or an anonymous id'
);
select throws_ok(
  $$insert into public.policy_acceptances (user_id, policy, version) values ('d0000000-0000-4000-8000-0000000000a1', 'terms', 'v1')$$,
  '23514', null, 'policy versions are semver'
);

select * from finish();
rollback;
