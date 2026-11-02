"""Free-text guard for notes and reasons (SG-20).

TODO(SG-21): replace with sg_data.phi.guard_text (Presidio plus custom recognizers). Until then
this rejects the obvious identifier patterns: email addresses, phone numbers, SSN-like numbers
and long digit runs that look like record or badge IDs. Only entity types are reported: the
matched text is never echoed, logged or stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sg_api.core.errors import ApiError

PHI_DETECTED = "https://sterileguard.dev/problems/phi-detected"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL_ADDRESS", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("US_SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        "PHONE_NUMBER",
        re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),
    ),
    ("ID_NUMBER", re.compile(r"(?<!\d)(?:[A-Za-z]{1,4}[-#:]?\s?)?\d{6,}(?!\d)")),
)


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    entity_types: list[str]


def guard_text(text: str | None) -> GuardResult:
    if not text:
        return GuardResult(True, [])
    found = [name for name, pattern in _PATTERNS if pattern.search(text)]
    # An SSN or phone number also looks like a long digit run: report the specific type only.
    if "ID_NUMBER" in found and ({"US_SSN", "PHONE_NUMBER"} & set(found)):
        found.remove("ID_NUMBER")
    return GuardResult(not found, found)


def require_clean(text: str | None, field: str) -> None:
    """422 phi_detected naming the field and entity types, never the text."""
    result = guard_text(text)
    if not result.ok:
        raise ApiError(
            422,
            f"{field} looks like it contains identifiers ({', '.join(result.entity_types)}). "
            "Do not enter patient or employee names, contact details or ID numbers.",
            PHI_DETECTED,
        )
