-- SG-04: invite-only onboarding. Admins invite by email; the invite turns into a membership
-- the first time the invited user signs in at aal2 (accept_pending_invites).

create extension if not exists citext with schema extensions;

create table public.invites (
  id uuid primary key default gen_random_uuid(),
  email extensions.citext not null,
  department_id uuid not null references public.departments (id) on delete cascade,
  role public.app_role not null,
  invited_by uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '7 days',
  accepted_at timestamptz,
  revoked_at timestamptz,
  constraint invites_email_format check (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$')
);
create index invites_department_id_idx on public.invites (department_id);
create index invites_invited_by_idx on public.invites (invited_by);
create index invites_email_pending_idx on public.invites (email)
  where accepted_at is null and revoked_at is null;

alter table public.invites enable row level security;
revoke all on public.invites from anon;

-- dept_admin of the department and platform_admin can read, create and revoke. No one else.
-- A dept_admin can never invite a platform_admin.
create policy invites_select on public.invites
for select to authenticated
using (
  (select public.is_aal2()) and (
    (select public.is_platform_admin())
    or public.has_role(department_id, array['dept_admin']::public.app_role[])
  )
);
create policy invites_insert on public.invites
for insert to authenticated
with check (
  (select public.is_aal2())
  and invited_by = (select auth.uid())
  and (
    (select public.is_platform_admin())
    or (role <> 'platform_admin'
        and public.has_role(department_id, array['dept_admin']::public.app_role[]))
  )
);
create policy invites_update on public.invites
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

-- Convert the caller's unexpired, unrevoked invites into memberships. Called by the web app
-- right after the first successful aal2 sign-in. Returns the number of invites accepted.
-- Emails compare with lower(): with an empty search_path the citext operators are not found.
create function public.accept_pending_invites()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  accepted integer := 0;
  me uuid := (select auth.uid());
  my_email text := (select auth.email());
begin
  if me is null or my_email is null or not public.is_aal2() then
    return 0;
  end if;

  insert into public.memberships (user_id, department_id, role)
  select me, i.department_id, i.role
  from public.invites i
  where lower(i.email::text) = lower(my_email)
    and i.accepted_at is null
    and i.revoked_at is null
    and i.expires_at > now()
  on conflict do nothing;

  update public.invites i
  set accepted_at = now()
  where lower(i.email::text) = lower(my_email)
    and i.accepted_at is null
    and i.revoked_at is null
    and i.expires_at > now();
  get diagnostics accepted = row_count;
  return accepted;
end;
$$;
revoke execute on function public.accept_pending_invites() from anon, public;
grant execute on function public.accept_pending_invites() to authenticated;
