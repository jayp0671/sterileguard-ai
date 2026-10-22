# AGENTS.md

Entry point for Codex, Claude Code and any other coding agent working on SterileGuard AI.

## Project

SterileGuard AI forecasts next-day overtime for the morning operation (7:00 AM to 3:00 PM) of a
hospital Dental Central Sterile department and recommends staffing changes the evening before.
Outputs: overtime labor-hours with an 80% range, a burden category with probability, SHAP drivers
in plain language, staffing scenarios with a minimum-change recommendation, a short LLM briefing,
and predicted vs actual tracking. Decision support only: it never makes staffing decisions.
Academic prototype for CPE 595 (Stevens, Group 8). Stack: Next.js on Vercel, FastAPI on a
Hugging Face Space, Supabase (Postgres, Auth, Storage), scikit-learn, SimPy, NVIDIA NIM.

## Hard rules (never break)

1. No patient data, no employee names or IDs anywhere (DB, logs, fixtures, prompts, screenshots).
2. Real data never enters git. It lives only in Supabase with `source = 'real'`. Fixtures are synthetic.
3. No secrets in code. Use `.env` locally and the GitHub, Vercel, Hugging Face secret stores.
4. The model uses only features known at 7:00 AM.
5. Never claim HIPAA compliance. Say "HIPAA-style safeguards" and "academic prototype".
6. Free tiers only.
7. Without an ADR and a human reviewer, do not edit merged migrations, weaken RLS, change auth
   settings, change legal page text, or edit test expectations to make tests pass.
8. Every staffing recommendation is labeled "Model estimate, not a guarantee."
9. Check current official docs before using a third-party API detail you are unsure of.

## Start of every session

1. Read `ops/memory/STATE.md` and the tail of `ops/memory/handoff.md`.
2. Read ClickUp ticket SG-00 and the ticket you are working on, plus the plan sections it cites
   (`docs/PLAN.md`).
3. If the ticket conflicts with the code or plan, stop and record it in `handoff.md` and the PR.

## How to run things

- `sg --help` lists everything. Every command takes `--dry-run` and `--json`.
- `sg doctor` checks your machine. `sg bootstrap` installs. `sg dev` runs web (3000) and API (8000).
- `sg memory sync` rebuilds STATE.md. `sg memory handoff` appends a handoff entry.
- `sg memory adr new "Title"` creates an ADR. `sg test ...` runs tests (SG-05).
- Python: `uv run ...`. JS: `pnpm ...` / `pnpm --filter @sg/web ...`.

## Definition of Done

- Branch `sg-XX/short-name`, conventional commits referencing the ticket
  (`feat(api): forecast endpoint [SG-15]`).
- Every acceptance criterion met and ticked in the PR description.
- New behavior covered by tests; `sg test affected` and CI green.
- No secrets, real data or PHI in the diff (gitleaks clean).
- `ops/memory/handoff.md` updated, `sg memory sync` run, ADR for any deviation from the plan.
- PR titled `[SG-XX] ...` with screenshots for UI changes, one teammate review, squash merge.
- ClickUp ticket set to complete with the PR link in a comment.
- Log meaningful AI help in `docs/ai-usage-log.md`.

## Where things live

- `docs/PLAN.md` technical plan (source of truth). `docs/adr/` decisions. `docs/domain/` domain
  reference. `docs/testing.md` test strategy. `docs/ai-usage-log.md` AI usage.
- `ops/memory/` STATE, TASKS, handoff, DECISIONS, CONVENTIONS, GLOSSARY.
- `ops/runbooks/` auth settings, deploy, restore, data import.
- `supabase/` migrations, seed, pgTAP tests.
- Conventions: `ops/memory/CONVENTIONS.md`. Domain terms: `ops/memory/GLOSSARY.md`.
