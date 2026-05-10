"""Agent Runtime Protocol.

Defines the contract for top-level agent runtimes that plug into Taskforce.
The native Taskforce ``Agent`` (``core/domain/lean_agent.py``) satisfies this
protocol, and external frameworks (e.g. Hermes, OpenClaw) can ship adapters
that satisfy it too. The :class:`AgentExecutor` only depends on this surface
when dispatching mission execution.

Adapters MAY run in-process (importing a foreign Python SDK) or out-of-process
(speaking HTTP/ACP/gRPC to a separate runtime). The protocol is intentionally
minimal — v1 covers only mission execution + streaming. Cross-runtime tool
sharing, ``ask_user`` bridging and sub-agent spawning are out of scope.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from taskforce.core.domain.models import StreamEvent


@runtime_checkable
class AgentRuntimeProtocol(Protocol):
    """Top-level agent runtime contract.

    Implementations expose at minimum a streaming execute method and a
    cleanup hook. ``state_manager`` is optional — stateless adapters may
    omit it (the executor probes for it via ``getattr``).

    Attributes:
        runtime_name: Short identifier (``"taskforce"``, ``"hermes"``,
            ``"openclaw"``, …) used by the registry and surfaced in CLI/UI.
    """

    runtime_name: str

    async def execute_stream(
        self,
        mission: str,
        session_id: str,
    ) -> AsyncIterator[StreamEvent]:
        """Execute ``mission`` and yield :class:`StreamEvent`s in real time.

        Implementations should emit at least ``COMPLETE`` (success) or
        ``ERROR`` (failure) as the terminal event so the executor can build
        a final ``ExecutionResult``.
        """
        ...

    async def close(self) -> None:
        """Release runtime resources (HTTP clients, sub-processes, …)."""
        ...

    def request_interrupt(self, reason: str | None = None) -> None:
        """Cooperatively request the runtime to stop the current mission."""
        ...

    def clear_interrupt(self) -> None:
        """Reset any pending interrupt request."""
        ...


# Public re-export hint for typing call sites.
__all__ = ["AgentRuntimeProtocol", "RuntimeFactory"]


# A factory accepts the resolved profile dictionary (already merged with
# defaults / extends / agent-package configs) and returns a runtime instance.
# Async to allow factories that establish network connections at startup.
RuntimeFactory = Any  # documented type; concrete signature:
# Callable[[dict[str, Any]], Awaitable[AgentRuntimeProtocol]]
