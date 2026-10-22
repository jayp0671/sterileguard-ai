# Handoff log

Append-only. One entry per session: date, person or agent, ticket, done, next, gotchas.
Add entries with `sg memory handoff --ticket SG-XX --done "..." --next "..." --gotchas "..."`.

## 2026-10-21 · Claude Code (for Jay) · SG-02

- Done: Next 16.4.2 web (shadcn radix-nova, zod env, Supabase SSR clients, health page), FastAPI (problem+json, request IDs, JSON logs, /health, /ready), @sg/contracts (openapi-fetch client, ApiError), sg contracts gen/check, sg test unit/api/affected, ci.yml with 7 jobs, API Dockerfile
- Next: SG-03 tenancy schema and RLS
- Gotchas: Next 16 renamed middleware.ts to proxy.ts. shadcn v4 has no 'form' component; 'field' replaces it. vitest 5/jsdom 30 need Node 22+, so .npmrc pins use-node-version=24.22.1. Root .env is loaded by next.config.ts. Docker image build not yet verified locally (Docker Desktop was starting).

## 2026-10-21 · Claude Code (for Jay) · SG-03

- Done: supabase init (signups off, TOTP on, 900s JWT, 12-char passwords), 0001_tenancy.sql (app_role, orgs/facilities/departments/profiles/memberships, aal2-gated RLS, security-definer helpers), seed.sql, pgTAP smoke test, supabase/README.md RLS pattern, sg db migrate/reset/seed/types/lint/rls-test, CI db job
- Next: SG-04 auth
- Gotchas: Docker Desktop would not start in the agent session, so the migration and RLS matrix were checked in PGlite with a stubbed auth schema (24/24). pgTAP runs in the CI db job. Staging is not migrated yet: the Supabase MCP only sees an unrelated project; needs SUPABASE_DB_URL_STAGING or MCP access to sterileguard-ai. Prod project not created.

## 2026-10-21 · Claude Code (for Jay) · SG-04

- Done: 0002_invites (RLS, accept_pending_invites), 0003_session_policy (session_age_seconds), API JWKS verification + aal2 + 12h server check + recent-TOTP dependency, POST /v1/admin/invites (+resend, revoke) with domain and platform_admin rules, POST /v1/audit/auth-event, web proxy route guard, /auth/confirm, sign-in, magic-link, accept-invite (zxcvbn), reset-password, mfa enroll/challenge, idle timeout modal, sign out of all devices, ReauthDialog, auth-settings runbook, ADR-0002
- Next: SG-05 test harness
- Gotchas: Dashboard auth settings, SMTP, Turnstile secret and email templates must be applied by hand from ops/runbooks/auth-settings.md. citext operators are not visible under search_path='', so emails compare with lower(). zxcvbn-ts v4 uses ZxcvbnFactory. Email links must use the token_hash templates in the runbook.

## 2026-10-21 · Claude Code (for Jay) · SG-05

- Done: docs/testing.md (all 16 layers), pytest strict markers + Hypothesis ci/dev profiles + polyfactory + per-member conftests, 80% coverage gate on sg_api/sim/ml/data, Vitest with RTL + MSW (no network) + 70% coverage gate, Playwright (chromium/firefox/webkit/tablet, per-role TOTP global setup via otplib), sg test unit/api/db/e2e/a11y/visual/affected/all (+ stubs for load/security/i18n/agents), JUnit + latest.json, bug and PR templates
- Next: SG-06 real data intake docs and template
- Gotchas: MSW 3 renamed onUnhandledRequest to onUnhandledFrame. Role-scoped e2e specs skip until SG-16 seeds demo users and E2E_* env vars are set. docs/testing.md needs Jay and Leo review.

## 2026-10-21 · Claude Code (for Jay) · SG-06

- Done: docs/domain/daily-log-template.xlsx + .csv (exact column names, README sheet, validation, no values), data-dictionary.md (5 questions with proposed answers marked TO CONFIRM, every field defined), parameters.md (every parameter with source and confidence, estimates marked), data-access.md (status table plus both request drafts), .gitignore guard for real-data filenames
- Next: Sprint 2 starts with SG-08 (schema and shift tables). First: Jay applies the blocked items listed in STATE (Supabase access, Docker, auth dashboard settings), then mark SG-02..SG-06 in ClickUp
- Gotchas: Only Leo can: fill week 1 privately, answer the five TO CONFIRM questions, verify parameters, send both approval requests, and log 5+ real days. ClickUp writes were denied for this agent after SG-01, so SG-02..SG-06 status and comments still need updating in ClickUp.

## 2026-10-22 · Claude Code (for Jay) · Sprint 1 verify

- Done: .env split into local and *_STAGING blocks (DB password URL-encoded, backup in .env.bak); sg db guards local vs hosted and redacts URLs; Python pgTAP runner; staging migrated (0001-0003), seeded, lint clean, pgTAP 23/23; unit 77/39/4 pass; e2e chromium 3 pass, 1 skip; ClickUp SG-02 and SG-03 marked complete with comments
- Next: Open a PR for sprint1/verify; mark SG-04, SG-05, SG-06 complete in ClickUp; run local stack, db tests, Docker image build and CI check once Docker and gh work in the agent session; create local demo users to unblock the role spec
- Gotchas: Docker and gh are not visible from the agent session (no daemon pipe; gh not logged in). Local SUPABASE_ANON_KEY and NEXT_PUBLIC_SUPABASE_ANON_KEY are empty until 'supabase status -o env'. The agent will not create accounts on hosted Supabase.
