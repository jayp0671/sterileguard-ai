# Handoff log

Append-only. One entry per session: date, person or agent, ticket, done, next, gotchas.
Add entries with `sg memory handoff --ticket SG-XX --done "..." --next "..." --gotchas "..."`.

## 2026-10-21 · Claude Code (for Jay) · SG-02

- Done: Next 16.4.2 web (shadcn radix-nova, zod env, Supabase SSR clients, health page), FastAPI (problem+json, request IDs, JSON logs, /health, /ready), @sg/contracts (openapi-fetch client, ApiError), sg contracts gen/check, sg test unit/api/affected, ci.yml with 7 jobs, API Dockerfile
- Next: SG-03 tenancy schema and RLS
- Gotchas: Next 16 renamed middleware.ts to proxy.ts. shadcn v4 has no 'form' component; 'field' replaces it. vitest 5/jsdom 30 need Node 22+, so .npmrc pins use-node-version=24.22.1. Root .env is loaded by next.config.ts. Docker image build not yet verified locally (Docker Desktop was starting).
