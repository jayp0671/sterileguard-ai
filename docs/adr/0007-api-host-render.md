# 0007. Host the API on Render instead of a Hugging Face Space

- Status: accepted (Jay, Oct 30)
- Date: 2026-10-30
- Deciders: Jay
- Ticket: SG-16

## Context and problem statement

The plan (§4, §17.1) hosts the FastAPI service on a free Hugging Face Space with the Docker SDK.
Creating the Space on Oct 30 failed with `402 Payment Required`: Hugging Face now requires a PRO
subscription to host Docker (and Gradio) Spaces on free CPU; only static Spaces stay free. Hard
rule 6 is free tiers only.

## Considered options

1. Hugging Face PRO: paid, breaks rule 6.
2. Vercel Python functions: the API's dependencies (scikit-learn, SciPy, pandas, SHAP, PyArrow)
   exceed the function size limit.
3. Render free web service: Docker from the repo, no card needed, 750 instance hours a month,
   sleeps after 15 minutes idle and wakes in about a minute (render.com/docs/free).
4. Other hosts with a free Docker tier that need a card on file or have no free tier for new
   accounts.

## Decision outcome

Chosen option 3, Render. `render.yaml` defines the service (same `apps/api/Dockerfile`, health
check `/health`, deploy from main after CI passes). The API with the active model loaded used
about 270 MB in a local measurement, inside the free instance's memory. The staging API URL is
`https://sterileguard-api.onrender.com`.

### Consequences

- Good: free, deploys from git on every green main, no custom deploy workflow to maintain.
- Bad: the first request after 15 idle minutes waits about a minute (the demo runbook already
  says to wake the API ahead of time); the keep-alive only pings every 6 hours to stay well inside
  750 hours. Secrets are entered once in the Render dashboard when the Blueprint is created.
- The Hugging Face deploy workflow and Space staging script are removed.

## Links

- Plan section: §4.1, §17.1
- `render.yaml`, `ops/runbooks/deploy.md`
