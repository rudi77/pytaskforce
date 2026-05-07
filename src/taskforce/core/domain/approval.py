"""Approval-flow value objects.

A tool with ``requires_approval=True`` cannot run until an
:class:`ApprovalServiceProtocol` says yes. The service receives an
:class:`ApprovalRequest` describing what's about to happen and
returns an :class:`ApprovalDecision` indicating whether to proceed.

Both objects are framework-defined and tenant-unaware; the enterprise
plugin wraps them with persistence + REST and emits AuditEvents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.core.utils.time import utc_now


class ApprovalStatus(str, Enum):
    """Lifecycle state of an approval request."""

    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class ApprovalRequest:
    """A tool-execution attempt that needs human consent before running."""

    request_id: str
    session_id: str
    tool_name: str
    tool_params: dict[str, Any]
    risk_level: ApprovalRiskLevel
    preview: str
    """Human-readable preview produced by ``tool.get_approval_preview()``."""
    requested_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)
    """Open slot for plugin-side context (caller user_id, tenant_id, ...)."""


@dataclass(frozen=True)
class ApprovalDecision:
    """Result of an approval check returned by the service."""

    request_id: str
    status: ApprovalStatus
    decided_at: datetime = field(default_factory=utc_now)
    decided_by: str | None = None
    """Identifier of the human / system that decided. ``None`` for
    auto-approval paths or in test stubs."""
    reason: str | None = None

    @property
    def granted(self) -> bool:
        return self.status is ApprovalStatus.GRANTED


__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalStatus",
]
