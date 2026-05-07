"""Approval service protocol.

A tool-execution gate consults an installed ``ApprovalServiceProtocol``
when a tool has ``requires_approval=True``. The service may prompt
the user via stdin (CLI default), block on a REST grant (enterprise
async flow) or auto-approve (testing). The framework only sees the
protocol — implementations live in infrastructure or in the plugin.
"""

from __future__ import annotations

from typing import Protocol

from taskforce.core.domain.approval import ApprovalDecision, ApprovalRequest


class ApprovalServiceProtocol(Protocol):
    """Decides whether a tool execution may proceed."""

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Block until a decision is made.

        Implementations:

        * **CLI** prompts via stdin and returns immediately on input.
        * **Enterprise** parks the request in an async queue and
          resolves when an admin calls
          ``POST /admin/approvals/{id}/grant|deny``.
        * **Auto-approve** (test) returns ``GRANTED`` synchronously.

        Implementations are expected to apply their own timeout —
        a stuck approval should resolve as ``TIMED_OUT`` rather than
        hang the agent forever.
        """
        ...
