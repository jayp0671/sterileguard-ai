"""SG-25: admin console, policy acceptance and cookie consent. Synthetic users only."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sg_api import deps
from sg_api.core import auth, ratelimit, roles
from sg_api.core.config import Settings, get_settings
from sg_api.core.errors import ApiError
from sg_api.db import service_client
from sg_api.main import create_app

from .test_security_plans import DEPT, OTHER, SUP, TECH, FakeGateway, FakeJWKS, auth_h

ADMIN = "30000000-0000-4000-8000-0000000000d1"
FRESH = lambda: [{"method": "totp", "timestamp": int(time.time())}]  # noqa: E731


class AdminGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.memberships.append({"user_id": ADMIN, "department_id": DEPT, "role": "dept_admin"})
        self.settings: dict[str, Any] = {"washers": 2, "burden_thresholds": {"x": 1}}
        self.inserted: list[tuple[str, dict[str, Any]]] = []
        self.accepted: set[tuple[str, str, str]] = set()
        self.audit = [
            {
                "id": i,
                "occurred_at": f"2026-11-{10 + i:02d}T10:00:00+00:00",
                "actor_id": ADMIN,
                "actor_role": "authenticated",
                "action": "update",
                "entity": "memberships",
                "entity_id": f"e{i}",
                "before": {"role": "technician"},
                "after": {"role": "supervisor"},
                "request_id": None,
                "department_id": DEPT,
            }
            for i in range(1, 8)
        ]
        self.audit_params: list[dict[str, str]] = []

    async def select(self, token_: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        eq = {k: v.removeprefix("eq.") for k, v in params.items() if v.startswith("eq.")}
        if table == "memberships" and "department_id" in eq:
            return [
                {**m, "created_at": "2026-10-01T00:00:00+00:00"}
                for m in self.memberships
                if m["department_id"] == eq["department_id"]
            ]
        if table == "departments" and params.get("select") == "settings":
            return [{"settings": self.settings}]
        if table == "audit_log":
            self.audit_params.append(params)
            rows = sorted(self.audit, key=lambda r: -r["id"])
            if "and" in params and "id.lt." in params["and"]:
                cut = int(params["and"].split("id.lt.")[1].split(",")[0].rstrip(")"))
                rows = [r for r in rows if r["id"] < cut]
            return rows[: int(params["limit"])]
        if table == "policy_acceptances":
            return [
                {"policy": p, "version": v, "accepted_at": "2026-11-23T10:00:00+00:00"}
                for u, p, v in self.accepted
                if u == eq["user_id"]
            ]
        if table == "invites":
            return []
        return await super().select(token_, table, params)

    async def insert(self, token_: str, table: str, row: dict[str, Any]) -> dict[str, Any]:
        self.inserted.append((table, row))
        if table == "memberships":
            self.memberships.append(row)
        if table == "policy_acceptances":
            key = (row["user_id"], row["policy"], row["version"])
            if key in self.accepted:
                raise ApiError(409, "conflict")
            self.accepted.add(key)
        return row

    async def delete(self, token_: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        eq = {k: v.removeprefix("eq.") for k, v in params.items()}
        gone = [m for m in self.memberships if all(m[k] == v for k, v in eq.items())]
        self.memberships = [m for m in self.memberships if m not in gone]
        return gone

    async def update(
        self, token_: str, table: str, params: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        assert table == "departments"
        self.settings = patch["settings"]
        return [{"settings": self.settings}]


@pytest.fixture
def gw() -> AdminGateway:
    return AdminGateway()


@pytest.fixture
def svc_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    calls: list[tuple[str, Any]] = []

    async def auth_user(self: Any, uid: str) -> dict[str, Any]:
        return {
            "email": f"{uid[-4:]}@example.test",
            "last_sign_in_at": "2026-11-22T09:00:00+00:00",
            "factors": [{"id": "f1", "status": "verified"}, {"id": "f0", "status": "unverified"}],
        }

    async def auth_factors(self: Any, uid: str) -> list[dict[str, Any]]:
        return [{"id": "f1"}, {"id": "f2"}]

    async def delete_factor(self: Any, uid: str, fid: str) -> None:
        calls.append(("delete_factor", (uid, fid)))

    async def select(self: Any, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        return [{"user_id": TECH, "display_name": "Tech One"}] if table == "profiles" else []

    async def insert(
        self: Any, table: str, row: dict[str, Any], upsert_on: str | None = None
    ) -> None:
        calls.append(("insert", (table, row)))

    for name, fn in {
        "auth_user": auth_user,
        "auth_factors": auth_factors,
        "delete_factor": delete_factor,
        "select": select,
        "insert": insert,
    }.items():
        monkeypatch.setattr(service_client.ServiceClient, name, fn)
    return calls


@pytest.fixture
def api(gw: AdminGateway, svc_calls: list[Any]) -> Iterator[TestClient]:
    settings = Settings(
        env="test", supabase_url="http://db.invalid:54321", supabase_service_role_key="svc"
    )
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


def test_members_list(api: TestClient) -> None:
    res = api.get("/v1/admin/members", params={"department_id": DEPT}, headers=auth_h(ADMIN))
    assert res.status_code == 200, res.text
    tech = next(m for m in res.json() if m["user_id"] == TECH)
    assert tech["display_name"] == "Tech One" and tech["roles"] == ["technician"]
    assert tech["mfa_factors"] == 1 and tech["email"].endswith("@example.test")


def test_supervisor_cannot_use_admin(api: TestClient) -> None:
    assert (
        api.get(
            "/v1/admin/members", params={"department_id": DEPT}, headers=auth_h(SUP)
        ).status_code
        == 403
    )
    assert (
        api.get(
            "/v1/admin/members", params={"department_id": OTHER}, headers=auth_h(ADMIN)
        ).status_code
        == 404
    )


def test_role_change_needs_reauth_and_keeps_one_admin(api: TestClient, gw: AdminGateway) -> None:
    body = {"department_id": DEPT, "roles": ["supervisor"]}
    assert (
        api.put(f"/v1/admin/members/{TECH}/roles", json=body, headers=auth_h(ADMIN)).status_code
        == 401
    )
    res = api.put(f"/v1/admin/members/{TECH}/roles", json=body, headers=auth_h(ADMIN, amr=FRESH()))
    assert res.status_code == 200 and res.json()["roles"] == ["supervisor"]
    assert {m["role"] for m in gw.memberships if m["user_id"] == TECH} == {"supervisor"}
    res = api.put(
        f"/v1/admin/members/{ADMIN}/roles",
        json={"department_id": DEPT, "roles": ["supervisor"]},
        headers=auth_h(ADMIN, amr=FRESH()),
    )
    assert res.status_code == 409  # the last dept_admin
    res = api.put(
        f"/v1/admin/members/{TECH}/roles",
        json={"department_id": DEPT, "roles": ["platform_admin"]},
        headers=auth_h(ADMIN, amr=FRESH()),
    )
    assert res.status_code == 403


def test_remove_member_blocks_last_admin(api: TestClient, gw: AdminGateway) -> None:
    url = f"/v1/admin/members/{ADMIN}"
    assert (
        api.delete(
            url, params={"department_id": DEPT}, headers=auth_h(ADMIN, amr=FRESH())
        ).status_code
        == 409
    )
    res = api.delete(
        f"/v1/admin/members/{TECH}",
        params={"department_id": DEPT},
        headers=auth_h(ADMIN, amr=FRESH()),
    )
    assert res.status_code == 204 and not any(m["user_id"] == TECH for m in gw.memberships)


def test_mfa_reset_removes_factors_and_is_audited(
    api: TestClient, gw: AdminGateway, svc_calls: list[Any]
) -> None:
    url = f"/v1/admin/members/{TECH}/mfa-reset"
    assert api.post(url, json={"department_id": DEPT}, headers=auth_h(ADMIN)).status_code == 401
    res = api.post(url, json={"department_id": DEPT}, headers=auth_h(ADMIN, amr=FRESH()))
    assert res.status_code == 200 and res.json()["factors_removed"] == 2
    assert [c for c in svc_calls if c[0] == "delete_factor"] == [
        ("delete_factor", (TECH, "f1")),
        ("delete_factor", (TECH, "f2")),
    ]
    action = next(r for t, r in gw.inserted if t == "admin_actions")
    assert (
        action["action"] == "mfa_reset"
        and action["target_user_id"] == TECH
        and action["actor_id"] == ADMIN
    )


def test_settings_are_validated_and_unknown_keys_kept(api: TestClient, gw: AdminGateway) -> None:
    cur = api.get(
        "/v1/admin/settings", params={"department_id": DEPT}, headers=auth_h(ADMIN)
    ).json()
    assert cur["washers"] == 2 and len(cur["shift_windows"]) == 4
    new = {**cur, "washers": 3}
    res = api.put(
        "/v1/admin/settings", json={"department_id": DEPT, "settings": new}, headers=auth_h(ADMIN)
    )
    assert res.status_code == 200 and res.json()["washers"] == 3
    assert gw.settings["burden_thresholds"] == {"x": 1}  # not editable here, kept
    bad = {**cur, "washers": 99}
    assert (
        api.put(
            "/v1/admin/settings",
            json={"department_id": DEPT, "settings": bad},
            headers=auth_h(ADMIN),
        ).status_code
        == 422
    )
    windows = [dict(w) for w in cur["shift_windows"]]
    windows[0]["end"] = "06:00"
    assert (
        api.put(
            "/v1/admin/settings",
            json={"department_id": DEPT, "settings": {**cur, "shift_windows": windows}},
            headers=auth_h(ADMIN),
        ).status_code
        == 422
    )


def test_audit_log_filters_and_cursor(api: TestClient, gw: AdminGateway) -> None:
    res = api.get(
        "/v1/admin/audit",
        params={
            "department_id": DEPT,
            "limit": 3,
            "entity": "memberships",
            "from": "2026-11-01",
            "to": "2026-11-30",
        },
        headers=auth_h(ADMIN),
    )
    page = res.json()
    assert [r["id"] for r in page["items"]] == [7, 6, 5] and page["next_cursor"] == 5
    p = gw.audit_params[-1]
    assert p["entity"] == "eq.memberships" and "occurred_at.gte.2026-11-01" in p["and"]
    page2 = api.get(
        "/v1/admin/audit",
        params={"department_id": DEPT, "limit": 3, "before_id": 5},
        headers=auth_h(ADMIN),
    ).json()
    assert [r["id"] for r in page2["items"]] == [4, 3, 2]


def test_audit_export_needs_reauth_and_is_audited(api: TestClient, gw: AdminGateway) -> None:
    url = "/v1/admin/audit/export.csv"
    assert api.get(url, params={"department_id": DEPT}, headers=auth_h(ADMIN)).status_code == 401
    res = api.get(url, params={"department_id": DEPT}, headers=auth_h(ADMIN, amr=FRESH()))
    assert res.status_code == 200 and res.text.splitlines()[0].startswith("id,occurred_at")
    assert len(res.text.strip().splitlines()) == 8
    action = next(r for t, r in gw.inserted if t == "admin_actions")
    assert action["action"] == "audit_export" and action["detail"]["rows"] == 7


def test_policy_acceptance(api: TestClient) -> None:
    st = api.get("/v1/me/policies", headers=auth_h(TECH)).json()
    assert not st["all_accepted"] and {p["policy"] for p in st["policies"]} == {"terms", "privacy"}
    for pol in ("terms", "privacy"):
        res = api.post(
            "/v1/me/policies", json={"policy": pol, "version": "1.0.0"}, headers=auth_h(TECH)
        )
        assert res.status_code == 200
    again = api.post(
        "/v1/me/policies", json={"policy": "terms", "version": "1.0.0"}, headers=auth_h(TECH)
    )
    assert again.status_code == 200 and again.json()["all_accepted"]
    old = api.post(
        "/v1/me/policies", json={"policy": "terms", "version": "0.9.0"}, headers=auth_h(TECH)
    )
    assert old.status_code == 409


def test_consent_anonymous_and_gpc(api: TestClient, svc_calls: list[Any]) -> None:
    res = api.post(
        "/v1/consents",
        json={"anon_id": "a1b2c3d4e5", "version": "1.0.0", "analytics": True, "gpc": True},
    )
    assert res.status_code == 201 and res.json() == {"recorded": True, "analytics": False}
    table, row = next(c[1] for c in svc_calls if c[0] == "insert")
    assert (
        table == "consents"
        and row["analytics"] is False
        and row["gpc"] is True
        and row["user_id"] is None
    )
    assert api.post("/v1/consents", json={"version": "1.0.0"}).status_code == 422
    assert (
        api.post("/v1/consents", json={"anon_id": "a1b2c3d4e5", "version": "9.9.9"}).status_code
        == 409
    )
