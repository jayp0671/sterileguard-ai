# Data import runbook (SG-21)

For real log files, such as Leo's week 1 or later Kronos exports. Real files stay on the
private team drive or the steward's laptop: never copy one into the repo, a ticket, a chat or
a prompt.

## 1. Profile (writes nothing)

```
uv run sg data profile "D:/private/week1.xlsx"
```

It prints the sheet and header row it chose, which columns the PHI guard dropped (names, IDs,
badge numbers), how many text cells it blocked, the proposed mapping (`exact`, `synonym`,
`fuzzy` or `template`), and row-level errors. Add `--sheet "Name"` to pick a sheet, and
`--week-start 2026-09-14` when the days are column headers like Mon, Tue.

## 2. Dry run against staging

```
uv run sg data import "D:/private/week1.xlsx" --department dental-cs --env staging
```

Same report, using the department's settings and saved mapping templates. Nothing is written.
Fix errors in a copy of the file, not by hand in the database.

## 3. Commit

```
uv run sg data import "D:/private/week1.xlsx" --department dental-cs --env staging --commit
```

- Valid rows load as `source = 'real'` plans (final) and actuals (approved), under one new
  dataset that points at the import job.
- Days that already have a real row are skipped. `--overwrite` replaces them: a department
  admin's decision, recorded by the audit triggers.
- Running the same file again changes nothing (matched by content hash).
- The mapping is saved as a template, so the next file with the same columns maps itself.

## Afterwards

- Check the days on the Shift history page (`/app/history`).
- The raw file is never uploaded by the CLI. Uploads through the app (SG-24) are deleted after
  commit, or 24 hours after upload at the latest (SG-30 nightly job).
