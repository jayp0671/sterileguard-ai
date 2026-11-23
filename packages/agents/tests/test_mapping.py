"""SG-23 Part C and SG-26 Part B: mapping agent in replay mode over synthetic files."""

from __future__ import annotations

import asyncio
import json

from golden import MAPPING_CASES
from make_cassettes import FIELDS, mapping_inputs

from sg_agents import mapping
from sg_agents.nim import NimClient

PLANTED = ["Mario Hernandez", "Debra Jones", "Amanda Diaz", "cart late", "washer slow", "quiet day"]


def run_case(client: NimClient, case: dict) -> dict:  # type: ignore[type-arg]
    unmapped, profile, taken = mapping_inputs(case)
    return asyncio.run(mapping.suggest(client, unmapped, profile, FIELDS, taken))


def test_agent_resolves_more_columns_than_deterministic_matching() -> None:
    client = NimClient(mode="replay")
    before = after = 0
    correct = total = 0
    for case in MAPPING_CASES:
        unmapped, _, _ = mapping_inputs(case)
        resolved = run_case(client, case)
        before += 0
        after += len(resolved)
        for col in unmapped:
            want = case["expected"].get(col)
            if want is None:
                continue
            total += 1
            correct += resolved.get(col, {}).get("field") == want
    assert after > before  # deterministic left these unmapped; the agent proposes fields
    assert total and correct / total >= 0.9, (correct, total)


def test_payload_never_holds_phi_columns_or_text_samples() -> None:
    client = NimClient(mode="replay")
    for case in MAPPING_CASES:
        run_case(client, case)
    sent = json.dumps([r["messages"] for r in client.requests])
    for planted in PLANTED:
        assert planted not in sent, planted
    assert "Employee" not in sent  # the dropped names column, not even its header
    for req in client.requests:
        body = req["messages"][0]["content"]
        payload = json.loads(body.split("Input:", 1)[1])
        for col in payload["columns"]:
            if col["dtype"] not in ("number", "date"):
                assert col["samples"] == [], col
            assert len(col["samples"]) <= 3


def test_invalid_json_is_retried_once() -> None:
    client = NimClient(mode="replay")
    case = next(c for c in MAPPING_CASES if c["name"] == "afternoon_cover")
    resolved = run_case(client, case)
    assert len(client.requests) == 2
    assert resolved["Noon crew"]["field"] == "aft_11_staff"
    assert resolved["Late crew"]["confidence"] < 0.6  # shown as "uncertain"


def test_suggestions_are_filtered_to_what_was_sent_and_offered() -> None:
    payload = {"columns": [{"header": "A"}, {"header": "B"}], "fields": [{"name": "mf_cases"}]}
    items = mapping.parse(
        '```json\n[{"column":"A","field":"mf_cases","confidence":0.9,"reason":"x"},'
        '{"column":"B","field":"mf_cases","confidence":0.5,"reason":"y"},'
        '{"column":"Z","field":"mf_cases","confidence":1,"reason":"z"},'
        '{"column":"B","field":"department_id","confidence":1,"reason":"z"}]\n```'
    )
    assert mapping.clean(items, payload) == {
        "A": {"field": "mf_cases", "confidence": 0.9, "reason": "x"}
    }


def test_no_unmapped_columns_means_no_call() -> None:
    client = NimClient(mode="replay")
    assert asyncio.run(mapping.suggest(client, [], [], FIELDS)) == {}
    assert client.requests == []


def test_nim_off_means_manual_mapping() -> None:
    case = MAPPING_CASES[0]
    assert run_case(NimClient(mode="off"), case) == {}
