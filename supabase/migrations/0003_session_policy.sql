-- SG-04: server-side enforcement of the 12-hour absolute session limit (plan §9.2).
-- Every access token carries a session_id claim that matches auth.sessions.id. The API calls this
-- with the user's token and rejects sessions older than 12 hours. Returns null when the session
-- no longer exists (signed out, including "sign out of all devices").

create function public.session_age_seconds()
returns integer
language sql
stable
security definer
set search_path = ''
as $$
  select extract(epoch from (now() - s.created_at))::integer
  from auth.sessions s
  where s.id = nullif(auth.jwt() ->> 'session_id', '')::uuid
    and s.user_id = (select auth.uid());
$$;
revoke execute on function public.session_age_seconds() from anon, public;
grant execute on function public.session_age_seconds() to authenticated;
