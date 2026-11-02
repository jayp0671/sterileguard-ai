"""Parse messy CSV and Excel files into a raw table (SG-21, plan §10.1 step 2).

Everything is read as text first: later steps decide types. Steps: size check, encoding and
delimiter detection (CSV), sheet choice and merged-cell filling (Excel), empty rows and columns
dropped, whitespace stripped, header row detection (two-row headers joined), and a trailing
"Total" row dropped.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

MAX_BYTES = 10 * 1024 * 1024
EXTENSIONS = (".csv", ".xlsx", ".xls")
TOTAL_ROW = re.compile(r"^(grand\s+)?totals?:?$", re.IGNORECASE)
HEADER_TEXT_SHARE = 0.5


class ParseError(ValueError):
    """The file cannot be read (wrong type, too large, empty)."""


@dataclass
class ParseReport:
    filename: str
    file_type: str
    size_bytes: int
    encoding: str | None = None
    delimiter: str | None = None
    sheet: str | None = None
    sheets: list[str] = field(default_factory=list)
    header_rows: list[int] = field(default_factory=list)
    rows: int = 0
    columns: int = 0
    dropped_empty_rows: int = 0
    dropped_empty_columns: int = 0
    dropped_total_row: bool = False
    merged_ranges_filled: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cell(v: Any) -> Any:
    """Strip text; keep dates and numbers as they are (openpyxl gives real types)."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s or None
    if isinstance(v, float) and pd.isna(v):
        return None
    return v


def _decode(data: bytes) -> tuple[str, str]:
    from charset_normalizer import from_bytes

    for enc in ("utf-8-sig",):
        try:
            return data.decode(enc), "utf-8"
        except UnicodeDecodeError:
            pass
    best = from_bytes(data).best()
    if best is None:
        return data.decode("latin-1"), "latin-1"
    return str(best), str(best.encoding)


def _delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:50])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ";" if sample.count(";") > sample.count(",") else ","


def _read_csv(data: bytes, report: ParseReport) -> list[list[Any]]:
    text, report.encoding = _decode(data)
    report.delimiter = _delimiter(text)
    return [list(r) for r in csv.reader(io.StringIO(text), delimiter=report.delimiter)]


def _xlsx_sheets(data: bytes) -> dict[str, tuple[list[list[Any]], int]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), data_only=True)
    out: dict[str, tuple[list[list[Any]], int]] = {}
    for ws in wb.worksheets:
        grid = [list(r) for r in ws.iter_rows(values_only=True)]
        merged = list(ws.merged_cells.ranges)
        for rng in merged:
            top = grid[rng.min_row - 1][rng.min_col - 1] if grid else None
            for r in range(rng.min_row - 1, min(rng.max_row, len(grid))):
                for c in range(rng.min_col - 1, min(rng.max_col, len(grid[r]))):
                    grid[r][c] = top
        out[ws.title] = (grid, len(merged))
    return out


def _xls_sheets(data: bytes) -> dict[str, tuple[list[list[Any]], int]]:
    import xlrd

    book = xlrd.open_workbook(file_contents=data, formatting_info=False)
    out: dict[str, tuple[list[list[Any]], int]] = {}
    for sh in book.sheets():
        grid: list[list[Any]] = []
        for r in range(sh.nrows):
            row: list[Any] = []
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    row.append(xlrd.xldate.xldate_as_datetime(cell.value, book.datemode))
                else:
                    row.append(cell.value if cell.value != "" else None)
            grid.append(row)
        out[sh.name] = (grid, 0)
    return out


def _filled(grid: list[list[Any]]) -> int:
    return sum(1 for r in grid for v in r if _cell(v) is not None)


def _is_text(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    try:
        float(v.replace(",", ""))
        return False
    except ValueError:
        return True


def _header_index(rows: list[list[Any]]) -> int:
    """First row where at least half of the non-empty cells are non-numeric strings."""
    for i, r in enumerate(rows):
        present = [v for v in r if v is not None]
        if len(present) >= 2 and sum(_is_text(v) for v in present) / len(present) >= (
            HEADER_TEXT_SHARE
        ):
            return i
    return 0


def _ffill_row(row: list[Any]) -> list[Any]:
    out, last = [], None
    for v in row:
        last = v if v is not None else last
        out.append(last)
    return out


def _looks_like_header(row: list[Any], data_row: list[Any] | None) -> bool:
    """A second header row: mostly text while the row after it is mostly not."""
    present = [v for v in row if v is not None]
    if not present or sum(_is_text(v) for v in present) / len(present) < 0.8:
        return False
    if data_row is None:
        return False
    nxt = [v for v in data_row if v is not None]
    return bool(nxt) and sum(_is_text(v) for v in nxt) / len(nxt) < HEADER_TEXT_SHARE


def _headers(top: list[Any], second: list[Any] | None) -> list[str]:
    top = _ffill_row(top) if second is not None else top
    names: list[str] = []
    for j, v in enumerate(top):
        parts = [str(v) if v is not None else ""]
        if (
            second is not None
            and j < len(second)
            and second[j] is not None
            and str(second[j]) != parts[0]
        ):
            parts.append(str(second[j]))
        name = " ".join(p for p in parts if p).strip() or f"column_{j + 1}"
        names.append(name)
    seen: dict[str, int] = {}
    unique = []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        unique.append(n if seen[n] == 1 else f"{n} ({seen[n]})")
    return unique


def parse_bytes(
    data: bytes, filename: str, sheet: str | None = None
) -> tuple[pd.DataFrame, ParseReport]:
    ext = Path(filename).suffix.lower()
    if ext not in EXTENSIONS:
        raise ParseError(f"unsupported file type {ext or '(none)'}; use .csv, .xlsx or .xls")
    if len(data) > MAX_BYTES:
        raise ParseError("file is larger than 10 MB")
    report = ParseReport(filename=Path(filename).name, file_type=ext[1:], size_bytes=len(data))
    if ext == ".csv":
        grid = _read_csv(data, report)
    else:
        sheets = _xlsx_sheets(data) if ext == ".xlsx" else _xls_sheets(data)
        report.sheets = list(sheets)
        if sheet is not None:
            if sheet not in sheets:
                raise ParseError(f"sheet {sheet!r} not found; sheets: {', '.join(sheets)}")
            report.sheet = sheet
        else:
            report.sheet = max(sheets, key=lambda name: _filled(sheets[name][0]))
        grid, report.merged_ranges_filled = sheets[report.sheet]

    rows = [[_cell(v) for v in r] for r in grid]
    width = max((len(r) for r in rows), default=0)
    rows = [r + [None] * (width - len(r)) for r in rows]
    before = len(rows)
    rows = [r for r in rows if any(v is not None for v in r)]
    report.dropped_empty_rows = before - len(rows)
    if not rows:
        raise ParseError("the file has no data")
    keep = [j for j in range(width) if any(r[j] is not None for r in rows)]
    report.dropped_empty_columns = width - len(keep)
    rows = [[r[j] for j in keep] for r in rows]

    h = _header_index(rows)
    second = rows[h + 1] if h + 1 < len(rows) else None
    two_row = (
        _looks_like_header(second, rows[h + 2] if h + 2 < len(rows) else None) if second else False
    )
    report.header_rows = [h, h + 1] if two_row else [h]
    columns = _headers(rows[h], second if two_row else None)
    body = rows[h + (2 if two_row else 1) :]

    if body:
        first = next((v for v in body[-1] if v is not None), None)
        if isinstance(first, str) and TOTAL_ROW.match(first):
            body = body[:-1]
            report.dropped_total_row = True

    df = pd.DataFrame(body, columns=columns, dtype=object)
    df = df.map(lambda v: v.date() if isinstance(v, dt.datetime) and v.time() == dt.time() else v)
    report.rows, report.columns = len(df), len(df.columns)
    return df, report


def parse_file(path: str | Path, sheet: str | None = None) -> tuple[pd.DataFrame, ParseReport]:
    p = Path(path)
    return parse_bytes(p.read_bytes(), p.name, sheet)
