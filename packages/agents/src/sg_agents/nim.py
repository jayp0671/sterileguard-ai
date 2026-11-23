"""NVIDIA NIM client (SG-23, plan §13).

The hosted NIM API is OpenAI-compatible (https://integrate.api.nvidia.com/v1, bearer key from
build.nvidia.com), so calls go through the `openai` SDK with NVIDIA's base URL. Everything
around the call is ours, because the free tier is rate limited (about 40 requests a minute)
and every agent must fall back to a non-AI path:

- a token bucket at 30 requests a minute per process;
- up to 3 retries with exponential backoff and jitter on 429, 5xx, timeouts and connection
  errors;
- a 20 second timeout per attempt;
- a circuit breaker that opens for 5 minutes after 5 consecutive failed calls.

Modes (`NIM_MODE`):
- `live` calls NVIDIA (needs NIM_API_KEY);
- `record` calls NVIDIA and saves each answer to tests/cassettes/<agent>/<input_hash>.json;
- `replay` reads cassettes and never touches the network; a missing cassette is an error,
  so tests cannot silently fall back. CI always runs in replay.
- `off` (the default without a key) makes every call unavailable, so agents use their
  template or manual fallback.

Usage records carry hashes, token counts, latency and status, never prompt or answer text.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml

Mode = Literal["live", "record", "replay", "off"]
RETRYABLE = frozenset({408, 409, 429, 500, 502, 503, 504})


class NimError(Exception):
    """A call failed; agents catch this and fall back."""


class NimUnavailable(NimError):
    """No key, mode off, or the circuit breaker is open."""


class CassetteMissing(AssertionError):
    """Replay mode found no recorded answer: record one, never call live in tests."""


class TransportError(Exception):
    def __init__(self, status: int | None, message: str = "") -> None:
        super().__init__(message or f"transport error {status}")
        self.status = status

    @property
    def retryable(self) -> bool:
        return self.status is None or self.status in RETRYABLE


# --------------------------------------------------------------------------------------------
# Config and prompts
# --------------------------------------------------------------------------------------------


def prompts_dir() -> Path:
    """ops/prompts: SG_PROMPTS_DIR, else the first ancestor of this file that has it."""
    if env := os.environ.get("SG_PROMPTS_DIR"):
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "ops" / "prompts"
        if (candidate / "models.yaml").exists():
            return candidate
    raise FileNotFoundError("ops/prompts/models.yaml not found; set SG_PROMPTS_DIR")


@dataclass(frozen=True)
class Config:
    base_url: str = "https://integrate.api.nvidia.com/v1"
    models: Mapping[str, str] = field(default_factory=dict)
    requests_per_minute: int = 30
    timeout_s: float = 20.0
    max_retries: int = 3
    breaker_failures: int = 5
    breaker_open_s: float = 300.0

    def model(self, agent: str) -> str:
        if agent not in self.models:
            raise KeyError(f"no model configured for agent {agent!r} in models.yaml")
        return self.models[agent]


def load_config(path: Path | None = None) -> Config:
    raw = yaml.safe_load((path or prompts_dir() / "models.yaml").read_text(encoding="utf-8"))
    return Config(
        base_url=raw.get("base_url", Config.base_url),
        models=dict(raw.get("models") or {}),
        requests_per_minute=int(raw.get("requests_per_minute", 30)),
        timeout_s=float(raw.get("timeout_s", 20)),
        max_retries=int(raw.get("max_retries", 3)),
        breaker_failures=int(raw.get("breaker_failures", 5)),
        breaker_open_s=float(raw.get("breaker_open_s", 300)),
    )


def load_prompt(agent: str, version: str = "v1") -> str:
    return (prompts_dir() / agent / f"{version}.md").read_text(encoding="utf-8")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def cache_key(agent: str, prompt_version: str, model: str, payload: Any, locale: str = "") -> str:
    """sha256(agent + prompt_version + model + canonical input JSON + locale). Also the
    cassette file name, so a recorded answer belongs to exactly one input."""
    raw = "\x1f".join([agent, prompt_version, model, canonical(payload), locale])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------
# Reliability
# --------------------------------------------------------------------------------------------

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class TokenBucket:
    """`rate` tokens a minute, bucket size `rate` would allow bursts the free tier rejects, so
    the bucket holds at most `burst` tokens (default 5)."""

    def __init__(
        self,
        per_minute: int,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        burst: int = 5,
    ) -> None:
        self.rate = per_minute / 60.0
        self.capacity = float(max(1, min(burst, per_minute)))
        self.tokens = self.capacity
        self.clock = clock
        self.sleep = sleep
        self.updated = clock()
        self.lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self.clock()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now

    async def acquire(self) -> float:
        """Wait for a token; returns how long it waited (seconds)."""
        waited = 0.0
        async with self.lock:
            self._refill()
            while self.tokens < 1:
                wait = (1 - self.tokens) / self.rate
                await self.sleep(wait)
                waited += wait
                self._refill()
            self.tokens -= 1
        return waited


class CircuitBreaker:
    def __init__(self, failures: int, open_s: float, clock: Clock = time.monotonic) -> None:
        self.threshold = failures
        self.open_s = open_s
        self.clock = clock
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if self.clock() - self.opened_at >= self.open_s:
            # Half-open: let the next call try; one more failure re-opens it.
            self.opened_at = None
            self.failures = self.threshold - 1
            return False
        return True

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = self.clock()


def backoff(attempt: int, rng: random.Random, base: float = 0.5, cap: float = 8.0) -> float:
    """Exponential backoff with full jitter: uniform(0, min(cap, base * 2**attempt))."""
    return rng.uniform(0, min(cap, base * (2**attempt)))


# --------------------------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------------------------


@dataclass
class Completion:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


class Transport(Protocol):
    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> Completion: ...


class OpenAITransport:
    """The real call, through the openai SDK pointed at NVIDIA. SDK retries are off: ours
    are counted by the breaker and the limiter."""

    def __init__(self, base_url: str, api_key: str) -> None:
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key, max_retries=0)

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> Completion:
        import openai

        try:
            resp = await self.client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        except openai.APIStatusError as exc:
            raise TransportError(exc.status_code, "NIM returned an error") from exc
        except (openai.APITimeoutError, openai.APIConnectionError) as exc:
            raise TransportError(None, "NIM timed out or was unreachable") from exc
        usage = resp.usage
        return Completion(
            text=(resp.choices[0].message.content or "").strip(),
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
        )


# --------------------------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------------------------


@dataclass
class ChatResult:
    text: str
    model: str
    input_hash: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    source: Literal["live", "replay"] = "live"


UsageSink = Callable[[dict[str, Any]], Any]


def default_cassette_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "cassettes"


def resolve_mode(api_key: str | None) -> Mode:
    mode = os.environ.get("NIM_MODE", "").strip().lower()
    if mode in ("live", "record", "replay", "off"):
        return mode  # type: ignore[return-value]
    return "live" if api_key else "off"


class NimClient:
    def __init__(
        self,
        config: Config | None = None,
        *,
        mode: Mode | None = None,
        api_key: str | None = None,
        transport: Transport | None = None,
        cassette_dir: Path | None = None,
        on_call: UsageSink | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.config = config or load_config()
        self.api_key = api_key if api_key is not None else os.environ.get("NIM_API_KEY") or None
        self.mode: Mode = mode or resolve_mode(self.api_key)
        self._transport = transport
        self.cassettes = cassette_dir or default_cassette_dir()
        self.on_call = on_call
        self.sleep = sleep
        self.rng = rng or random.Random()
        self.bucket = TokenBucket(self.config.requests_per_minute, clock, sleep)
        self.breaker = CircuitBreaker(
            self.config.breaker_failures, self.config.breaker_open_s, clock
        )
        # Replay keeps every request it served, so tests can assert what would have been sent.
        self.requests: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        if self.mode == "replay":
            return True
        return self.mode in ("live", "record") and bool(self.api_key or self._transport)

    def transport(self) -> Transport:
        if self._transport is None:
            if not self.api_key:
                raise NimUnavailable("NIM_API_KEY is not set")
            self._transport = OpenAITransport(self.config.base_url, self.api_key)
        return self._transport

    def _cassette(self, agent: str, input_hash: str) -> Path:
        return self.cassettes / agent / f"{input_hash}.json"

    async def _usage(self, **record: Any) -> None:
        if self.on_call is None:
            return
        try:
            out = self.on_call(record)
            if asyncio.iscoroutine(out):
                await out
        except Exception:  # usage logging must never break a call
            pass

    async def chat(
        self,
        agent: str,
        prompt_version: str,
        messages: list[dict[str, str]],
        *,
        input_hash: str,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> ChatResult:
        model = self.config.model(agent)
        started = time.perf_counter()
        base = {
            "agent": agent,
            "model": model,
            "prompt_version": prompt_version,
            "input_hash": input_hash,
        }

        if self.mode == "replay":
            path = self._cassette(agent, input_hash)
            if not path.exists():
                raise CassetteMissing(f"no cassette {path.relative_to(self.cassettes)}")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.requests.append({"agent": agent, "input_hash": input_hash, "messages": messages})
            if data.get("error"):
                # A recorded outage: the agent must fall back exactly as it would live.
                raise NimError(f"replayed error {data['error']}")
            return ChatResult(
                text=data["text"],
                model=data.get("model", model),
                input_hash=input_hash,
                source="replay",
            )

        if not self.available:
            raise NimUnavailable("NIM is off (no NIM_API_KEY, or NIM_MODE=off)")
        if self.breaker.is_open:
            await self._usage(**base, status="breaker_open", latency_ms=0)
            raise NimUnavailable("NIM circuit breaker is open")

        last: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            await self.bucket.acquire()
            try:
                done = await self.transport().complete(
                    model,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=self.config.timeout_s,
                )
            except TransportError as exc:
                last = exc
                if exc.retryable and attempt < self.config.max_retries:
                    await self.sleep(backoff(attempt, self.rng))
                    continue
                break
            self.breaker.success()
            latency = int((time.perf_counter() - started) * 1000)
            await self._usage(
                **base,
                output_hash=sha(done.text),
                tokens_in=done.tokens_in,
                tokens_out=done.tokens_out,
                latency_ms=latency,
                status="ok",
            )
            if self.mode == "record":
                path = self._cassette(agent, input_hash)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps({"model": model, "messages": messages, "text": done.text}, indent=2)
                    + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
            return ChatResult(
                text=done.text,
                model=model,
                input_hash=input_hash,
                tokens_in=done.tokens_in,
                tokens_out=done.tokens_out,
                latency_ms=latency,
            )

        self.breaker.failure()
        status = getattr(last, "status", None)
        await self._usage(
            **base,
            status=f"error_{status}" if status else "error_network",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        raise NimError(f"NIM call failed after retries ({status or 'network'})") from last
