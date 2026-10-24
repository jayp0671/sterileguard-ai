# Supabase

Migrations in `migrations/NNNN_name.sql` are the only way the schema changes. Never edit a merged
migration; add a new one. `seed.sql` is for local and staging only.

| Command | What it does |
| --- | --- |
| `sg db reset` | Local only: recreate the database, apply all migrations and the seed |
| `sg db migrate --env local\|staging\|prod` | Apply pending migrations (prod needs `--confirm`) |
| `sg db seed` | Re-run `seed.sql` on the local database |
| `sg db types` | Generate `packages/contracts/src/db.ts` |
| `sg db lint` | `supabase db lint`, fails on error-level findings |
| `sg db rls-test` | pgTAP tests in `tests/` |

## RLS pattern (the standard every table copies)

RLS is enabled on every table. Policies call security-definer helpers with an empty
`search_path`, which `anon` cannot execute:

- `public.is_aal2()`: the JWT `aal` claim is `aal2` (two-factor completed).
- `public.is_member(dept uuid)`: the user has any role in the department.
- `public.has_role(dept uuid, roles public.app_role[])`: the user has one of the roles there.
- `public.is_platform_admin()`: the user holds `platform_admin` anywhere.

```sql
-- select
using ((select public.is_aal2())
       and (public.is_member(department_id) or (select public.is_platform_admin())));

-- insert / update / delete (role lists from plan §2.2)
with check ((select public.is_aal2())
            and public.has_role(department_id, array['supervisor','dept_admin']::public.app_role[]));
```

Requiring `aal2` inside RLS means a user who has not completed two-factor sees nothing, even
with a valid token. Organizations and facilities are visible through departments the user belongs
to. A `dept_admin` manages memberships in their own department but can never grant or modify
`platform_admin`; only a `platform_admin` does that.

Wrap helper calls that do not depend on the row in `(select ...)` so Postgres evaluates them once
per query, not once per row.

### RLS permission matrix (SG-12)

`supabase/tests/0010_rls_matrix.test.sql` checks every table x select/insert/update/delete x
every role in department A, a department-B technician, an aal1 user and anon. Expected results
are the `rules` rows (one per table and operation, listing the allowed actors); every other
actor must be denied. **Every migration that adds a table must add its four rules there.** The
coverage assertion fails if any table in `public` is missing. Run it with
`sg test db --env staging --runner python` (no Docker) or `sg test db` against the local stack.

## `departments.settings` shape

Validated by a Pydantic `DepartmentSettings` model in the API (SG-11).

```json
{
  "shift_windows": [
    {"key": "morning", "start": "07:00", "end": "15:00", "default_staff": 3},
    {"key": "aft_11",  "start": "11:00", "end": "19:00", "default_staff": 3},
    {"key": "aft_13",  "start": "13:00", "end": "21:00", "default_staff": 1},
    {"key": "aft_15",  "start": "15:00", "end": "23:00", "default_staff": 2}
  ],
  "outside_support_default": 2,
  "outside_support_until": "20:00",
  "washers": 2,
  "sterilizers": 2,
  "mf_cases_default": 20,
  "burden_thresholds": null,
  "alert_threshold_hours": null,
  "retention_days_drafts": 90
}
```

## Environments

- Local: Supabase CLI in Docker (`pnpm exec supabase start`).
- Staging/dev: hosted project `sterileguard-ai`. Set `SUPABASE_DB_URL_STAGING` in `.env`.
- Prod: not created yet. Set `SUPABASE_DB_URL_PROD` when it exists.

Use asymmetric JWT signing keys so the API can verify tokens through
`https://<ref>.supabase.co/auth/v1/.well-known/jwks.json`.
