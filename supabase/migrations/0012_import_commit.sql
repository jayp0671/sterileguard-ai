-- SG-24: commit an import job from the API with the data steward's own token (ADR-0010).
--
-- RLS (0004) lets only supervisors and dept admins write plans, and only technicians and up
-- write actuals, so a data steward cannot load the rows they reviewed. Instead of widening those
-- policies, one security definer function does the whole commit for a job the caller may run:
--
--   - caller is aal2 and holds data_steward or dept_admin in the job's department;
--   - overwrite of existing real days is a dept_admin decision;
--   - every row is forced to the job's department, source 'real', the new dataset and the
--     caller as author (the payload cannot choose them), plans are 'final' and actuals
--     'approved' by the caller (approving the import is the review, ADR-0009);
--   - only real columns of the target table are written (names come from pg_attribute), and
--     ids, timestamps and the workflow columns are never taken from the payload;
--   - a job commits once; a second job with the same file (content hash) changes nothing;
--   - existing real days are skipped unless overwrite is set.
--
-- Every insert and update fires the existing audit triggers (datasets, shift_plans,
-- shift_actuals, import_jobs), with the caller as actor, so the commit is fully audited.

create function public.commit_import(
  p_job_id uuid,
  p_plans jsonb,
  p_actuals jsonb,
  p_overwrite boolean default false
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  uid uuid := (select auth.uid());
  job public.import_jobs%rowtype;
  previous uuid;
  ds uuid := gen_random_uuid();
  plans jsonb := coalesce(p_plans, '[]'::jsonb);
  actuals jsonb := coalesce(p_actuals, '[]'::jsonb);
  existing date[] := '{}';
  skipped date[];
  n_plans integer := 0;
  n_actuals integer := 0;
  forced_plan jsonb;
  forced_actual jsonb;
  cols text;
  sets text;
begin
  if uid is null or not (select public.is_aal2()) then
    raise exception 'two-factor sign-in required' using errcode = '42501';
  end if;
  if jsonb_typeof(plans) <> 'array' or jsonb_typeof(actuals) <> 'array' then
    raise exception 'plans and actuals must be JSON arrays' using errcode = '22023';
  end if;
  if jsonb_array_length(plans) > 5000 or jsonb_array_length(actuals) > 5000 then
    raise exception 'too many rows in one import (max 5000)' using errcode = '54000';
  end if;

  select * into job from public.import_jobs where id = p_job_id for update;
  if not found
     or not public.has_role(job.department_id, array['data_steward', 'dept_admin']::public.app_role[])
  then
    -- Same answer for "missing" and "not yours", so job ids are not confirmed to outsiders.
    raise exception 'import job not found' using errcode = 'P0002';
  end if;
  if p_overwrite and not public.has_role(job.department_id, array['dept_admin']::public.app_role[]) then
    raise exception 'only a department admin may overwrite existing days' using errcode = '42501';
  end if;
  if job.status in ('committed', 'cancelled', 'failed') then
    raise exception 'import job is already %', job.status using errcode = '55000';
  end if;

  -- The same file was committed by another job: change nothing.
  select j.id into previous from public.import_jobs j
  where j.department_id = job.department_id and j.content_hash = job.content_hash
    and j.status = 'committed' and j.id <> job.id
  order by j.created_at limit 1;
  if previous is not null then
    update public.import_jobs set status = 'cancelled', rows_committed = 0, approved_by = uid
    where id = job.id;
    return jsonb_build_object(
      'import_job_id', previous, 'dataset_id', null, 'rows_committed', 0, 'plans', 0,
      'actuals', 0, 'skipped_dates', '[]'::jsonb, 'already_committed', true
    );
  end if;

  if not p_overwrite then
    select coalesce(array_agg(distinct d), '{}') into existing from (
      select plan_date as d from public.shift_plans
      where department_id = job.department_id and source = 'real'
        and plan_date in (select (e ->> 'plan_date')::date from jsonb_array_elements(plans) e)
      union
      select shift_date from public.shift_actuals
      where department_id = job.department_id and source = 'real'
        and shift_date in (select (e ->> 'shift_date')::date from jsonb_array_elements(actuals) e)
    ) s;
  end if;
  skipped := existing;

  -- Fields the payload may never set, and the values the function forces instead.
  forced_plan := jsonb_build_object(
    'department_id', job.department_id, 'source', 'real', 'dataset_id', ds, 'status', 'final',
    'created_by', uid, 'updated_by', uid
  );
  forced_actual := jsonb_build_object(
    'department_id', job.department_id, 'source', 'real', 'dataset_id', ds,
    'status', 'approved', 'approved_by', uid, 'approved_at', now(), 'created_by', uid,
    'submitted_by', uid, 'created_by_role',
    case when public.has_role(job.department_id, array['dept_admin']::public.app_role[])
         then 'dept_admin' else 'data_steward' end,
    'reopen_reason', null, 'reopened_by', null, 'reopened_at', null
  );
  select coalesce(jsonb_agg((e - array['id', 'created_at', 'updated_at']) || forced_plan), '[]')
    into plans
  from jsonb_array_elements(plans) e
  where not ((e ->> 'plan_date')::date = any (existing));
  select coalesce(jsonb_agg((e - array['id', 'created_at', 'updated_at']) || forced_actual), '[]')
    into actuals
  from jsonb_array_elements(actuals) e
  where not ((e ->> 'shift_date')::date = any (existing));

  if jsonb_array_length(plans) = 0 and jsonb_array_length(actuals) = 0 then
    update public.import_jobs set status = 'committed', rows_committed = 0, approved_by = uid
    where id = job.id;
    return jsonb_build_object(
      'import_job_id', job.id, 'dataset_id', null, 'rows_committed', 0, 'plans', 0,
      'actuals', 0, 'skipped_dates', to_jsonb(skipped), 'already_committed', false
    );
  end if;

  insert into public.datasets (id, department_id, source, name, row_count, content_hash,
                               import_job_id, created_by)
  values (ds, job.department_id, 'real', left('import ' || job.original_filename, 200),
          jsonb_array_length(plans), job.content_hash, job.id, uid);

  -- Plans: only columns that exist on the table and appear in the payload.
  if jsonb_array_length(plans) > 0 then
    select string_agg(format('%I', a.attname), ', ' order by a.attnum),
           string_agg(format('%1$I = excluded.%1$I', a.attname), ', ' order by a.attnum)
      into cols, sets
    from pg_attribute a
    where a.attrelid = 'public.shift_plans'::regclass and a.attnum > 0 and not a.attisdropped
      and a.attname not in ('id', 'created_at', 'updated_at')
      and exists (select 1 from jsonb_array_elements(plans) e where e ? a.attname);
    execute format(
      'insert into public.shift_plans (%1$s) select %1$s from jsonb_populate_recordset(null::public.shift_plans, $1) '
      || 'on conflict (department_id, plan_date, source) do %2$s',
      cols, case when p_overwrite then 'update set ' || sets else 'nothing' end
    ) using plans;
    get diagnostics n_plans = row_count;
  end if;

  if jsonb_array_length(actuals) > 0 then
    select string_agg(format('%I', a.attname), ', ' order by a.attnum),
           string_agg(format('%1$I = excluded.%1$I', a.attname), ', ' order by a.attnum)
      into cols, sets
    from pg_attribute a
    where a.attrelid = 'public.shift_actuals'::regclass and a.attnum > 0 and not a.attisdropped
      and a.attname not in ('id', 'created_at', 'updated_at')
      and exists (select 1 from jsonb_array_elements(actuals) e where e ? a.attname);
    execute format(
      'insert into public.shift_actuals (%1$s) select %1$s from jsonb_populate_recordset(null::public.shift_actuals, $1) '
      || 'on conflict (department_id, shift_date, source) do %2$s',
      cols, case when p_overwrite then 'update set ' || sets else 'nothing' end
    ) using actuals;
    get diagnostics n_actuals = row_count;
  end if;

  update public.import_jobs
  set status = 'committed', rows_committed = n_plans, approved_by = uid
  where id = job.id;

  return jsonb_build_object(
    'import_job_id', job.id, 'dataset_id', ds, 'rows_committed', n_plans, 'plans', n_plans,
    'actuals', n_actuals, 'skipped_dates', to_jsonb(skipped), 'already_committed', false
  );
end;
$$;

comment on function public.commit_import(uuid, jsonb, jsonb, boolean) is
  'SG-24 / ADR-0010: data steward or dept admin commits a reviewed import job; audited by triggers.';

revoke execute on function public.commit_import(uuid, jsonb, jsonb, boolean) from anon, public;
grant execute on function public.commit_import(uuid, jsonb, jsonb, boolean) to authenticated;
