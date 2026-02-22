"""FastAPI dependency injection providers.

Centralizes all dependency creation for API routes, replacing module-level
singletons with request-scoped or lazily-created instances via ``Depends()``.

Clean Architecture Notes:
- Only imports from application and core layers (never infrastructure directly)
- Provides properly typed return values for route function signatures
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from taskforce.application.executor import AgentExecutor
from taskforce.application.factory import AgentFactory
from taskforce.application.tool_registry import get_tool_registry
from taskforce.core.utils.paths import get_base_path


# ---------------------------------------------------------------------------
# AgentExecutor
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_executor() -> AgentExecutor:
    """Provide a shared AgentExecutor instance.

    Uses ``lru_cache`` so the executor is created once and reused across
    requests (equivalent to the old module-level singleton, but testable
    via ``get_executor.cache_clear()``).
    """
    return AgentExecutor()


# ---------------------------------------------------------------------------
# AgentFactory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_factory() -> AgentFactory:
    """Provide a shared AgentFactory instance."""
    return AgentFactory()


# ---------------------------------------------------------------------------
# FileAgentRegistry (via application layer)
# ---------------------------------------------------------------------------


def get_agent_registry():
    """Provide a FileAgentRegistry wired through the application layer.

    Imports infrastructure lazily so the API layer module itself does not
    have a top-level dependency on infrastructure.
    """
    from taskforce.infrastructure.persistence.file_agent_registry import (
        FileAgentRegistry,
    )

    return FileAgentRegistry(
        tool_mapper=get_tool_registry(),
        base_path=get_base_path(),
    )


# ---------------------------------------------------------------------------
# Communication Gateway
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_gateway_components():
    """Provide Communication Gateway components.

    Lazily imports extension infrastructure so the API layer module itself
    does not have a top-level dependency on extensions.
    """
    from taskforce_extensions.infrastructure.communication.gateway_registry import (
        build_gateway_components,
    )

    return build_gateway_components(
        work_dir=os.getenv("TASKFORCE_WORK_DIR", ".taskforce"),
    )


def get_gateway():
    """Provide a CommunicationGateway instance."""
    from taskforce.application.gateway import CommunicationGateway

    components = get_gateway_components()
    return CommunicationGateway(
        executor=get_executor(),
        conversation_store=components.conversation_store,
        recipient_registry=components.recipient_registry,
        outbound_senders=components.outbound_senders,
    )


def get_inbound_adapters() -> dict[str, Any]:
    """Provide inbound adapters from gateway components."""
    return get_gateway_components().inbound_adapters
