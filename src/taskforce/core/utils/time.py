"""Shared UTC time helpers.

Provides a single ``utc_now`` function so that every module that needs the
current UTC timestamp uses the same implementation instead of maintaining
private copies.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)
