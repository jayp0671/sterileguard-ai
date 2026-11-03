# TASKS

Mirror of ClickUp (SterileGuard workspace, folder SterileGuard AI). ClickUp is the source of truth.
Edit with `sg memory task add|done`.

Current sprint: Sprint 4 (Nov 2-8) Scenarios, shift logging, imports; midterm video due Nov 8

| ID | Title | Lead | Status | PR |
| --- | --- | --- | --- | --- |
| SG-00 | READ FIRST: agent briefing, hard rules, DoD | All | reference | |
| SG-01 | Monorepo, sg CLI core, repo memory, agent hooks, skills | Jay | done |  |
| SG-02 | Web and API scaffolds, typed API contract, CI | Jay, Carlos | done; CI and Docker image unverified |  |
| SG-03 | Supabase projects, tenancy schema, roles, RLS | Jay | done; staging migrated, pgTAP 23/23 |  |
| SG-04 | Auth: invite-only, password, magic link, TOTP, session policy | Jay | done; TOTP journey pending demo users |  |
| SG-05 | Test strategy and harness for every layer | Carlos | done; review pending |  |
| SG-06 | Real data intake: week 1, log template, sim parameters | Leo | repo done; Leo tasks pending |  |
| SG-07 | Course admin: Carlos joined | All | done | |
| SG-08 | Canonical schema, shift tables, datasets, audit log | Leo, Jay | done | #2 |
| SG-09 | SimPy simulator, calibration, 5,000-day dataset | Leo, Jay | done; real-day calibration waits on Leo | #3 |
| SG-10 | Design system, app shell, styled auth | Jay | done; screenshots and web-design-guidelines audit pending | #4 |
| SG-11 | API security layer and Plan Tomorrow | Jay | done; staging migrated (0006) | #5 |
| SG-12 | Simulator correctness suite and RLS matrix | Carlos | done; matrix 375/375 on staging | #6 |
| SG-13 | ML pipeline: features, baselines, GBM with ranges, tuning, evaluation | Leo | done; ADR-0005 and term dates need Leo | #8 |
| SG-14 | SHAP drivers and model registry with hot swap | Leo, Jay | done; staging migrated (0007); ADR-0006 needs Leo | #9 |
| SG-15 | Forecast API and Forecast home page | Jay | done; staging migrated (0008) | #10, #13 |
| SG-16 | Staging deployment, keep-alive, demo seed | Jay, Leo | done; web on Vercel, API on Render (ADR-0007); shared demo users not created | #12, #15-#19 |
| SG-17 | ML activation gates and first E2E journeys | Carlos | gates done; E2E specs written, never run (need demo users + E2E_* secrets) | #11 |
| SG-18 | Midterm presentation and live demo (moved to Nov 8, video) | All | deck updated, live demo works; placeholders, narrated video and Canvas are the team's | #14 |
| SG-19 | Staffing scenario engine, API, Scenarios page | Leo, Jay | done; staging migrated (0009); ADR-0008 needs Leo; screenshots on the PR; staffing sensitivity finding for Leo | #21, #28 |
| SG-20 | Shift actuals: API, Log a shift, history, approvals, backfill | Jay | done; staging migrated (0010); screenshots on the PR | #22, #27 |
| SG-21 | Import pipeline v1 and PHI guard | Leo | done; staging migrated (0011); ADR-0009 needs Leo | #23 |
| SG-22 | Tests: messy fixtures, import and PHI tests, contract fuzzing | Carlos | done; contract job nightly | #24 |
