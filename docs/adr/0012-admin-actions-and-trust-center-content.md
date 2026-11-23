# 0012. Audited admin actions and plain-Markdown Trust Center pages

- Status: proposed (needs a human reviewer; legal page text is a draft for human review)
- Date: 2026-11-23
- Deciders: Jay
- Ticket: SG-25

## Context and problem statement

SG-25 asks for an admin console, an audit log viewer, the Trust Center, policy acceptance and
cookie consent, with migration `0011_compliance.sql`. Several points needed a decision:

1. Migrations 0011 to 0013 were already taken.
2. The MFA reset and the audit export must be audited. But audit rows are written only by table
   triggers (0005, append-only), and neither action changes a public table: the reset deletes
   factors in Supabase Auth, and the export reads.
3. The ticket asks for MDX content. No MDX tooling is installed, and the pages are text and
   tables.
4. The sitemap (SG-10 nav) already defines `/app/admin/users`, `/app/admin/department` and
   `/app/admin/audit`. The ticket says `/app/admin`.
5. The subprocessor list in plan §14.4 predates ADR-0007 (the API is on Render, not Hugging
   Face). Resend, Sentry and PostHog are not configured.
6. Listing members' email, last sign-in and factor count needs the Auth admin API, so it needs
   the service role.

## Decision outcome

1. The migration is `0014_compliance.sql`: `policy_acceptances`, `consents`, `admin_actions`.
2. `admin_actions(department_id, actor_id, action in ('mfa_reset','audit_export'),
   target_user_id, detail)` has the standard audit trigger. Each reset and each export inserts
   one row with the admin's own token (RLS: dept_admin or platform admin, actor must be the
   caller, append-only), so both actions show up in the audit log viewer. Policy acceptances
   are audited the same way. Consents are written only by the API's service role, because the
   banner shows before sign-in.
3. Pages are Markdown with frontmatter (`title`, `version`, `effective_date`, `status`) in
   `apps/web/src/content/legal/en/`, rendered by a small parser into React elements. No raw
   HTML is rendered, and links are limited to site paths, https and mailto. If MDX components
   are needed later, the files can be renamed.
4. Routes follow the existing sitemap: `/app/admin/users`, `/app/admin/department`,
   `/app/admin/audit`. Data retention (`/app/admin/retention`) stays a nav stub.
5. The subprocessors page lists what is in use today (Supabase, Vercel, Render, NVIDIA, GitHub,
   Cloudflare Turnstile) and marks Hugging Face, Resend/Gmail, Sentry and PostHog as not in use.
   The PostHog loader exists but stays inert without `NEXT_PUBLIC_POSTHOG_KEY`, and it never
   loads before analytics consent or with Global Privacy Control.
6. The service role is used only after `require_role` confirms dept_admin (or platform admin)
   for that department. It is used for auth user lookups, profile display names and factor
   deletion. Role changes, removals, settings and audit reads use the admin's token, so RLS and
   triggers apply.

Also:

- `sg compliance check` verifies the 11 pages, `security.txt` (Contact, Expires within a year,
  Policy), the footer notice, that the API's `POLICY_VERSIONS` match the pages, that no page
  claims HIPAA compliance, and that no schema name contains patient_name, mrn, ssn or dob
  (migrations always, the live database with `--env`).
- The security contact is the repository's GitHub security advisories page, not a personal
  email address.
- The audit log viewer uses server cursor pagination ("Older/Newer") rather than DataTable's
  client paging, with a detail drawer for the before/after diff.

### Consequences

- Good: every admin action is in the same append-only log, and no RLS policy was widened.
- Bad: the legal text is a student draft, not legal advice, and must be reviewed by a person
  before the release (SG-34). A factor deleted directly in the Supabase dashboard is not in the
  app's audit log.

## Links

- Plan sections: §2.2, §14
- Code: `supabase/migrations/0014_compliance.sql`, `apps/api/src/sg_api/routers/admin_console.py`,
  `apps/api/src/sg_api/routers/compliance.py`, `apps/web/src/content/legal/en/`,
  `ops/scripts/src/sg_cli/commands/compliance.py`
