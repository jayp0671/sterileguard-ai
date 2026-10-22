-- SG-08: datasets, shift plans (inputs known at 7:00 AM) and shift actuals (outcomes).
-- Columns mirror packages/data/src/sg_data/schema.py; the drift test
-- (packages/data/tests/test_db_drift.py) fails if the two diverge. Ranges match schema.py.
-- The ticket names this 0003_shift_data.sql; 0003 was already taken by SG-04, so it is 0004
-- and the audit migration is 0005.

create table public.datasets (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references public.departments (id) on delete cascade,
  source text not null check (source in ('real', 'simulated')),
  name text not null,
  row_count integer not null check (row_count >= 0),
  content_hash text not null,
  config_hash text,
  seed bigint,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now()
);
create index datasets_department_id_idx on public.datasets (department_id);
create index datasets_created_by_idx on public.datasets (created_by);

create table public.shift_plans (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references public.departments (id) on delete cascade,
  plan_date date not null,
  -- Tier 1 inputs
  regular_patients integer not null check (regular_patients between 0 and 800),
  morning_staff_present integer not null check (morning_staff_present between 0 and 20),
  -- Tier 2 inputs (null until filled; defaults carry a __missing flag)
  mf_cases integer check (mf_cases between 0 and 80),
  student_clinic_sessions integer check (student_clinic_sessions between 0 and 40),
  aft_11_staff integer check (aft_11_staff between 0 and 20),
  aft_13_staff integer check (aft_13_staff between 0 and 20),
  aft_15_staff integer check (aft_15_staff between 0 and 20),
  outside_support_staff integer check (outside_support_staff between 0 and 20),
  ot_available_staff integer check (ot_available_staff between 0 and 20),
  washers_up integer check (washers_up between 0 and 10),
  sterilizers_up integer check (sterilizers_up between 0 and 10),
  carryover_backlog_estimate integer check (carryover_backlog_estimate between 0 and 2),
  is_holiday boolean,
  academic_event text check (academic_event in ('none', 'exam', 'break', 'semester_start')),
  mf_cases__missing boolean not null default false,
  student_clinic_sessions__missing boolean not null default false,
  aft_11_staff__missing boolean not null default false,
  aft_13_staff__missing boolean not null default false,
  aft_15_staff__missing boolean not null default false,
  outside_support_staff__missing boolean not null default false,
  ot_available_staff__missing boolean not null default false,
  washers_up__missing boolean not null default false,
  sterilizers_up__missing boolean not null default false,
  carryover_backlog_estimate__missing boolean not null default false,
  is_holiday__missing boolean not null default false,
  academic_event__missing boolean not null default false,
  -- meta
  source text not null check (source in ('real', 'simulated')),
  dataset_id uuid references public.datasets (id) on delete cascade,
  status text not null default 'draft' check (status in ('draft', 'final')),
  created_by uuid references auth.users (id) on delete set null,
  updated_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint shift_plans_ot_available_le_morning
    check (ot_available_staff is null or ot_available_staff <= morning_staff_present),
  constraint shift_plans_unique_day unique (department_id, plan_date, source)
);
create index shift_plans_department_date_idx on public.shift_plans (department_id, plan_date desc);
create index shift_plans_dataset_id_idx on public.shift_plans (dataset_id);
create index shift_plans_created_by_idx on public.shift_plans (created_by);
create index shift_plans_updated_by_idx on public.shift_plans (updated_by);

create table public.shift_actuals (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references public.departments (id) on delete cascade,
  shift_date date not null,
  ot_labor_hours numeric(5, 2) not null check (ot_labor_hours between 0 and 60),
  -- Tier 3 (calibration and analysis only, never model inputs)
  emergency_intake_patients integer check (emergency_intake_patients between 0 and 200),
  returned_unused_estimate integer check (returned_unused_estimate between 0 and 2000),
  equipment_downtime_minutes integer check (equipment_downtime_minutes between 0 and 900),
  notes text check (char_length(notes) <= 500),
  -- meta
  source text not null check (source in ('real', 'simulated')),
  dataset_id uuid references public.datasets (id) on delete cascade,
  status text not null default 'draft' check (status in ('draft', 'submitted', 'approved')),
  submitted_by uuid references auth.users (id) on delete set null,
  approved_by uuid references auth.users (id) on delete set null,
  approved_at timestamptz,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint shift_actuals_unique_day unique (department_id, shift_date, source)
);
create index shift_actuals_department_date_idx
  on public.shift_actuals (department_id, shift_date desc);
create index shift_actuals_dataset_id_idx on public.shift_actuals (dataset_id);
create index shift_actuals_created_by_idx on public.shift_actuals (created_by);
create index shift_actuals_submitted_by_idx on public.shift_actuals (submitted_by);
create index shift_actuals_approved_by_idx on public.shift_actuals (approved_by);

create trigger shift_plans_set_updated_at
before update on public.shift_plans
for each row execute function public.set_updated_at();
create trigger shift_actuals_set_updated_at
before update on public.shift_actuals
for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Row-level security (plan §2.2). Same pattern as 0001: aal2 required for everything.
-- The service role bypasses RLS for simulation jobs (SG-09).
-- ---------------------------------------------------------------------------

alter table public.datasets enable row level security;
alter table public.shift_plans enable row level security;
alter table public.shift_actuals enable row level security;
revoke all on public.datasets, public.shift_plans, public.shift_actuals from anon;

-- datasets: members read; data_steward and dept_admin register datasets.
create policy datasets_select on public.datasets
for select to authenticated
using (
  (select public.is_aal2())
  and (public.is_member(department_id) or (select public.is_platform_admin()))
);
create policy datasets_insert on public.datasets
for insert to authenticated
with check (
  (select public.is_aal2())
  and public.has_role(department_id, array['data_steward', 'dept_admin']::public.app_role[])
);

-- shift_plans: members read; supervisor and dept_admin write.
create policy shift_plans_select on public.shift_plans
for select to authenticated
using (
  (select public.is_aal2())
  and (public.is_member(department_id) or (select public.is_platform_admin()))
);
create policy shift_plans_insert on public.shift_plans
for insert to authenticated
with check (
  (select public.is_aal2())
  and public.has_role(department_id, array['supervisor', 'dept_admin']::public.app_role[])
);
create policy shift_plans_update on public.shift_plans
for update to authenticated
using (
  (select public.is_aal2())
  and public.has_role(department_id, array['supervisor', 'dept_admin']::public.app_role[])
)
with check (
  (select public.is_aal2())
  and public.has_role(department_id, array['supervisor', 'dept_admin']::public.app_role[])
);

-- shift_actuals: members read; technician and above insert unapproved rows they own.
-- Update: a technician only their own unapproved rows (and cannot approve); a supervisor any
-- unapproved row; approved rows only by dept_admin (reopen flow, SG-20).
create policy shift_actuals_select on public.shift_actuals
for select to authenticated
using (
  (select public.is_aal2())
  and (public.is_member(department_id) or (select public.is_platform_admin()))
);
create policy shift_actuals_insert on public.shift_actuals
for insert to authenticated
with check (
  (select public.is_aal2())
  and created_by = (select auth.uid())
  and (
    public.has_role(department_id, array['dept_admin']::public.app_role[])
    or (status <> 'approved'
        and public.has_role(department_id,
              array['technician', 'supervisor']::public.app_role[]))
  )
);
create policy shift_actuals_update on public.shift_actuals
for update to authenticated
using (
  (select public.is_aal2()) and (
    public.has_role(department_id, array['dept_admin']::public.app_role[])
    or (status <> 'approved'
        and public.has_role(department_id, array['supervisor']::public.app_role[]))
    or (status <> 'approved'
        and created_by = (select auth.uid())
        and public.has_role(department_id, array['technician']::public.app_role[]))
  )
)
with check (
  (select public.is_aal2()) and (
    public.has_role(department_id, array['dept_admin', 'supervisor']::public.app_role[])
    or (status <> 'approved'
        and created_by = (select auth.uid())
        and public.has_role(department_id, array['technician']::public.app_role[]))
  )
);
