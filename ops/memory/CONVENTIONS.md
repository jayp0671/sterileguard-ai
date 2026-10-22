# Conventions

## Hard rules (from SG-00, never break)

1. No patient data and no employee names or IDs anywhere: database, logs, fixtures, prompts,
   screenshots. Counts and aggregates only.
2. Real data never enters git. Real rows live only in Supabase with `source = 'real'`. All test
   fixtures are synthetic.
3. No secrets in code. `.env` (gitignored) locally; GitHub, Vercel and Hugging Face secret stores
   in the cloud.
4. The forecast model uses only features known at 7:00 AM (feature registry, SG-13).
5. Never claim HIPAA compliance. Say "HIPAA-style safeguards" and "academic prototype".
6. Free tiers only. No paid services or SDKs that need billing.
7. Without an ADR and a human reviewer, never: edit merged migrations, weaken RLS, change auth
   settings, change legal page text, or edit test expectations to make tests pass.
8. Every staffing recommendation is labeled "Model estimate, not a guarantee."
9. When unsure about a third-party API (Supabase, Hugging Face, NIM, Vercel), check current docs.

## Branches and commits

- Branch per ticket: `sg-XX/short-name` (e.g. `sg-03/tenancy-rls`).
- Conventional commits referencing the ticket: `feat(api): forecast endpoint [SG-15]`.
  Types: feat, fix, docs, chore, refactor, test, perf, ci, build. Enforced by lefthook.
- PR title `[SG-XX] ...`, acceptance checklist ticked, screenshots for UI, one teammate review,
  squash merge.

## Folders

- `apps/web` Next.js (@sg/web); `apps/api` FastAPI (sg_api).
- `packages/{data,sim,ml,agents}` Python (sg_data, sg_sim, sg_ml, sg_agents), `src/` layout.
- `packages/contracts` generated OpenAPI + TS types. Never hand-edit generated files.
- `supabase/migrations/NNNN_name.sql`, numbered in ticket order. Add new ones; never edit merged.
- `ops/scripts` the sg CLI; `ops/memory` repo memory; `ops/reports` generated output.
- Docs in `docs/` (PLAN.md, adr/, domain/, security/, testing.md, ai-usage-log.md).

## Naming and style

- Python: Ruff (line length 100, rules E,F,I,B,UP,SIM,RUF), mypy strict, snake_case modules.
- TypeScript: strict, `noUncheckedIndexedAccess`, Biome formatting, PascalCase components,
  camelCase functions, kebab-case file names for routes.
- SQL: snake_case, plural table names, every FK indexed, RLS enabled on every table.
- Tests: `test_<unit>_<behavior>` (Python), `<component>.test.tsx` (web),
  `<journey>.spec.ts` (Playwright).
