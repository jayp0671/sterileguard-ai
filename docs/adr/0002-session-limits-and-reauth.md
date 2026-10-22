# 0002. Session limits and re-authentication on the free plan

- Status: accepted
- Date: 2026-10-21
- Deciders: Jay Patel (Tech Lead)
- Ticket: SG-04

## Context and problem statement

Plan §9.2 requires a 12-hour absolute session limit, a 15-minute idle logout, and
re-authentication for sensitive actions. Supabase's time-boxed sessions and inactivity timeout
are Pro-plan features, and the project must stay on free tiers.

## Considered options

1. Client-only enforcement (cookie plus idle hook).
2. Server-side check in the API through a security-definer RPC on `auth.sessions`.
3. A separate one-time reauth token endpoint (`POST /v1/auth/reauth`, `X-Reauth-Token`).

## Decision outcome

- 12-hour limit: options 1 and 2 together. The web proxy signs the user out using the
  `sg_session_started_at` cookie; the API calls `public.session_age_seconds()` (migration 0003),
  which maps the JWT `session_id` to `auth.sessions.created_at`, and rejects sessions older than
  12 hours or already signed out. Results are cached for 60 seconds per session.
- Idle: client-side only (`useIdleTimeout`). A server cannot tell idle from a closed tab without
  extra infrastructure; short 15-minute access tokens bound the exposure.
- Re-auth: the JWT `amr` claim lists each method with a timestamp (confirmed in the current
  Supabase JWT claims reference). A fresh `challengeAndVerify` adds a `totp` entry; the API
  dependency `require_recent_totp` accepts it for 5 minutes. Option 3 is not needed.
- Email links use `/auth/confirm` with `token_hash` and `verifyOtp` (Supabase SSR pattern).
- Next.js 16 renamed `middleware.ts` to `proxy.ts`; the route guard lives in `src/proxy.ts`.

### Consequences

- Good: everything stays on the free plan, and "sign out of all devices" also cuts API access.
- Bad: the idle rule can be bypassed by a modified client; accepted for an academic prototype.
