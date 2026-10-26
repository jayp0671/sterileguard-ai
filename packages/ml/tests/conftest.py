"""Fixtures for packages/ml tests. Synthetic data only, fixed seeds, no network."""

from __future__ import annotations

import pandas as pd
import pytest

from sg_ml.data import config_for
from sg_ml.features import FeatureContext
from sg_ml.testing import FAST_PARAMS, synthetic_rows

__all__ = ["FAST_PARAMS", "synthetic_rows"]


@pytest.fixture(scope="session")
def rows() -> pd.DataFrame:
    return synthetic_rows()


@pytest.fixture(scope="session")
def ctx() -> FeatureContext:
    return FeatureContext.from_config(config_for({}))
