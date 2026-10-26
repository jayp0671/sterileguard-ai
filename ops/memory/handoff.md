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

## 2026-10-22 · Claude Code (for Jay) · Sprint 1 close

- Done: ClickUp SG-02 to SG-06 marked complete with comments; TASKS.md updated
- Next: Jay: gh auth login and Docker in the agent session, then: open the PR for sprint1/verify, read CI and fix it, supabase start + local keys into .env, local db tests, API image build + /ready, local demo users for the role e2e spec. Then Sprint 2: SG-08
- Gotchas: none new

## 2026-10-22 · Claude Code (for Jay) · SG-08

- Done: sg_data.schema (FieldSpec registry, to_pandera, to_pydantic, db_columns), defaults.fill_tier2, 0004_shift_data (datasets, shift_plans, shift_actuals, RLS), 0005_audit (append-only audit_log + audit_row_change on 6 tables), pgTAP 0004 (23), drift test, repo field-list scan; local and staging migrated, pgTAP 46/46 on both
- Next: SG-09 simulator
- Gotchas: Ticket named the files 0003_shift_data/0004_audit; 0003 was taken, so they are 0004/0005 and SG-11 idempotency becomes 0006. to_pandera returns a DataFrameSchema (runtime-generated columns). Missing-setting Tier 2 defaults use FieldSpec.fallback. gh is not logged in, so PRs are opened by Jay.

## 2026-10-22 · Claude Code (for Jay) · SG-09

- Done: sg_sim: process-per-worker SimPy model (staff windows, stayers, batch washers/sterilizers with load wait, downtime, BI recall, carryover), sampler, simulate_day/sequence, export validated by sg_data schema, LHS 5,000-day dataset (250x20 workdays, multiprocessing) in local and staging (dataset 5fa1a749, 5000 plans + 5000 actuals), calibrate (Optuna TPE) + validate (KS), sg sim run/calibrate/validate; 24 tests; ADR-0003
- Next: SG-10 design system and shell
- Gotchas: First-draft machine capacity and stage times could not clear a day; capacities raised to 40 load units and stage_time 0.55 pre-calibration (ADR-0003, Leo to verify). No real days yet, so calibration is plausibility-only (dental_cs.calibrated.yaml); MAE criterion waits for Leo's week 1. Windows: spawned pool needs OPENBLAS_NUM_THREADS=1. Carryover capped at 400 units between days.

## 2026-10-24 · Claude Code (for Jay) · SG-10

- Done: ADR-0004 design direction (instrument panel, surgical steel); tokens.css (steel/teal scales, status sets, hex for exact contrast) mapped into Tailwind and shadcn; IBM Plex via next/font; next-themes; sg test a11y --tokens (51 contrast checks); brand mark, favicon, PWA icons and manifest; MetricCard, BurdenBadge, StatusPill, DriverList, StaffTimeline, EmptyState, ErrorState, PageHeader, DataTable (TanStack v9), ChartFrame, all tested; app shell (role-filtered sidebar from GET /v1/me, department switcher, language, theme, user menu, Ctrl/Cmd+K palette, skip link); split-layout auth screens; /app/style (404 in production); GET /v1/me
- Next: SG-11 API security and Plan Tomorrow
- Gotchas: TanStack Table v9 uses tableFeatures() and useTable; numeric columns sort descending first. Biome 2.6 also formats YAML. NEXT_PUBLIC_APP_ENV gates the style page. web-design-guidelines skill is not installed here, so that audit is still open. Repo moved into OneDrive - stevens.edu: OneDrive locks node_modules and .venv files; work happened in a worktree at AppData\Local\sg-wt.

## 2026-10-24 · Claude Code (for Jay) · SG-11

- Done: JWKS cache 10 min, 403 mfa-required problem type; require_role (path/query/body department, 60 s membership cache, 403 forbidden-role, 404 for non-members); db/user_client and db/service_client; X-Request-ID forwarded to PostgREST; rate limits on limits (120/min default, forecasts POST and scenarios 30/min, agents 10/min, 429 with Retry-After, verified-user keys); Idempotency-Key middleware + 0006_idempotency.sql (staging applied); GET/PUT /v1/plans/{date} with suggestions, sources and date rules; /app/plan page generated from OpenAPI (labels and groups from schema.py), 10 s debounced autosave with Idempotency-Key, finalize, 409 reload, read-only for technicians
- Next: SG-12 tests
- Gotchas: Migration is 0006 (0005 is the audit log). slowapi was dropped: its middleware cannot see routes in included routers on FastAPI 0.120+, so every route was exempt; limits used directly. Idempotency middleware must sit inside GZip. 0006 was applied to staging with psycopg plus a supabase_migrations.schema_migrations row (supabase CLI was unavailable), so db push sees it as applied. PlanPut is the OpenAPI component the form reads.

## 2026-10-24 · Claude Code (for Jay) · SG-12

- Done: test_correctness.py: Hypothesis property (conservation, overtime bounds, staff pool, presence, machine counts, downtime), reproducibility (assert_frame_equal + content_hash), hand-computed golden scenario (8.5 h), slow directional and performance tests; 0010_rls_matrix.test.sql: 11 tables x 4 ops x 8 actors from a rules table, one-audit-row checks for 6 audited tables, coverage of every public table, helper search_path and anon checks; mutation proof on staging (loosened shift_plans_insert -> 2 unexpected allows, rolled back); sg test db aliases sg db rls-test; CI db job gated on DB changes but always reports; db-nightly.yml
- Next: Sprint 3: open and merge the stacked PRs SG-08 to SG-12, then SG-13 feature registry and first model
- Gotchas: Stayers decide one at a time, so the first to leave can make the next stay (golden case). Local pgTAP not run this session (Docker Desktop off); staging 375/375. Matrix must be extended by every DB ticket; the coverage assertion enforces it.

## 2026-10-24 · Claude Code (for Jay) · Sprint 2 close

- Done: PRs #2 to #6 (SG-08 to SG-12) merged with all 8 required checks green; stacked branches rebased onto main after each squash merge; fixed sg db types writing Supabase CLI messages into db.ts; RLS matrix verified in CI under pg_prove
- Next: Sprint 3: SG-13 feature registry and first model on the 5,000-day simulated dataset
- Gotchas: Vercel preview deployments fail (not a required check); inspect with vercel inspect. Local pgTAP still needs Docker Desktop. Calibration against real days waits on Leo.

## 2026-10-25 · jayp0671 · SG-13

- Done: sg_ml: feature registry (known_at_7am, LeakageError, full/core sets, engineered/calendar/lag/__missing features, coefficients from the calibrated sim config), FieldSpec.monotone in sg_data, baselines (rule, Ridge, logistic both ways), monotone HGB with 80% range, calibrated classifier, RF, Optuna TPE, evaluation JSON + Markdown report, sg ml train/compare/notebook, notebooks 01 and 02, ml-notebooks CI job, ADR-0005. Tuned run on calibrated dataset a76064e0: MAE 0.819 vs Ridge 1.909 (57% better), 80% coverage 0.804, core MAE 6.74
- Next: SG-14 SHAP drivers and model registry
- Gotchas: The staging 5,000-day dataset 5fa1a749 was generated from dental_cs.yaml, not the calibrated config (sg sim run defaults to the uncalibrated file); training uses a76064e0 regenerated with --config dental_cs.calibrated.yaml (local parquet only, not uploaded yet). sim parquet now gets a .json lineage sidecar. sklearn 1.9 HGB quantile loss sticks at 0 when many targets tie with the start value and breaks monotonic constraints: see ADR-0005 (served p50 is the squared-error model). week_of_semester term dates are placeholders for Leo. Field-scan test now skips data/ (gitignored run output).
