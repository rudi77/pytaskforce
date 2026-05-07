"""Stdin-prompt approval service for single-user CLI runs."""

from __future__ import annotations

import asyncio
import sys
import uuid

from taskforce.core.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
)


class CLIApprovalService:
    """Block on a stdin Y/N prompt for each approval request.

    Suitable for ``taskforce run mission`` / ``taskforce chat`` where a
    human is in front of the terminal. Multi-user deployments install
    the enterprise REST-backed service instead.
    """

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        # ``input()`` is blocking — run it in the default executor so
        # it does not pin the event loop while waiting for the human.
        prompt = self._format_prompt(request)
        loop = asyncio.get_running_loop()
        try:
            answer = await loop.run_in_executor(None, _ask, prompt)
        except (EOFError, KeyboardInterrupt):
            return ApprovalDecision(
                request_id=request.request_id,
                status=ApprovalStatus.DENIED,
                decided_by="cli",
                reason="aborted_by_user",
            )

        granted = answer.strip().lower() in {"y", "yes", "j", "ja"}
        return ApprovalDecision(
            request_id=request.request_id,
            status=ApprovalStatus.GRANTED if granted else ApprovalStatus.DENIED,
            decided_by="cli",
            reason="user_input",
        )

    @staticmethod
    def _format_prompt(request: ApprovalRequest) -> str:
        risk = request.risk_level.value.upper()
        return (
            f"\n[approval] {request.tool_name} ({risk}): {request.preview}\n"
            f"  → allow this action? [y/N] "
        )


def _ask(prompt: str) -> str:
    """Blocking stdin read — runs in a background thread.

    Writes the prompt to *stderr* (not stdout) so a piped/captured
    stdout does not swallow it. Tools running under ``pytest -s`` or
    inside a UI subprocess therefore still see the question. Falls
    back to ``input("")`` so any TTY hookup still works.
    """
    sys.stderr.write(prompt)
    sys.stderr.flush()
    return input("")


def new_request_id() -> str:
    """Helper used by the gate when generating ApprovalRequest ids."""
    return str(uuid.uuid4())


__all__ = ["CLIApprovalService", "new_request_id"]
