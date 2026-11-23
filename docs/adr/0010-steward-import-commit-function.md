# 0010. Data steward commits through a security definer function

- Status: proposed (needs a human reviewer: Leo or Carlos)
- Date: 2026-11-23
- Deciders: Jay
- Ticket: SG-24

## Context and problem statement

SG-24 adds the Imports review UI. A data steward reviews a file and commits its valid rows as
real plans and approved actuals. Under RLS (0004), only supervisors and department admins
insert plans, and only technicians and above insert actuals, so the steward's own token cannot
write them. ADR-0009 left v1 commits to the CLI (a direct database connection) and said SG-24
would need "a commit function (security definer, steward or dept_admin check) rather than a
wider RLS policy".

Options:

1. Widen the shift_plans and shift_actuals insert policies to data stewards.
2. Commit from the API with the service role.
3. One security definer function, `public.commit_import(job, plans, actuals, overwrite)`,
   that the steward calls with their own token.

## Decision outcome

Option 3, migration `0012_import_commit.sql`. The function:

- requires aal2 and `data_steward` or `dept_admin` in the **job's** department (otherwise it
  answers "not found", so job ids are not confirmed to outsiders); platform admins are not
  included, matching the import_jobs policies;
- lets only a `dept_admin` overwrite existing real days;
- forces department, `source = 'real'`, the new dataset, author, `status = 'final'` for plans
  and `'approved'` (by the caller) for actuals, and ignores ids and timestamps in the payload;
- writes only columns that exist on the table (names from `pg_attribute`, quoted with `%I`);
- commits a job once (`55000` after that), and a second job with the same file (content
  hash) changes nothing;
- caps a commit at 5,000 rows each.

Every insert and update goes through the existing audit triggers with the steward as actor.
The function is in the RLS matrix (2 rules x 8 actors) and has its own pgTAP file (16 checks).

### Consequences

- Good: RLS on the shift tables is unchanged. The service role stays out of request handlers.
  The commit is one transaction and is fully audited.
- Bad: the API sends the rows it validated, and the function trusts their values. A steward
  calling the function directly could load values the pipeline would have rejected. Table
  check constraints still apply, and the steward is already trusted to load the department's
  data. If that matters later, move validation into SQL.

## Links

- Plan sections: §2.2, §10.1
- Code: `supabase/migrations/0012_import_commit.sql`, `supabase/tests/0012_import_commit.test.sql`,
  `apps/api/src/sg_api/services/imports.py`
- Related: ADR-0009
