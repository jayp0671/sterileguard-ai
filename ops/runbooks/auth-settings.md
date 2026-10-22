# Auth settings runbook (SG-04)

Supabase dashboard settings are not in migrations. This file is the record of every value. Apply
them to staging (`sterileguard-ai`) and, when it exists, prod. Changing any of these needs an ADR
and a reviewer (SG-00 hard rules). Local values live in `supabase/config.toml`.

| Area | Setting | Value |
| --- | --- | --- |
| Sign-ups | Allow new users to sign up | **Off** (invite-only) |
| Email provider | Enabled | On |
| Email provider | Confirm email | On |
| Passwords | Minimum length | 12 |
| Passwords | Required characters | Lowercase, uppercase, digits |
| Passwords | Leaked password protection | Pro plan only; not available on free. The zxcvbn meter (score >= 3) is the control |
| MFA | TOTP (App Authenticator) | Enroll and verify enabled |
| MFA | Max enrolled factors | 10 (users are told to enroll a backup) |
| URL configuration | Site URL | Staging/prod web URL (e.g. the Vercel production domain) |
| URL configuration | Redirect allowlist | `http://localhost:3000/**`, staging and prod domains `/**`, Vercel previews `https://*-<team>.vercel.app/**` |
| Sessions | JWT expiry | 900 seconds |
| Sessions | Refresh token rotation | On, reuse interval 10 s |
| Sessions | Time-box / inactivity timeout | Pro plan only; enforced by the app instead (see below) |
| JWT signing keys | Algorithm | Asymmetric (ECC P-256 / ES256). API verifies via `/auth/v1/.well-known/jwks.json` |
| Bot protection | CAPTCHA provider | Cloudflare Turnstile, secret key from the Cloudflare dashboard |
| SMTP | Custom SMTP | On (see below) |

## Session policy enforcement

- Idle: 15 minutes, warning at 14 (web `useIdleTimeout`).
- Absolute 12 hours: enforced twice. The web proxy reads the `sg_session_started_at` cookie set at
  sign-in. The API calls `public.session_age_seconds()` with the user's token (it maps the JWT
  `session_id` claim to `auth.sessions.created_at`) and rejects sessions older than 12 hours or
  that no longer exist (so "sign out of all devices" also stops API access). See ADR-0002.
- Re-authentication for sensitive actions: a fresh TOTP verification within 5 minutes, read from
  the JWT `amr` claim (`method: "totp"`, `timestamp`).

## SMTP

Supabase's built-in email is rate limited and only delivers to project team members.

- Preferred: Resend. Host `smtp.resend.com`, port 465, user `resend`, password = Resend API key.
  Needs a verified sending domain.
- No domain: a dedicated project Gmail account with an app password. Host `smtp.gmail.com`,
  port 465. Sender name "SterileGuard AI".

## Email templates

Every link goes through `/auth/confirm` (server-side `verifyOtp`, works with the SSR cookie
session). Each template ends with the footer "Academic prototype. Not for clinical use."

| Template | Link |
| --- | --- |
| Invite user | `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=invite` |
| Magic link | `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email` |
| Reset password | `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=recovery` |

Example invite body:

```html
<h2>You're invited to SterileGuard AI</h2>
<p>Your department admin invited you. The link expires in 7 days.</p>
<p><a href="{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=invite">Accept the invite</a></p>
<p>You will set a password and two-factor authentication.</p>
<hr><p style="font-size:12px">Academic prototype. Not for clinical use. Do not enter patient information.</p>
```

## Lost authenticator

Supabase has no recovery codes. A dept_admin resets the user's factors (admin UI in SG-25; until
then, a platform admin deletes the factor in the dashboard under Authentication > Users). Every
reset is audited.

## Logs

Supabase keeps its own auth logs (Dashboard > Logs > Auth). The app also posts auth events to
`POST /v1/audit/auth-event`, logged as JSON until `audit_log` lands in SG-08.
