"""Fill missing Tier 2 inputs from department settings (SG-08, plan §10.0).

Missing Tier 2 values are filled, never invented: each filled field gets a <field>__missing
flag so the model and the UI know the value is a department default. Tier 1 inputs and
outcomes are never filled, and provided values are never overwritten.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from sg_data.schema import BY_NAME, TIER2_INPUTS


def resolve_setting(settings: dict[str, Any], path: str) -> Any:
    """Follow a dotted path. A segment that matches the "key" of a list item selects it."""
    node: Any = settings
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list):
            match = [i for i in node if isinstance(i, dict) and i.get("key") == part]
            if not match:
                return None
            node = match[0]
        else:
            return None
    return node


def default_for(name: str, settings: dict[str, Any]) -> Any:
    spec = BY_NAME[name]
    if spec.tier != 2 or spec.role != "input":
        raise ValueError(f"{name} is not a Tier 2 input and is never auto-filled")
    value = resolve_setting(settings, spec.default_from) if spec.default_from else None
    return spec.fallback if value is None else value


def fill_tier2(df: pd.DataFrame, settings: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    for name in TIER2_INPUTS:
        if name not in out.columns:
            out[name] = pd.NA
        missing = out[name].isna()
        out[f"{name}__missing"] = missing.astype(bool)
        if missing.any():
            out[name] = out[name].astype(object)
            out.loc[missing, name] = default_for(name, settings)
    return out
