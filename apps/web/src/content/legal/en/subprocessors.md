---
title: Subprocessors
version: 1.0.0
effective_date: 2026-11-23
status: draft, needs human review
---
| Provider | What it does | Data | Status |
| --- | --- | --- | --- |
| Supabase | Database, authentication, file storage | Accounts, operational counts, logs | In use |
| Vercel | Hosts the web app | Request logs | In use |
| Render | Hosts the API | Request logs | In use |
| NVIDIA (NIM API) | Language model for briefings and import suggestions | Forecast numbers and column headers only, no personal data | In use when configured |
| GitHub | Source code, CI | No production data | In use |
| Cloudflare (Turnstile) | Bot protection on sign-in forms | Browser signals | In use when enabled |
| Hugging Face | Former API host, still available for deployment | None today | Not in use |
| Resend or Gmail | Sending invite and sign-in emails | Email address | Not in use (Supabase sends auth emails) |
| Sentry | Error monitoring | Error reports without personal data | Not in use |
| PostHog | Optional analytics, only with consent | Anonymous usage counts | Not in use |

All providers are used on their free tiers. None has signed a Business Associate Agreement.
