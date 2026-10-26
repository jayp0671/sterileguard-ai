"""Model registry (SG-14, plan §12.7): register a run as a candidate version, activate it once
its gates pass, roll back. Rows live in public.model_versions; artifacts and cards in the
private Storage bucket `models` under <version>/.

Status changes go through the database functions activate_model_version and
rollback_model_version (supabase/migrations/0007_models.sql), so the rules live in one place
and the swap of the active row is one transaction. `sg ml` runs this with the service role on
local or staging (resolved through the sg db guards, never prod).
"""

from __future__ import annotations

import datetime as dt
import io
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import joblib

from sg_ml.data import ROOT, SIM_DIR

ARTIFACT = "artifact.joblib"
CARD = "model_card.json"

INTENDED_USE = (
    "Decision support for next-day overtime of the morning operation (7:00 AM to 3:00 PM) of a "
    "Dental Central Sterile department, computed the evening before from inputs known by 7:00 AM. "
    "It never makes staffing decisions. Model estimate, not a guarantee."
)
LIMITATIONS = [
    "Trained on simulated days from the calibrated SimPy model; real-data validation is pending "
    "(about 35 to 40 real days expected by late November).",
    "Burden categories are provisional terciles of simulated overtime until real-data "
    "thresholds are frozen (SG-29).",
    "Returned unused instruments, emergency patients and downtime are unknown before the shift "
    "and are not inputs, so days with large surprises will be under-predicted.",
    "The central estimate is a conditional mean; the 80% range comes from quantile models "
    "(ADR-0005).",
    "Academic prototype with HIPAA-style safeguards; not for clinical use.",
]


class RegistryError(RuntimeError):
    pass


class Backend(Protocol):
    def upload(self, path: str, data: bytes, content_type: str) -> None: ...
    def insert(self, row: dict[str, Any]) -> dict[str, Any]: ...
    def activate(self, version: str, actor: str | None) -> dict[str, Any]: ...
    def rollback(self, feature_set: str, actor: str | None) -> dict[str, Any]: ...
    def list(self) -> list[dict[str, Any]]: ...


def git_sha(short: bool = True) -> str:
    cmd = ["git", "rev-parse", "--short", "HEAD"] if short else ["git", "rev-parse", "HEAD"]
    try:
        return subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "nogit"


def make_version(now: dt.datetime, sha: str) -> str:
    """YYYYMMDD-HHMM-<short git sha>, in UTC."""
    return f"{now.astimezone(dt.UTC):%Y%m%d-%H%M}-{sha[:7]}"


def data_hash(dataset_ids: list[str], sim_dir: Path = SIM_DIR) -> str | None:
    """Content hash of the training dataset, from its lineage sidecar when there is one."""
    hashes = []
    for ds in dataset_ids:
        sidecar = sim_dir / f"{ds}.json"
        if sidecar.exists():
            hashes.append(json.loads(sidecar.read_text(encoding="utf-8")).get("content_hash"))
    return ",".join(h for h in hashes if h) or None


def build_card(run: dict[str, Any], version: str, created_at: str) -> dict[str, Any]:
    m = run["metrics"]
    return {
        "version": version,
        "created_at": created_at,
        "run_id": run["run_id"],
        "datasets": run["dataset_ids"],
        "feature_set": run["feature_set"],
        "features": run["feature_list"],
        "hyperparameters": run["params"],
        "metrics": {
            "regression": m["regression"],
            "classification": {
                k: {x: v[x] for x in ("macro_f1", "recall_high", "roc_auc_ovr", "brier")}
                for k, v in m["classification"].items()
            },
            "improvement_vs_best_baseline": m["improvement_vs_best_baseline"],
            "feature_sets": m["feature_sets"],
        },
        "thresholds": run["thresholds"],
        "thresholds_source": run["thresholds_source"],
        "gates": run.get("gates"),
        "gates_passed": bool(run.get("gates_passed", False)),
        "intended_use": INTENDED_USE,
        "limitations": LIMITATIONS,
        "shap_global_top10": run.get("shap_global", [])[:10],
        "sim_config_hash": run.get("sim_config_hash"),
    }


@dataclass
class Registered:
    version: str
    artifact_path: str
    row: dict[str, Any]


def register(
    run_dir: Path, backend: Backend, *, sha: str | None = None, now: dt.datetime | None = None
) -> Registered:
    """Upload the artifact and card, insert a candidate row (gates_passed from the run)."""
    run = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    sha = sha or git_sha()
    now = now or dt.datetime.now(dt.UTC)
    version = make_version(now, sha)
    card = build_card(run, version, now.isoformat(timespec="seconds"))
    artifact_path = f"{version}/{ARTIFACT}"
    backend.upload(artifact_path, (run_dir / ARTIFACT).read_bytes(), "application/octet-stream")
    backend.upload(f"{version}/{CARD}", json.dumps(card, indent=2).encode(), "application/json")
    row = backend.insert(
        {
            "version": version,
            "feature_set": run["feature_set"],
            "artifact_path": artifact_path,
            "card": card,
            "metrics": card["metrics"],
            "training_dataset_ids": run["dataset_ids"],
            "data_hash": data_hash(run["dataset_ids"]),
            "code_sha": sha,
            "gates_passed": card["gates_passed"],
        }
    )
    return Registered(version, artifact_path, row)


def load_artifact(data: bytes) -> dict[str, Any]:
    """Artifacts are produced by sg ml train and stored in the private bucket only."""
    artifact: dict[str, Any] = joblib.load(io.BytesIO(data))
    return artifact


# ---------------------------------------------------------------------------
# Postgres + Supabase Storage backend (service role)
# ---------------------------------------------------------------------------


class PostgresBackend:
    """Direct Postgres for rows (service-role equivalent, bypasses RLS like `sg sim run`) and
    the Storage REST API with the service-role key for objects."""

    def __init__(self, db_url: str, supabase_url: str, service_key: str, bucket: str = "models"):
        self.db_url = db_url
        self.storage = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}"
        self.key = service_key

    def upload(self, path: str, data: bytes, content_type: str) -> None:
        import httpx

        resp = httpx.post(
            f"{self.storage}/{path}",
            content=data,
            headers={
                "Authorization": f"Bearer {self.key}",
                "apikey": self.key,
                "Content-Type": content_type,
                "x-upsert": "false",
            },
            timeout=120.0,
        )
        if resp.status_code >= 400:
            raise RegistryError(f"storage upload of {path} failed ({resp.status_code})")

    def _call(self, sql: str, args: tuple[Any, ...]) -> dict[str, Any]:
        import psycopg
        from psycopg.rows import dict_row

        try:
            with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
                row = conn.execute(sql, args).fetchone()
                conn.commit()
        except psycopg.Error as exc:
            raise RegistryError(str(exc).splitlines()[0]) from exc
        if row is None:
            raise RegistryError("no row returned")
        return dict(row)

    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        return self._call(
            "insert into public.model_versions (version, feature_set, artifact_path, card, "
            "metrics, training_dataset_ids, data_hash, code_sha, gates_passed) values "
            "(%s, %s, %s, %s, %s, %s::uuid[], %s, %s, %s) returning version, status, gates_passed",
            (
                row["version"],
                row["feature_set"],
                row["artifact_path"],
                Jsonb(row["card"]),
                Jsonb(row["metrics"]),
                row["training_dataset_ids"],
                row["data_hash"],
                row["code_sha"],
                row["gates_passed"],
            ),
        )

    def activate(self, version: str, actor: str | None) -> dict[str, Any]:
        return self._call(
            "select version, feature_set, status from public.activate_model_version(%s, %s)",
            (version, actor),
        )

    def rollback(self, feature_set: str, actor: str | None) -> dict[str, Any]:
        return self._call(
            "select version, feature_set, status from public.rollback_model_version(%s, %s)",
            (feature_set, actor),
        )

    def list(self) -> list[dict[str, Any]]:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            rows = conn.execute(
                "select version, feature_set, status, gates_passed, created_at, activated_at, "
                "metrics -> 'regression' -> 'hgb_p50' ->> 'mae' as mae "
                "from public.model_versions order by created_at desc"
            ).fetchall()
        return [dict(r) for r in rows]
