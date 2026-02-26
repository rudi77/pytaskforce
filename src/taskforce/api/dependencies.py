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
# AgentRegistry (via application layer)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_agent_registry():
    """Provide a shared FileAgentRegistry instance.

    Uses ``lru_cache`` so the registry is created once and reused across
    requests.  The infrastructure import is lazy (inside the function body)
    so the API-layer module has no top-level dependency on infrastructure.
    """
    from taskforce.application.infrastructure_builder import InfrastructureBuilder

    builder = InfrastructureBuilder()
    return builder.build_agent_registry()


# ---------------------------------------------------------------------------
# Communication Gateway
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_gateway_components():
    """Provide Communication Gateway components.

    Routes through the application-layer InfrastructureBuilder so that
    the API layer has no direct dependency on extensions/infrastructure.
    """
    from taskforce.application.infrastructure_builder import InfrastructureBuilder

    builder = InfrastructureBuilder()
    return builder.build_gateway_components(
        work_dir=os.getenv("TASKFORCE_WORK_DIR", ".taskforce"),
    )


@lru_cache(maxsize=1)
def get_gateway():
    """Provide a CommunicationGateway instance.

    Also wires the gateway into the AgentExecutor (for channel-targeted
    ``ask_user`` routing) and into the AgentFactory (so that
    ``SendNotificationTool`` receives a gateway reference at instantiation).
    """
    from taskforce.application.gateway import CommunicationGateway
    from taskforce.infrastructure.persistence.pending_channel_store import (
        FilePendingChannelQuestionStore,
    )

    components = get_gateway_components()
    executor = get_executor()
    work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
    gw = CommunicationGateway(
        executor=executor,
        conversation_store=components.conversation_store,
        recipient_registry=components.recipient_registry,
        outbound_senders=components.outbound_senders,
        pending_channel_store=FilePendingChannelQuestionStore(work_dir=work_dir),
    )

    # Inject gateway into executor so channel-targeted ask_user is routed
    executor._gateway = gw

    # Inject gateway into factory so SendNotificationTool is wired
    executor.factory.set_gateway(gw)

    return gw


def get_inbound_adapters() -> dict[str, Any]:
    """Provide inbound adapters from gateway components."""
    return get_gateway_components().inbound_adapters
