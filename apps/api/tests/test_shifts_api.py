"""SG-20: shift actuals workflow, backfill and the notes guard. Synthetic ids only."""

from __future__ import annotations

import datetime as dt
import logging
import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from sg_api import deps
from sg_api.core import auth, ratelimit, roles
from sg_api.core.config import Settings, get_settings
from sg_api.core.text_guard import guard_text
from sg_api.main import create_app

from .test_security_plans import DEPT, SUP, TECH, FakeGateway, FakeJWKS, auth_h

ADMIN = "30000000-0000-4000-8000-0000000000a3"
TECH2 = "30000000-0000-4000-8000-0000000000a4"
NY = dt.timezone(dt.timedelta(hours=-4))
TODAY = dt.datetime.now(NY).date()
YESTERDAY = TODAY - dt.timedelta(days=1)
FAKE_EMAIL = "pat.doe@example.test"
FAKE_PHONE = "201-555-0147"


class ShiftGateway(FakeGateway):
    """In-memory shift_actuals with the 0004 RLS update rule, plus forecasts and audit rows."""

    def __init__(self) -> None:
        super().__init__()
        self.memberships += [
            {"user_id": ADMIN, "department_id": DEPT, "role": "dept_admin"},
            {"user_id": TECH2, "department_id": DEPT, "role": "technician"},
        ]
        self.actuals: dict[str, dict[str, Any]] = {}
        self.forecasts: list[dict[str, Any]] = []
        self.who: dict[str, str] = {}

    def _role(self, token_: str) -> tuple[str, str]:
        import jwt

        sub = jwt.decode(token_, options={"verify_signature": False})["sub"]
        role = next(m["role"] for m in self.memberships if m["user_id"] == sub)
        return sub, role

    async def select(self, token_: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        eq = {k: v.removeprefix("eq.") for k, v in params.items() if v.startswith("eq.")}
        if table == "shift_actuals":
            rows = [
                r for r in self.actuals.values() if all(str(r.get(k)) == v for k, v in eq.items())
            ]
            rows.sort(key=lambda r: r["shift_date"], reverse=True)
            off = int(params.get("offset", "0"))
            return rows[off : off + int(params.get("limit", "1000"))]
        if table == "forecasts":
            return self.forecasts
        if table == "audit_log":
            return [
                {
                    "occurred_at": "2026-11-02T10:00:00+00:00",
                    "action": "update",
                    "actor_role": "authenticated",
                    "before": {"status": "submitted", "ot_labor_hours": 4},
                    "after": {"status": "approved", "ot_labor_hours": 4},
                }
            ]
        return await super().select(token_, table, params)

    async def insert(self, token_: str, table: str, row: dict[str, Any]) -> dict[str, Any]:
        assert table == "shift_actuals"
        now = dt.datetime.now(dt.UTC).isoformat()
        saved = {**row, "id": str(uuid.uuid4()), "created_at": now, "updated_at": now}
        self.actuals[saved["id"]] = saved
        return saved

    async def update(
        self, token_: str, table: str, params: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        row = self.actuals.get(params["id"].removeprefix("eq."))
        if row is None:
            return []
        sub, role = self._role(token_)
        allowed = (
            role == "dept_admin"
            or (row["status"] != "approved" and role == "supervisor")
            or (row["status"] != "approved" and role == "technician" and row["created_by"] == sub)
        )
        if not allowed or (role == "technician" and patch.get("status") == "approved"):
            return []  # RLS filters the row out
        row.update(patch)
        return [row]


@pytest.fixture
def gw() -> ShiftGateway:
    return ShiftGateway()


@pytest.fixture
def api(gw: ShiftGateway) -> Iterator[TestClient]:
    settings = Settings(env="test", supabase_url="http://db.invalid:54321")
    app = create_app(settings)
    verifier = auth.TokenVerifier(settings, FakeJWKS())  # type: ignore[arg-type]
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[auth.get_verifier] = lambda: verifier
    app.dependency_overrides[deps.get_gateway] = lambda: gw
    deps._session_cache.clear()
    roles.clear_membership_cache()
    ratelimit.reset()
    with TestClient(app) as client:
        yield client


def log_shift(api: TestClient, who: str = TECH, **body: Any) -> httpx.Response:
    payload = {"department_id": DEPT, "shift_date": YESTERDAY.isoformat(), "ot_labor_hours": 4.5}
    resp: httpx.Response = api.post("/v1/shifts", json={**payload, **body}, headers=auth_h(who))
    return resp


def act(api: TestClient, sid: str, action: str, who: str, **body: Any) -> httpx.Response:
    resp: httpx.Response = api.post(
        f"/v1/shifts/{sid}/{action}", json={"department_id": DEPT, **body}, headers=auth_h(who)
    )
    return resp


def test_technician_logs_supervisor_approves_admin_reopens(
    api: TestClient, gw: ShiftGateway
) -> None:
    resp = log_shift(api, emergency_intake_patients=12, notes="Washer 2 down after lunch")
    assert resp.status_code == 201, resp.text
    shift = resp.json()
    assert shift["status"] == "draft" and shift["source"] == "real" and shift["mine"]
    assert shift["author_role"] == "technician"
    sid = shift["id"]

    assert act(api, sid, "approve", SUP).status_code == 409  # still a draft
    assert act(api, sid, "submit", TECH).json()["status"] == "submitted"
    assert act(api, sid, "approve", TECH).status_code == 403
    approved = act(api, sid, "approve", SUP)
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert gw.actuals[sid]["approved_by"] == SUP

    # Locked: nobody edits an approved row, not even a supervisor or its author.
    for who in (TECH, SUP, ADMIN):
        resp = api.patch(
            f"/v1/shifts/{sid}",
            json={"department_id": DEPT, "ot_labor_hours": 9},
            headers=auth_h(who),
        )
        assert resp.status_code == 409 and resp.json()["type"].endswith("actual-locked")

    assert act(api, sid, "reopen", SUP, reason="wrong total").status_code == 403
    assert act(api, sid, "reopen", ADMIN, reason="x").status_code == 422
    reopened = act(api, sid, "reopen", ADMIN, reason="wrong overtime total")
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "submitted"
    assert gw.actuals[sid]["reopen_reason"] == "wrong overtime total"
    assert gw.actuals[sid]["approved_by"] is None


def test_author_and_supervisor_edit_rules(api: TestClient) -> None:
    sid = log_shift(api).json()["id"]
    other = api.patch(
        f"/v1/shifts/{sid}",
        json={"department_id": DEPT, "ot_labor_hours": 3},
        headers=auth_h(TECH2),
    )
    assert other.status_code == 403
    mine = api.patch(
        f"/v1/shifts/{sid}", json={"department_id": DEPT, "ot_labor_hours": 3}, headers=auth_h(TECH)
    )
    assert mine.status_code == 200 and mine.json()["ot_labor_hours"] == 3
    sup = api.patch(
        f"/v1/shifts/{sid}",
        json={"department_id": DEPT, "equipment_downtime_minutes": 30},
        headers=auth_h(SUP),
    )
    assert sup.status_code == 200 and sup.json()["ot_labor_hours"] == 3


def test_one_real_actual_per_date(api: TestClient) -> None:
    first = log_shift(api).json()
    dup = log_shift(api, who=SUP)
    assert dup.status_code == 409
    assert dup.json()["type"].endswith("actual-exists")
    assert first["id"] in dup.json()["detail"]


def test_future_dates_are_refused(api: TestClient) -> None:
    resp = log_shift(api, shift_date=(TODAY + dt.timedelta(days=1)).isoformat())
    assert resp.status_code == 422


def plan_inputs() -> dict[str, Any]:
    return {"regular_patients": 392, "morning_staff_present": 3, "mf_cases": 20}


def test_supervisor_backfills_a_real_day(api: TestClient, gw: ShiftGateway) -> None:
    day = TODAY - dt.timedelta(days=20)
    resp = log_shift(api, who=SUP, shift_date=day.isoformat(), plan=plan_inputs())
    assert resp.status_code == 201, resp.text
    assert resp.json()["source"] == "real"
    plan = gw.plans[(DEPT, day.isoformat())]
    assert plan["source"] == "real" and plan["status"] == "final"
    assert plan["regular_patients"] == 392
    # Tier 2 gaps come from department settings and are flagged.
    assert plan["mf_cases__missing"] is False and plan["washers_up__missing"] is True


def test_backfill_rules(api: TestClient, gw: ShiftGateway) -> None:
    day = TODAY - dt.timedelta(days=21)
    tech = log_shift(api, shift_date=day.isoformat(), plan=plan_inputs())
    assert tech.status_code == 403
    gw.plans[(DEPT, day.isoformat())] = {"id": "p", "plan_date": day.isoformat()}
    again = log_shift(api, who=SUP, shift_date=day.isoformat(), plan=plan_inputs())
    assert again.status_code == 409


@pytest.mark.parametrize(
    ("notes", "entity"),
    [
        (f"call {FAKE_EMAIL} about the late cart", "EMAIL_ADDRESS"),
        (f"reached charge desk at {FAKE_PHONE}", "PHONE_NUMBER"),
        ("tray tagged 123-45-6789", "US_SSN"),
        ("chart MRN 00482913 came back", "ID_NUMBER"),
    ],
)
def test_notes_with_identifiers_are_rejected_without_echo(
    api: TestClient, gw: ShiftGateway, caplog: pytest.LogCaptureFixture, notes: str, entity: str
) -> None:
    caplog.set_level(logging.DEBUG)
    resp = log_shift(api, notes=notes)
    assert resp.status_code == 422
    body = resp.json()
    assert body["type"].endswith("phi-detected")
    assert entity in body["detail"]
    for needle in (FAKE_EMAIL, FAKE_PHONE, "123-45-6789", "00482913"):
        assert needle not in resp.text
        assert needle not in caplog.text
    assert gw.actuals == {}


def test_reopen_reason_passes_the_guard(api: TestClient, gw: ShiftGateway) -> None:
    sid = log_shift(api).json()["id"]
    act(api, sid, "submit", TECH)
    act(api, sid, "approve", SUP)
    resp = act(api, sid, "reopen", ADMIN, reason=f"asked by {FAKE_EMAIL}")
    assert resp.status_code == 422 and FAKE_EMAIL not in resp.text
    assert gw.actuals[sid]["status"] == "approved"


def test_counts_in_notes_are_allowed() -> None:
    assert guard_text("392 patients, 20 MF cases, 2 washers, back at 19:30").ok
    assert guard_text(None).ok


def test_history_pairs_actuals_with_forecasts(api: TestClient, gw: ShiftGateway) -> None:
    log_shift(api, ot_labor_hours=9.0)
    log_shift(api, who=SUP, shift_date=(YESTERDAY - dt.timedelta(days=1)).isoformat())
    gw.forecasts = [
        {
            "target_date": YESTERDAY.isoformat(),
            "ot_p10": 6.0,
            "ot_p50": 7.5,
            "ot_p90": 10.0,
            "model_version": "v",
            "created_at": "2026-11-01T20:00:00+00:00",
        }
    ]
    resp = api.get("/v1/shifts", params={"department_id": DEPT, "limit": 1}, headers=auth_h(TECH))
    assert resp.status_code == 200, resp.text
    page = resp.json()
    assert page["has_more"] is True and page["next_offset"] == 1
    item = page["items"][0]
    assert item["shift_date"] == YESTERDAY.isoformat()
    assert item["error"] == 1.5 and item["inside_range"] is True
    rest = api.get(
        "/v1/shifts", params={"department_id": DEPT, "offset": 1}, headers=auth_h(TECH)
    ).json()
    assert rest["items"][0]["forecast"] is None and rest["items"][0]["error"] is None


def test_detail_has_audit_trail_for_dept_admins_only(api: TestClient) -> None:
    sid = log_shift(api).json()["id"]
    tech = api.get(f"/v1/shifts/{sid}", params={"department_id": DEPT}, headers=auth_h(TECH))
    assert tech.json()["audit"] is None
    admin = api.get(f"/v1/shifts/{sid}", params={"department_id": DEPT}, headers=auth_h(ADMIN))
    assert admin.json()["audit"][0]["changes"] == {"status": ["submitted", "approved"]}


def test_export_needs_fresh_two_factor(api: TestClient) -> None:
    log_shift(api)
    params = {
        "department_id": DEPT,
        "from": (TODAY - dt.timedelta(days=7)).isoformat(),
        "to": TODAY.isoformat(),
    }
    stale = api.get("/v1/shifts/export", params=params, headers=auth_h(SUP))
    assert stale.status_code == 401 and stale.json()["type"].endswith("reauth-required")
    fresh = auth_h(SUP, amr=[{"method": "totp", "timestamp": int(time.time())}])
    resp = api.get("/v1/shifts/export", params=params, headers=fresh)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("date,overtime_hours,predicted_p50")
    assert len(lines) == 2
    assert api.get("/v1/shifts/export", params=params, headers=auth_h(TECH)).status_code == 403


async def test_log_through_the_real_supabase_gateway() -> None:
    """The real gateway (not a fake) carries a backfill: plan upsert and actual insert are JSON."""
    import json

    from sg_api.services import shifts
    from sg_api.services.supabase import SupabaseGateway

    sent: list[tuple[str, str, Any]] = []

    def handle(req: httpx.Request) -> httpx.Response:
        table = req.url.path.rsplit("/", 1)[-1]
        if req.method == "GET":
            if table == "departments":
                return httpx.Response(
                    200, json=[{"settings": {}, "facilities": {"timezone": "America/New_York"}}]
                )
            return httpx.Response(200, json=[])
        body = json.loads(req.content)
        sent.append((req.method, table, body))
        now = "2026-11-02T22:00:00+00:00"
        return httpx.Response(
            201, json=[{**body, "id": "r1", "created_at": now, "updated_at": now}]
        )

    settings = Settings(env="test", supabase_url="http://sb.test", supabase_anon_key="anon")
    gw = SupabaseGateway(settings, httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    day = TODAY - dt.timedelta(days=30)
    body = shifts.ShiftCreate(
        department_id=DEPT, shift_date=day, ot_labor_hours=6.5, plan=plan_inputs()
    )
    out = await shifts.create(gw, "user-tok", SUP, DEPT, frozenset({"supervisor"}), body)
    assert out.source == "real" and out.author_role == "supervisor"
    assert [(m, t) for m, t, _ in sent] == [("POST", "shift_plans"), ("POST", "shift_actuals")]
    assert sent[0][2]["source"] == "real" and sent[0][2]["status"] == "final"
