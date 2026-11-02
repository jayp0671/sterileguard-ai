-- SG-20: shift actuals workflow columns. Not named in the ticket: "reopen {reason} (the reason
-- is stored in the audit row)" needs the reason on the row, because audit rows are written only
-- by the table trigger (nobody, not even the service role, can insert into audit_log). The
-- history's "author role" column needs the role the author held when logging. Migrations are
-- numbered in merge order, so the SG-21 imports migration becomes 0011.
--
-- RLS is unchanged (0004): approved rows stay editable only by dept_admin, and the API allows
-- that only through reopen.

alter table public.shift_actuals
  add column created_by_role text
    check (created_by_role in ('technician', 'supervisor', 'dept_admin', 'data_steward', 'platform_admin')),
  add column reopen_reason text check (char_length(reopen_reason) between 3 and 500),
  add column reopened_by uuid references auth.users (id) on delete set null,
  add column reopened_at timestamptz;

create index shift_actuals_reopened_by_idx on public.shift_actuals (reopened_by);

comment on column public.shift_actuals.reopen_reason is
  'Why a dept_admin reopened an approved row (SG-20); the audit row keeps every reason.';
