# 0011. NIM agents: hosted API details, guardrail and stand-in cassettes

- Status: proposed (needs a human reviewer: Leo for the mapping agent, Carlos for the evals)
- Date: 2026-11-23
- Deciders: Jay
- Ticket: SG-23 (and SG-26 Part B)

## Context and problem statement

SG-23 asks for a NIM client, a briefing agent with a number guardrail and an import mapping
agent, with migration `0010_agents.sql`. Several details differ from the ticket or could not be
done as written:

1. Migrations 0010 to 0012 were already taken.
2. The ticket asks for JSON response format "if the chosen model supports it". The hosted
   chat schema (docs.api.nvidia.com, llama-3.3-70b-instruct, checked 2026-11-23) has no
   `response_format`, `guided_json` or `nvext` field.
3. Model IDs must be confirmed callable on the free tier, but no `NIM_API_KEY` is configured.
4. The ticket places the mapping agent in `sg_data/imports/llm_mapping.py`.
5. The guardrail must reject a person's name. The PHI guard uses spaCy's small English model,
   which reads ordinary Spanish words as names.

## Decision outcome

1. The migration is `0013_agents.sql`: `agent_calls` (hashes only) and `agent_cache`. RLS is
   enabled with no policies, and anon and authenticated have no privileges. The API writes
   through the service role. Both tables are in the RLS matrix (all 8 actors denied).
2. The mapping agent asks for a JSON array in the prompt, strips code fences, validates with
   Pydantic, and retries once with a corrective message.
3. Models are pinned in `ops/prompts/models.yaml` from the NVIDIA catalog
   (`meta/llama-3.3-70b-instruct` for briefing, mapping and translation;
   `qwen/qwen2.5-coder-32b-instruct` for coding). `sg agents ping` confirms them once Jay adds
   the key (ops/runbooks/nim.md). Until then, `NIM_MODE` defaults to `off` and every agent uses
   its fallback.
4. The mapping agent lives in `sg_agents/mapping.py`, so `sg_data` (CLI, deterministic
   pipeline) has no LLM dependency. The API injects it into the import service.
5. For English, the guardrail runs the full PHI guard. For Spanish it keeps the pattern
   recognizers (email, phone, SSN, MRN, honorific + surname) but ignores spaCy's PERSON. The
   input never contains names, and SG-27 can add a Spanish model.

Also:

- Guardrail numbers: the input is rounded to 1 decimal once, in `build_input`. The answer may
  use only numbers from the input's values or from its strings (driver texts, the date).
  Spanish decimal commas count. `burden_prob_pct` is in the input, so "70%" is allowed.
- Only LLM answers that pass the guardrail are cached. They are cached per forecast and locale.
- **The cassettes are hand-written stand-ins** (`"stand_in": true`, written by
  `make_cassettes.py`). They test the client, parsing, guardrail, fallback and payload rules,
  but they say nothing about the model's real answers. The evals' 100% mapping accuracy
  measures the pipeline, not the model. `sg agents record` replaces them with live answers.

### Consequences

- Good: CI and local tests make zero live calls (the transport is disabled in conftest), and
  the product works the same with or without a key.
- Bad: model quality is unmeasured until live cassettes are recorded, and a model ID could
  have left the catalog without us knowing.

## Links

- Plan sections: §10.1, §13
- Code: `packages/agents/src/sg_agents/`, `ops/prompts/`, `apps/api/src/sg_api/routers/agents.py`,
  `supabase/migrations/0013_agents.sql`, `ops/runbooks/nim.md`
