"""Import pipeline v1 (SG-21): parse, PHI guard, profile, map, transform, validate, commit."""

from sg_data.imports.pipeline import ImportResult, run

__all__ = ["ImportResult", "run"]
