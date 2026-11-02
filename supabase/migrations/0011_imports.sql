-- SG-21: import jobs, mapping templates and the private imports bucket (plan §10.1). The ticket
-- names this file 0009_imports.sql; 0009 (scenarios) and 0010 (shift reopen) merged first, so
-- imports are 0011.
--
-- Data stewards and department admins of a department see and run its imports. Jobs are never
-- deleted by users (cancel instead). Raw files live in the private `imports` bucket under
-- <department_id>/<job_id>/ and are deleted after commit, or 24 hours after upload at the latest
-- (SG-30 nightly job). Reports hold entity types, columns and rows, never matched text.

create table public.import_jobs (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references public.departments (id) on delete cascade,
  storage_path text,
  original_filename text not null check (char_length(original_filename) <= 255),
  content_hash text not null,
  status text not null default 'uploaded'
    check (status in ('uploaded', 'parsed', 'mapped', 'validated', 'committed', 'failed', 'cancelled')),
  parse_report jsonb,
  mapping jsonb,
  validation_report jsonb,
  phi_findings jsonb,
  rows_committed integer check (rows_committed >= 0),
  created_by uuid references auth.users (id) on delete set null,
  approved_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table public.import_jobs is 'File imports (SG-21): reports only, never raw values.';
create index import_jobs_department_created_idx on public.import_jobs (department_id, created_at desc);
create index import_jobs_department_hash_idx on public.import_jobs (department_id, content_hash);
create index import_jobs_created_by_idx on public.import_jobs (created_by);
create index import_jobs_approved_by_idx on public.import_jobs (approved_by);

create trigger import_jobs_set_updated_at
before update on public.import_jobs
for each row execute function public.set_updated_at();

create table public.mapping_templates (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references public.departments (id) on delete cascade,
  column_signature text not null,
  mapping jsonb not null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  unique (department_id, column_signature)
);
create index mapping_templates_created_by_idx on public.mapping_templates (created_by);

-- Lineage: each committed import creates one datasets row that points at its job.
alter table public.datasets
  add column import_job_id uuid references public.import_jobs (id) on delete set null;
create index datasets_import_job_id_idx on public.datasets (import_job_id);

alter table public.import_jobs enable row level security;
alter table public.mapping_templates enable row level security;
revoke all on public.import_jobs, public.mapping_templates from anon;
revoke delete, truncate on public.import_jobs from authenticated;

create policy import_jobs_select on public.import_jobs
for select to authenticated
using (
  (select public.is_aal2())
  and public.has_role(department_id, array['data_steward', 'dept_admin']::public.app_role[])
);
create policy import_jobs_insert on public.import_jobs
for insert to authenticated
with check (
  (select public.is_aal2())
  and public.has_role(department_id, array['data_steward', 'dept_admin']::public.app_role[])
  and created_by = (select auth.uid())
);
create policy import_jobs_update on public.import_jobs
for update to authenticated
using (
  (select public.is_aal2())
  and public.has_role(department_id, array['data_steward', 'dept_admin']::public.app_role[])
)
with check (
  (select public.is_aal2())
  and public.has_role(department_id, array['data_steward', 'dept_admin']::public.app_role[])
);

create policy mapping_templates_select on public.mapping_templates
for select to authenticated
using (
  (select public.is_aal2())
  and public.has_role(department_id, array['data_steward', 'dept_admin']::public.app_role[])
);
create policy mapping_templates_insert on public.mapping_templates
for insert to authenticated
with check (
  (select public.is_aal2())
  and public.has_role(department_id, array['data_steward', 'dept_admin']::public.app_role[])
  and created_by = (select auth.uid())
);
create policy mapping_templates_update on public.mapping_templates
for update to authenticated
using (
  (select public.is_aal2())
  and public.has_role(department_id, array['data_steward', 'dept_admin']::public.app_role[])
)
with check (
  (select public.is_aal2())
  and public.has_role(department_id, array['data_steward', 'dept_admin']::public.app_role[])
);
create policy mapping_templates_delete on public.mapping_templates
for delete to authenticated
using (
  (select public.is_aal2())
  and public.has_role(department_id, array['dept_admin']::public.app_role[])
);

create trigger import_jobs_audit
after insert or update or delete on public.import_jobs
for each row execute function public.audit_row_change();
create trigger mapping_templates_audit
after insert or update or delete on public.mapping_templates
for each row execute function public.audit_row_change();

-- Private bucket for raw uploads, one folder per department. Guarded because CI starts Postgres
-- without the storage service.
do $$
begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public, file_size_limit)
    values ('imports', 'imports', false, 10485760)
    on conflict (id) do nothing;

    execute $p$
      create policy imports_objects_select on storage.objects
      for select to authenticated
      using (
        bucket_id = 'imports'
        and (select public.is_aal2())
        and public.has_role(
          ((storage.foldername(name))[1])::uuid,
          array['data_steward', 'dept_admin']::public.app_role[]
        )
      )
    $p$;
    execute $p$
      create policy imports_objects_insert on storage.objects
      for insert to authenticated
      with check (
        bucket_id = 'imports'
        and (select public.is_aal2())
        and public.has_role(
          ((storage.foldername(name))[1])::uuid,
          array['data_steward', 'dept_admin']::public.app_role[]
        )
      )
    $p$;
    execute $p$
      create policy imports_objects_delete on storage.objects
      for delete to authenticated
      using (
        bucket_id = 'imports'
        and (select public.is_aal2())
        and public.has_role(
          ((storage.foldername(name))[1])::uuid,
          array['data_steward', 'dept_admin']::public.app_role[]
        )
      )
    $p$;
  end if;
end;
$$;
