"""Shift actuals (SG-20, plan §2.3, §6.2, §7.2): what actually happened each day, through a
draft -> submitted -> approved workflow, plus backfilling real past days.

RLS (migration 0004) is the floor; this module adds the workflow rules on top: approved rows
are locked except a dept_admin reopen with a reason, technicians edit only their own rows, and
one real actual per department and date. Notes and reasons pass the text guard, which never
echoes what it matched.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model

from sg_api.core.errors import ApiError
from sg_api.core.logging import get_logger
from sg_api.core.text_guard import require_clean
from sg_api.services import plans
from sg_api.services.supabase import Gateway, Row
from sg_data.schema import names, to_pydantic

log = get_logger("sg_api.audit")

Status = Literal["draft", "submitted", "approved"]
ShiftActualIn: Any = to_pydantic("actual_in")
ACTUAL_FIELDS = list(ShiftActualIn.model_fields)
# The target: the one required field of an actual.
TARGET = next(n for n, f in ShiftActualIn.model_fields.items() if f.is_required())
NOTES = "notes"
TIER3_FIELDS = [n for n in names(tiers={3}) if n != NOTES]
LEADS = frozenset({"supervisor", "dept_admin"})
ROLE_ORDER = ("dept_admin", "supervisor", "data_steward", "technician", "platform_admin")
EXISTS = "https://sterileguard.dev/problems/actual-exists"
LOCKED = "https://sterileguard.dev/problems/actual-locked"
BAD_TRANSITION = "https://sterileguard.dev/problems/bad-transition"
PAGE_MAX = 100

ShiftCreate: Any = create_model(
    "ShiftCreate",
    __base__=ShiftActualIn,
    department_id=(str, ...),
    shift_date=(dt.date, ...),
    plan=(
        plans.ShiftPlanIn | None,
        Field(None, description="Backfill: the day's plan inputs, when no plan exists"),
    ),
)

_PATCH_FIELDS: dict[str, Any] = {
    "department_id": (str, ...),
    **{
        name: (field.annotation | None, Field(None, description=field.description))
        for name, field in ShiftActualIn.model_fields.items()
    },
}
ShiftPatch: Any = create_model("ShiftPatch", **_PATCH_FIELDS)


class ReopenIn(BaseModel):
    department_id: str
    reason: str = Field(min_length=3, max_length=500)


class DepartmentIn(BaseModel):
    department_id: str


class ForecastRef(BaseModel):
    ot_p10: float
    ot_p50: float
    ot_p90: float
    model_version: str


class ShiftOut(BaseModel):
    id: str
    department_id: str
    shift_date: dt.date
    ot_labor_hours: float
    emergency_intake_patients: int | None = None
    returned_unused_estimate: int | None = None
    equipment_downtime_minutes: int | None = None
    notes: str | None = None
    status: Status
    source: Literal["real", "simulated"]
    author_role: str | None = Field(None, description="The author's role when the row was logged")
    mine: bool = Field(description="The caller wrote this row")
    approved_at: dt.datetime | None = None
    reopen_reason: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    forecast: ForecastRef | None = None
    error: float | None = Field(None, description="Actual minus predicted p50, hours")
    inside_range: bool | None = Field(None, description="Actual inside the 80% range")


class ShiftPage(BaseModel):
    items: list[ShiftOut]
    has_more: bool
    next_offset: int | None = None


class AuditEntry(BaseModel):
    occurred_at: dt.datetime
    action: str
    actor_role: str | None = None
    changes: dict[str, list[Any]] = Field(description="field -> [before, after]")


class ShiftDetail(ShiftOut):
    audit: list[AuditEntry] | None = Field(None, description="dept_admin and platform_admin only")


def author_role(roles: frozenset[str]) -> str:
    return next(r for r in ROLE_ORDER if r in roles)


def to_out(row: Row, user_id: str, forecast: Row | None = None) -> ShiftOut:
    actual = float(row[TARGET])
    ref = None
    error = inside = None
    if forecast:
        ref = ForecastRef(
            ot_p10=float(forecast["ot_p10"]),
            ot_p50=float(forecast["ot_p50"]),
            ot_p90=float(forecast["ot_p90"]),
            model_version=forecast["model_version"],
        )
        error = round(actual - ref.ot_p50, 2)
        inside = ref.ot_p10 <= actual <= ref.ot_p90
    measured: dict[str, Any] = {k: row.get(k) for k in ACTUAL_FIELDS}
    return ShiftOut(
        **measured,
        id=str(row["id"]),
        department_id=str(row["department_id"]),
        shift_date=row["shift_date"],
        status=row["status"],
        source=row["source"],
        author_role=row.get("created_by_role"),
        mine=str(row.get("created_by")) == user_id,
        approved_at=row.get("approved_at"),
        reopen_reason=row.get("reopen_reason"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        forecast=ref,
        error=error,
        inside_range=inside,
    )


async def _forecasts_for(
    gw: Gateway, token: str, dept: str, dates: list[dt.date]
) -> dict[dt.date, Row]:
    if not dates:
        return {}
    rows = await gw.select(
        token,
        "forecasts",
        {
            "select": "target_date,ot_p10,ot_p50,ot_p90,model_version,created_at",
            "department_id": f"eq.{dept}",
            "and": f"(target_date.gte.{min(dates).isoformat()},"
            f"target_date.lte.{max(dates).isoformat()})",
            "order": "target_date.asc,created_at.desc",
        },
    )
    latest: dict[dt.date, Row] = {}
    for r in rows:
        latest.setdefault(dt.date.fromisoformat(str(r["target_date"])), r)
    return latest


async def _row(gw: Gateway, token: str, dept: str, shift_id: str) -> Row:
    rows = await gw.select(
        token,
        "shift_actuals",
        {"select": "*", "id": f"eq.{shift_id}", "department_id": f"eq.{dept}"},
    )
    if not rows:
        raise ApiError(404, "shift actual not found")
    return rows[0]


async def _with_forecast(gw: Gateway, token: str, row: Row, user_id: str) -> ShiftOut:
    day = dt.date.fromisoformat(str(row["shift_date"]))
    fc = await _forecasts_for(gw, token, str(row["department_id"]), [day])
    return to_out(row, user_id, fc.get(day))


async def list_shifts(
    gw: Gateway,
    token: str,
    user_id: str,
    dept: str,
    start: dt.date | None,
    end: dt.date | None,
    status: Status | None,
    limit: int,
    offset: int,
) -> ShiftPage:
    params = {
        "select": "*",
        "department_id": f"eq.{dept}",
        "order": "shift_date.desc,source.asc",
        "limit": str(min(limit, PAGE_MAX) + 1),
        "offset": str(offset),
    }
    bounds = [
        f"shift_date.gte.{start.isoformat()}" if start else None,
        f"shift_date.lte.{end.isoformat()}" if end else None,
    ]
    if any(bounds):
        params["and"] = f"({','.join(b for b in bounds if b)})"
    if status:
        params["status"] = f"eq.{status}"
    rows = await gw.select(token, "shift_actuals", params)
    more = len(rows) > limit
    rows = rows[:limit]
    fc = await _forecasts_for(
        gw, token, dept, [dt.date.fromisoformat(str(r["shift_date"])) for r in rows]
    )
    items = [to_out(r, user_id, fc.get(dt.date.fromisoformat(str(r["shift_date"])))) for r in rows]
    return ShiftPage(items=items, has_more=more, next_offset=offset + limit if more else None)


async def create(
    gw: Gateway, token: str, user_id: str, dept: str, roles: frozenset[str], body: Any
) -> ShiftOut:
    _, tz = await plans.department(gw, token, dept)
    day: dt.date = body.shift_date
    if day > plans.today_in(tz):
        raise ApiError(422, "a shift can be logged on or after its date, not before")
    await require_clean(body.notes, NOTES)
    existing = await gw.select(
        token,
        "shift_actuals",
        {
            "select": "id",
            "department_id": f"eq.{dept}",
            "shift_date": f"eq.{day.isoformat()}",
            "source": "eq.real",
        },
    )
    if existing:
        raise ApiError(
            409,
            f"{day.isoformat()} is already logged: /app/history?shift={existing[0]['id']}",
            EXISTS,
        )
    if body.plan is not None:
        if not roles & LEADS:
            raise ApiError(403, "only supervisors and department admins can backfill a plan")
        if await plans._saved_row(gw, token, dept, day):
            raise ApiError(409, f"a plan for {day.isoformat()} already exists; log the actual only")
        backfill = plans.PlanPut(**body.plan.model_dump(), status="final", backfill=True)
        await plans.save_plan(gw, token, user_id, dept, day, backfill)
    row = await gw.insert(
        token,
        "shift_actuals",
        {
            "department_id": dept,
            "shift_date": day.isoformat(),
            **{k: getattr(body, k) for k in ACTUAL_FIELDS},
            "source": "real",
            "status": "draft",
            "created_by": user_id,
            "created_by_role": author_role(roles),
        },
    )
    log.info("shift_logged", department_id=dept, shift_id=row["id"], backfill=body.plan is not None)
    return await _with_forecast(gw, token, row, user_id)


def _can_edit(row: Row, user_id: str, roles: frozenset[str]) -> None:
    if row["status"] == "approved":
        raise ApiError(409, "approved rows are locked; a department admin can reopen it", LOCKED)
    if str(row.get("created_by")) != user_id and not roles & LEADS:
        raise ApiError(403, "only the author or a supervisor can change this row")


async def update(
    gw: Gateway,
    token: str,
    user_id: str,
    dept: str,
    roles: frozenset[str],
    shift_id: str,
    body: Any,
) -> ShiftOut:
    row = await _row(gw, token, dept, shift_id)
    _can_edit(row, user_id, roles)
    patch = body.model_dump(exclude_unset=True, exclude={"department_id"})
    if TARGET in patch and patch[TARGET] is None:
        raise ApiError(422, f"{TARGET} cannot be empty")
    await require_clean(patch.get(NOTES), NOTES)
    if not patch:
        return await _with_forecast(gw, token, row, user_id)
    saved = await gw.update(token, "shift_actuals", {"id": f"eq.{shift_id}"}, patch)
    return await _with_forecast(gw, token, saved[0] if saved else row, user_id)


async def transition(
    gw: Gateway,
    token: str,
    user_id: str,
    dept: str,
    roles: frozenset[str],
    shift_id: str,
    action: Literal["submit", "approve", "reopen"],
    reason: str | None = None,
) -> ShiftOut:
    row = await _row(gw, token, dept, shift_id)
    now = dt.datetime.now(dt.UTC).isoformat()
    if action == "submit":
        _can_edit(row, user_id, roles)
        if row["status"] != "draft":
            raise ApiError(409, "only a draft can be submitted", BAD_TRANSITION)
        patch: Row = {"status": "submitted", "submitted_by": user_id}
    elif action == "approve":
        if row["status"] != "submitted":
            raise ApiError(409, "only a submitted row can be approved", BAD_TRANSITION)
        patch = {"status": "approved", "approved_by": user_id, "approved_at": now}
    else:
        if row["status"] != "approved":
            raise ApiError(409, "only an approved row can be reopened", BAD_TRANSITION)
        await require_clean(reason, "reason")
        patch = {
            "status": "submitted",
            "approved_by": None,
            "approved_at": None,
            "reopen_reason": reason,
            "reopened_by": user_id,
            "reopened_at": now,
        }
    saved = await gw.update(token, "shift_actuals", {"id": f"eq.{shift_id}"}, patch)
    if not saved:
        # RLS filtered the update out: the caller's role cannot make this change.
        raise ApiError(403, f"your role cannot {action} this row")
    log.info(f"shift_{action}", department_id=dept, shift_id=shift_id, user_id=user_id)
    return await _with_forecast(gw, token, saved[0], user_id)


def _changes(before: Row | None, after: Row | None) -> dict[str, list[Any]]:
    skip = {"updated_at", "created_at", "id", "department_id"}
    keys = set(before or {}) | set(after or {})
    out: dict[str, list[Any]] = {}
    for k in sorted(keys - skip):
        old, new = (before or {}).get(k), (after or {}).get(k)
        if old != new:
            out[k] = [old, new]
    return out


async def detail(
    gw: Gateway, token: str, user_id: str, dept: str, roles: frozenset[str], shift_id: str
) -> ShiftDetail:
    row = await _row(gw, token, dept, shift_id)
    out = await _with_forecast(gw, token, row, user_id)
    audit = None
    if roles & {"dept_admin", "platform_admin"}:
        rows = await gw.select(
            token,
            "audit_log",
            {
                "select": "occurred_at,action,actor_role,before,after",
                "entity": "eq.shift_actuals",
                "entity_id": f"eq.{shift_id}",
                "order": "occurred_at.asc",
            },
        )
        audit = [
            AuditEntry(
                occurred_at=r["occurred_at"],
                action=r["action"],
                actor_role=r.get("actor_role"),
                changes=_changes(r.get("before"), r.get("after")),
            )
            for r in rows
        ]
    return ShiftDetail(**out.model_dump(), audit=audit)


CSV_COLUMNS = [
    "date",
    "overtime_hours",
    "predicted_p50",
    "predicted_p10",
    "predicted_p90",
    "error",
    "inside_range",
    "status",
    "source",
    "author_role",
    *TIER3_FIELDS,
]


async def export_csv(
    gw: Gateway, token: str, user_id: str, dept: str, start: dt.date, end: dt.date
) -> str:
    """Counts and hours only (no notes). The caller has re-authenticated; the export is logged
    to the audit logger with who, which department and which dates."""
    items: list[ShiftOut] = []
    offset = 0
    while True:
        page = await list_shifts(gw, token, user_id, dept, start, end, None, PAGE_MAX, offset)
        items.extend(page.items)
        if page.next_offset is None:
            break
        offset = page.next_offset
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for s in items:
        f = s.forecast
        writer.writerow(
            [
                s.shift_date.isoformat(),
                s.ot_labor_hours,
                f.ot_p50 if f else "",
                f.ot_p10 if f else "",
                f.ot_p90 if f else "",
                "" if s.error is None else s.error,
                "" if s.inside_range is None else ("yes" if s.inside_range else "no"),
                s.status,
                s.source,
                s.author_role or "",
                *[("" if getattr(s, k) is None else getattr(s, k)) for k in TIER3_FIELDS],
            ]
        )
    log.info(
        "shifts_exported",
        user_id=user_id,
        department_id=dept,
        start=start.isoformat(),
        end=end.isoformat(),
        rows=len(items),
    )
    return buf.getvalue()
