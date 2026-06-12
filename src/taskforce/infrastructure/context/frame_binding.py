"""Task-local frame binding for ctxman sub-agent frames.

When a parent agent (ctxman backend, frames enabled) spawns a sequential
sub-agent, it pushes a frame on its own ctxman session and publishes a
``FrameBinding`` via a ``ContextVar``. The sub-agent's context-manager
factory (running in the same asyncio task) picks the binding up and
builds an adapter that shares the parent's session, rendering with
``scope="frame"``.

Parallel sub-agents must NOT set the binding: ctxman frames are
LIFO-only, so concurrent siblings get their own sessions instead.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from taskforce.infrastructure.context.ctxman_client import CtxmanClient


@dataclass(frozen=True)
class FrameBinding:
    """Shared-session binding handed from parent to sub-agent."""

    client: CtxmanClient
    session_id: str
    frame_id: str


_frame_binding: ContextVar[FrameBinding | None] = ContextVar(
    "ctxman_frame_binding",
    default=None,
)


def get_frame_binding() -> FrameBinding | None:
    """Return the active frame binding for this task context, if any."""
    return _frame_binding.get()


def set_frame_binding(binding: FrameBinding | None) -> Token:
    """Set (or clear) the frame binding; returns the reset token."""
    return _frame_binding.set(binding)


def reset_frame_binding(token: Token) -> None:
    """Restore the previous binding via the token from ``set_frame_binding``."""
    _frame_binding.reset(token)
