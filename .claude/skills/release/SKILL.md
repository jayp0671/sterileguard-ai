---
name: release
description: Release and smoke-test procedure for SterileGuard AI (web on Vercel, API on Hugging Face Spaces, Supabase migrations). Use when cutting a release or deploying.
---

# Release

Skeleton until SG-34 builds `sg release`. Procedure:

1. Main is green in CI; `sg test all` passes locally.
2. `sg db migrate --env staging`, verify, then `sg db migrate --env prod --confirm` (prints
   pending migrations first).
3. Tag `vX.Y.Z` on main. `release.yml` deploys the API Space and runs smoke tests; Vercel
   deploys the web app from main.
4. Wake the Hugging Face Space and Supabase before a demo (`sg ops keepalive`).
5. `sg release smoke` against the live URLs: sign-in page loads, `/health` returns ok, the
   forecast page renders.
6. Update `CHANGELOG.md`, `sg memory sync`, add a handoff entry.
7. Rollback: redeploy the previous tag; never edit merged migrations (write a forward fix).
