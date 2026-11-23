---
title: AI Transparency Notice
version: 1.0.0
effective_date: 2026-11-23
status: draft, needs human review
---
## Where AI is used

| Feature | What it does | Who decides |
| --- | --- | --- |
| Overtime forecast | A gradient-boosted model estimates next-day overtime with an 80% range | The supervisor |
| Drivers (SHAP) | Explains which inputs pushed the estimate up or down | Information only |
| Staffing scenarios | Re-runs the model for staffing changes and suggests the smallest change | The supervisor |
| Briefing | A language model (NVIDIA NIM) rewrites the forecast numbers into sentences | Information only |
| Import suggestions | A language model suggests how file columns map to fields | A data steward approves each one |
| Translations (planned) | A language model drafts Spanish text | Reviewed before release |

## Forecasts are estimates

Every forecast and recommendation is a **model estimate, not a guarantee**. The app never makes
staffing decisions.

## Safeguards

- The forecast model uses only information known by 7:00 AM.
- The briefing may only repeat numbers from the forecast. Answers with any other number, a
  link, a name or a missing "Model estimate." are discarded and a fixed template is used.
- Import suggestions are never applied automatically, and columns that look like identifiers
  are never sent to the language model. Only headers and numeric or date samples are sent.
- The language model never sees patient or employee information.

## Limitations

- The model is trained on simulated days from a calibrated simulator; checking it on real days
  is in progress.
- Burden categories are provisional until enough real data exists.
- Unknown events (equipment failure, unexpected cases) are not inputs, so such days are
  under-predicted.

## Model card summary

The current model, its data, metrics and activation gates are shown on the Model performance
page inside the app.
