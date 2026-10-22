---
name: sterileguard-conventions
description: Code style, folder rules, naming, branch and commit format, and the hard rules for the SterileGuard AI repo. Use before writing or reviewing any code in this repo.
---

# SterileGuard conventions

The full text lives in `ops/memory/CONVENTIONS.md`; read it. The essentials:

- Hard rules: no patient data, no employee names or IDs, real data never in git, no secrets in
  code, features known at 7:00 AM only, never claim HIPAA compliance, free tiers only, label
  recommendations "Model estimate, not a guarantee."
- Branch `sg-XX/short-name`; commits `type(scope): subject [SG-XX]`.
- Python: `src/` layout, Ruff (100 cols) and mypy strict. TS: strict, Biome.
- Migrations: new numbered files only, never edit a merged one. RLS on every table.
- Generated files (`packages/contracts/openapi.json`, `src/schema.d.ts`, `src/db.ts`,
  `ops/memory/STATE.md`) are never edited by hand.
- Deviations from `docs/PLAN.md` need an ADR (`sg memory adr new "Title"`).
