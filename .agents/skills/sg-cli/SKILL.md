---
name: sg-cli
description: Which sg command to run for which job in the SterileGuard repo (setup, database, tests, memory, contracts). Use whenever you need to run, test, migrate, or record work.
---

# sg CLI

Run as `uv run sg <group> <command>`. Every command accepts `--dry-run` and `--json` in any
position and writes a report to `ops/reports/<group>/`.

| Job | Command |
| --- | --- |
| Check machine | `sg doctor` |
| First-time setup | `sg bootstrap` |
| Run everything locally | `sg dev` (web 3000, API 8000) |
| Rebuild STATE.md | `sg memory sync` |
| Record the session | `sg memory handoff --ticket SG-XX --done "..." --next "..." --gotchas "..."` |
| New decision record | `sg memory adr new "Title"` |
| Update task mirror | `sg memory task done SG-XX --pr <url>` |
| Database | `sg db migrate --env local|staging`, `sg db reset`, `sg db types`, `sg db lint` |
| Contracts | `sg contracts gen` after any API response model change |
| Tests | `sg test unit`, `sg test api`, `sg test e2e --project chromium`, `sg test affected` |

Commands that print "not implemented yet, see SG-XX" are stubs; the named ticket builds them.
Prefer sg over ad-hoc scripts so reports and memory stay consistent.
