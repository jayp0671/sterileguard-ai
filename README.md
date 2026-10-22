# SterileGuard AI

SterileGuard AI forecasts next-day overtime for a hospital Dental Central Sterile department and
recommends staffing changes before the shift starts. It shows an overtime estimate with an 80%
range, a burden category, plain-language drivers (SHAP), staffing scenarios and a short AI
briefing. It is decision support only, stores no patient data, and is an academic prototype for
CPE 595 Applied Machine Learning (Stevens, Group 8). HIPAA-style safeguards, not HIPAA certified.

## Quickstart

Needs git, Node 24 (see `.nvmrc`), pnpm, uv, and Docker for the local database.

```bash
uv run sg bootstrap
uv run sg doctor
uv run sg dev
```

Web runs on http://localhost:3000, the API on http://localhost:8000.

## Links

- [AGENTS.md](AGENTS.md): how people and AI agents work in this repo
- [docs/PLAN.md](docs/PLAN.md): technical plan v1.0
- [docs/ai-usage-log.md](docs/ai-usage-log.md): AI tools used and how
- [docs/testing.md](docs/testing.md): test strategy

## AI tools used

Claude Code and Codex for implementation, NVIDIA NIM for in-app agents. See the AI usage log.
