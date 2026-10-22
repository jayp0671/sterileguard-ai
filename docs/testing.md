# Test strategy

Owner: Carlos (QA and Testing Lead). Status: draft for review by Jay and Leo (SG-05).
Plan reference: §15. Every layer has a runner, a folder, one `sg test` command and a CI job, so a
feature ticket only adds tests, never setup.

## Layers

| Layer | Tool | Folder | `sg test` command | CI job | Owner | When |
| --- | --- | --- | --- | --- | --- | --- |
| Static | TypeScript strict, Biome, Ruff, mypy strict | everywhere | (lint/typecheck jobs) | `lint`, `typecheck` | Jay | pre-commit, PR |
| Web unit | Vitest, Testing Library, MSW | `apps/web/src/**/*.test.ts(x)` | `unit --web-only` | `test-web` | Jay | pre-push, PR |
| API and ML unit | pytest, Hypothesis, polyfactory | `apps/api/tests`, `packages/*/tests` | `unit --python-only`, `api` | `test-py` | Jay, Leo | pre-push, PR |
| Contract | OpenAPI regen + drift check; Schemathesis (SG-22) | `packages/contracts` | `sg contracts check` | `contracts` | Jay, Carlos | PR |
| Database | pgTAP via Supabase CLI | `supabase/tests` | `db` | `db` | Jay, Carlos (SG-12) | PR |
| Data | pandera | `packages/data/tests` | `unit` | `test-py` | Leo (SG-21) | PR |
| ML gates | pytest | `packages/ml/tests` | `unit` | `test-py` | Leo (SG-13, SG-17) | PR, weekly retrain |
| Simulation | pytest | `packages/sim/tests` | `unit` | `test-py` | Leo (SG-09, SG-12) | PR |
| End-to-end | Playwright (chromium, firefox, webkit, tablet) | `apps/web/e2e/*.spec.ts` | `e2e [--project X] [--headed]` | `e2e.yml` (SG-17) | Carlos | PR, release |
| Visual regression | Playwright screenshots, `@visual` tag | `apps/web/e2e` | `visual [--update]` | `e2e.yml` | Carlos (SG-31) | PR |
| Accessibility | axe-core for Playwright, Lighthouse CI, `@a11y` tag | `apps/web/e2e` | `a11y` | `e2e.yml` | Carlos (SG-28) | PR, release |
| i18n | custom checks, pseudo-locale | `apps/web/src/messages` | `i18n` | `i18n.yml` | Carlos (SG-27) | PR |
| Load | k6 | `ops/load` | `load` | manual | Carlos (SG-31) | before demos |
| Security | gitleaks, CodeQL, Semgrep, audits, ZAP baseline | repo | `security` | `secrets`, `security.yml` | Carlos (SG-28) | pre-commit, PR, weekly |
| Agent evals | pytest with recorded NIM responses, `nim` marker | `packages/agents/tests` | `agents` | `test-py` | Jay, Carlos (SG-26) | PR |
| Smoke | Playwright against live URLs | `apps/web/e2e/smoke` | `e2e` with `E2E_BASE_URL` | `release.yml` | Carlos (SG-34) | after deploy |

`sg test affected` runs only what changed since `origin/main` (pytest for touched Python members,
`turbo run test --filter=...[origin/main]` for JS); a change to `pyproject.toml` or `uv.lock`
runs every Python member. `sg test all` runs unit, api, db (if local Supabase is up) and e2e on
chromium.

Every command writes JUnit XML and upserts `ops/reports/test/latest.json`
(`suite, passed, failed, skipped, duration_s, timestamp, commit`). `sg memory sync` copies the
summary into `ops/memory/STATE.md`.

## Test data rules

- Synthetic only. Never real data, never patient or employee names, not even in fixtures.
- Factories (polyfactory for Pydantic models) and fixed seeds (`__random_seed__ = 595`,
  Hypothesis `derandomize=True` in CI).
- No network in unit tests: MSW fails any unhandled request in Vitest; Python tests use fakes or
  `httpx.MockTransport`. NVIDIA NIM calls are recorded once and replayed (`nim` marker).
- E2E credentials come from `E2E_<ROLE>_EMAIL`, `E2E_<ROLE>_PASSWORD` and
  `E2E_<ROLE>_TOTP_SECRET` env vars, never the repo. Storage state goes to the gitignored
  `apps/web/e2e/.auth/`. Users come from `sg demo seed-demo` (SG-16); until then, role specs skip.

## Naming

- Python: `test_<unit>_<behavior>` in `tests/test_<module>.py`.
- Web: `<component>.test.tsx`, `<module>.test.ts` next to the code.
- Playwright: `<journey>.spec.ts`; tags `@a11y`, `@visual`, `@smoke` in test titles.
- pytest markers (strict): `slow`, `integration`, `e2e`, `nim`.

## Coverage targets

- 80% lines on `sg_api`, `sg_sim`, `sg_ml`, `sg_data` (enforced by `[tool.coverage.report]
  fail_under`). `sg_cli` is tested but not held to the target.
- 70% lines on `apps/web/src/lib`, `src/hooks` and logic-bearing components (Vitest threshold).

## Hypothesis profiles

`HYPOTHESIS_PROFILE=ci` (CI): `max_examples=50, deadline=None, derandomize=True`.
`dev` (default locally): 100 examples. Registered in the repo-root `conftest.py`.

## Flaky test policy

1. Tag it: `@pytest.mark.skip(reason="flaky: SG-XX")` or Playwright `test.fixme` with the ticket.
2. Open a ClickUp ticket the same day with the failure output and request_id.
3. Fix within the sprint. A quarantined test older than one sprint blocks the next release.

## Bugs

Use `.github/ISSUE_TEMPLATE/bug.md`: steps, expected, actual, environment, request_id,
screenshots, severity (P0 blocks the demo, P1 breaks a journey, P2 everything else).
