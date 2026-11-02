"""Map source columns to schema fields (SG-21, plan §10.1 step 4). Deterministic first: a
saved template for the file's column signature, then exact names, synonyms and labels from
sg_data.schema, then RapidFuzz token_set_ratio >= 85. Each column maps to at most one field and
each field to at most one column; conflicts go to the highest score. LLM suggestions come in
SG-23."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

from sg_data.schema import FIELDS

FUZZY_MIN = 85
Method = Literal["exact", "synonym", "fuzzy", "template"]
# Fields an import can fill: inputs and outcomes (meta fields are set by the pipeline).
MAPPABLE = [f for f in FIELDS if f.role != "meta"]


@dataclass(frozen=True)
class ColumnMapping:
    column: str
    field: str | None
    method: Method | None
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize(header: str) -> str:
    """Lowercase, units in brackets removed, punctuation to spaces, spaces collapsed."""
    s = str(header).lower()
    s = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", " ", s)
    s = s.replace("#", " number ").replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def signature(headers: Iterable[str]) -> str:
    """sha256 of the sorted normalized headers: one template per file layout."""
    joined = "\n".join(sorted(normalize(h) for h in headers))
    return hashlib.sha256(joined.encode()).hexdigest()


def _candidates() -> dict[str, list[tuple[str, Method]]]:
    out: dict[str, list[tuple[str, Method]]] = {}
    for f in MAPPABLE:
        names: list[tuple[str, Method]] = [(normalize(f.name), "exact")]
        names += [(normalize(s), "synonym") for s in f.synonyms]
        if f.label:
            names.append((normalize(f.label), "synonym"))
        out[f.name] = names
    return out


def _score(header: str, field: str, cands: list[tuple[str, Method]]) -> tuple[float, Method] | None:
    from rapidfuzz import fuzz

    norm = normalize(header)
    for name, method in cands:
        if norm == name:
            return 100.0, method
    best = max(fuzz.token_set_ratio(norm, name) for name, _ in cands)
    return (float(best), "fuzzy") if best >= FUZZY_MIN else None


def propose(
    headers: list[str],
    templates: Mapping[str, Mapping[str, str | None]] | None = None,
    skip: Iterable[str] = (),
) -> list[ColumnMapping]:
    """One entry per header (in order). `templates` maps a column signature to a saved
    {column: field} mapping. Columns in `skip` (dropped by the PHI guard) map to nothing."""
    skipped = set(skip)
    sig = signature(headers)
    if templates and sig in templates:
        saved = templates[sig]
        return [
            ColumnMapping(h, saved.get(h), "template" if saved.get(h) else None, 100.0)
            for h in headers
        ]
    cands = _candidates()
    scored: list[tuple[float, int, str, str, Method]] = []
    for i, h in enumerate(headers):
        if h in skipped:
            continue
        for field, names in cands.items():
            hit = _score(h, field, names)
            if hit:
                # exact beats synonym beats fuzzy at the same score
                rank = {"exact": 2, "synonym": 1, "fuzzy": 0}[hit[1]]
                scored.append((hit[0] + rank / 10, i, h, field, hit[1]))
    scored.sort(key=lambda t: (-t[0], t[1]))
    taken_cols: dict[str, ColumnMapping] = {}
    taken_fields: set[str] = set()
    for score, _, h, field, method in scored:
        if h in taken_cols or field in taken_fields:
            continue
        taken_cols[h] = ColumnMapping(h, field, method, round(min(score, 100.0), 1))
        taken_fields.add(field)
    return [taken_cols.get(h, ColumnMapping(h, None, None, 0.0)) for h in headers]


def as_dict(mapping: Iterable[ColumnMapping]) -> dict[str, str | None]:
    return {m.column: m.field for m in mapping}
