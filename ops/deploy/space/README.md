---
title: SterileGuard AI API (staging)
emoji: 🧪
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Academic prototype API. Synthetic and aggregate data only.
---

# SterileGuard AI API (staging)

FastAPI service for SterileGuard AI, an academic prototype (CPE 595, Stevens, Group 8) that
forecasts next-day overtime for a Dental Central Sterile department. Decision support only:
every forecast is a model estimate, not a guarantee. HIPAA-style safeguards; no patient data and
no employee names are stored or processed.

- `GET /health` liveness, `GET /ready` database and loaded model versions
- Source and documentation: https://github.com/jayp0671/sterileguard-ai

This Space is deployed by `.github/workflows/deploy-api.yml`; do not edit files here directly.
