# 0009. Import pipeline v1 and the PHI guard

- Status: proposed (needs Leo's review; Carlos for the SG-22 tests)
- Date: 2026-11-02
- Deciders: Jay, Leo
- Ticket: SG-21

## Context and problem statement

SG-21 asks for a deterministic import pipeline (`sg_data/imports/`), migration
`0009_imports.sql`, and a PHI guard built on Microsoft Presidio with spaCy, used both by imports
and by the API for free text. Four things needed a decision:

1. **Migration number.** 0009 (scenarios) and 0010 (shift reopen, SG-20) merged first.
2. **Which spaCy model.** The ticket says `en_core_web_sm` "for speed; document the choice".
   The API runs on Render's free instance (512 MB).
3. **Who commits.** RLS (0004) lets only supervisors and department admins insert plans, and
   only technicians, supervisors and department admins insert actuals. A data steward, who owns
   imports, cannot write either with their own token.
4. **Identity columns versus counts.** The schema lists "employees" as a synonym of
   `morning_staff_present` (a count), but the ticket drops columns whose header suggests
   "employee".

## Decision outcome

1. The migration is `0011_imports.sql` (import_jobs, mapping_templates, `datasets.import_job_id`
   for lineage, private `imports` bucket with per-department folder policies).
2. `en_core_web_sm` 3.8.0, installed from the official explosion/spacy-models release. Measured
   on Windows: about 120 MB resident and 4 s to load, about 5 ms per short text. The API (about
   270 MB with the model loaded) stays near 400 MB. The analyzer loads once, warmed in a
   background task at API startup (skipped in tests), and checks run in a worker thread. The
   small model misses some short names, so a pattern recognizer adds honorific plus surname
   ("Dr. Okafor") as PERSON. Blocking entity types: PERSON, EMAIL_ADDRESS, PHONE_NUMBER,
   US_SSN, MRN, DATE_OF_BIRTH. DATE_TIME, NRP and LOCATION do not block: shift notes mention
   times and places.
3. In v1, commits run from `sg data import --commit` over a direct database connection (the
   same pattern as `sg demo`), audited by the table triggers. The import job, dataset and
   mapping template rows are written in the same transaction. The upload, review and approve
   API for data stewards comes with the Imports UI (SG-24), which will need a commit function
   (security definer, steward or dept_admin check) rather than a wider RLS policy.
4. Strong header words (name, id, mrn, badge, dob, ssn, email, phone) always drop the column.
   Weak words (employee, patient, staff, worker, tech) drop it only when most values are text.
   So "Employees: 3" maps to staff present, and "Employee: <names>" is dropped.

Also:

- Findings record entity type, column and row, never the matched text. A blocked cell is
  cleared and its row flagged; the rest of the row still imports. Columns with findings get
  no sample values in the profile.
- Imported actuals are stored as approved: approving the import is the review step.
- Idempotency is by the file's content hash (a second commit of the same file changes
  nothing), and existing real days are skipped unless `--overwrite`.

### Consequences

- Good: no identifier reaches the database, the reports or the logs (tests capture logs); the
  same code runs in the CLI and, later, the API.
- Bad: the API image grows by the spaCy model (about 15 MB wheel plus spaCy itself), and the
  first free-text check after a cold start waits for the warm-up if it has not finished.
  `en_core_web_sm` has lower name recall than the larger models; the custom patterns and the
  UI warning ("Do not enter patient or employee names") cover the gap.

## Links

- Plan sections: §10.1 to §10.3, §14
- Code: `packages/data/src/sg_data/imports/`, `packages/data/src/sg_data/phi.py`,
  `apps/api/src/sg_api/core/text_guard.py`, `ops/scripts/src/sg_cli/commands/data.py`,
  `supabase/migrations/0011_imports.sql`
