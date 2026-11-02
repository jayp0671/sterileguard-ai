"""Turn mapped raw columns into canonical values (SG-21, plan §10.1 step 5).

Dates (month-first, Excel serials), shift labels, durations ("3h30", "3:30", "3.5", "210 min",
"3 hrs"), booleans, wide files with days as columns, and per-person punch-out times aggregated
to daily overtime past 15:00. Values that do not parse become row-level errors, never guesses.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from dateutil import parser as dateparser

from sg_data.imports.mapping import normalize
from sg_data.schema import BY_NAME

EXCEL_EPOCH = dt.date(1899, 12, 30)
SCHEDULED_END_MIN = 15 * 60
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
SHIFT_HEADERS = {"shift", "shift type", "shift name"}
OUT_TIME_WORDS = ("out", "clock out", "punch out", "left", "end time", "time out", "departure")
TARGET = next(f.name for f in BY_NAME.values() if f.role == "outcome" and f.tier == 1)
DATE = next(f.name for f in BY_NAME.values() if f.dtype == "date")
TRUE = {"y", "yes", "true", "1", "x", "t"}
FALSE = {"n", "no", "false", "0", "f", ""}


@dataclass
class TransformResult:
    frame: pd.DataFrame
    errors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


def parse_date(v: Any) -> dt.date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, int | float) or (isinstance(v, str) and re.fullmatch(r"\d{5}(\.0+)?", v)):
        serial = float(v)
        if 20000 <= serial <= 80000:  # Excel serial day numbers (1954 to 2119)
            return EXCEL_EPOCH + dt.timedelta(days=int(serial))
        return None
    try:
        parsed: dt.datetime = dateparser.parse(
            str(v), dayfirst=False, default=dt.datetime(2026, 1, 1)
        )
        return parsed.date()
    except (ValueError, OverflowError):
        return None


def parse_duration(v: Any) -> float | None:
    """Hours as a decimal: 3h30, 3:30, 3.5, 210 min, 3 hrs, 45m."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, dt.time):
        return v.hour + v.minute / 60
    s = str(v).strip().lower().replace(",", ".")
    if m := re.fullmatch(r"(\d+(?:\.\d+)?)", s):
        return float(m.group(1))
    if m := re.fullmatch(r"(\d+):(\d{1,2})", s):
        return int(m.group(1)) + int(m.group(2)) / 60
    if m := re.fullmatch(r"(\d+)\s*h(?:rs?|ours?)?\s*(\d{1,2})\s*(?:m|min|mins|minutes)?", s):
        return int(m.group(1)) + int(m.group(2)) / 60
    if m := re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)", s):
        return float(m.group(1))
    if m := re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:m|min|mins|minutes)", s):
        return float(m.group(1)) / 60
    return None


def parse_bool(v: Any) -> bool | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in TRUE:
        return True
    if s in FALSE:
        return False
    return None


def parse_int(v: Any) -> int | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        f = float(str(v).replace(",", "").strip())
    except ValueError:
        return None
    return round(f) if abs(f - round(f)) < 1e-9 else None


def parse_time_minutes(v: Any) -> int | None:
    """Clock time -> minutes after midnight: 19:30, 7:30 PM, 7pm, a time or datetime."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, dt.datetime | dt.time):
        return v.hour * 60 + v.minute
    s = str(v).strip().lower().replace(".", "")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if not m:
        return None
    h, mins, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 23 or mins > 59:
        return None
    return h * 60 + mins


def normalize_shift(label: Any) -> str | None:
    """AM, 7-3, morning, day -> morning; PM, 3-11, evening -> evening; night -> night."""
    if label is None:
        return None
    s = normalize(str(label))
    if s in {"am", "morning", "day", "days", "7 3", "07 15", "7 15", "first", "1st"}:
        return "morning"
    if s in {"pm", "afternoon", "evening", "3 11", "15 23", "second", "2nd", "swing"}:
        return "evening"
    if s in {"night", "nights", "11 7", "23 7", "third", "3rd", "noc"}:
        return "night"
    return None


# ---------------------------------------------------------------------------
# Layouts
# ---------------------------------------------------------------------------


def _header_date(h: str, week_start: dt.date | None) -> dt.date | None:
    s = normalize(h)
    for i, day in enumerate(WEEKDAYS):
        if s in {day, day[:3]} and week_start is not None:
            return week_start + dt.timedelta(days=(i - week_start.weekday()) % 7)
    if re.search(r"\d", str(h)):
        return parse_date(h)
    return None


def reshape_wide(df: pd.DataFrame, week_start: dt.date | None = None) -> tuple[pd.DataFrame, bool]:
    """Days as columns (first column holds the measure names) -> one row per day."""
    if df.shape[1] < 4:
        return df, False
    dates = {str(c): _header_date(str(c), week_start) for c in df.columns[1:]}
    day_cols = [c for c, d in dates.items() if d is not None]
    if len(day_cols) < 3 or len(day_cols) < (df.shape[1] - 1) * 0.6:
        return df, False
    measures = df.iloc[:, 0].astype(str).tolist()
    rows = []
    for c in day_cols:
        rec: dict[str, Any] = {"date": dates[c]}
        for name, value in zip(measures, df[c].tolist(), strict=True):
            rec[name] = value
        rows.append(rec)
    return pd.DataFrame(rows, dtype=object), True


def find_out_time_column(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        s = normalize(str(col))
        if any(w == s or s.startswith(w) or s.endswith(w) for w in OUT_TIME_WORDS):
            values = df[col].dropna()
            if len(values) and values.map(parse_time_minutes).notna().mean() >= 0.8:
                return str(col)
    return None


def aggregate_punches(
    df: pd.DataFrame, date_col: str, out_col: str
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Per-person rows -> one row per date with total hours past 15:00. Other columns keep the
    first value of the day. The per-person rows exist only in memory, here."""
    errors: list[dict[str, Any]] = []
    work = df.copy()
    work["_date"] = work[date_col].map(parse_date)
    minutes = work[out_col].map(parse_time_minutes)
    for pos, (raw, m) in enumerate(zip(work[out_col].tolist(), minutes.tolist(), strict=True)):
        if raw is not None and m is None:
            errors.append(
                {"row": pos, "column": out_col, "value": str(raw), "message": "not a clock time"}
            )
    work["_ot"] = minutes.map(lambda m: max(0, m - SCHEDULED_END_MIN) / 60 if m is not None else 0)
    others = [c for c in work.columns if c not in {date_col, out_col, "_date", "_ot"}]
    grouped = work.dropna(subset=["_date"]).groupby("_date", sort=True)
    out = grouped[others].first() if others else pd.DataFrame(index=grouped.size().index)
    out[TARGET] = grouped["_ot"].sum().round(2)
    out = out.reset_index().rename(columns={"_date": date_col})
    return out, errors


# ---------------------------------------------------------------------------
# Canonical frame
# ---------------------------------------------------------------------------


def _convert(spec_dtype: str, v: Any) -> tuple[Any, bool]:
    """(value, ok). Missing is ok; a value that does not parse is not."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip()):
        return None, True
    if spec_dtype == "date":
        d = parse_date(v)
        return d, d is not None
    if spec_dtype == "float":
        h = parse_duration(v)
        return (round(h, 2) if h is not None else None), h is not None
    if spec_dtype == "int":
        i = parse_int(v)
        return i, i is not None
    if spec_dtype == "bool":
        b = parse_bool(v)
        return b, b is not None
    if spec_dtype == "enum":
        s = normalize(str(v)).replace(" ", "_")
        return s, True
    return str(v).strip(), True


def to_canonical(df: pd.DataFrame, mapping: Mapping[str, str | None]) -> TransformResult:
    """Mapped columns renamed to schema fields and converted. Keeps `_source_row` (0-based
    position in the parsed file) so errors point at the user's rows."""
    errors: list[dict[str, Any]] = []
    notes: list[str] = []
    work = df.reset_index(drop=True).copy()
    work["_source_row"] = range(len(work))

    shift_col = next((c for c in work.columns if normalize(str(c)) in SHIFT_HEADERS), None)
    if shift_col is not None:
        labels = work[shift_col].map(normalize_shift)
        dropped = int((labels != "morning").sum())
        work = work[labels == "morning"]
        notes.append(f"kept morning-shift rows only ({dropped} other rows dropped)")

    date_src = next((c for c, f in mapping.items() if f == DATE), None)
    out_col = find_out_time_column(work) if date_src is not None else None
    if out_col is not None and TARGET not in mapping.values() and date_src is not None:
        dup_dates = work[date_src].map(parse_date).duplicated().any()
        if dup_dates:
            first_rows = work.groupby(work[date_src].map(parse_date))["_source_row"].min()
            work, punch_errors = aggregate_punches(
                work.drop(columns=["_source_row"]), date_src, out_col
            )
            work["_source_row"] = work[date_src].map(lambda d: int(first_rows.get(d, -1)))
            errors += punch_errors
            mapping = {**mapping, TARGET: TARGET}
            notes.append(f"overtime aggregated from per-person out times in {out_col!r}")

    out = pd.DataFrame({"_source_row": work["_source_row"].astype(int).tolist()})
    for col, fld in mapping.items():
        if fld is None or col not in work.columns:
            continue
        spec = BY_NAME[fld]
        converted = []
        for pos, raw in zip(out["_source_row"].tolist(), work[col].tolist(), strict=True):
            value, ok = _convert(spec.dtype, raw)
            if not ok:
                errors.append(
                    {
                        "row": int(pos),
                        "column": str(col),
                        "value": str(raw),
                        "message": f"could not read {spec.label or fld} from this value",
                    }
                )
            converted.append(value)
        out[fld] = converted
    return TransformResult(out, errors, notes)
