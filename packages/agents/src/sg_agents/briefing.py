"""Briefing agent (SG-23 Part B, plan §13).

The LLM rewords the structured forecast into 3 or 4 sentences. It never predicts: a guardrail
rejects any answer that states a number not present in the input (after the input's own
rounding to 1 decimal), runs over 600 characters, contains a link or something that looks
like a person's name or contact details, or does not end with the localized "Model estimate."
A rejected or failed call falls back to a fixed template, so the page always has a briefing.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from sg_agents.nim import NimClient, NimError, cache_key, canonical, load_prompt

AGENT = "briefing"
PROMPT_VERSION = "v1"
MAX_CHARS = 600
ENDINGS = {"en": "Model estimate.", "es": "Estimación del modelo."}
CLASS_WORDS = {
    "en": {"low": "low", "moderate": "moderate", "high": "high"},
    "es": {"low": "baja", "moderate": "moderada", "high": "alta"},
}
NUMBER = re.compile(r"(?<![\w.,])-?\d+(?:[.,]\d+)?(?![\w])")
URL = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(com|org|net|edu|gov|io|dev|ai)\b)", re.I)
Locale = Literal["en", "es"]


def phi_identity_check(text: str, locale: str) -> bool:
    """True when the text looks like it names a person or holds contact details or IDs.
    spaCy's small English model reads Spanish words as names, so for Spanish only the pattern
    recognizers count (email, phone, SSN, MRN, honorific + surname); see SG-27."""
    from sg_data.phi import guard_text

    types = set(guard_text(text).entity_types)
    if locale != "en":
        types.discard("PERSON")
    return bool(types)


def r1(x: float) -> float:
    return round(float(x) + 0.0, 1)


def build_input(
    forecast: Mapping[str, Any],
    locale: Locale = "en",
    minimum_change: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The only facts the LLM sees. Numbers are rounded to 1 decimal here, once."""
    probs = forecast.get("burden_probs") or {}
    cls = str(forecast.get("burden_class", "moderate"))
    prob = float(probs.get(cls, 0.0))
    drivers = sorted(forecast.get("drivers") or [], key=lambda d: d.get("rank", 99))[:3]
    return {
        "date": str(forecast["target_date"]),
        "ot_p10": r1(forecast["ot_p10"]),
        "ot_p50": r1(forecast["ot_p50"]),
        "ot_p90": r1(forecast["ot_p90"]),
        "burden_class": cls,
        "burden_prob": round(prob, 2),
        "burden_prob_pct": round(prob * 100),
        "drivers": [
            {"text": str(d.get("default_text", "")), "hours": r1(d.get("contribution_hours", 0))}
            for d in drivers
        ],
        "minimum_change": (
            {
                "text": str(minimum_change["text"]),
                "from_p50": r1(minimum_change["from_p50"]),
                "to_p50": r1(minimum_change["to_p50"]),
            }
            if minimum_change
            else None
        ),
        "locale": locale,
    }


def _walk_numbers(obj: Any) -> Iterable[float]:
    if isinstance(obj, bool):
        return
    if isinstance(obj, int | float):
        yield float(obj)
        yield r1(obj)
    elif isinstance(obj, str):
        for m in NUMBER.finditer(obj):
            yield float(m.group().replace(",", "."))
    elif isinstance(obj, Mapping):
        for v in obj.values():
            yield from _walk_numbers(v)
    elif isinstance(obj, list | tuple):
        for v in obj:
            yield from _walk_numbers(v)


def allowed_numbers(payload: Mapping[str, Any]) -> set[float]:
    return {round(x, 6) for x in _walk_numbers(payload)}


def numbers_in(text: str) -> list[float]:
    return [float(m.group().replace(",", ".")) for m in NUMBER.finditer(text)]


@dataclass
class Check:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def check(
    text: str,
    payload: Mapping[str, Any],
    identity_check: Callable[[str, str], bool] | None = None,
) -> Check:
    """Every rule the answer must pass; reasons name the rule, never echo the text."""
    locale = str(payload.get("locale", "en"))
    reasons: list[str] = []
    allowed = allowed_numbers(payload)
    invented = [n for n in numbers_in(text) if round(n, 6) not in allowed]
    if invented:
        reasons.append(f"number_not_in_input:{len(invented)}")
    if len(text) > MAX_CHARS:
        reasons.append("too_long")
    if URL.search(text):
        reasons.append("url")
    if not text.rstrip().endswith(ENDINGS.get(locale, ENDINGS["en"])):
        reasons.append("missing_ending")
    if identity_check is not None and identity_check(text, locale):
        reasons.append("identifier")
    return Check(ok=not reasons, reasons=reasons)


def template(payload: Mapping[str, Any]) -> str:
    """i18n key briefing.template, filled from the same input (so it passes the guardrail)."""
    locale = str(payload.get("locale", "en"))
    cls = CLASS_WORDS.get(locale, CLASS_WORDS["en"]).get(str(payload["burden_class"]), "")
    drivers = [d["text"].rstrip(".") for d in payload.get("drivers", []) if d.get("text")]
    mc = payload.get("minimum_change")

    def f(x: float) -> str:
        text = f"{x:.1f}"
        return text if locale == "en" else text.replace(".", ",")

    if locale == "es":
        out = (
            f"Lo más probable es que mañana haya {f(payload['ot_p50'])} horas extra "
            f"(rango de {f(payload['ot_p10'])} a {f(payload['ot_p90'])}), un día de carga {cls}."
        )
        if drivers:
            out += (
                " Los factores principales son " + " y ".join(d.lower() for d in drivers[:2]) + "."
            )
        if mc:
            out += f" {mc['text']} las bajaría de {f(mc['from_p50'])} a {f(mc['to_p50'])} horas."
        return f"{out} {ENDINGS['es']}"
    out = (
        f"Tomorrow's overtime is most likely {f(payload['ot_p50'])} hours "
        f"(range {f(payload['ot_p10'])} to {f(payload['ot_p90'])}), a {cls} burden day."
    )
    if drivers:
        out += (
            " The biggest factors are "
            + " and ".join(d[0].lower() + d[1:] for d in drivers[:2])
            + "."
        )
    if mc:
        out += f" {mc['text']} would bring it from {f(mc['from_p50'])} to {f(mc['to_p50'])} hours."
    return f"{out} {ENDINGS['en']}"


@dataclass
class Briefing:
    text: str
    source: Literal["llm", "template"]
    model: str | None
    prompt_version: str
    rejected: list[str] = field(default_factory=list)


def input_hash(client: NimClient, payload: Mapping[str, Any]) -> str:
    return cache_key(
        AGENT, PROMPT_VERSION, client.config.model(AGENT), payload, str(payload["locale"])
    )


def messages(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    prompt = load_prompt(AGENT, PROMPT_VERSION).replace("{input_json}", canonical(payload))
    return [{"role": "user", "content": prompt}]


async def generate(
    client: NimClient,
    payload: Mapping[str, Any],
    identity_check: Callable[[str, str], bool] | None = None,
) -> Briefing:
    """LLM briefing if it passes every rule, else the template. Never raises for NIM trouble."""
    fallback = template(payload)
    if not client.available:
        return Briefing(fallback, "template", None, PROMPT_VERSION, ["nim_unavailable"])
    try:
        result = await client.chat(
            AGENT, PROMPT_VERSION, messages(payload), input_hash=input_hash(client, payload)
        )
    except NimError:
        return Briefing(fallback, "template", None, PROMPT_VERSION, ["nim_error"])
    text = " ".join(result.text.split())
    verdict = check(text, payload, identity_check)
    if not verdict.ok:
        return Briefing(fallback, "template", result.model, PROMPT_VERSION, verdict.reasons)
    return Briefing(text, "llm", result.model, PROMPT_VERSION)
