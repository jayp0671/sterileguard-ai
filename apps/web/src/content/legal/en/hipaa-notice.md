---
title: HIPAA Notice
version: 1.0.0
effective_date: 2026-11-23
status: draft, needs human review
---
## No patient information

SterileGuard AI does not collect or store patient information. It works only with daily
department totals (for example, the number of scheduled patients), never with individual
patients or their records.

**Do not enter patient information anywhere in the app**, including notes and uploaded files.
Text that looks like names, phone numbers, email addresses or ID numbers is blocked, and
uploaded columns that look like identifiers are removed before anything is stored.

## Not HIPAA compliant or certified

SterileGuard AI is an academic prototype. It is **not** HIPAA compliant and has not been
certified or audited. Our hosting providers' free tiers do not offer Business Associate
Agreements, and **no Business Associate Agreement exists** with any of them.

## HIPAA-style safeguards

Even though the app holds no patient information, it follows the kinds of safeguards the HIPAA
Security Rule describes, because a hospital would expect them:

- Invite-only accounts, roles and row-level security on every table
- Mandatory two-factor authentication for every role
- Automatic sign-out after 15 minutes idle and a 12-hour session limit
- An append-only audit log of sign-ins, data changes, exports and admin actions
- Validation, approvals and checksums for imported data
- HTTPS everywhere and encryption at rest by the hosting providers
- Aggregate overtime only, never individual time records

## Questions

See the [Security page](/trust/security).
