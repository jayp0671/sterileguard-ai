"""SG-23 Part B and SG-26 Part B: briefing guardrail and golden replays."""

from __future__ import annotations

import asyncio

import pytest
from golden import ADVERSARIAL, BRIEFING_CASES, LOCALES
from hypothesis import given, settings
from hypothesis import strategies as st
from make_cassettes import adversarial_inputs

from sg_agents import briefing
from sg_agents.nim import NimClient

identity = briefing.phi_identity_check


def payloads() -> list[dict[str, object]]:
    return [
        briefing.build_input(c, loc, c.get("minimum_change"))  # type: ignore[arg-type]
        for c in BRIEFING_CASES
        for loc in LOCALES
    ]


@pytest.mark.parametrize("payload", payloads(), ids=lambda p: f"{p['date']}-{p['locale']}")
def test_golden_replays_pass_the_guardrail(payload: dict[str, object]) -> None:
    out = asyncio.run(briefing.generate(NimClient(mode="replay"), payload, identity))
    assert out.source == "llm", out.rejected
    assert out.text.endswith(briefing.ENDINGS[str(payload["locale"])])


@pytest.mark.parametrize("name", list(ADVERSARIAL))
def test_adversarial_replays_are_rejected_and_fall_back(name: str) -> None:
    payload = adversarial_inputs()[name]
    out = asyncio.run(briefing.generate(NimClient(mode="replay"), payload, identity))
    assert out.source == "template" and out.rejected, name
    assert out.text == briefing.template(payload)


def test_nim_down_uses_the_template() -> None:
    payload = payloads()[0]
    out = asyncio.run(briefing.generate(NimClient(mode="off"), payload, identity))
    assert out.source == "template" and out.rejected == ["nim_unavailable"]
    assert out.text.startswith("Tomorrow's overtime is most likely")


@pytest.mark.parametrize("payload", payloads()[:6], ids=lambda p: f"{p['date']}-{p['locale']}")
def test_the_template_always_passes_its_own_guardrail(payload: dict[str, object]) -> None:
    assert briefing.check(briefing.template(payload), payload, identity).ok


def test_numbers_are_matched_after_the_inputs_rounding() -> None:
    p = briefing.build_input(
        {
            "target_date": "2026-11-24",
            "ot_p10": 10.94,
            "ot_p50": 11.76,
            "ot_p90": 12.51,
            "burden_class": "moderate",
            "burden_probs": {"moderate": 0.7},
            "drivers": [],
        }
    )
    assert p["ot_p50"] == 11.8
    ok = "Most likely 11.8 hours, range 10.9 to 12.5, a moderate day (70% likely). Model estimate."
    assert briefing.check(ok, p).ok
    assert "number_not_in_input:1" in briefing.check(ok.replace("11.8", "11.76"), p).reasons
    assert briefing.check(ok.replace("11.8", "12"), p).reasons[0].startswith("number_not_in_input")


def test_spanish_decimal_commas_count_as_numbers() -> None:
    p = briefing.build_input(
        {
            "target_date": "2026-11-24",
            "ot_p10": 1,
            "ot_p50": 2.5,
            "ot_p90": 4,
            "burden_class": "low",
            "burden_probs": {"low": 0.9},
            "drivers": [],
        },
        "es",
    )
    assert briefing.check("Unas 2,5 horas extra. Estimación del modelo.", p).ok
    assert not briefing.check("Unas 3,5 horas extra. Estimación del modelo.", p).ok


@settings(max_examples=200, deadline=None)
@given(
    case=st.sampled_from(BRIEFING_CASES),
    locale=st.sampled_from(LOCALES),
    invented=st.floats(min_value=0, max_value=500, allow_nan=False).map(lambda x: round(x, 1)),
)
def test_property_no_briefing_ever_contains_an_invented_number(case, locale, invented) -> None:  # type: ignore[no-untyped-def]
    """An answer with any number absent from the input is never accepted."""
    payload = briefing.build_input(case, locale, case.get("minimum_change"))
    allowed = briefing.allowed_numbers(payload)
    if round(invented, 6) in allowed or (
        round(float(int(invented)), 6) in allowed and invented == int(invented)
    ):
        return
    shown = f"{invented:.1f}" if locale == "en" else f"{invented:.1f}".replace(".", ",")
    body = briefing.template(payload)[: -len(briefing.ENDINGS[locale])]
    text = f"{body}Also {shown} hours. {briefing.ENDINGS[locale]}"
    verdict = briefing.check(text, payload)
    assert not verdict.ok and any(r.startswith("number_not_in_input") for r in verdict.reasons)
    # And whatever generate() returns only ever holds input numbers.
    for n in briefing.numbers_in(briefing.template(payload)):
        assert round(n, 6) in allowed
