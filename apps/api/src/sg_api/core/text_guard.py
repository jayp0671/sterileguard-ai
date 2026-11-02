"""Free-text guard for notes and reasons (SG-20, SG-21).

Uses sg_data.phi.guard_text: Presidio with spaCy's small English model plus custom recognizers
for names, emails, phone numbers, SSNs, MRN-like IDs and dates of birth. Only entity types are
reported: the matched text is never echoed, logged or stored. The analyzer loads once (about
4 s); the API warms it in the background at startup, and checks run in a worker thread so the
event loop never waits on spaCy.
"""

from __future__ import annotations

import asyncio

from sg_api.core.errors import ApiError
from sg_data.phi import GuardResult, analyzer, guard_text

PHI_DETECTED = "https://sterileguard.dev/problems/phi-detected"

__all__ = ["PHI_DETECTED", "GuardResult", "guard_text", "require_clean", "warm"]


async def require_clean(text: str | None, field: str) -> None:
    """422 phi_detected naming the field and entity types, never the text."""
    if not text or not text.strip():
        return
    result = await asyncio.to_thread(guard_text, text)
    if not result.ok:
        raise ApiError(
            422,
            f"{field} looks like it contains identifiers ({', '.join(result.entity_types)}). "
            "Do not enter patient or employee names, contact details or ID numbers.",
            PHI_DETECTED,
        )


async def warm() -> None:
    await asyncio.to_thread(analyzer)
