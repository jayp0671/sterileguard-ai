-- SG-25: policy acceptance, cookie consent log, and audited admin actions (plan §14).
-- The ticket names this 0011_compliance.sql; 0011 to 0013 were already taken, so it is 0014.
--
-- admin_actions is not in the ticket. Two audited admin actions change nothing in a public
-- table: resetting a user's two-factor factors (Supabase Auth, through the service role) and
-- exporting the audit log. Audit rows are written only by table triggers (0005), so each of
-- these actions inserts one admin_actions row, and its trigger puts it in audit_log.

create table public.policy_acceptances (
  user_id uuid not null references auth.users (id) on delete cascade,
  policy text not null check (policy in ('terms', 'privacy')),
  version text not null check (version ~ '^\d+\.\d+\.\d+$'),
  accepted_at timestamptz not null default now(),
  primary key (user_id, policy, version)
);
comment on table public.policy_acceptances is 'SG-25: which Terms and Privacy versions each user accepted.';

create table public.consents (
  id bigint generated always as identity primary key,
  user_id uuid references auth.users (id) on delete set null,
  anon_id text check (char_length(anon_id) between 8 and 64),
  version text not null check (version ~ '^\d+\.\d+\.\d+$'),
  analytics boolean not null default false,
  gpc boolean not null default false,
  created_at timestamptz not null default now(),
  check (user_id is not null or anon_id is not null)
);
comment on table public.consents is 'SG-25: cookie consent choices, logged against the cookie policy version.';
create index consents_user_id_idx on public.consents (user_id);
create index consents_created_at_idx on public.consents (created_at desc);

create table public.admin_actions (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references public.departments (id) on delete cascade,
  actor_id uuid not null references auth.users (id) on delete cascade,
  action text not null check (action in ('mfa_reset', 'audit_export')),
  target_user_id uuid references auth.users (id) on delete set null,
  detail jsonb not null default '{}',
  created_at timestamptz not null default now()
);
comment on table public.admin_actions is 'SG-25: admin actions with no row of their own, so the audit trigger records them.';
create index admin_actions_department_created_idx on public.admin_actions (department_id, created_at desc);
create index admin_actions_actor_id_idx on public.admin_actions (actor_id);
create index admin_actions_target_user_id_idx on public.admin_actions (target_user_id);

alter table public.policy_acceptances enable row level security;
alter table public.consents enable row level security;
alter table public.admin_actions enable row level security;
revoke all on public.policy_acceptances, public.consents, public.admin_actions from anon;
revoke all on public.consents from authenticated;
revoke update, delete, truncate on public.policy_acceptances, public.admin_actions from authenticated;

-- Acceptances: each signed-in user reads and adds only their own; never edited or removed.
create policy policy_acceptances_select on public.policy_acceptances
for select to authenticated
using ((select public.is_aal2()) and user_id = (select auth.uid()));
create policy policy_acceptances_insert on public.policy_acceptances
for insert to authenticated
with check ((select public.is_aal2()) and user_id = (select auth.uid()));

-- Consents: written by the API's service role only (the banner shows before sign-in).

-- Admin actions: dept admins of the department and platform admins; the actor is the caller.
create policy admin_actions_select on public.admin_actions
for select to authenticated
using (
  (select public.is_aal2()) and (
    (select public.is_platform_admin())
    or public.has_role(department_id, array['dept_admin']::public.app_role[])
  )
);
create policy admin_actions_insert on public.admin_actions
for insert to authenticated
with check (
  (select public.is_aal2())
  and actor_id = (select auth.uid())
  and (
    (select public.is_platform_admin())
    or public.has_role(department_id, array['dept_admin']::public.app_role[])
  )
);

create trigger policy_acceptances_audit
after insert or update or delete on public.policy_acceptances
for each row execute function public.audit_row_change();
create trigger admin_actions_audit
after insert or update or delete on public.admin_actions
for each row execute function public.audit_row_change();
