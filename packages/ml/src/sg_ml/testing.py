"""Synthetic training data and a tiny model for tests in every package (SG-13, SG-14).

synthetic_rows lays out simulator-shaped rows (20-workday sequences every 28 days from the
sg_sim design start) with an overtime rule that has the expected directions, so training is
fast and tests never need the SimPy model. Synthetic only: no real data, no names.
"""

from __future__ import annotations

import io
from functools import lru_cache
from typing import Any

import joblib
import numpy as np
import pandas as pd

from sg_data.schema import FIELDS
from sg_ml.features import F
from sg_sim.dataset import DESIGN_START, SEQ_DAYS, SEQ_SPACING
from sg_sim.run import workdays

DEPT = "00000000-0000-4000-8000-000000000003"


def synthetic_rows(
    n_seq: int = 40, seed: int = 7, *, invert_staffing: bool = False
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for k in range(n_seq):
        backlog = 0.0
        for d in workdays(DESIGN_START + k * SEQ_SPACING, SEQ_DAYS):
            morning = int(rng.integers(2, 6))
            row: dict[str, Any] = {
                F.department_id: DEPT,
                F.source: "simulated",
                F.dataset_id: None,
                F.created_by: None,
                F.date: d,
                F.regular_patients: int(rng.normal(366, 60)),
                F.morning_staff_present: morning,
                F.mf_cases: int(rng.poisson(20)),
                F.student_clinic_sessions: int(rng.poisson(4)),
                F.aft_11_staff: int(rng.integers(1, 5)),
                F.aft_13_staff: int(rng.integers(0, 3)),
                F.aft_15_staff: int(rng.integers(1, 4)),
                F.outside_support_staff: int(rng.integers(0, 4)),
                F.ot_available_staff: int(rng.integers(0, morning + 1)),
                F.washers_up: int(rng.integers(1, 3)),
                F.sterilizers_up: int(rng.integers(1, 3)),
                F.carryover_backlog_estimate: int(min(2, round(backlog))),
                F.is_holiday: False,
                F.academic_event: "none",
                F.emergency_intake_patients: int(rng.poisson(10)),
                F.returned_unused_estimate: int(rng.poisson(5)),
                F.equipment_downtime_minutes: 0,
                F.notes: None,
            }
            staff = (
                row[F.morning_staff_present] * 8
                + row[F.aft_11_staff] * 4
                + row[F.aft_13_staff] * 2
                + row[F.outside_support_staff] * 3
                + (row[F.sterilizers_up] + row[F.washers_up]) * 2
            )
            if invert_staffing:
                staff = 60 - staff
            load = row[F.regular_patients] * 0.08 + row[F.mf_cases] * 0.3 + backlog * 3
            ot = max(0.0, load - staff * 0.55 + rng.normal(0, 1.0))
            backlog = min(2.0, ot / 6)
            row[F.ot_labor_hours] = round(ot, 2)
            rows.append(row)
    df = pd.DataFrame(rows, columns=[f.name for f in FIELDS])
    df["date"] = pd.to_datetime(df["date"])
    return df


FAST_PARAMS = {
    "learning_rate": 0.1,
    "max_iter": 150,
    "max_leaf_nodes": 15,
    "min_samples_leaf": 10,
    "l2_regularization": 0.0,
}


@lru_cache(maxsize=4)
def tiny_artifact_bytes(seed: int = 7, n_seq: int = 15) -> bytes:
    """A trained full-feature-set artifact as joblib bytes (what Storage would hold)."""
    from sg_ml.data import config_for
    from sg_ml.features import FeatureContext
    from sg_ml.train import train

    rows = synthetic_rows(n_seq=n_seq, seed=seed)
    ctx = FeatureContext.from_config(config_for({}))
    result = train(rows, {"id": f"synthetic-{seed}"}, ctx, "full", seed=seed, params=FAST_PARAMS)
    buf = io.BytesIO()
    joblib.dump(result.artifact, buf)
    return buf.getvalue()


def feature_row(seed: int = 7) -> dict[str, Any]:
    """One synthetic plan with every registered feature, ready for build_matrix."""
    from sg_ml.data import config_for
    from sg_ml.features import FeatureContext, add_features

    rows = synthetic_rows(n_seq=1, seed=seed)
    F = add_features(rows, FeatureContext.from_config(config_for({})))
    return {str(k): v for k, v in F.iloc[-1].to_dict().items()}
