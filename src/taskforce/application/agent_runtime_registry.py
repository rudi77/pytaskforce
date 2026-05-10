"""Agent runtime registry.

Module-level registry mapping a ``runtime`` name (``"taskforce"``,
``"hermes"``, ``"openclaw"``, …) to a factory that produces an
:class:`~taskforce.core.interfaces.agent_runtime.AgentRuntimeProtocol`
instance from a resolved profile dictionary.

Foreign agent packages register themselves at import time::

    from taskforce.application.agent_runtime_registry import register_runtime

    async def _factory(profile_dict):
        return HermesRuntime(profile_dict.get("runtime_config", {}))

    register_runtime("hermes", _factory)

The :class:`~taskforce.application.agent_creation_pipeline.AgentCreationPipeline`
consults this registry when a profile carries a non-default ``runtime`` field.

Thread-safety mirrors :mod:`taskforce.application.infrastructure_overrides`:
registration happens once at startup (CLI bootstrap or plugin init) before
worker threads serve traffic, so the underlying dict is not guarded.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from taskforce.core.interfaces.agent_runtime import AgentRuntimeProtocol

logger = structlog.get_logger(__name__)


RuntimeFactory = Callable[[dict[str, Any]], Awaitable["AgentRuntimeProtocol"]]


DEFAULT_RUNTIME = "taskforce"


_runtimes: dict[str, RuntimeFactory] = {}


def register_runtime(name: str, factory: RuntimeFactory) -> None:
    """Register ``factory`` under ``name``.

    Re-registering the same name overwrites the previous factory and logs a
    warning. The framework reserves ``"taskforce"`` for the built-in native
    runtime.
    """
    if not name or not name.strip():
        raise ValueError("runtime name must be a non-empty string")
    normalized = name.strip().lower()
    if normalized in _runtimes:
        logger.warning("agent_runtime_overwritten", runtime=normalized)
    _runtimes[normalized] = factory
    logger.debug("agent_runtime_registered", runtime=normalized)


def get_runtime(name: str) -> RuntimeFactory:
    """Return the factory registered under ``name``.

    Raises :class:`KeyError` if no runtime with that name is registered.
    """
    normalized = (name or "").strip().lower()
    try:
        return _runtimes[normalized]
    except KeyError as exc:
        available = ", ".join(sorted(_runtimes)) or "<none>"
        raise KeyError(
            f"Agent runtime '{name}' is not registered. " f"Available runtimes: {available}"
        ) from exc


def list_runtimes() -> list[str]:
    """Return the names of all currently registered runtimes (sorted)."""
    return sorted(_runtimes)


def is_registered(name: str) -> bool:
    """Return ``True`` when ``name`` is a registered runtime."""
    return (name or "").strip().lower() in _runtimes


def unregister_runtime(name: str) -> None:
    """Remove ``name`` from the registry. No-op if not registered.

    Mostly useful in tests; production code should not unregister runtimes.
    """
    _runtimes.pop((name or "").strip().lower(), None)


def clear_runtimes() -> None:
    """Remove all registered runtimes. Test helper only.

    The built-in ``"taskforce"`` runtime is re-registered lazily on the
    next :func:`get_runtime` call via :func:`_ensure_builtin_registered`.
    """
    _runtimes.clear()


# ---------------------------------------------------------------------------
# Built-in Taskforce runtime
# ---------------------------------------------------------------------------


async def _taskforce_runtime_factory(profile_dict: dict[str, Any]) -> AgentRuntimeProtocol:
    """Default factory returning a native Taskforce :class:`Agent`.

    Loads via the existing :class:`AgentFactory` — i.e. the same code path
    as ``factory.create_agent_from_profile``. The resolved profile dict is
    passed via ``profile_dict["__profile_name__"]`` (preferred) or the
    ``profile`` key, both of which the pipeline supplies.

    The native :class:`taskforce.core.domain.lean_agent.Agent` already
    satisfies :class:`AgentRuntimeProtocol` structurally — it exposes
    ``execute_stream``, ``close``, ``request_interrupt``, ``clear_interrupt``.
    It does not declare a ``runtime_name`` attribute; we stamp one on the
    instance so registry callers can introspect uniformly.
    """
    from taskforce.application.factory import AgentFactory

    profile_name = (
        profile_dict.get("__profile_name__") or profile_dict.get("profile") or DEFAULT_RUNTIME
    )
    user_context = profile_dict.get("__user_context__")
    planning_strategy = profile_dict.get("__planning_strategy__")
    planning_strategy_params = profile_dict.get("__planning_strategy_params__")

    factory = AgentFactory()
    agent = await factory.create_agent(
        config=profile_name,
        user_context=user_context,
        planning_strategy=planning_strategy,
        planning_strategy_params=planning_strategy_params,
    )

    if not hasattr(agent, "runtime_name"):
        try:
            agent.runtime_name = DEFAULT_RUNTIME  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            pass
    return agent  # type: ignore[return-value]


def _ensure_builtin_registered() -> None:
    """Ensure the built-in ``taskforce`` runtime is in the registry."""
    if DEFAULT_RUNTIME not in _runtimes:
        _runtimes[DEFAULT_RUNTIME] = _taskforce_runtime_factory


# Register at import time so callers see ``"taskforce"`` from the start.
_ensure_builtin_registered()


__all__ = [
    "DEFAULT_RUNTIME",
    "RuntimeFactory",
    "register_runtime",
    "get_runtime",
    "list_runtimes",
    "is_registered",
    "unregister_runtime",
    "clear_runtimes",
]
