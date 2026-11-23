---
title: Data Retention Policy
version: 1.0.0
effective_date: 2026-11-23
status: draft, needs human review
---
## Retention periods

| Data | Kept for |
| --- | --- |
| Audit log | 6 years (mirrors HIPAA's documentation retention rule) |
| Shift plans, shift logs and forecasts | While the department uses the app |
| Unsubmitted shift drafts | Per department setting (default 90 days) |
| Uploaded import files | Deleted on commit or cancel, and within 24 hours at the latest |
| Import reports (counts, error rows, no identifiers) | While the department uses the app |
| AI usage records (hashes only) | 1 year |
| Cookie consent records | 2 years |
| Accounts | Until removed by a department admin, or on request |

## Requesting deletion

Ask your department admin to remove your account, or open an issue at
[https://github.com/jayp0671/sterileguard-ai/issues](https://github.com/jayp0671/sterileguard-ai/issues) (no personal details in the issue) and we will contact you.
Audit log rows are kept for their retention period even after an account is removed; they
identify users by internal ID only.
