"""Forecasts (SG-15, plan §6.2, §7.2, §12): compute tomorrow's overtime from a saved plan, store
it with its SHAP drivers, and read the latest forecast and the predicted-vs-actual history.

Inputs are the saved plan (known before 7:00 AM), Tier 2 gaps filled from department settings,
and lags from approved actuals of earlier dates. Every forecast is a model estimate, not a
guarantee.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from sg_api.core.errors import ApiError
from sg_api.core.logging import get_logger
from sg_api.services.models import LoadedModel, ModelService
from sg_api.services.plans import PLAN_FIELDS, department, today_in
from sg_api.services.supabase import Gateway, Row
from sg_ml import driver_text
from sg_ml.features import FeatureContext, add_features, build_matrix, lags_from_history

log = get_logger("sg_api.forecasts")

DISCLAIMER = "Model estimate, not a guarantee."
NO_PLAN = "https://sterileguard.dev/problems/no-plan"
NO_FORECAST = "https://sterileguard.dev/problems/no-forecast"
MODEL_NOT_LOADED = "https://sterileguard.dev/problems/model-not-loaded"
HISTORY_LOOKBACK_DAYS = 10
Trigger = Literal["manual", "scheduled", "scenario"]


class DriverOut(BaseModel):
    rank: int
    feature: str
    value: str | None = None
    contribution_hours: float
    text_key: str = Field(description="i18n key drivers.<feature>.<pos|neg>")
    text_params: dict[str, Any]
    default_text: str


class Thresholds(BaseModel):
    low_max: float = Field(description="Overtime hours at or below which a day is low burden")
    moderate_max: float = Field(description="Upper bound of moderate burden")
    source: str = Field(description="simulated_provisional until real-data thresholds exist")


class ForecastOut(BaseModel):
    id: str
    department_id: str
    target_date: dt.date
    plan_id: str | None = None
    model_version: str
    feature_set: Literal["full", "core"]
    ot_p10: float
    ot_p50: float
    ot_p90: float
    burden_class: Literal["low", "moderate", "high"]
    burden_probs: dict[str, float]
    thresholds: Thresholds
    trigger: Trigger
    created_at: dt.datetime
    drivers: list[DriverOut] = []
    disclaimer: str = DISCLAIMER


class ForecastIn(BaseModel):
    department_id: str
    target_date: dt.date


class HistoryPoint(BaseModel):
    date: dt.date
    ot_p10: float
    ot_p50: float
    ot_p90: float
    actual: float | None = Field(None, description="Approved actual overtime, when logged")
    model_version: str


def next_workday(today: dt.date) -> dt.date:
    """Tomorrow, or Monday when tomorrow falls on a weekend."""
    day = today + dt.timedelta(days=1)
    while day.weekday() >= 5:
        day += dt.timedelta(days=1)
    return day


async def _plan(gw: Gateway, token: str, dept: str, day: dt.date) -> Row:
    rows = await gw.select(
        token,
        "shift_plans",
        {
            "select": "*",
            "department_id": f"eq.{dept}",
            "plan_date": f"eq.{day.isoformat()}",
            "source": "eq.real",
            # One plan per date; final is the plan of record, a draft is used until then.
            "order": "status.desc",
            "limit": "1",
        },
    )
    if not rows:
        raise ApiError(409, f"no plan saved for {day.isoformat()}; plan tomorrow first", NO_PLAN)
    return rows[0]


async def approved_actuals(
    gw: Gateway, token: str, dept: str, start: dt.date, end: dt.date
) -> dict[dt.date, float]:
    """Approved overtime per date in [start, end]; a real row wins over a simulated one."""
    rows = await gw.select(
        token,
        "shift_actuals",
        {
            "select": "shift_date,ot_labor_hours,source",
            "department_id": f"eq.{dept}",
            "status": "eq.approved",
            "and": f"(shift_date.gte.{start.isoformat()},shift_date.lte.{end.isoformat()})",
        },
    )
    out: dict[dt.date, float] = {}
    for r in sorted(rows, key=lambda r: r.get("source") == "real"):
        if r.get("ot_labor_hours") is not None:
            out[dt.date.fromisoformat(str(r["shift_date"]))] = float(r["ot_labor_hours"])
    return out


def feature_frame(
    model: LoadedModel,
    plan: Row,
    day: dt.date,
    settings: dict[str, Any],
    history: dict[dt.date, float],
) -> pd.DataFrame:
    values = {k: plan.get(k) for k in PLAN_FIELDS}
    flags = {k: v for k, v in plan.items() if k.endswith("__missing")}
    row = pd.DataFrame([{**values, **flags, "date": pd.Timestamp(day)}])
    ctx = FeatureContext.from_dict(model.artifact["context"])
    frame = add_features(row, ctx, settings, lags=False)
    for k, v in lags_from_history(day, history).items():
        frame[k] = v
    return build_matrix(frame, model.feature_list)


def drivers_for(model: LoadedModel, X: pd.DataFrame) -> list[DriverOut]:
    explanation = model.explainer.explain(X)
    out = []
    for d in explanation.drivers:
        key, params, text = driver_text.sentence(d.feature, d.value, d.contribution_hours)
        out.append(
            DriverOut(
                rank=d.rank,
                feature=d.feature,
                value=None if d.value is None else driver_text.display_value(d.feature, d.value),
                contribution_hours=round(d.contribution_hours, 3),
                text_key=key,
                text_params=params,
                default_text=text,
            )
        )
    return out


async def compute(
    gw: Gateway,
    token: str,
    user_id: str,
    dept: str,
    day: dt.date,
    service: ModelService,
    trigger: Trigger = "manual",
) -> ForecastOut:
    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    def lap(stage: str) -> None:
        nonlocal t0
        now = time.perf_counter()
        timings[stage] = round((now - t0) * 1000, 1)
        t0 = now

    model = service.get("full")
    if model is None:
        raise ApiError(503, "no active model is loaded; try again shortly", MODEL_NOT_LOADED)
    plan = await _plan(gw, token, dept, day)
    settings, _ = await department(gw, token, dept)
    history = await approved_actuals(
        gw, token, dept, day - dt.timedelta(days=HISTORY_LOOKBACK_DAYS), day - dt.timedelta(days=1)
    )
    lap("load")
    X = feature_frame(model, plan, day, settings, history)
    pred = model.predict(X)
    lap("predict")
    drivers = drivers_for(model, X)
    lap("explain")
    saved = await gw.insert(
        token,
        "forecasts",
        {
            "department_id": dept,
            "target_date": day.isoformat(),
            "plan_id": plan.get("id"),
            "model_version": model.version,
            "feature_set": model.feature_set,
            "ot_p10": pred.p10,
            "ot_p50": pred.p50,
            "ot_p90": pred.p90,
            "burden_class": pred.burden_class,
            "burden_probs": pred.burden_probs,
            "thresholds": model.thresholds,
            "trigger": trigger,
            "created_by": user_id,
        },
    )
    await gw.insert_many(
        token,
        "forecast_drivers",
        [{"forecast_id": saved["id"], **d.model_dump()} for d in drivers],
    )
    lap("save")
    log.info("forecast_computed", department_id=dept, model_version=model.version, ms=timings)
    return to_out(saved, drivers)


def to_out(row: Row, drivers: list[DriverOut]) -> ForecastOut:
    return ForecastOut(
        id=str(row["id"]),
        department_id=str(row["department_id"]),
        target_date=row["target_date"],
        plan_id=row.get("plan_id"),
        model_version=row["model_version"],
        feature_set=row["feature_set"],
        ot_p10=float(row["ot_p10"]),
        ot_p50=float(row["ot_p50"]),
        ot_p90=float(row["ot_p90"]),
        burden_class=row["burden_class"],
        burden_probs=row.get("burden_probs") or {},
        thresholds=Thresholds(**(row.get("thresholds") or {})),
        trigger=row["trigger"],
        created_at=row["created_at"],
        drivers=sorted(drivers, key=lambda d: d.rank),
    )


SELECT = "*,forecast_drivers(*)"


def _from_joined(row: Row) -> ForecastOut:
    drivers = [DriverOut(**d) for d in row.pop("forecast_drivers", None) or []]
    return to_out(row, drivers)


async def next_day(gw: Gateway, token: str, dept: str) -> ForecastOut:
    _, tz = await department(gw, token, dept)
    target = next_workday(today_in(tz))
    rows = await gw.select(
        token,
        "forecasts",
        {
            "select": SELECT,
            "department_id": f"eq.{dept}",
            "target_date": f"eq.{target.isoformat()}",
            "order": "created_at.desc",
            "limit": "1",
        },
    )
    if not rows:
        raise ApiError(404, f"no forecast yet for {target.isoformat()}", NO_FORECAST)
    return _from_joined(rows[0])


async def by_id(gw: Gateway, token: str, forecast_id: str) -> ForecastOut:
    rows = await gw.select(token, "forecasts", {"select": SELECT, "id": f"eq.{forecast_id}"})
    if not rows:
        raise ApiError(404, "forecast not found")
    return _from_joined(rows[0])


async def history(gw: Gateway, token: str, dept: str, days: int) -> list[HistoryPoint]:
    """The latest forecast per date for the last `days` days, with approved actuals."""
    _, tz = await department(gw, token, dept)
    end = today_in(tz)
    start = end - dt.timedelta(days=days)
    rows = await gw.select(
        token,
        "forecasts",
        {
            "select": "target_date,ot_p10,ot_p50,ot_p90,model_version,created_at",
            "department_id": f"eq.{dept}",
            "and": f"(target_date.gte.{start.isoformat()},target_date.lte.{end.isoformat()})",
            "order": "target_date.asc,created_at.desc",
        },
    )
    actuals = await approved_actuals(gw, token, dept, start, end)
    latest: dict[dt.date, Row] = {}
    for r in rows:
        latest.setdefault(dt.date.fromisoformat(str(r["target_date"])), r)
    return [
        HistoryPoint(
            date=d,
            ot_p10=float(r["ot_p10"]),
            ot_p50=float(r["ot_p50"]),
            ot_p90=float(r["ot_p90"]),
            actual=actuals.get(d),
            model_version=r["model_version"],
        )
        for d, r in sorted(latest.items())
    ]
