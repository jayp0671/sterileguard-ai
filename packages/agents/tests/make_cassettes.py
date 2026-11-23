"""Write the agent cassettes for the golden cases.

    uv run python packages/agents/tests/make_cassettes.py            # hand-written stand-ins
    NIM_API_KEY=... uv run python packages/agents/tests/make_cassettes.py --live   # real answers

Stand-ins are deterministic answers written here, marked "stand_in": true. They exercise the
client, parsing, guardrail and fallback without a key. --live replaces every non-adversarial
cassette with NVIDIA's real answer (about 50 calls, under 2 minutes at 30 per minute).
Adversarial cassettes are always stand-ins: they are the attack, not a recording.
"""

# ruff: noqa: E501 (golden strings and stand-in answers read better unwrapped)

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from golden import ADVERSARIAL, BRIEFING_CASES, LOCALES, MAPPING_CASES, forecast  # noqa: E402

from sg_agents import briefing, mapping  # noqa: E402
from sg_agents.nim import Completion, NimClient, load_config  # noqa: E402
from sg_data.imports.mapping import MAPPABLE  # noqa: E402
from sg_data.imports.pipeline import run  # noqa: E402

CASSETTES = HERE / "cassettes"
FIELDS = [{"name": f.name, "description": f.description, "unit": f.unit} for f in MAPPABLE]


def adversarial_inputs() -> dict[str, dict[str, Any]]:
    return {
        name: briefing.build_input(forecast(100 + i), "en") for i, name in enumerate(ADVERSARIAL)
    }


def mapping_inputs(case: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    res = run(case["csv"].encode(), f"{case['name']}.csv")
    unmapped = [m.column for m in res.mapping if m.field is None]
    taken = [m.field for m in res.mapping if m.field]
    return unmapped, res.profile, taken


def standin_briefing(p: dict[str, Any]) -> str:
    """A plausible answer that uses only input numbers (worded unlike the template)."""
    es = p["locale"] == "es"
    n = (lambda x: f"{x:.1f}".replace(".", ",")) if es else (lambda x: f"{x:.1f}")
    d = p["drivers"][0]["text"].rstrip(".") if p["drivers"] else ""
    cls = briefing.CLASS_WORDS[p["locale"]][p["burden_class"]]
    mc = p["minimum_change"]
    if es:
        s = f"Para mañana el modelo espera {n(p['ot_p50'])} horas extra, entre {n(p['ot_p10'])} y {n(p['ot_p90'])}."
        s += f" Es un día de carga {cls}, sobre todo por: {d.lower()}."
        if mc:
            s += f" {mc['text']} reduciría la estimación de {n(mc['from_p50'])} a {n(mc['to_p50'])} horas."
        return f"{s} {briefing.ENDINGS['es']}"
    s = f"Expect about {n(p['ot_p50'])} overtime hours tomorrow, somewhere between {n(p['ot_p10'])} and {n(p['ot_p90'])}."
    s += f" That makes it a {cls} burden day, mainly because of this: {d[0].lower() + d[1:]}."
    if mc:
        s += f" {mc['text']} would lower the estimate from {n(mc['from_p50'])} to {n(mc['to_p50'])} hours."
    return f"{s} {briefing.ENDINGS['en']}"


def standin_mapping(case: dict[str, Any], payload_columns: list[str], attempt: int) -> str:
    if case["name"] == "afternoon_cover" and attempt == 0:
        return "Sure! Here are my suggestions: Noon crew -> aft_11_staff"  # invalid JSON: forces the retry
    out = []
    for col in payload_columns:
        field = case["expected"].get(col)
        conf = 0.55 if col in ("Late crew", "Backlog level") else 0.86
        out.append({"column": col, "field": field, "confidence": conf, "reason": "header meaning"})
    return json.dumps(out)


class StandIn:
    """A transport that answers from a function instead of the network."""

    def __init__(self) -> None:
        self.answer = ""

    async def complete(self, model: str, messages: list[dict[str, str]], **_: Any) -> Completion:
        return Completion(self.answer)


def mark(agent: str, key: str, stand_in: bool, extra: dict[str, Any] | None = None) -> None:
    path = CASSETTES / agent / f"{key}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["stand_in"] = stand_in
    data.update(extra or {})
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


async def main(live: bool) -> None:
    cfg = load_config()
    fake = StandIn()
    standin = NimClient(cfg, mode="record", transport=fake, cassette_dir=CASSETTES)
    real = NimClient(cfg, mode="record", cassette_dir=CASSETTES) if live else None
    client = real or standin

    for case in BRIEFING_CASES:
        for loc in LOCALES:
            p = briefing.build_input(case, loc, case.get("minimum_change"))  # type: ignore[arg-type]
            fake.answer = standin_briefing(p)
            await briefing.generate(client, p)
            mark("briefing", briefing.input_hash(client, p), not live)

    for name, p in adversarial_inputs().items():
        fake.answer = ADVERSARIAL[name]
        await briefing.generate(standin, p)
        mark("briefing", briefing.input_hash(standin, p), True, {"adversarial": name})

    for case in MAPPING_CASES:
        unmapped, profile, taken = mapping_inputs(case)
        payload = mapping.build_payload(unmapped, profile, FIELDS, taken)
        sent = [c["header"] for c in payload["columns"]]
        if not sent:
            continue
        model = cfg.model("mapping")
        for attempt in range(2):
            fake.answer = standin_mapping(case, sent, attempt)
            key = mapping.cache_key(
                "mapping", mapping.PROMPT_VERSION, model, {"payload": payload, "attempt": attempt}
            )
            prompt = mapping.load_prompt("mapping", mapping.PROMPT_VERSION).replace(
                "{input_json}", mapping.canonical(payload)
            )
            msgs = [{"role": "user", "content": prompt}]
            await client.chat("mapping", mapping.PROMPT_VERSION, msgs, input_hash=key)
            mark("mapping", key, not live, {"case": case["name"], "attempt": attempt})
            if case["name"] != "afternoon_cover":
                break
    print(f"wrote cassettes under {CASSETTES}")


if __name__ == "__main__":
    asyncio.run(main("--live" in sys.argv))
