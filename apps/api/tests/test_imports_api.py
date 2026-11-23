"""SG-24: imports review API. Synthetic files only; the fake names, phone and email below are
planted to prove the PHI guard keeps them out of every response, the rejected-rows CSV and
the logs."""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sg_api import deps
from sg_api.core import auth, ratelimit, roles
from sg_api.core.config import Settings, get_settings
from sg_api.main import create_app

from .test_security_plans import DEPT, OTHER, SUP, FakeGateway, FakeJWKS, auth_h

STEWARD = "30000000-0000-4000-8000-0000000000b1"
ADMIN = "30000000-0000-4000-8000-0000000000b2"
FAKE = ["Mario Hernandez", "Debra Jones", "Amanda Diaz", "248-555-0171", "stacie60@example.test"]

# A Leo-style weekly log: a names column, a misspelled header, a header nothing matches
# ("Clinic blocks", fixed by hand in the test), a phone and an email in notes, and one row
# with an impossible patient count.
LEO_CSV = (
    b"Date,Employee,Patients,Morning staf,OT hrs,Clinic blocks,Notes\n"
    b"2026-10-12,Mario Hernandez,332,3,6,4,call 248-555-0171 about the late cart\n"
    b"2026-10-13,Debra Jones,268,2,4.75,3,washer slow after lunch\n"
    b"2026-10-14,Amanda Diaz,379,3,0,5,emailed stacie60@example.test about trays\n"
    b"2026-10-15,Mario Hernandez,9999,3,2.25,4,\n"
    b"2026-10-16,Debra Jones,358,3,0.5,2,\n"
)


class ImportGateway(FakeGateway):
    """import_jobs, mapping_templates and a Storage bucket in memory, plus a commit_import that
    follows the 0012 rules (department and source forced, existing days skipped, once per job)."""

    def __init__(self) -> None:
        super().__init__()
        self.memberships += [
            {"user_id": STEWARD, "department_id": DEPT, "role": "data_steward"},
            {"user_id": ADMIN, "department_id": DEPT, "role": "dept_admin"},
            {"user_id": SUP, "department_id": OTHER, "role": "data_steward"},
        ]
        self.jobs: dict[str, dict[str, Any]] = {}
        self.templates: dict[tuple[str, str], dict[str, Any]] = {}
        self.objects: dict[str, bytes] = {}
        self.real_days: set[str] = {"2026-10-16"}
        self.committed: list[dict[str, Any]] = []
        self.rpc_payloads: list[dict[str, Any]] = []

    async def select(self, token_: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        eq = {k: v.removeprefix("eq.") for k, v in params.items() if v.startswith("eq.")}
        if table == "import_jobs":
            rows = [j for j in self.jobs.values() if all(str(j.get(k)) == v for k, v in eq.items())]
            return sorted(rows, key=lambda r: r["created_at"], reverse=True)
        if table == "mapping_templates":
            return [t for (d, _), t in self.templates.items() if d == eq["department_id"]]
        return await super().select(token_, table, params)

    async def insert(self, token_: str, table: str, row: dict[str, Any]) -> dict[str, Any]:
        assert table == "import_jobs"
        now = dt.datetime.now(dt.UTC).isoformat()
        saved = {
            "storage_path": None,
            "parse_report": None,
            "mapping": None,
            "validation_report": None,
            "phi_findings": None,
            "rows_committed": None,
            "approved_by": None,
            **row,
            "created_at": now,
            "updated_at": now,
        }
        self.jobs[row["id"]] = saved
        return saved

    async def update(
        self, token_: str, table: str, params: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        job = self.jobs[params["id"].removeprefix("eq.")]
        # Responses are JSON: make sure every stored report serializes.
        job.update(json.loads(json.dumps(patch)))
        return [job]

    async def upsert(
        self, token_: str, table: str, row: dict[str, Any], on_conflict: str
    ) -> dict[str, Any]:
        assert table == "mapping_templates"
        saved = {**row, "id": str(uuid.uuid4())}
        self.templates[(row["department_id"], row["column_signature"])] = saved
        return saved

    async def rpc_result(
        self, token_: str, fn: str, args: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        assert fn == "commit_import" and args is not None
        self.rpc_payloads.append(json.loads(json.dumps(args)))
        job = self.jobs[args["p_job_id"]]
        if job["status"] == "committed":
            return 400, {"code": "55000"}
        plans = [p for p in args["p_plans"] if p["plan_date"] not in self.real_days]
        acts = [a for a in args["p_actuals"] if a["shift_date"] not in self.real_days]
        skipped = sorted({p["plan_date"] for p in args["p_plans"]} & self.real_days)
        self.committed += plans
        job.update(status="committed", rows_committed=len(plans))
        return 200, {
            "import_job_id": job["id"],
            "dataset_id": str(uuid.uuid4()),
            "rows_committed": len(plans),
            "plans": len(plans),
            "actuals": len(acts),
            "skipped_dates": skipped,
            "already_committed": False,
        }

    async def storage_upload(
        self, token_: str, bucket: str, path: str, data: bytes, content_type: str
    ) -> None:
        assert bucket == "imports" and path.startswith(f"{DEPT}/")
        self.objects[path] = data

    async def storage_download(self, token_: str, bucket: str, path: str) -> bytes:
        return self.objects[path]

    async def storage_delete(self, token_: str, bucket: str, path: str) -> None:
        self.objects.pop(path, None)


@pytest.fixture
def gw() -> ImportGateway:
    return ImportGateway()


@pytest.fixture
def api(gw: ImportGateway) -> Iterator[TestClient]:
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


def upload(
    api: TestClient, data: bytes = LEO_CSV, name: str = "week-1.csv", who: str = STEWARD
) -> Any:
    return api.post(
        "/v1/imports",
        params={"department_id": DEPT},
        files={"file": (name, data, "text/csv")},
        headers=auth_h(who),
    )


def assert_no_fake_phi(text: str) -> None:
    for s in FAKE:
        assert s not in text, f"planted value {s!r} leaked"


def test_full_flow_upload_review_fix_mapping_commit_rejected(
    api: TestClient, gw: ImportGateway, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    res = upload(api)
    assert res.status_code == 201, res.text
    job = res.json()
    jid = job["id"]
    assert job["status"] == "validated" and job["file_available"]
    assert job["phi"]["columns_removed"] == 1  # Employee
    assert job["phi"]["cells_blocked"] >= 2  # phone, email
    assert_no_fake_phi(res.text)

    cols = {c["column"]: c for c in job["columns"]}
    assert "Employee" not in cols  # dropped columns are counted, not listed
    assert cols["Morning staf"]["field"] == "morning_staff_present"
    assert cols["Morning staf"]["method"] == "fuzzy"
    assert cols["Notes"]["samples"] == []  # flagged column: no samples
    assert all(len(c["samples"]) <= 3 for c in job["columns"])
    assert job["validation"]["invalid_rows"] == 1
    bad = [e for e in job["validation"]["errors"] if e["kind"] == "invalid"]
    assert bad and bad[0]["row"] == 3 and bad[0]["column"] == "regular_patients"
    assert job["validation"]["preview"], "preview rows"
    first = job["validation"]["preview"][0]["cells"]
    assert first["notes"]["hidden"] and first["notes"]["value"] is None

    # Fix one mapping by hand: "Clinic blocks" is the clinic session count.
    res = api.patch(
        f"/v1/imports/{jid}/mapping",
        json={"department_id": DEPT, "mapping": {"Clinic blocks": "student_clinic_sessions"}},
        headers=auth_h(STEWARD),
    )
    assert res.status_code == 200, res.text
    fixed = {c["column"]: c for c in res.json()["columns"]}
    assert fixed["Clinic blocks"]["field"] == "student_clinic_sessions"
    assert fixed["Clinic blocks"]["method"] == "manual" and not fixed["Clinic blocks"]["uncertain"]
    assert fixed["Morning staf"]["method"] == "fuzzy"  # untouched columns keep their badge

    # Rejected rows download: the bad row with an error column, no identifiers.
    res = api.get(
        f"/v1/imports/{jid}/rejected.csv", params={"department_id": DEPT}, headers=auth_h(STEWARD)
    )
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert lines[0].endswith(",error") and "Employee" not in lines[0]
    assert len(lines) == 2 and "9999" in lines[1] and "regular_patients" in lines[1]
    assert_no_fake_phi(res.text)

    # Commit: Oct 16 already exists as a real day and is skipped.
    res = api.post(
        f"/v1/imports/{jid}/commit", json={"department_id": DEPT}, headers=auth_h(STEWARD)
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["plans"] == 3 and out["skipped_dates"] == ["2026-10-16"]
    payload = gw.rpc_payloads[0]
    assert payload["p_overwrite"] is False
    assert {p["plan_date"] for p in payload["p_plans"]} == {
        "2026-10-12",
        "2026-10-13",
        "2026-10-14",
        "2026-10-16",
    }
    assert all(p["student_clinic_sessions"] is not None for p in payload["p_plans"])
    assert_no_fake_phi(json.dumps(payload))
    assert not gw.objects, "the raw file is deleted after commit"
    assert gw.jobs[jid]["storage_path"] is None
    assert len(gw.templates) == 1, "the reviewed mapping is saved as a template"

    res = api.post(
        f"/v1/imports/{jid}/commit", json={"department_id": DEPT}, headers=auth_h(STEWARD)
    )
    assert res.status_code == 409

    hist = api.get("/v1/imports", params={"department_id": DEPT}, headers=auth_h(STEWARD))
    assert hist.status_code == 200
    assert hist.json()[0]["status"] == "committed" and hist.json()[0]["created_by_me"]
    assert_no_fake_phi(caplog.text)


def test_template_maps_the_next_file_with_the_same_columns(
    api: TestClient, gw: ImportGateway
) -> None:
    jid = upload(api).json()["id"]
    api.patch(
        f"/v1/imports/{jid}/mapping",
        json={"department_id": DEPT, "mapping": {"Clinic blocks": "student_clinic_sessions"}},
        headers=auth_h(STEWARD),
    )
    res = api.post(
        f"/v1/imports/{jid}/template", json={"department_id": DEPT}, headers=auth_h(STEWARD)
    )
    assert res.status_code == 201, res.text
    again = upload(api, LEO_CSV.replace(b"2026-10-1", b"2026-11-1")).json()
    cols = {c["column"]: c for c in again["columns"]}
    assert cols["Clinic blocks"]["field"] == "student_clinic_sessions"
    assert cols["Clinic blocks"]["method"] == "template"


@pytest.mark.parametrize(
    ("name", "data", "status"),
    [
        ("week.pdf", b"%PDF-1.7", 415),
        ("week.xlsx", b"not a zip file", 415),
        ("week.csv", b"PK\x03\x04zipped", 415),
        ("week.csv", b"", 422),
        ("week.csv", b"a" * (10 * 1024 * 1024 + 1), 413),
    ],
    ids=["pdf", "fake-xlsx", "zip-as-csv", "empty", "too-big"],
)
def test_type_and_size_checks(api: TestClient, name: str, data: bytes, status: int) -> None:
    assert upload(api, data, name).status_code == status


def test_roles_and_tenancy(api: TestClient) -> None:
    assert upload(api, who=SUP).status_code == 403  # supervisor of DEPT: not an import role
    jid = upload(api).json()["id"]
    # A steward of another department cannot see the job.
    res = api.get(f"/v1/imports/{jid}", params={"department_id": OTHER}, headers=auth_h(SUP))
    assert res.status_code == 404


def test_overwrite_is_dept_admin_only(api: TestClient) -> None:
    jid = upload(api).json()["id"]
    res = api.post(
        f"/v1/imports/{jid}/commit",
        json={"department_id": DEPT, "overwrite": True},
        headers=auth_h(STEWARD),
    )
    assert res.status_code == 403


def test_bad_mapping_rejected(api: TestClient) -> None:
    jid = upload(api).json()["id"]
    for mapping in ({"Nope": "mf_cases"}, {"Clinic blocks": "department_id"}):
        res = api.patch(
            f"/v1/imports/{jid}/mapping",
            json={"department_id": DEPT, "mapping": mapping},
            headers=auth_h(STEWARD),
        )
        assert res.status_code == 422, mapping
    res = api.patch(
        f"/v1/imports/{jid}/mapping",
        json={"department_id": DEPT, "mapping": {"Clinic blocks": "regular_patients"}},
        headers=auth_h(STEWARD),
    )
    assert res.status_code == 422  # two columns -> one field


def test_cancel_deletes_the_file(api: TestClient, gw: ImportGateway) -> None:
    jid = upload(api).json()["id"]
    res = api.post(
        f"/v1/imports/{jid}/cancel", json={"department_id": DEPT}, headers=auth_h(STEWARD)
    )
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    assert not gw.objects


def test_unparseable_file_fails_cleanly(api: TestClient, gw: ImportGateway) -> None:
    res = upload(api, b"just,one\n", "tiny.csv")
    assert res.status_code == 201
    assert res.json()["status"] in ("failed", "validated")
    if res.json()["status"] == "failed":
        assert not gw.objects


def test_fields_endpoint_lists_mappable_fields(api: TestClient) -> None:
    res = api.get("/v1/imports/fields", params={"department_id": DEPT}, headers=auth_h(STEWARD))
    names = {f["name"] for f in res.json()}
    assert {"date", "regular_patients", "ot_labor_hours"} <= names
    assert "department_id" not in names
