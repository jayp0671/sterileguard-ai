-- SG-11: Idempotency-Key storage for POST, PUT and PATCH (plan §7.2). The ticket names this
-- 0005_idempotency.sql; 0005 is the SG-08 audit log, so it is 0006.
-- A key is scoped to its user. The same key with the same body replays the stored response;
-- with a different body the API returns 409. Rows older than 24 hours are ignored and purged.

create table public.idempotency_keys (
  user_id uuid not null references auth.users (id) on delete cascade,
  key text not null check (char_length(key) between 1 and 200),
  method text not null check (method in ('POST', 'PUT', 'PATCH')),
  path text not null,
  body_hash text not null,
  status integer not null,
  response jsonb not null,
  created_at timestamptz not null default now(),
  primary key (user_id, key)
);
create index idempotency_keys_created_at_idx on public.idempotency_keys (created_at);

alter table public.idempotency_keys enable row level security;
revoke all on public.idempotency_keys from anon;

-- Each user sees and writes only their own keys (the API stores them with the user's token).
create policy idempotency_keys_select on public.idempotency_keys
for select to authenticated
using ((select public.is_aal2()) and user_id = (select auth.uid()));
create policy idempotency_keys_insert on public.idempotency_keys
for insert to authenticated
with check ((select public.is_aal2()) and user_id = (select auth.uid()));
-- Update lets an expired key (older than 24 h) be reused.
create policy idempotency_keys_update on public.idempotency_keys
for update to authenticated
using ((select public.is_aal2()) and user_id = (select auth.uid()))
with check ((select public.is_aal2()) and user_id = (select auth.uid()));

-- Purge keys older than 24 hours. Scheduled jobs call it with the service role (SG-30).
create function public.purge_idempotency_keys()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  removed integer;
begin
  delete from public.idempotency_keys where created_at < now() - interval '24 hours';
  get diagnostics removed = row_count;
  return removed;
end;
$$;
revoke execute on function public.purge_idempotency_keys() from anon, authenticated, public;
grant execute on function public.purge_idempotency_keys() to service_role;
