-- SG-03: tenancy schema, roles and the RLS pattern every later table copies.
-- Organization -> Facility -> Department -> Members with roles (plan §2.1, §2.2, §8).
-- No patient data and no employee names: profiles hold only an optional display name.

create type public.app_role as enum (
  'technician', 'supervisor', 'dept_admin', 'data_steward', 'platform_admin'
);

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  allowed_email_domains text[] not null default '{}',
  created_at timestamptz not null default now()
);

create table public.facilities (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations (id) on delete cascade,
  name text not null,
  timezone text not null default 'America/New_York',
  created_at timestamptz not null default now()
);
create index facilities_organization_id_idx on public.facilities (organization_id);

create table public.departments (
  id uuid primary key default gen_random_uuid(),
  facility_id uuid not null references public.facilities (id) on delete cascade,
  name text not null,
  slug text not null unique,
  settings jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint departments_slug_format check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  constraint departments_settings_object check (jsonb_typeof(settings) = 'object')
);
create index departments_facility_id_idx on public.departments (facility_id);

create table public.profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  locale text not null default 'en',
  theme text not null default 'system',
  created_at timestamptz not null default now(),
  constraint profiles_theme_values check (theme in ('system', 'light', 'dark'))
);

create table public.memberships (
  user_id uuid not null references auth.users (id) on delete cascade,
  department_id uuid not null references public.departments (id) on delete cascade,
  role public.app_role not null,
  created_at timestamptz not null default now(),
  primary key (user_id, department_id, role)
);
create index memberships_department_id_idx on public.memberships (department_id);
-- user_id is the leading primary key column, so it is already indexed.

-- ---------------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------------

create function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger departments_set_updated_at
before update on public.departments
for each row execute function public.set_updated_at();

create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (user_id) values (new.id) on conflict do nothing;
  return new;
end;
$$;
revoke execute on function public.handle_new_user() from anon, authenticated, public;

create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Helpers (security definer, empty search_path, not callable by anon)
-- ---------------------------------------------------------------------------

create function public.is_aal2()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce((auth.jwt() ->> 'aal') = 'aal2', false);
$$;

create function public.is_member(dept uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.memberships m
    where m.user_id = (select auth.uid()) and m.department_id = dept
  );
$$;

create function public.has_role(dept uuid, roles public.app_role[])
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.memberships m
    where m.user_id = (select auth.uid()) and m.department_id = dept and m.role = any (roles)
  );
$$;

create function public.is_platform_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.memberships m
    where m.user_id = (select auth.uid()) and m.role = 'platform_admin'
  );
$$;

revoke execute on function public.is_aal2() from anon, public;
revoke execute on function public.is_member(uuid) from anon, public;
revoke execute on function public.has_role(uuid, public.app_role[]) from anon, public;
revoke execute on function public.is_platform_admin() from anon, public;
grant execute on function public.is_aal2() to authenticated, service_role;
grant execute on function public.is_member(uuid) to authenticated, service_role;
grant execute on function public.has_role(uuid, public.app_role[]) to authenticated, service_role;
grant execute on function public.is_platform_admin() to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Row-level security. Pattern (see supabase/README.md):
--   select: is_aal2() and (is_member(department_id) or is_platform_admin())
--   write:  is_aal2() and has_role(department_id, array[...]::app_role[])
-- A user who has not completed two-factor (aal1) sees nothing.
-- ---------------------------------------------------------------------------

alter table public.organizations enable row level security;
alter table public.facilities enable row level security;
alter table public.departments enable row level security;
alter table public.profiles enable row level security;
alter table public.memberships enable row level security;

-- Anonymous users never touch tenancy tables.
revoke all on public.organizations, public.facilities, public.departments, public.profiles,
  public.memberships from anon;

-- organizations: visible through departments the user belongs to; platform admin manages.
create policy organizations_select on public.organizations
for select to authenticated
using (
  (select public.is_aal2()) and (
    (select public.is_platform_admin())
    or exists (
      select 1
      from public.facilities f
      join public.departments d on d.facility_id = f.id
      where f.organization_id = organizations.id and public.is_member(d.id)
    )
  )
);
create policy organizations_write on public.organizations
for all to authenticated
using ((select public.is_aal2()) and (select public.is_platform_admin()))
with check ((select public.is_aal2()) and (select public.is_platform_admin()));

-- facilities: same visibility rule.
create policy facilities_select on public.facilities
for select to authenticated
using (
  (select public.is_aal2()) and (
    (select public.is_platform_admin())
    or exists (
      select 1 from public.departments d
      where d.facility_id = facilities.id and public.is_member(d.id)
    )
  )
);
create policy facilities_write on public.facilities
for all to authenticated
using ((select public.is_aal2()) and (select public.is_platform_admin()))
with check ((select public.is_aal2()) and (select public.is_platform_admin()));

-- departments: members read; dept_admin edits settings; platform admin creates and deletes.
create policy departments_select on public.departments
for select to authenticated
using ((select public.is_aal2()) and (public.is_member(id) or (select public.is_platform_admin())));
create policy departments_update on public.departments
for update to authenticated
using (
  (select public.is_aal2())
  and (public.has_role(id, array['dept_admin']::public.app_role[])
       or (select public.is_platform_admin()))
)
with check (
  (select public.is_aal2())
  and (public.has_role(id, array['dept_admin']::public.app_role[])
       or (select public.is_platform_admin()))
);
create policy departments_insert on public.departments
for insert to authenticated
with check ((select public.is_aal2()) and (select public.is_platform_admin()));
create policy departments_delete on public.departments
for delete to authenticated
using ((select public.is_aal2()) and (select public.is_platform_admin()));

-- profiles: users read and edit their own row. Rows are created by the auth trigger.
create policy profiles_select_own on public.profiles
for select to authenticated
using ((select public.is_aal2()) and user_id = (select auth.uid()));
create policy profiles_update_own on public.profiles
for update to authenticated
using ((select public.is_aal2()) and user_id = (select auth.uid()))
with check ((select public.is_aal2()) and user_id = (select auth.uid()));

-- memberships: users read their own rows; a dept_admin manages their department but can never
-- grant or touch platform_admin; only a platform_admin manages platform_admin.
create policy memberships_select on public.memberships
for select to authenticated
using (
  (select public.is_aal2()) and (
    user_id = (select auth.uid())
    or public.has_role(department_id, array['dept_admin']::public.app_role[])
    or (select public.is_platform_admin())
  )
);
create policy memberships_insert on public.memberships
for insert to authenticated
with check (
  (select public.is_aal2()) and (
    (select public.is_platform_admin())
    or (role <> 'platform_admin'
        and public.has_role(department_id, array['dept_admin']::public.app_role[]))
  )
);
create policy memberships_update on public.memberships
for update to authenticated
using (
  (select public.is_aal2()) and (
    (select public.is_platform_admin())
    or (role <> 'platform_admin'
        and public.has_role(department_id, array['dept_admin']::public.app_role[]))
  )
)
with check (
  (select public.is_aal2()) and (
    (select public.is_platform_admin())
    or (role <> 'platform_admin'
        and public.has_role(department_id, array['dept_admin']::public.app_role[]))
  )
);
create policy memberships_delete on public.memberships
for delete to authenticated
using (
  (select public.is_aal2()) and (
    (select public.is_platform_admin())
    or (role <> 'platform_admin'
        and public.has_role(department_id, array['dept_admin']::public.app_role[]))
  )
);
