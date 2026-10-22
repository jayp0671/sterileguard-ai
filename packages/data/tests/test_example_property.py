"""Example Hypothesis property test (SG-05). Real transforms arrive in SG-21."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st


def hours_from_minutes(minutes: int) -> float:
    return round(minutes / 60, 2)


@given(st.integers(min_value=0, max_value=24 * 60))
def test_hours_from_minutes_is_bounded_and_monotone(minutes: int) -> None:
    hours = hours_from_minutes(minutes)
    assert 0 <= hours <= 24
    assert hours_from_minutes(minutes + 1) >= hours
