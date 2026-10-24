"""Plan Tomorrow (SG-11, plan §2.3): load, suggest and save a department's plan for a date.

Suggestions never invent Tier 1 inputs: they come from the same-weekday average of the last
four real plans, or stay empty. Tier 2 inputs come from department settings. Every suggested
field carries its source so the UI can show a "Suggested" tag with a tooltip.
"""

from __future__ import annotations

import datetime as dt
import statistics
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, create_model

from sg_api.core.errors import ApiError
from sg_api.services.supabase import Gateway, Row
from sg_data.defaults import default_for, resolve_setting
from sg_data.schema import BY_NAME, TIER2_INPUTS, names, to_pydantic

ShiftPlanIn: Any = to_pydantic("plan_in")
ShiftPlanValues: Any = to_pydantic("plan_values")

PLAN_FIELDS = [n for n in names(roles={"input"}) if n != "date"]
TIER1_INPUTS = [n for n in names(roles={"input"}, tiers={1}) if n != "date"]
MAX_DAYS_AHEAD = 14
HISTORY_DAYS = 4
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

PlanStatus = Literal["draft", "final"]

PlanPut: Any = create_model(
    "PlanPut",
    __base__=ShiftPlanIn,
    status=(PlanStatus, Field("draft", description="draft autosaves; final is the plan of record")),
    backfill=(
        bool,
        Field(False, description="Allow a past date, to enter real days already worked"),
    ),
)


class PlanOut(BaseModel):
    department_id: str
    date: dt.date
    suggested: bool = Field(description="True when nothing is saved and these are suggestions")
    status: PlanStatus | None = None
    values: ShiftPlanValues
    sources: dict[str, str] = Field(
        description="Per field: saved, settings:<key>, default, history:<description> or none"
    )
    missing: list[str] = Field(
        default_factory=list, description="Tier 2 fields filled from department defaults"
    )
    updated_at: dt.datetime | None = None


async def department(gw: Gateway, token: str, dept: str) -> tuple[dict[str, Any], ZoneInfo]:
    rows = await gw.select(
        token, "departments", {"select": "settings,facilities(timezone)", "id": f"eq.{dept}"}
    )
    if not rows:
        raise ApiError(404, "department not found")
    tz = (rows[0].get("facilities") or {}).get("timezone") or "America/New_York"
    return dict(rows[0].get("settings") or {}), ZoneInfo(tz)


def today_in(tz: ZoneInfo, now: dt.datetime | None = None) -> dt.date:
    return (now or dt.datetime.now(dt.UTC)).astimezone(tz).date()


def _setting_source(name: str, settings: dict[str, Any]) -> str:
    path = BY_NAME[name].default_from
    if path and resolve_setting(settings, path) is not None:
        return f"settings:{path}"
    return "default"


def suggest(dept: str, day: dt.date, settings: dict[str, Any], history: list[Row]) -> PlanOut:
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for name in TIER2_INPUTS:
        values[name] = default_for(name, settings)
        sources[name] = _setting_source(name, settings)
    same = [
        r for r in history if dt.date.fromisoformat(str(r["plan_date"])).weekday() == day.weekday()
    ][:HISTORY_DAYS]
    for name in TIER1_INPUTS:
        seen = [r[name] for r in same if r.get(name) is not None]
        if seen:
            values[name] = round(statistics.fmean(seen))
            plural = "s" if len(seen) != 1 else ""
            sources[name] = (
                f"history:average of the last {len(seen)} {WEEKDAYS[day.weekday()]}{plural}"
            )
        else:
            values[name] = None
            sources[name] = "none"
    morning = values.get(TIER1_INPUTS[-1]) if TIER1_INPUTS else None
    ot_name = next((n for n in TIER2_INPUTS if n.startswith("ot_available")), None)
    if ot_name and morning is not None and values[ot_name] is not None:
        values[ot_name] = min(values[ot_name], morning)
    return PlanOut(
        department_id=dept,
        date=day,
        suggested=True,
        status=None,
        values=ShiftPlanValues(**values),
        sources=sources,
        missing=list(TIER2_INPUTS),
    )


def _saved(dept: str, day: dt.date, row: Row) -> PlanOut:
    values = {k: row.get(k) for k in PLAN_FIELDS}
    missing = [n for n in TIER2_INPUTS if row.get(f"{n}__missing")]
    return PlanOut(
        department_id=dept,
        date=day,
        suggested=False,
        status=row.get("status"),
        values=ShiftPlanValues(**values),
        sources={k: ("default" if k in missing else "saved") for k in PLAN_FIELDS},
        missing=missing,
        updated_at=row.get("updated_at"),
    )


async def _saved_row(gw: Gateway, token: str, dept: str, day: dt.date) -> Row | None:
    rows = await gw.select(
        token,
        "shift_plans",
        {
            "select": "*",
            "department_id": f"eq.{dept}",
            "plan_date": f"eq.{day.isoformat()}",
            "source": "eq.real",
        },
    )
    return rows[0] if rows else None


async def get_plan(gw: Gateway, token: str, dept: str, day: dt.date) -> PlanOut:
    row = await _saved_row(gw, token, dept, day)
    if row:
        return _saved(dept, day, row)
    settings, _ = await department(gw, token, dept)
    history = await gw.select(
        token,
        "shift_plans",
        {
            "select": ",".join(["plan_date", *TIER1_INPUTS]),
            "department_id": f"eq.{dept}",
            "source": "eq.real",
            "plan_date": f"lt.{day.isoformat()}",
            "order": "plan_date.desc",
            "limit": "60",
        },
    )
    return suggest(dept, day, settings, history)


def check_date(day: dt.date, today: dt.date, status: str, backfill: bool) -> None:
    """Final plans: tomorrow to 14 days ahead. Past dates (and today) only as a backfill."""
    if day > today + dt.timedelta(days=MAX_DAYS_AHEAD):
        raise ApiError(422, f"plans can be at most {MAX_DAYS_AHEAD} days ahead")
    if day <= today and not backfill:
        raise ApiError(422, "this date has started or passed; set backfill to enter a real day")
    if status == "final" and not backfill and day < today + dt.timedelta(days=1):
        raise ApiError(422, "a final plan must be for tomorrow or later")


async def save_plan(
    gw: Gateway, token: str, user_id: str, dept: str, day: dt.date, body: Any
) -> PlanOut:
    settings, tz = await department(gw, token, dept)
    check_date(day, today_in(tz), body.status, body.backfill)
    existing = await _saved_row(gw, token, dept, day)
    row: Row = {
        "department_id": dept,
        "plan_date": day.isoformat(),
        "source": "real",
        "status": body.status,
        "updated_by": user_id,
        "created_by": existing["created_by"] if existing else user_id,
    }
    for name in PLAN_FIELDS:
        row[name] = getattr(body, name)
    for name in TIER2_INPUTS:
        missing = row[name] is None
        row[f"{name}__missing"] = missing
        if missing:
            row[name] = default_for(name, settings)
    saved = await gw.upsert(token, "shift_plans", row, on_conflict="department_id,plan_date,source")
    return _saved(dept, day, saved)
