---
title: Security
version: 1.0.0
effective_date: 2026-11-23
status: draft, needs human review
---
## Practices

- Invite-only accounts, mandatory two-factor authentication, 15-minute idle sign-out and a
  12-hour session limit
- Role checks in the API and row-level security on every database table, tested on every change
- Re-authentication for sensitive actions (role changes, exports, model activation)
- Rate limits, input validation and a guard that blocks identifiers in free text
- Secrets only in provider secret stores; secret scanning before every commit and in CI
- Dependency and code scanning on every pull request
- An append-only audit log

## Report a vulnerability

Please report privately through GitHub security advisories:
[https://github.com/jayp0671/sterileguard-ai/security/advisories/new](https://github.com/jayp0671/sterileguard-ai/security/advisories/new). Do not include personal or
patient data. We acknowledge reports within 5 business days. Please give us reasonable time to
fix an issue before disclosing it. This is a student project with no bug bounty.

Machine-readable contact details are at [/.well-known/security.txt](/.well-known/security.txt).
