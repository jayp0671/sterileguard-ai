# 0001. Monorepo and tooling

- Status: accepted
- Date: 2026-10-21
- Deciders: Jay Patel (Tech Lead)
- Ticket: SG-01

## Context and problem statement

Three developers switch between Claude Code and Codex on macOS, Linux and Windows. We need a
single repository whose setup, commands and memory work the same for people, CI and agents.

## Considered options

1. One monorepo: pnpm + Turborepo for JS, a uv workspace for Python, one `sg` CLI (Typer).
2. Separate repos for web, API and ML.
3. Makefile-only tooling.

## Decision outcome

Chosen option 1, as in plan §5 and §16.

- Node: pnpm workspace (`apps/web`, `packages/contracts`) with Turborepo tasks build, dev, lint,
  typecheck, test. `.nvmrc` pins Node 24 (Active LTS).
- Python 3.12: uv workspace with members `apps/api`, `packages/{data,sim,ml,agents}`,
  `ops/scripts`, each in `src/` layout with its own `pyproject.toml` (hatchling).
- Lint and format: Biome for TS/JSON; Ruff (100 cols, E,F,I,B,UP,SIM,RUF) and mypy strict.
- `sg` CLI in `ops/scripts` (package `sg_cli`). Global `--dry-run` and `--json` are accepted in
  any position; every run writes `ops/reports/<group>/<timestamp>-<command>.md`.
- Repo memory in `ops/memory/`; `STATE.md` is generated deterministically (no timestamps) so
  `sg memory sync` is idempotent.
- Git hooks via lefthook (installed from npm so no global install is needed); gitleaks runs in
  pre-commit when installed locally and always in CI.
- Claude Code hooks call small stdlib-only Python scripts in `ops/scripts/hooks/` through
  `uv run --no-project` so they work on every OS.

### Deviations from the ticket

- The repository is **private** (`jayp0671/sterileguard-ai`), not public. Consequences: GitHub
  Actions minutes are capped (2,000/month free), CodeQL is not free on private repos, and the
  course requires a public repo by submission. Revisit before SG-34.
- One Supabase project (`sterileguard-ai`) acts as staging/dev for now; prod comes later (SG-03).

### Consequences

- Good: one clone, one bootstrap, one CLI for humans, CI and agents.
- Bad: two package managers to learn; Windows users need the `.cmd` shims on PATH.
