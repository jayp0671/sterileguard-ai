---
name: add-feature
description: End-to-end checklist for adding a feature to SterileGuard AI, from schema to API to UI to tests to docs to memory. Use when starting any feature ticket.
---

# Add a feature

Work through these in order. Skip a step only if the ticket clearly does not touch it.

1. **Read**: SG-00, the ticket, `ops/memory/STATE.md`, the handoff tail, and cited plan sections.
2. **Schema**: canonical fields in `packages/data` (one place, plan §10.2).
3. **Migration**: new `supabase/migrations/NNNN_name.sql`; RLS enabled; policies use
   `public.is_aal2()` plus `public.has_role(...)`; index every FK; `source`, `created_by`,
   timestamps on business rows. Add a pgTAP test in `supabase/tests/`.
4. **API**: router, service, repository, Pydantic schemas under `apps/api/src/sg_api`; role
   dependency; idempotency key on creates; problem+json errors; queries with the user's token.
5. **Contracts**: `sg contracts gen`; commit `openapi.json` and `schema.d.ts`.
6. **UI**: run `frontend-design` first; call the API only through `@sg/contracts`; strings in
   `src/messages/en.json`; WCAG 2.2 AA; footer disclaimer intact.
7. **Tests**: unit (pytest / Vitest), API, RLS, and an E2E journey if user-facing.
8. **Docs**: update `docs/` and add an ADR for any deviation from the plan.
9. **Memory**: `sg memory handoff ...`, `sg memory sync`, log AI help in `docs/ai-usage-log.md`.
10. **PR**: `[SG-XX] ...`, acceptance checklist ticked, screenshots, one teammate review.
