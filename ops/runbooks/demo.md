# Demo runbook (SG-16, midterm Oct 30)

The demo organization is synthetic: department **Dental Central Sterile** (`dental-cs`) in
"Demo Health System", with 90 days of simulated history (`source = simulated`). Never use real
data or real names in a demo. Every number on screen is a model estimate, not a guarantee.

## 30 minutes before

1. Open the API URL in a browser: `https://sterileguard-api.onrender.com/health`. A sleeping
   free Render service takes about a minute to wake; do this **at least 3 minutes** before presenting.
2. `/ready` must show `"status": "ready"` and `"models": {"full": "<version>"}`.
3. Reset the demo state (identical every time):
   ```
   uv run sg demo reset-demo --env staging
   ```
   It prints a state checksum; the same day gives the same checksum.
4. `uv run sg release smoke --env staging` passes.

## On the presenter laptop

1. Sign in at the staging site as the demo **supervisor** (email and password in
   `ops/secrets/demo-totp.json`, never on a slide or in a screenshot).
2. Have the authenticator app ready with the supervisor's TOTP entry (from the same file).
3. Close notifications, chat apps and other tabs. Browser zoom 100%, light theme.
4. Keep the backup screen recording open in a second window: `ops/reports/demo/midterm-backup-walkthrough.webm`
   (gitignored; recorded Oct 30 from the real Plan and Forecast screens on staging demo data; no
   narration, so narrate over it). Screenshots for slides are beside it.
5. The deck is the "SterileGuard AI Midterm" artifact (Jay's claude.ai account; share it with the
   team before presenting). Placeholders to fill: Carlos's last name, the calibration plot.

## Live demo script (2 minutes or less)

1. **Plan tomorrow** (`/app/plan`): show suggested values and their sources, change 7:00 AM
   staff, **Finalize plan**.
2. **Forecast** (`/app`): **Compute forecast** (or Recompute). Read the estimate and its 80%
   range, the burden category and probability.
3. **Drivers**: read the top two sentences; open **Why these factors?**.
4. **History**: the 14-day predicted band vs actual dots; toggle **View as table**.

If anything fails: switch to the backup recording, and say so.

## After

`uv run sg demo reset-demo --env staging` so the next session starts clean.

## Shared demo users and E2E secrets (SG-26, Jay)

The agent never creates hosted accounts or enters secrets, so these steps are Jay's. Run them
in the main checkout (`C:\Users\JayVe\OneDrive - stevens.edu\sterileguard-ai`), which has `.env`.

1. Add one line to `.env`: an inbox you control that supports plus addressing (Gmail does).
   Each demo user becomes `you+sg-<role>@...`, so the invite and reset emails come to you.
   `DEMO_EMAIL_BASE=your.name@gmail.com`
2. Create the users (one per role, plus an `outsider` technician in a second department for
   the tenant isolation journey) with TOTP enrolled, and reseed the demo history:
   `uv run sg demo seed-demo --env staging`
   Passwords and TOTP secrets go to `ops/secrets/demo-totp.json` (gitignored). The run is
   idempotent: it reuses existing users.
3. Copy them into GitHub Actions secrets (needs `gh auth login`; values are never printed):
   `uv run sg demo e2e-secrets` (lists the 18 names), then
   `uv run sg demo e2e-secrets --apply`
4. If Vercel previews are protected: Vercel dashboard > sterileguard-ai > Settings >
   Deployment Protection > Protection Bypass for Automation > Create, then
   `gh secret set VERCEL_AUTOMATION_BYPASS_SECRET` and paste it.
5. Run the journeys once against staging and read the summary:
   `gh workflow run e2e.yml -f base_url=https://sterileguard-ai.vercel.app`
   then the flake check (10 runs per project):
   `gh workflow run e2e-flake.yml -f base_url=https://sterileguard-ai.vercel.app`

Journeys 2 to 6 write data (a finalized plan, an applied scenario, a logged and approved
shift, an import, a role change that is changed back). Run `uv run sg demo reset-demo --env
staging` before a live demo.
