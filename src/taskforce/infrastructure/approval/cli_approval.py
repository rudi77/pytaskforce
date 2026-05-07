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


# Module-level lock that serialises stdin prompts. Two parallel sub-
# agents asking for approval at the same time would otherwise both
# call blocking ``input()`` on the global stdin — Python serialises
# the reads at the OS level but the prompts get interleaved on
# stderr and the user has no way to tell which question their answer
# is for. This lock keeps prompts strictly one-at-a-time.
_stdin_lock: asyncio.Lock | None = None


def _get_stdin_lock() -> asyncio.Lock:
    """Lazy-init the lock on the running loop.

    Created on first use so the lock binds to whichever event loop
    the agent runs on, not the import-time loop.
    """
    global _stdin_lock
    if _stdin_lock is None:
        _stdin_lock = asyncio.Lock()
    return _stdin_lock


class CLIApprovalService:
    """Block on a stdin Y/N prompt for each approval request.

    Suitable for ``taskforce run mission`` / ``taskforce chat`` where a
    human is in front of the terminal. Multi-user deployments install
    the enterprise REST-backed service instead.

    Concurrent prompts are serialised by a module-level
    ``asyncio.Lock`` so two parallel sub-agents asking for approval
    do not interleave their questions on stderr.
    """

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        # ``input()`` is blocking — run it in the default executor so
        # it does not pin the event loop while waiting for the human.
        prompt = self._format_prompt(request)
        loop = asyncio.get_running_loop()
        async with _get_stdin_lock():
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
