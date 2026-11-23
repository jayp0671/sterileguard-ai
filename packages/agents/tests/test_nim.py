"""SG-23 Part A: limiter, retries, breaker, modes and usage records. No network."""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Any

import pytest

from sg_agents.nim import (
    CassetteMissing,
    CircuitBreaker,
    Completion,
    Config,
    NimClient,
    NimError,
    NimUnavailable,
    TokenBucket,
    TransportError,
    backoff,
    cache_key,
    load_config,
)

CFG = Config(models={"briefing": "meta/llama-3.3-70b-instruct"}, requests_per_minute=30)
MSGS = [{"role": "user", "content": "hi"}]


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


class Scripted:
    """Raises or answers in order; counts calls."""

    def __init__(self, *steps: Any) -> None:
        self.steps = list(steps)
        self.calls = 0

    async def complete(self, model: str, messages: list[dict[str, str]], **kw: Any) -> Completion:
        self.calls += 1
        step = self.steps.pop(0) if self.steps else "ok"
        if isinstance(step, Exception):
            raise step
        return Completion(step, tokens_in=10, tokens_out=5)


def client(transport: Any, clock: FakeClock, **kw: Any) -> NimClient:
    return NimClient(
        CFG,
        mode="live",
        api_key="test-key",
        transport=transport,
        clock=clock,
        sleep=clock.sleep,
        rng=random.Random(0),
        **kw,
    )


def test_models_yaml_pins_every_agent() -> None:
    cfg = load_config()
    assert cfg.base_url == "https://integrate.api.nvidia.com/v1"
    assert set(cfg.models) == {"briefing", "mapping", "translation", "coding"}
    assert all("/" in m for m in cfg.models.values())
    assert cfg.requests_per_minute == 30 and cfg.timeout_s == 20 and cfg.max_retries == 3


def test_token_bucket_holds_30_per_minute() -> None:
    clock = FakeClock()
    bucket = TokenBucket(30, clock, clock.sleep)

    async def go() -> None:
        for _ in range(35):
            await bucket.acquire()

    asyncio.run(go())
    # 5 burst tokens, then one every 2 s: 30 more take 60 s.
    assert clock.t == pytest.approx(60.0)


def test_retries_429_and_5xx_with_backoff_then_succeeds() -> None:
    clock = FakeClock()
    t = Scripted(TransportError(429), TransportError(503), TransportError(None), "fine")
    c = client(t, clock)
    out = asyncio.run(c.chat("briefing", "v1", MSGS, input_hash="h"))
    assert out.text == "fine" and t.calls == 4
    backoffs = [s for s in clock.slept if s > 0]
    assert len(backoffs) == 3
    assert all(0 <= b <= 8 for b in backoffs)


def test_does_not_retry_client_errors() -> None:
    clock = FakeClock()
    t = Scripted(TransportError(400))
    with pytest.raises(NimError):
        asyncio.run(client(t, clock).chat("briefing", "v1", MSGS, input_hash="h"))
    assert t.calls == 1


def test_gives_up_after_three_retries() -> None:
    clock = FakeClock()
    t = Scripted(*[TransportError(500)] * 10)
    with pytest.raises(NimError):
        asyncio.run(client(t, clock).chat("briefing", "v1", MSGS, input_hash="h"))
    assert t.calls == 4


def test_backoff_is_exponential_with_full_jitter() -> None:
    rng = random.Random(1)
    caps = [0.5, 1, 2, 4, 8, 8]
    for attempt, cap in enumerate(caps):
        assert all(0 <= backoff(attempt, rng) <= cap for _ in range(50))


def test_breaker_opens_after_five_failures_for_five_minutes() -> None:
    clock = FakeClock()
    b = CircuitBreaker(5, 300, clock)
    for _ in range(4):
        b.failure()
    assert not b.is_open
    b.failure()
    assert b.is_open
    clock.t += 299
    assert b.is_open
    clock.t += 2
    assert not b.is_open  # half-open: one try allowed
    b.failure()
    assert b.is_open  # and one more failure re-opens it


def test_open_breaker_short_circuits_calls() -> None:
    clock = FakeClock()
    t = Scripted(*[TransportError(500)] * 100)
    c = client(t, clock)
    for _ in range(5):
        with pytest.raises(NimError):
            asyncio.run(c.chat("briefing", "v1", MSGS, input_hash="h"))
    calls = t.calls
    with pytest.raises(NimUnavailable):
        asyncio.run(c.chat("briefing", "v1", MSGS, input_hash="h"))
    assert t.calls == calls  # no request while open


def test_usage_records_hashes_never_text() -> None:
    clock = FakeClock()
    seen: list[dict[str, Any]] = []
    secret = "the answer text"
    c = client(Scripted(secret), clock, on_call=seen.append)
    asyncio.run(
        c.chat("briefing", "v1", [{"role": "user", "content": "prompt text"}], input_hash="ih")
    )
    (rec,) = seen
    assert rec["status"] == "ok" and rec["input_hash"] == "ih" and len(rec["output_hash"]) == 64
    assert rec["tokens_in"] == 10 and rec["tokens_out"] == 5
    assert secret not in json.dumps(rec) and "prompt text" not in json.dumps(rec)


def test_replay_reads_cassettes_and_missing_one_fails(tmp_path: Path) -> None:
    (tmp_path / "briefing").mkdir()
    (tmp_path / "briefing" / "abc.json").write_text(json.dumps({"text": "hello", "model": "m"}))
    c = NimClient(CFG, mode="replay", cassette_dir=tmp_path)
    assert asyncio.run(c.chat("briefing", "v1", MSGS, input_hash="abc")).text == "hello"
    assert c.requests[0]["messages"] == MSGS
    with pytest.raises(CassetteMissing):
        asyncio.run(c.chat("briefing", "v1", MSGS, input_hash="missing"))


def test_record_mode_writes_the_cassette(tmp_path: Path) -> None:
    clock = FakeClock()
    c = NimClient(
        CFG,
        mode="record",
        transport=Scripted("saved"),
        cassette_dir=tmp_path,
        clock=clock,
        sleep=clock.sleep,
    )
    asyncio.run(c.chat("briefing", "v1", MSGS, input_hash="k1"))
    assert json.loads((tmp_path / "briefing" / "k1.json").read_text())["text"] == "saved"


def test_off_without_key() -> None:
    c = NimClient(CFG, mode=None, api_key="")
    assert c.mode in ("off", "replay")  # replay here because the test env forces it
    off = NimClient(CFG, mode="off")
    assert not off.available
    with pytest.raises(NimUnavailable):
        asyncio.run(off.chat("briefing", "v1", MSGS, input_hash="h"))


def test_cache_key_depends_on_every_part() -> None:
    base = cache_key("briefing", "v1", "m", {"a": 1}, "en")
    assert base == cache_key("briefing", "v1", "m", {"a": 1}, "en")
    for other in (
        cache_key("mapping", "v1", "m", {"a": 1}, "en"),
        cache_key("briefing", "v2", "m", {"a": 1}, "en"),
        cache_key("briefing", "v1", "m2", {"a": 1}, "en"),
        cache_key("briefing", "v1", "m", {"a": 2}, "en"),
        cache_key("briefing", "v1", "m", {"a": 1}, "es"),
    ):
        assert other != base
