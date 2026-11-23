"""LLM agents behind the API (SG-23, plan §13).

One NimClient per process (its limiter and breaker are per process, as the ticket asks). Usage
rows (hashes only) and guarded answers go to agent_calls and agent_cache through the service
role, which no user role can read; without a service key the cache is in memory only.
The briefing is cached per forecast and locale. Every failure falls back to the template.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from cachetools import TTLCache

from sg_agents import briefing, mapping
from sg_agents.nim import NimClient, cache_key, load_config
from sg_api.core.config import Settings
from sg_api.core.logging import get_logger
from sg_api.db.service_client import ServiceClient

log = get_logger("sg_api.agents")


class AgentService:
    def __init__(self, settings: Settings, client: NimClient | None = None) -> None:
        self.settings = settings
        self.service = ServiceClient(settings) if settings.supabase_service_role_key else None
        self.client = client or NimClient(
            load_config(), api_key=settings.nim_api_key or None, on_call=self._log_call
        )
        self.memory: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=1024, ttl=24 * 3600)

    async def _log_call(self, record: Mapping[str, Any]) -> None:
        log.info("agent_call", **{k: v for k, v in record.items() if k != "output_hash"})
        if self.service is not None:
            row = {
                k: record.get(k)
                for k in (
                    "agent",
                    "model",
                    "prompt_version",
                    "input_hash",
                    "output_hash",
                    "tokens_in",
                    "tokens_out",
                    "latency_ms",
                    "status",
                )
            }
            await self.service.insert("agent_calls", row)

    async def _cache_get(self, key: str) -> dict[str, Any] | None:
        if key in self.memory:
            return self.memory[key]
        if self.service is None:
            return None
        try:
            rows = await self.service.select(
                "agent_cache", {"select": "value", "key": f"eq.{key}", "expires_at": "gt.now()"}
            )
        except Exception:
            return None
        if rows:
            self.memory[key] = rows[0]["value"]
            return dict(rows[0]["value"])
        return None

    async def _cache_put(self, key: str, agent: str, value: dict[str, Any]) -> None:
        self.memory[key] = value
        if self.service is not None:
            try:
                await self.service.insert(
                    "agent_cache", {"key": key, "agent": agent, "value": value}, upsert_on="key"
                )
            except Exception:
                log.warning("agent_cache_write_failed", agent=agent)

    async def briefing(
        self,
        forecast: Mapping[str, Any],
        locale: briefing.Locale,
        minimum_change: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        payload = briefing.build_input(forecast, locale, minimum_change)
        model = self.client.config.model(briefing.AGENT)
        key = cache_key(
            briefing.AGENT,
            briefing.PROMPT_VERSION,
            model,
            {"forecast_id": str(forecast["id"]), "payload": payload},
            locale,
        )
        if cached := await self._cache_get(key):
            return cached
        out = await briefing.generate(self.client, payload, _identity)
        value = {
            "text": out.text,
            "source": out.source,
            "model": out.model,
            "prompt_version": out.prompt_version,
        }
        if out.rejected:
            log.info("briefing_fallback", reasons=out.rejected)
        if out.source == "llm":  # templates are free to rebuild; only cache paid answers
            await self._cache_put(key, briefing.AGENT, value)
        return value

    async def suggest_mapping(
        self,
        unmapped: list[str],
        profile: list[dict[str, Any]],
        taken: list[str],
    ) -> dict[str, dict[str, Any]]:
        from sg_api.services.imports import field_options

        return await mapping.suggest(self.client, unmapped, profile, field_options(), taken)


def _identity(text: str, locale: str) -> bool:
    return briefing.phi_identity_check(text, locale)


async def warm_check(service: AgentService) -> None:  # pragma: no cover - startup only
    await asyncio.sleep(0)
