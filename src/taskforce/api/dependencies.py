"""FastAPI dependency injection providers.

Centralizes all dependency creation for API routes, replacing module-level
singletons with request-scoped or lazily-created instances via ``Depends()``.

Clean Architecture Notes:
- Only imports from application and core layers (never infrastructure directly)
- Provides properly typed return values for route function signatures
"""

from __future__ import annotations

from functools import lru_cache

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
