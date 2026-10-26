# Demo runbook (SG-16, midterm Oct 30)

The demo organization is synthetic: department **Dental Central Sterile** (`dental-cs`) in
"Demo Health System", with 90 days of simulated history (`source = simulated`). Never use real
data or real names in a demo. Every number on screen is a model estimate, not a guarantee.

## 30 minutes before

1. Open the API URL in a browser: `https://jayp671-sterileguard-api.hf.space/health`. A sleeping
   free Space takes a minute or two to wake; do this **at least 3 minutes** before presenting.
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
4. Keep the backup screen recording open in a second window.

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
