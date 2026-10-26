"""Fixtures for packages/ml tests. Synthetic data only, fixed seeds, no network.

synthetic_rows lays out simulator-shaped rows (20-workday sequences every 28 days from the
sg_sim design start) with an overtime rule that has the expected directions, so training is
fast and the tests never need the SimPy model."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sg_data.schema import FIELDS
from sg_ml.data import config_for
from sg_ml.features import FeatureContext
from sg_sim.dataset import DESIGN_START, SEQ_DAYS, SEQ_SPACING
from sg_sim.run import workdays

DEPT = "00000000-0000-4000-8000-000000000003"


def synthetic_rows(
    n_seq: int = 40, seed: int = 7, *, invert_staffing: bool = False
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_seq):
        backlog = 0.0
        for d in workdays(DESIGN_START + k * SEQ_SPACING, SEQ_DAYS):
            morning = int(rng.integers(2, 6))
            row = {
                "department_id": DEPT,
                "source": "simulated",
                "dataset_id": None,
                "created_by": None,
                "date": d,
                "regular_patients": int(rng.normal(366, 60)),
                "morning_staff_present": morning,
                "mf_cases": int(rng.poisson(20)),
                "student_clinic_sessions": int(rng.poisson(4)),
                "aft_11_staff": int(rng.integers(1, 5)),
                "aft_13_staff": int(rng.integers(0, 3)),
                "aft_15_staff": int(rng.integers(1, 4)),
                "outside_support_staff": int(rng.integers(0, 4)),
                "ot_available_staff": int(rng.integers(0, morning + 1)),
                "washers_up": int(rng.integers(1, 3)),
                "sterilizers_up": int(rng.integers(1, 3)),
                "carryover_backlog_estimate": int(min(2, round(backlog))),
                "is_holiday": False,
                "academic_event": "none",
                "emergency_intake_patients": int(rng.poisson(10)),
                "returned_unused_estimate": int(rng.poisson(5)),
                "equipment_downtime_minutes": 0,
                "notes": None,
            }
            staff = (
                row["morning_staff_present"] * 8
                + row["aft_11_staff"] * 4
                + row["aft_13_staff"] * 2
                + row["outside_support_staff"] * 3
                + (row["sterilizers_up"] + row["washers_up"]) * 2
            )
            if invert_staffing:
                staff = 60 - staff
            load = row["regular_patients"] * 0.08 + row["mf_cases"] * 0.3 + backlog * 3
            ot = max(0.0, load - staff * 0.55 + rng.normal(0, 1.0))
            backlog = min(2.0, ot / 6)
            row["ot_labor_hours"] = round(ot, 2)
            rows.append(row)
    df = pd.DataFrame(rows, columns=[f.name for f in FIELDS])
    df["date"] = pd.to_datetime(df["date"])
    return df


@pytest.fixture(scope="session")
def rows() -> pd.DataFrame:
    return synthetic_rows()


@pytest.fixture(scope="session")
def ctx() -> FeatureContext:
    return FeatureContext.from_config(config_for({}))


FAST_PARAMS = {
    "learning_rate": 0.1,
    "max_iter": 150,
    "max_leaf_nodes": 15,
    "min_samples_leaf": 10,
    "l2_regularization": 0.0,
}
