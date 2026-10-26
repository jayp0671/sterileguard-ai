# Deploy runbook: staging (SG-16)

Staging = Vercel (web) + a Hugging Face Space (API, free CPU, Docker) + the staging Supabase
project. Free tiers only. Secrets live only in the Vercel, Hugging Face and GitHub secret
stores, never in the repo.

## One-time setup (Jay)

### 1. Hugging Face Space (API)

1. Create a Space: owner `jayp671`, name `sterileguard-api`, SDK **Docker**, hardware
   **CPU basic (free)**, visibility public (the API itself enforces auth).
2. Space **Settings > Variables and secrets** (runtime):
   | Name | Kind | Value |
   | --- | --- | --- |
   | `ENV` | variable | `staging` |
   | `SUPABASE_URL` | variable | staging project URL |
   | `SUPABASE_JWKS_URL` | variable | `<url>/auth/v1/.well-known/jwks.json` |
   | `SUPABASE_ANON_KEY` | secret | staging anon key |
   | `SUPABASE_SERVICE_ROLE_KEY` | secret | staging service-role key (model loading only) |
   | `CORS_ORIGINS` | variable | `https://<staging-domain>,http://localhost:3000` |
   | `CORS_ORIGIN_REGEX` | variable | `^https://sterileguard-ai-[a-z0-9-]+-jays-projects-8a6490ad\.vercel\.app$` |
   | `INTERNAL_TOKEN` | secret | long random string (also used by deploy hooks) |
   | `MODEL_BUCKET` | variable | `models` |
   | `NIM_API_KEY` | secret | later (SG-23) |
3. GitHub repo **Settings > Secrets and variables > Actions**:
   - secret `HF_TOKEN` (a Hugging Face token with write access to the Space)
   - variable `HF_SPACE_ID` = `jayp671/sterileguard-api`
4. Run the `deploy-api` workflow once (Actions > deploy-api > Run workflow). Afterwards it runs
   on every push to main that touches the API or the Python packages. The workflow stages only
   the API build context (`ops/deploy/space/stage.sh`) and uploads it with
   `huggingface_hub.upload_folder`; the Space builds `Dockerfile` itself.
5. Check `https://jayp671-sterileguard-api.hf.space/ready`: `status: ready` and
   `models.full` set.

### 2. Vercel (web)

1. Project `sterileguard-ai` **Settings > General > Root Directory**: `apps/web` (it is `.`
   today, which is why previews fail). Framework, install command and the ignored build step
   come from `apps/web/vercel.json`.
2. **Settings > Environment Variables** (Production and Preview):
   `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (staging),
   `NEXT_PUBLIC_API_URL` (the Space URL), `NEXT_PUBLIC_SITE_URL` (the staging domain),
   `NEXT_PUBLIC_TURNSTILE_SITE_KEY`.
3. **Settings > Domains**: `sterileguard-staging.vercel.app` (or the chosen name) on `main`.
4. If previews use Vercel deployment protection, create a Protection Bypass for Automation
   secret and save it in GitHub as `VERCEL_AUTOMATION_BYPASS_SECRET` (used by `e2e.yml`).
5. Supabase staging **Auth > URL configuration**: add the staging domain and the preview
   pattern to the redirect allow list (see auth-settings.md).

### 3. Keep-alive

GitHub variable `API_URL` (the Space URL) and secret `SUPABASE_DB_URL_STAGING`. The `keepalive`
workflow pings `/health` and runs one query every 6 hours (free Spaces sleep, free Supabase
projects pause after about a week idle).

### 4. Demo users and E2E

`DEMO_EMAIL_BASE` in `.env` (a team inbox, e.g. `team@example.edu`; users become
`team+supervisor@...`), then `uv run sg demo seed-demo --env staging`. Copy the E2E values from
`ops/secrets/demo-totp.json` into GitHub secrets `E2E_SUPERVISOR_*` and `E2E_TECHNICIAN_*`
(`EMAIL`, `PASSWORD`, `TOTP_SECRET`). If Turnstile (captcha) is on for staging, password
sign-in from the CLI is refused; seed users with captcha temporarily off, or enroll TOTP in the
browser.

## Routine

- Model: `sg ml train --tune`, `sg ml evaluate --run <id>`, `sg ml register --run <id> --env
  staging`, `sg ml activate <version> --env staging`. The API picks it up within 5 minutes, or
  at once with `curl -X POST -H "X-Internal-Token: $INTERNAL_TOKEN" $API_URL/v1/internal/models/reload`.
- Migrations: `sg db migrate --env staging`, then `sg db rls-test --env staging --runner python`.
- Smoke: `sg release smoke --env staging` (needs `WEB_URL_STAGING` and `API_URL_STAGING`).
