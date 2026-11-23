-- SG-23: LLM usage log and response cache (plan §13). The ticket names this 0010_agents.sql;
-- 0010 to 0012 were already taken, so it is 0013.
--
-- agent_calls keeps hashes, token counts, latency and status, never prompt or answer text.
-- agent_cache keeps guarded answers (the briefing text, mapping suggestions) keyed by
-- sha256(agent + prompt_version + model + canonical input JSON + locale).
-- Only the API's service role reads or writes either table: no policy grants anything to
-- signed-in users, and anon and authenticated have no table privileges at all.

create table public.agent_calls (
  id bigint generated always as identity primary key,
  agent text not null check (agent in ('briefing', 'mapping', 'translation', 'coding')),
  model text not null check (char_length(model) <= 200),
  prompt_version text not null check (char_length(prompt_version) <= 20),
  input_hash text not null check (input_hash ~ '^[0-9a-f]{64}$'),
  output_hash text check (output_hash ~ '^[0-9a-f]{64}$'),
  tokens_in integer check (tokens_in >= 0),
  tokens_out integer check (tokens_out >= 0),
  latency_ms integer check (latency_ms >= 0),
  status text not null check (char_length(status) <= 40),
  created_at timestamptz not null default now()
);
comment on table public.agent_calls is 'SG-23: one row per NIM call; hashes only, never text.';
create index agent_calls_created_at_idx on public.agent_calls (created_at desc);
create index agent_calls_agent_created_idx on public.agent_calls (agent, created_at desc);

create table public.agent_cache (
  key text primary key check (key ~ '^[0-9a-f]{64}$'),
  agent text not null check (agent in ('briefing', 'mapping', 'translation', 'coding')),
  value jsonb not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '30 days'
);
comment on table public.agent_cache is 'SG-23: guarded agent answers; service role only.';
create index agent_cache_expires_at_idx on public.agent_cache (expires_at);

alter table public.agent_calls enable row level security;
alter table public.agent_cache enable row level security;
revoke all on public.agent_calls, public.agent_cache from anon, authenticated;
