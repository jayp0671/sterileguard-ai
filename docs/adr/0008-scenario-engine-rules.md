# 0008. Staffing scenario engine: support check, volunteer what-ifs, apply

- Status: proposed (needs Leo's review)
- Date: 2026-11-02
- Deciders: Jay, Leo
- Ticket: SG-19

## Context and problem statement

SG-19 specifies the engine (`sg_ml/scenarios.py`), migration `0008_scenarios.sql`, and the
Scenarios page. Building it against the code and the plan turned up five places where the
ticket cannot be followed as written:

1. **Migration number.** 0008 is the SG-15 forecasts table.
2. **Training support "stored in the model card".** No model card or artifact stores the
   min and max staffing seen in training, including the active model `20261026-0105-de605a9`.
3. **The volunteer lever.** "Staff willing to stay" (`ot_available_staff`, 0 to the morning
   staff count) costs no added staff-hours. Fewer volunteers lowers predicted overtime only
   because unfinished work moves to the next day. Counted like the other levers, the cheapest
   option meeting a target would usually be "nobody stays", which is a perverse recommendation.
4. **Grid size.** The default bounds give 3^4 staff combinations times 4 volunteer values
   (morning staff 3) = 324 options, not "about 250".
5. **Apply needs an update.** The ticket gives the `scenarios` table select and insert
   policies only, but "Apply" must mark the run applied.

## Decision outcome

1. The migration is `0009_scenarios.sql`.
2. `train()` now stores `staffing_support` (min and max per lever over the training rows) in
   the artifact and the run, and `build_card` copies it into the model card. For older
   artifacts the engine falls back to the min and max of `explainer_background`, the 200-row
   training sample saved with every artifact. That range can only be narrower than the full
   training range, so the fallback flags more options as low confidence, never fewer.
3. Volunteer changes stay in the grid, on the steppers and on the chart (as what-ifs), but
   options that change the volunteer count are never the minimum change and are left off the
   Pareto front. The page explains why under the stepper.
4. `MAX_OPTIONS = 500`; requests above it get 422. The speed test covers both 243 and 324
   options (the vectorized grid takes well under the 2 s budget).
5. `scenarios` gets a column-limited update (`applied`, `applied_option_id`, `applied_at`,
   `applied_by`) for supervisors and department admins, with `applied_by = auth.uid()`. The
   result and request columns cannot be updated, and runs cannot be deleted. The RLS matrix
   covers both updates. The audit trigger leaves the `result` payload (every option, about
   100 KB) out of `audit_log`.

Also:

- **Stale runs.** Apply returns 409 `plan-changed` if the plan was edited after the run.
  Without this, an option computed for an older plan could overwrite newer plan values.
- **Live updates.** The page fetches the grid once. Every stepper position is a grid option,
  so the "recompute 400 ms after the last change" is a lookup in the stored run. It gives the
  same numbers as a new model call and costs no extra requests against the 30-per-minute limit.

### Consequences

- Good: recommendations never rest on unsupported staffing or on fewer volunteers; old models
  keep working; applying an option cannot silently undo a newer plan edit.
- Bad: one scenario row is about 100 KB of JSON (compressed by Postgres), so heavy use grows
  the table. The SG-30 retention job should prune runs older than the retention window.

## Links

- Plan sections: §6.2, §12.6
- Code: `packages/ml/src/sg_ml/scenarios.py`, `apps/api/src/sg_api/services/scenarios.py`,
  `supabase/migrations/0009_scenarios.sql`, `apps/web/src/app/(app)/app/scenarios/`
