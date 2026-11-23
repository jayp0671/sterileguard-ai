---
title: Cookie Policy
version: 1.0.0
effective_date: 2026-11-23
status: draft, needs human review
---
## Essential cookies (always on)

| Cookie | Purpose | Duration |
| --- | --- | --- |
| `sb-<project>-auth-token` (Supabase Auth) | Keeps you signed in | Session, up to 12 hours |
| `sg_session_started_at` | Enforces the 12-hour session limit | 12 hours |
| `sg_consent` | Remembers your cookie choice | 12 months |
| `theme` (local storage) | Light or dark theme | Until you clear it |
| `sg_anon_id` (local storage) | Random ID that links your cookie choice before sign-in | Until you clear it |
| `sg.department` (local storage) | The department you last opened | Until you clear it |

## Analytics cookies (off by default)

| Cookie | Purpose | Duration |
| --- | --- | --- |
| `ph_<key>_posthog` (PostHog) | Counts which screens are used, without names | 12 months |

Analytics load **only** if you choose "Accept analytics". If your browser sends Global Privacy
Control, we treat it as a refusal. PostHog is not configured on the current prototype, so no
analytics cookie is set today even if you accept.

## Changing your choice

Use **Cookie settings** in the footer of any page. Each choice is logged with the version of
this policy.
