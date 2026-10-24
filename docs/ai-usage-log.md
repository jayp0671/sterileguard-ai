# AI usage log

Every meaningful use of an AI tool on this project. The course grades this.

| Date | Person | Tool | Purpose | Prompt summary | Contribution | Review |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-21 | Jay | Claude Code (Opus) | SG-01 to SG-06 implementation | Build Sprint 1 tickets from ClickUp specs and the technical plan | Generated scaffolding, CLI, schema, auth flows, test harness, docs | Jay reviews each PR before merge |
| 2026-10-22 | Jay | Claude Code (Opus) | SG-08 canonical schema, shift tables, audit log | Implement the ClickUp spec: one field registry, generated validators, migrations with RLS and audit | schema.py, defaults, migrations 0004/0005, pgTAP, drift and field-scan tests | Jay reviews the PR; Leo checks field ranges |
| 2026-10-22 | Jay | Claude Code (Opus) | SG-09 SimPy simulator | Build the discrete-event model, sampler, LHS dataset, calibration and sg sim commands | sg_sim package, configs, 5,000-day dataset on staging, ADR-0003 | Leo verifies parameters and capacity estimates |
| 2026-10-24 | Jay | Claude Code (Opus) | SG-10 design system and shell | frontend-design direction, tokens, components, app shell, auth screens, GET /v1/me | Web components and tests, ADR-0004 | Jay reviews UI in the browser before merge |
| 2026-10-24 | Jay | Claude Code (Opus) | SG-11 API security and Plan Tomorrow | Roles, rate limits, idempotency, plans endpoints and page | API middleware and routes, migration 0006, plan page and tests | Jay reviews; security review before release |
| 2026-10-24 | Jay | Claude Code (Opus) | SG-12 simulator tests and RLS matrix | Property and golden tests; table x operation x actor matrix in pgTAP | test_correctness.py, 0010_rls_matrix.test.sql, CI db gating | Carlos reviews the matrix rules against plan §2.2 |
