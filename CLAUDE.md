@AGENTS.md

## Claude Code notes

- Session start hook prints STATE.md and the handoff tail. The Stop hook reminds you to run
  `sg memory handoff` if you changed files without updating `handoff.md`.
- Edits are auto-formatted (Biome for ts/tsx/json, `ruff format` for py).
- Skills to use:
  - Planning a ticket: superpowers `writing-plans`, then `executing-plans`.
  - Any UI: `frontend-design` first; `web-design-guidelines` before release.
  - SQL and RLS: `postgres-best-practices`. Supabase MCP is staging only and read-only by default.
  - Testing a running app: `.claude/skills/webapp-testing`.
  - Project skills: `sterileguard-conventions`, `sg-cli`, `sterile-processing-domain`,
    `add-feature`, `release` (in `.claude/skills/`).
  - Before a PR: `/review` and `/security-review`.
- Prefer `sg` commands over ad-hoc scripts so reports land in `ops/reports/`.
