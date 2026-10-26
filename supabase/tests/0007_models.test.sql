-- SG-14: model registry status transitions (activate, refuse without gates, one active per
-- feature set, rollback) and their audit rows.
begin;
create extension if not exists pgtap with schema extensions;

select plan(14);

insert into auth.users (id, email, aud, role) values
  ('70000000-0000-4000-8000-0000000000a1', 'mv-admin@example.test', 'authenticated', 'authenticated');

insert into public.model_versions
  (version, feature_set, artifact_path, card, metrics, training_dataset_ids, gates_passed)
values
  ('mv-1', 'full', 'mv-1/artifact.joblib', '{}', '{}', '{}', true),
  ('mv-2', 'full', 'mv-2/artifact.joblib', '{}', '{}', '{}', true),
  ('mv-weak', 'full', 'mv-weak/artifact.joblib', '{}', '{}', '{}', false),
  ('mv-core', 'core', 'mv-core/artifact.joblib', '{}', '{}', '{}', true);

select throws_ok(
  $$select public.activate_model_version('mv-weak', '70000000-0000-4000-8000-0000000000a1')$$,
  '23514', null, 'activation is refused when gates have not passed'
);
select throws_ok(
  $$select public.activate_model_version('mv-missing', null)$$,
  'P0002', null, 'activating an unknown version fails'
);

select is(
  (select status from public.activate_model_version('mv-1', '70000000-0000-4000-8000-0000000000a1')),
  'active', 'mv-1 becomes active'
);
select is(
  (select activated_by from public.model_versions where version = 'mv-1'),
  '70000000-0000-4000-8000-0000000000a1'::uuid, 'activation records the actor'
);
select isnt((select activated_at from public.model_versions where version = 'mv-1'), null,
  'activation records the time');

select is(
  (select status from public.activate_model_version('mv-2', '70000000-0000-4000-8000-0000000000a1')),
  'active', 'mv-2 becomes active'
);
select is((select status from public.model_versions where version = 'mv-1'), 'retired',
  'the previous active version of the feature set is retired');
select is((select status from public.activate_model_version('mv-core', null)), 'active',
  'a core version activates independently of full');
select is(
  (select count(*)::integer from public.model_versions where status = 'active'), 2,
  'one active version per feature set'
);
select throws_ok(
  $$update public.model_versions set status = 'active' where version = 'mv-1'$$,
  '23505', null, 'a second active row for a feature set violates the unique index'
);

select is(
  (select version from public.rollback_model_version('full', '70000000-0000-4000-8000-0000000000a1')),
  'mv-1', 'rollback re-activates the most recent retired version'
);
select is((select status from public.model_versions where version = 'mv-2'), 'retired',
  'rollback retires the version it replaces');

select ok(
  (select count(*) from public.audit_log
   where entity = 'model_versions' and action = 'update'
     and after ->> 'version' = 'mv-1' and after ->> 'status' = 'active') >= 2,
  'every activation is in audit_log'
);
select ok(
  not has_function_privilege('authenticated', 'public.activate_model_version(text, uuid)', 'execute'),
  'signed-in users cannot call activate_model_version directly'
);

select * from finish();
rollback;
