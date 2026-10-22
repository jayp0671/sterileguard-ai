-- pgTAP smoke test for SG-04 invites and session policy.
begin;
create extension if not exists pgtap with schema extensions;
select plan(6);

select has_table('public', 'invites', 'invites exists');
select ok(
  (select relrowsecurity from pg_class where oid = 'public.invites'::regclass),
  'RLS enabled on invites'
);
select has_function('public', 'accept_pending_invites', 'accept_pending_invites exists');
select has_function('public', 'session_age_seconds', 'session_age_seconds exists');
select ok(
  not has_function_privilege('anon', 'public.accept_pending_invites()', 'execute'),
  'anon cannot accept invites'
);
select ok(
  not has_function_privilege('anon', 'public.session_age_seconds()', 'execute'),
  'anon cannot read session age'
);

select * from finish();
rollback;
