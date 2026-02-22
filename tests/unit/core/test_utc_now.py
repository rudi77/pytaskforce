"""Tests for the shared utc_now utility."""

from datetime import UTC, datetime

from taskforce.core.utils.time import utc_now


def test_utc_now_returns_aware_utc_datetime() -> None:
    """utc_now() must return a timezone-aware datetime in UTC."""
    now = utc_now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
    assert now.tzinfo == UTC
