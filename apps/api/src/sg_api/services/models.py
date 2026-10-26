"""Active model loading and hot swap (SG-14, plan §7.1, §12.7).

At startup the API loads the active `full` model (and `core` if one is active) from the private
`models` bucket with the service role. A background task checks for activation changes every
5 minutes, and POST /v1/internal/models/reload forces a check. A new model is built completely
(artifact loaded, SHAP explainer created) before one reference assignment swaps it in, so
requests in flight keep the model they started with and nothing restarts.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import pandas as pd

from sg_api.core.logging import get_logger
from sg_ml.explain import Explainer
from sg_ml.models import CLASSES, combine_quantiles
from sg_ml.registry import load_artifact

log = get_logger("sg_api.models")
RELOAD_INTERVAL_S = 300.0


class ModelSource(Protocol):
    async def active_versions(self) -> list[dict[str, Any]]: ...
    async def download(self, path: str) -> bytes: ...


@dataclass(frozen=True)
class Prediction:
    p10: float
    p50: float
    p90: float
    burden_class: str
    burden_probs: dict[str, float]


@dataclass(frozen=True)
class LoadedModel:
    version: str
    feature_set: str
    artifact: dict[str, Any]
    explainer: Explainer

    @property
    def feature_list(self) -> list[str]:
        return list(self.artifact["feature_list"])

    @property
    def thresholds(self) -> dict[str, Any]:
        return {
            "low_max": self.artifact["thresholds"][0],
            "moderate_max": self.artifact["thresholds"][1],
            "source": self.artifact.get("thresholds_source", "simulated_provisional"),
        }

    def predict(self, X: pd.DataFrame) -> Prediction:
        a = self.artifact
        band = combine_quantiles(
            [a[f"pipeline_p{q}"].predict(X[self.feature_list]) for q in (10, 50, 90)]
        )[0]
        clf = a["classifier"]
        proba = clf.predict_proba(X[self.feature_list])[0]
        probs = {str(c): float(p) for c, p in zip(clf.classes_, proba, strict=True)}
        probs = {c: round(probs.get(c, 0.0), 4) for c in CLASSES}
        return Prediction(
            p10=round(float(band[0]), 2),
            p50=round(float(band[1]), 2),
            p90=round(float(band[2]), 2),
            burden_class=max(probs, key=lambda c: probs[c]),
            burden_probs=probs,
        )


def build(version: str, feature_set: str, data: bytes) -> LoadedModel:
    artifact = load_artifact(data)
    explainer = Explainer(artifact["pipeline_p50"], artifact["feature_list"])
    # Warm the pipelines once so the first request does not pay for lazy initialisation.
    background = artifact.get("explainer_background")
    if isinstance(background, pd.DataFrame) and len(background):
        artifact["pipeline_p50"].predict(background.head(1))
    return LoadedModel(version, feature_set, artifact, explainer)


@dataclass
class ModelService:
    source: ModelSource | None
    models: dict[str, LoadedModel] = field(default_factory=dict)
    last_error: str | None = None

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    def get(self, feature_set: str = "full") -> LoadedModel | None:
        # One dict read of the current reference: a concurrent swap never yields a half state.
        return self.models.get(feature_set)

    def versions(self) -> dict[str, str]:
        return {fs: m.version for fs, m in self.models.items()}

    def swap(self, new: dict[str, LoadedModel]) -> None:
        self.models = new

    async def refresh(self) -> bool:
        """Load any newly activated versions; returns True if anything changed."""
        if self.source is None:
            return False
        async with self._lock:
            try:
                rows = await self.source.active_versions()
                current = self.models
                new: dict[str, LoadedModel] = {}
                for row in rows:
                    fs, version = str(row["feature_set"]), str(row["version"])
                    if fs in current and current[fs].version == version:
                        new[fs] = current[fs]
                        continue
                    data = await self.source.download(str(row["artifact_path"]))
                    new[fs] = await asyncio.to_thread(build, version, fs, data)
                    log.info("model_loaded", feature_set=fs, version=version)
                changed = {k: m.version for k, m in new.items()} != self.versions()
                if changed:
                    self.swap(new)
                self.last_error = None
                return changed
            except Exception as exc:  # keep serving the current model
                self.last_error = type(exc).__name__
                log.warning("model_reload_failed", error=type(exc).__name__)
                return False

    async def _loop(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            await self.refresh()

    def start(self, interval: float = RELOAD_INTERVAL_S) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(interval))

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


class SupabaseModelSource:
    """Active rows and artifacts through the service role (model loading only)."""

    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    async def active_versions(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = await self.client.select(
            "model_versions",
            {"select": "version,feature_set,artifact_path", "status": "eq.active"},
        )
        return rows

    async def download(self, path: str) -> bytes:
        data: bytes = await self.client.download(self.bucket, path)
        return data


def as_float_frame(row: dict[str, Any]) -> pd.DataFrame:
    """One-row frame from a feature dict; NaN for missing lags."""
    return pd.DataFrame([{k: (np.nan if v is None else v) for k, v in row.items()}])
