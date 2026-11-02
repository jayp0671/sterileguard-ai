"""PHI guard (SG-21, plan §10.1 step 6, §14).

Microsoft Presidio Analyzer with spaCy's small English model (en_core_web_sm: about 120 MB in
memory and 4 s to load, about 5 ms per short text; the larger models do not fit beside the API
on the free host, ADR-0009), plus custom recognizers for MRN-like IDs, US phone numbers, email
addresses, SSNs and dates of birth.

Rules:
- Columns whose normalized header suggests identity (name, employee, patient, mrn, id, dob,
  badge) are dropped before anything is stored, and reported.
- Only text columns are scanned, never numeric count columns (patient counts are not PHI).
- Findings record entity type, column and row only, never the matched text.

guard_text(s) is the API's free-text guard (shift notes, reasons): 422 phi_detected with the
entity types only.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from functools import cache
from typing import Any

import pandas as pd

# Entity types that block a cell. DATE_TIME, NRP and LOCATION are left out on purpose: shift
# notes mention times ("stayed until 8") and places ("sterile core"), which are not identifiers.
BLOCKING = (
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "MRN",
    "DATE_OF_BIRTH",
)
SCORE_MIN = 0.4
# Header words that mark a column as an identity column (whole words after normalization).
# Strong words drop the column whatever it holds; weak words ("Employees", "Patient") drop it
# only when it holds text, because a schema synonym such as "employees" names a staff count.
STRONG_IDENTITY = frozenset(
    {"name", "names", "mrn", "id", "ids", "dob", "badge", "ssn", "email", "phone", "surname"}
)
WEAK_IDENTITY = frozenset({"employee", "employees", "patient", "staff", "worker", "tech"})


@dataclass(frozen=True)
class Finding:
    entity_type: str
    column: str
    row: int | None = None  # None for a dropped column

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    entity_types: list[str]


# ---------------------------------------------------------------------------
# Analyzer (built once, lazily: the API pays the load only on its first free-text check)
# ---------------------------------------------------------------------------

_lock = threading.Lock()


def _custom_recognizers() -> list[Any]:
    from presidio_analyzer import Pattern, PatternRecognizer

    return [
        PatternRecognizer(
            supported_entity="MRN",
            patterns=[
                Pattern("mrn_prefixed", r"\b(?:MRN|MR|PT|ID|EMP|BADGE)[-#:\s]*\d{4,10}\b", 0.85),
                Pattern("long_digits", r"(?<![\d.])\d{6,10}(?![\d.])", 0.5),
            ],
            context=["mrn", "record", "patient", "chart", "badge", "employee", "id"],
        ),
        PatternRecognizer(
            supported_entity="EMAIL_ADDRESS",
            patterns=[Pattern("email_any_tld", r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", 0.9)],
        ),
        PatternRecognizer(
            supported_entity="PHONE_NUMBER",
            patterns=[
                Pattern(
                    "us_phone",
                    r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}(?!\d)",
                    0.7,
                )
            ],
        ),
        # The small spaCy model misses short names after a title ("Dr. Han's clinic").
        PatternRecognizer(
            supported_entity="PERSON",
            patterns=[
                Pattern(
                    "titled_name",
                    r"\b(?:Dr|Mr|Mrs|Ms|Miss|Mx|Prof|Nurse)\.?\s+[A-Z][a-z]+(?:[-'][A-Za-z]+)?",
                    0.7,
                )
            ],
        ),
        PatternRecognizer(
            supported_entity="US_SSN",
            patterns=[Pattern("ssn_dashed", r"\b\d{3}-\d{2}-\d{4}\b", 0.85)],
        ),
        PatternRecognizer(
            supported_entity="DATE_OF_BIRTH",
            patterns=[
                Pattern(
                    "dob_labeled",
                    r"\b(?:DOB|D\.O\.B\.|born|birth\s*date|date\s*of\s*birth)\b[:\s]*"
                    r"\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}",
                    0.85,
                )
            ],
        ),
    ]


@cache
def analyzer() -> Any:
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    with _lock:
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }
        )
        engine = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
        for rec in _custom_recognizers():
            engine.registry.add_recognizer(rec)
        return engine


def entities(text: str | None) -> list[str]:
    """Blocking entity types found in a text, sorted, without the matched text."""
    if text is None or not str(text).strip():
        return []
    results = analyzer().analyze(text=str(text), language="en", entities=list(BLOCKING))
    return sorted({r.entity_type for r in results if r.score >= SCORE_MIN})


def guard_text(text: str | None) -> GuardResult:
    found = entities(text)
    return GuardResult(not found, found)


# ---------------------------------------------------------------------------
# Frames (the import pipeline)
# ---------------------------------------------------------------------------


def _words(header: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9]+", " ", str(header).lower()).split())


def is_identity_column(header: str, values: pd.Series | None = None) -> bool:
    """True for 'Employee' (names), 'Patient Name', 'MRN', 'Badge #', 'DOB', 'Staff ID'.
    False for counts: 'Patients', 'Patient count', 'Employees' holding numbers."""
    words = _words(header)
    if words & STRONG_IDENTITY:
        return True
    if not words & WEAK_IDENTITY:
        return False
    if values is None:
        return True
    present = values.dropna().astype(str).str.strip()
    present = present[present != ""]
    return bool(len(present)) and bool(pd.to_numeric(present, errors="coerce").isna().any())


def text_columns(df: pd.DataFrame) -> list[str]:
    """Columns holding free text: object dtype with at least one value that is not a number,
    date or time. Numeric count columns are never scanned."""
    out = []
    for col in df.columns:
        if not (pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col])):
            continue
        values = df[col].dropna().astype(str).str.strip()
        values = values[values != ""]
        if values.empty:
            continue
        numeric = pd.to_numeric(values.str.replace(",", ""), errors="coerce").notna()
        timeish = values.str.fullmatch(r"[\d:./\-\s]+(?:am|pm|AM|PM|h|hrs?|min)?")
        if not (numeric | timeish).all():
            out.append(str(col))
    return out


@dataclass
class ScanResult:
    frame: pd.DataFrame
    dropped_columns: list[str]
    findings: list[Finding]
    blocked_rows: list[int]


def scan_frame(df: pd.DataFrame, skip: Iterable[str] = ()) -> ScanResult:
    """Drop identity columns, then block text cells with PHI (the cell is cleared and the row
    flagged). Returns a new frame; the input is not changed. Rows are 0-based positions."""
    skip = set(skip)
    findings: list[Finding] = []
    dropped = [
        str(c) for c in df.columns if str(c) not in skip and is_identity_column(str(c), df[c])
    ]
    for col in dropped:
        findings.append(Finding("IDENTITY_COLUMN", col))
    out = df.drop(columns=dropped).copy()
    blocked: set[int] = set()
    for col in text_columns(out):
        if col in skip:
            continue
        for pos, value in enumerate(out[col].tolist()):
            if value is None or (isinstance(value, float) and pd.isna(value)):
                continue
            found = entities(str(value))
            for ent in found:
                findings.append(Finding(ent, col, pos))
            if found:
                blocked.add(pos)
                out.loc[out.index[pos], col] = None
    return ScanResult(out, dropped, findings, sorted(blocked))
