"""Auto-approve service for tests and trusted batch runs."""

from __future__ import annotations

from taskforce.core.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
)


class AutoApproveService:
    """Always returns ``GRANTED`` immediately.

    Useful in unit tests, in CI runs that exercise approval-gated
    tools without human input, and in trusted batch jobs where the
    operator has accepted in advance that every tool runs.
    """

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(
            request_id=request.request_id,
            status=ApprovalStatus.GRANTED,
            decided_by="auto",
            reason="auto_approve_service",
        )


__all__ = ["AutoApproveService"]
