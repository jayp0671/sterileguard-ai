# Build from the repo root: docker build -f apps/api/Dockerfile -t sg-api .
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN useradd --create-home --uid 1000 app
WORKDIR /app

# Workspace metadata first for layer caching; every member's pyproject is needed by the lockfile.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/data/pyproject.toml packages/data/pyproject.toml
COPY packages/sim/pyproject.toml packages/sim/pyproject.toml
COPY packages/ml/pyproject.toml packages/ml/pyproject.toml
COPY packages/agents/pyproject.toml packages/agents/pyproject.toml
COPY ops/scripts/pyproject.toml ops/scripts/pyproject.toml
RUN uv sync --frozen --no-dev --package sg-api --no-install-workspace

COPY apps/api apps/api
COPY packages/data packages/data
COPY packages/sim packages/sim
COPY packages/ml packages/ml
COPY packages/agents packages/agents
RUN uv sync --frozen --no-dev --package sg-api --no-editable && chown -R app /app

ARG GIT_SHA=""
ENV GIT_SHA=${GIT_SHA} PATH="/app/.venv/bin:$PATH" PORT=7860
USER app
EXPOSE 7860
CMD ["sh", "-c", "uvicorn sg_api.main:create_app --factory --host 0.0.0.0 --port ${PORT:-7860}"]
