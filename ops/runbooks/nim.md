# NVIDIA NIM key (SG-23)

The briefing and import-mapping agents call NVIDIA's hosted NIM API (free developer tier,
about 40 requests a minute). Without a key everything still works: the Forecast page shows the
template "Summary" and the Imports page has no AI suggestions. Only Jay enters keys.

## 1. Get the key (build.nvidia.com)

1. Open https://build.nvidia.com and sign in (or create the free NVIDIA Developer account).
2. Open the model page for **meta / llama-3.3-70b-instruct**.
3. Click **Get API Key** → **Generate Key**. Copy it (it starts with `nvapi-`).
   Free tier only: do not add a payment method.

## 2. Local .env (main checkout)

Add or fill this line in `C:\Users\JayVe\OneDrive - stevens.edu\sterileguard-ai\.env`:

```
NIM_API_KEY=nvapi-...
```

Then check that every model in `ops/prompts/models.yaml` answers on the key (4 tiny calls):

```powershell
uv run sg agents ping
```

If a model fails with 404, pick a current one from https://docs.api.nvidia.com/nim/reference/llm-apis,
update `ops/prompts/models.yaml`, and ping again.

## 3. Render (staging API)

1. https://dashboard.render.com → **sterileguard-api** → **Environment**.
2. **Add Environment Variable**: key `NIM_API_KEY`, value: paste the key.
   Copy it from .env without changing it:
   `((Get-Content .env | Where-Object { $_ -like 'NIM_API_KEY=*' }) -replace '^[^=]*=','') | Set-Clipboard`
3. **Save, rebuild, and deploy**. Wait for the deploy, then open the Forecast page: the card
   title changes from "Summary" to "AI-generated summary" when the LLM answer passes the
   guardrail.

## 4. Optional: record real cassettes

The test cassettes in `packages/agents/tests/cassettes` are hand-written stand-ins
(`"stand_in": true`). To replace them with real answers (about 50 calls, under 2 minutes):

```powershell
uv run sg agents record
```

```powershell
uv run sg test agents
```

Review the diff before committing; the adversarial cassettes stay stand-ins on purpose. CI
always replays and never calls NVIDIA.
