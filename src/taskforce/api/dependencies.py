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

from fastapi import HTTPException, Request

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


def require_permission(permission: str):
    """Optionally enforce a permission when auth middleware supplied a user.

    The base framework has no auth provider of its own, so this dependency is a
    no-op unless a plugin middleware attaches ``request.state.user``. Enterprise
    users expose permissions as enum values; comparing by ``.value`` keeps this
    module independent from the enterprise package.
    """

    def dependency(request: Request) -> None:
        user = getattr(request.state, "user", None)
        if user is None:
            return

        permissions = getattr(user, "permissions", set()) or set()
        permission_values = {getattr(item, "value", str(item)) for item in permissions}
        if permission in permission_values:
            return

        raise HTTPException(status_code=403, detail="Forbidden")

    return dependency


# ---------------------------------------------------------------------------
# Agent Deployment (registry + lifecycle service)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_deployment_registry():
    """Provide a shared file-backed deployment registry."""
    from taskforce.infrastructure.persistence.file_agent_deployment_registry import (
        FileAgentDeploymentRegistry,
    )

    work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
    return FileAgentDeploymentRegistry(work_dir=work_dir)


@lru_cache(maxsize=1)
def get_agent_deployment_service():
    """Provide a shared :class:`AgentDeploymentService` instance."""
    from taskforce.application.agent_deployment_service import AgentDeploymentService
    from taskforce.application.tool_registry import get_tool_registry

    return AgentDeploymentService(
        agent_registry=get_agent_registry(),
        deployment_registry=get_deployment_registry(),
        tool_catalog=get_tool_registry(),
    )


# ---------------------------------------------------------------------------
# AuthManager (OAuth2 / token lifecycle)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_auth_manager():
    """Provide a shared :class:`AuthManager` instance.

    Returns ``None`` when the optional ``cryptography`` dependency is
    not installed — callers (typically the OAuth route) surface that
    as an HTTP 503 to the UI.
    """
    return get_factory()._ensure_auth_manager()


# ---------------------------------------------------------------------------
# Settings store (UI-managed runtime configuration)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_settings_store():
    """Provide a shared :class:`SettingsStoreProtocol` instance.

    Routes through ``InfrastructureBuilder`` so plugins can override the
    default file-based store. The instance is cached for the process —
    callers that need to rebuild it (e.g. after rotating the master
    key) should clear ``get_settings_store.cache_clear``.
    """
    from taskforce.application.infrastructure_builder import InfrastructureBuilder

    builder = InfrastructureBuilder()
    work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
    return builder.build_settings_store(work_dir=work_dir)


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
    from taskforce.application.infrastructure_overrides import (
        get_agent_lookup_override,
        get_recipient_resolver_override,
        get_workflow_lookup_override,
    )
    from taskforce.infrastructure.persistence.pending_channel_store import (
        FilePendingChannelQuestionStore,
    )

    components = get_gateway_components()
    executor = get_executor()
    work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
    conversation_manager = get_conversation_manager()

    # ADR-022 §4: optional plugin-provided recipient resolver and
    # @agent lookup. With nothing installed the gateway uses its
    # built-in pass-through resolver and treats @-prefixed messages
    # as plain text — single-tenant builds are unchanged.
    resolver_provider = get_recipient_resolver_override()
    recipient_resolver = resolver_provider() if resolver_provider else None
    lookup_provider = get_agent_lookup_override()
    agent_lookup = lookup_provider() if lookup_provider else None
    workflow_lookup_provider = get_workflow_lookup_override()
    workflow_lookup = workflow_lookup_provider() if workflow_lookup_provider else None

    async def _workflow_runner(workflow_id: str, session_id: str | None):
        service = get_workflow_runtime_service()
        return await service.run_workflow_id(
            workflow_id,
            get_executor(),
            session_id=session_id,
        )

    # ADR-022 §4 / G1: when an enterprise plugin installs a
    # gateway-components override, the right components are tenant-
    # scoped per-call. The components_provider is the per-request
    # gate the gateway consults so its outbound + broadcast paths
    # always see the *current* tenant's recipient registry and
    # outbound senders, even though the gateway itself is a process
    # singleton. With no override installed the provider returns the
    # same constructor-time GatewayComponents on every call —
    # bit-for-bit single-tenant behaviour.
    def _components_provider():
        from taskforce.application.infrastructure_builder import InfrastructureBuilder

        return InfrastructureBuilder().build_gateway_components(work_dir=work_dir)

    # Issue #157: optional always-on action-summary footer.  Read from
    # ``TASKFORCE_ACTIONS_SUMMARY`` env var; profile YAML can set this
    # via the same env var (CLI/api boot does not yet thread the
    # gateway: section through).  Invalid values fall back to disabled.
    actions_summary_mode = (
        os.getenv(
            "TASKFORCE_ACTIONS_SUMMARY",
            CommunicationGateway.ACTIONS_SUMMARY_DISABLED,
        )
        .strip()
        .lower()
    )
    if actions_summary_mode not in (
        CommunicationGateway.ACTIONS_SUMMARY_DISABLED,
        CommunicationGateway.ACTIONS_SUMMARY_FOOTER,
    ):
        actions_summary_mode = CommunicationGateway.ACTIONS_SUMMARY_DISABLED

    gw = CommunicationGateway(
        executor=executor,
        conversation_store=components.conversation_store,
        recipient_registry=components.recipient_registry,
        outbound_senders=components.outbound_senders,
        pending_channel_store=FilePendingChannelQuestionStore(work_dir=work_dir),
        conversation_manager=conversation_manager,
        conversation_manager_provider=get_conversation_manager,
        recipient_resolver=recipient_resolver,
        agent_lookup=agent_lookup,
        workflow_lookup=workflow_lookup,
        workflow_runner=_workflow_runner,
        components_provider=_components_provider,
        actions_summary_mode=actions_summary_mode,
    )

    # Inject gateway into executor so channel-targeted ask_user is routed
    executor._gateway = gw

    # Inject gateway into factory so SendNotificationTool is wired
    executor.factory.set_gateway(gw)

    return gw


def get_inbound_adapters() -> dict[str, Any]:
    """Provide inbound adapters from gateway components."""
    return get_gateway_components().inbound_adapters


# ---------------------------------------------------------------------------
# Conversation Manager (ADR-016: Persistent Agent Architecture)
# ---------------------------------------------------------------------------


def get_conversation_manager():
    """Provide a ConversationManager for the current request scope."""
    from taskforce.application.conversation_manager import ConversationManager
    from taskforce.application.infrastructure_builder import InfrastructureBuilder

    work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
    store = InfrastructureBuilder().build_conversation_store(work_dir=work_dir)
    return ConversationManager(store)


@lru_cache(maxsize=1)
def get_request_queue():
    """Provide a shared RequestQueue instance."""
    from taskforce.application.request_queue import RequestQueue

    return RequestQueue()


# ---------------------------------------------------------------------------
# Persistent Agent Service registry
# ---------------------------------------------------------------------------
#
# The butler daemon and the REST API can run as separate processes, so the
# API has no automatic handle on the daemon's PersistentAgentService.
# We expose a process-local register so an embedding host (a daemon that
# also serves the API, or tests) can publish its instance and the
# ``/api/v1/missions`` routes can find it via FastAPI ``Depends``.
# Returns ``None`` when no service is active — routes translate that to
# HTTP 503.

_PERSISTENT_AGENT_SERVICE: Any | None = None


def set_persistent_agent_service(service: Any | None) -> None:
    """Publish the current ``PersistentAgentService`` to the API layer.

    Called by the embedding host (butler daemon, REST server lifespan)
    on startup; pass ``None`` on shutdown so routes return 503.
    """
    global _PERSISTENT_AGENT_SERVICE
    _PERSISTENT_AGENT_SERVICE = service


def get_persistent_agent_service():
    """Return the registered ``PersistentAgentService`` or ``None``."""
    return _PERSISTENT_AGENT_SERVICE


# ---------------------------------------------------------------------------
# Active EventSource registry for webhook routing
# ---------------------------------------------------------------------------
#
# The generic ``POST /api/v1/events/{source_name}`` endpoint needs to find
# the live, started ``WebhookCapableEventSource`` instance (a registered
# factory is not enough — handle_inbound is method state). The butler
# daemon registers each started source here; webhook-capable sources
# created elsewhere can also opt in.

_ACTIVE_EVENT_SOURCES: dict[str, Any] = {}


def register_active_event_source(name: str, source: Any) -> None:
    """Publish a started event source so the events route can reach it."""
    _ACTIVE_EVENT_SOURCES[name] = source


def unregister_active_event_source(name: str) -> None:
    """Remove a source from the active registry (no-op if absent)."""
    _ACTIVE_EVENT_SOURCES.pop(name, None)


def get_active_event_source(name: str) -> Any | None:
    """Return the active source for ``name`` or ``None``."""
    return _ACTIVE_EVENT_SOURCES.get(name)


def list_active_event_sources() -> list[str]:
    """Return the names of currently registered active sources."""
    return sorted(_ACTIVE_EVENT_SOURCES.keys())


# ---------------------------------------------------------------------------
# Standing goals — store + evaluator (proactive layer)
# ---------------------------------------------------------------------------

_STANDING_GOAL_STORE: Any | None = None
_GOAL_EVALUATOR: Any | None = None


def set_standing_goal_store(store: Any | None) -> None:
    global _STANDING_GOAL_STORE
    _STANDING_GOAL_STORE = store


def get_standing_goal_store():
    """Return the registered store, lazily building a file-backed default.

    Falls back to a ``FileStandingGoalStore`` rooted at ``TASKFORCE_WORK_DIR``
    so the REST CRUD routes work without an explicit register step. The
    butler daemon overrides this on startup so writes from the daemon
    and from REST land in the same file.
    """
    global _STANDING_GOAL_STORE
    if _STANDING_GOAL_STORE is None:
        from taskforce.infrastructure.persistence.file_standing_goal_store import (
            FileStandingGoalStore,
        )

        work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
        _STANDING_GOAL_STORE = FileStandingGoalStore(work_dir=work_dir)
    return _STANDING_GOAL_STORE


def set_goal_evaluator(evaluator: Any | None) -> None:
    """Publish a ``GoalEvaluatorService`` so ``evaluate-now`` is reachable."""
    global _GOAL_EVALUATOR
    _GOAL_EVALUATOR = evaluator


def get_goal_evaluator():
    """Return the registered evaluator or ``None`` when no daemon is up."""
    return _GOAL_EVALUATOR


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_scheduler():
    """Provide the shared SchedulerService.

    Lazily constructed on first access; the API server's lifespan handler
    starts it on startup and stops it on shutdown so cron-triggered jobs
    fire while the API is up. The instance is keyed on the process so
    the workflow runtime service and any future agent that registers
    jobs share the same job store and event callback wiring.
    """
    from taskforce.infrastructure.scheduler.scheduler_service import SchedulerService

    work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
    return SchedulerService(work_dir=work_dir)


# ---------------------------------------------------------------------------
# Workflow Runtime Service
# ---------------------------------------------------------------------------


def get_workflow_runtime_service():
    """Provide a WorkflowRuntimeService for the current request scope.

    Store overrides may be tenant-scoped, so the runtime service must be
    constructed after auth/recipient resolution has populated the current
    tenant context. The scheduler remains shared; only the workflow stores
    are resolved per call.
    """
    from taskforce.application.infrastructure_builder import InfrastructureBuilder
    from taskforce.application.workflow_runtime_service import WorkflowRuntimeService

    work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
    store = InfrastructureBuilder().build_workflow_checkpoint_store(work_dir=work_dir)
    definition_store = InfrastructureBuilder().build_workflow_definition_store(work_dir=work_dir)
    # ADR-022 §7 / G3: thread the framework scheduler through so saved
    # workflow definitions with a schedule trigger automatically register
    # cron jobs without the API caller having to await a separate hook.
    return WorkflowRuntimeService(
        store, definition_store=definition_store, scheduler=get_scheduler()
    )
