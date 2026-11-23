"""Import mapping agent (SG-23 Part C, plan §10.1 and §13).

Runs only for columns still unmapped after templates and deterministic matching. What it may
send is narrow and asserted in tests:
- headers and inferred types of unmapped columns that the PHI guard did not flag (columns it
  dropped never reach the profile at all);
- up to 3 sample values, only for number or date columns; text samples are never sent;
- the schema fields still free, with descriptions and units.

The hosted NIM chat schema has no JSON response format, so the answer is parsed and validated
with Pydantic, with one retry on invalid JSON. Suggestions are never applied: the review
screen shows them (confidence under 0.6 is "uncertain") and a person picks. An approved
mapping is saved as a template, so the next file with the same columns needs no LLM call.

(The ticket places this in sg_data/imports/llm_mapping.py. It lives here so sg_data, which the
CLI and the deterministic pipeline use, has no LLM dependency.)
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from sg_agents.nim import NimClient, NimError, cache_key, canonical, load_prompt

AGENT = "mapping"
PROMPT_VERSION = "v1"
SAMPLE_TYPES = frozenset({"number", "date"})
MAX_SAMPLES = 3


class Suggestion(BaseModel):
    column: str
    field: str | None
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(default="", max_length=200)


class Suggestions(BaseModel):
    items: list[Suggestion]


def build_payload(
    unmapped: Sequence[str],
    profile: Iterable[Mapping[str, Any]],
    fields: Iterable[Mapping[str, Any]],
    taken: Iterable[str] = (),
) -> dict[str, Any]:
    by_col = {str(p["column"]): p for p in profile}
    columns = []
    for name in unmapped:
        p = by_col.get(name)
        if p is None or p.get("phi"):
            continue  # flagged or dropped columns are never sent, not even their header
        dtype = str(p.get("dtype", "empty"))
        samples = (
            [str(s) for s in p.get("samples", [])][:MAX_SAMPLES] if dtype in SAMPLE_TYPES else []
        )
        columns.append({"header": name, "dtype": dtype, "samples": samples})
    used = set(taken)
    return {
        "columns": columns,
        "fields": [
            {"name": f["name"], "description": f.get("description", ""), "unit": f.get("unit", "")}
            for f in fields
            if f["name"] not in used
        ],
    }


FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def parse(text: str) -> list[Suggestion]:
    raw = FENCE.sub("", text.strip())
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end < start:
        raise ValueError("no JSON array in the answer")
    return Suggestions(items=json.loads(raw[start : end + 1])).items


def clean(items: list[Suggestion], payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Only columns we sent and fields we offered; one column per field (highest confidence)."""
    sent = {c["header"] for c in payload["columns"]}
    offered = {f["name"] for f in payload["fields"]}
    best: dict[str, Suggestion] = {}
    for s in sorted(items, key=lambda s: -s.confidence):
        if s.column not in sent or s.field is None or s.field not in offered:
            continue
        if s.field in {b.field for b in best.values()} or s.column in best:
            continue
        best[s.column] = s
    return {
        c: {"field": s.field, "confidence": round(s.confidence, 2), "reason": s.reason}
        for c, s in best.items()
    }


async def suggest(
    client: NimClient,
    unmapped: Sequence[str],
    profile: Iterable[Mapping[str, Any]],
    fields: Iterable[Mapping[str, Any]],
    taken: Iterable[str] = (),
) -> dict[str, dict[str, Any]]:
    """{column: {field, confidence, reason}}; empty on any failure (manual mapping)."""
    payload = build_payload(unmapped, profile, fields, taken)
    if not payload["columns"] or not client.available:
        return {}
    prompt = load_prompt(AGENT, PROMPT_VERSION).replace("{input_json}", canonical(payload))
    msgs: list[dict[str, str]] = [{"role": "user", "content": prompt}]
    model = client.config.model(AGENT)
    for attempt in range(2):
        key = cache_key(AGENT, PROMPT_VERSION, model, {"payload": payload, "attempt": attempt})
        try:
            result = await client.chat(AGENT, PROMPT_VERSION, msgs, input_hash=key, max_tokens=800)
        except NimError:
            return {}
        try:
            return clean(parse(result.text), payload)
        except (ValueError, ValidationError):
            msgs = [
                *msgs,
                {"role": "assistant", "content": result.text},
                {
                    "role": "user",
                    "content": "That was not a valid JSON array. Reply with the JSON array only.",
                },
            ]
    return {}
