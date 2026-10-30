# Deploy runbook: staging (SG-16, ADR-0007)

Staging = Vercel (web) + Render (API, free Docker web service) + the staging Supabase project.
Free tiers only. Secrets live only in the Vercel, Render and GitHub secret stores, never in git.

## One-time setup (Jay, about 10 minutes)

### 1. API on Render

1. Sign in at https://dashboard.render.com with GitHub (free; no card needed).
2. **New > Blueprint**, connect the `jayp0671/sterileguard-ai` repository, branch `main`.
   Render reads `render.yaml` and shows one service, `sterileguard-api` (Free).
3. It asks for two values. Open the repo's `.env` and copy:
   - `SUPABASE_ANON_KEY` ← the value of `SUPABASE_ANON_KEY_STAGING`
   - `SUPABASE_SERVICE_ROLE_KEY` ← the value of `SUPABASE_SERVICE_ROLE_KEY_STAGING`
4. **Apply**. The first build takes about 5 to 10 minutes. Then
   `https://sterileguard-api.onrender.com/ready` shows `"status": "ready"` and the model version.
   (If Render gives the service a different URL, put it in `.env` as `API_URL_STAGING`.)

After this, Render redeploys the API on every push to main once CI passes.

### 2. Web on Vercel, and GitHub settings

From the repo folder:

```
uv run sg deploy staging
```

It sets the Vercel project's Root Directory to `apps/web`, adds the `NEXT_PUBLIC_*` variables
(staging Supabase URL and anon key, the API URL, site URL), deploys to production, and sets the
GitHub secret `SUPABASE_DB_URL_STAGING` and variable `API_URL` for the keep-alive workflow. It
reads `.env` and the CLI logins and never prints a secret. Safe to run again.

### 3. Demo users (for signing in)

Set `DEMO_EMAIL_BASE` in `.env` to a team inbox (for example `team@example.edu`; users become
`team+supervisor@...`), then:

```
uv run sg demo seed-demo --env staging
```

Logins and TOTP secrets land in `ops/secrets/demo-totp.json` (gitignored). For the e2e
workflow, copy the supervisor and technician values into GitHub secrets `E2E_SUPERVISOR_*` and
`E2E_TECHNICIAN_*` (`EMAIL`, `PASSWORD`, `TOTP_SECRET`). If Turnstile (captcha) is on for
staging, CLI sign-in is refused: turn it off while seeding, or enroll TOTP in the browser.

### 4. Supabase redirect URLs

Supabase staging **Auth > URL configuration**: add `https://sterileguard-ai.vercel.app` as the
site URL and to the redirect allow list (magic links, invites, password resets; see
auth-settings.md). Password plus TOTP sign-in works without it.

## Routine

- Model: `sg ml train --tune`, `sg ml evaluate --run <id>`, `sg ml register --run <id> --env
  staging`, `sg ml activate <version> --env staging`. The API picks it up within 5 minutes.
- Migrations: `sg db migrate --env staging`, then `sg db rls-test --env staging --runner python`.
- Smoke: `sg release smoke --env staging`.
- The free API sleeps after 15 idle minutes and takes about a minute to wake: open `/health`
  a few minutes before a demo.
