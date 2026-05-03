"""Infrastructure builder override hooks.

Lets a plugin replace the default behaviour of selected
``InfrastructureBuilder`` methods without subclassing or forking the
builder. Each override is a callable matching the corresponding builder
method's signature; ``InfrastructureBuilder`` consults the override
registry on each call and falls back to its built-in behaviour when no
override is installed.

This is the framework-side seam used by external packages (currently
``taskforce-enterprise``) to inject per-build store instances. The
framework itself never installs an override and never reads any of
the builder methods' return values differently when one is installed —
the override mechanism is entirely opt-in and additive.

Usage (from a plugin's bootstrap)::

    from taskforce.application.infrastructure_overrides import (
        set_agent_registry_override,
    )

    def my_agent_registry_provider():
        return MyTenantAwareRegistry(...)

    set_agent_registry_override(my_agent_registry_provider)

The framework's default tests run with no overrides installed; the
``clear_infrastructure_overrides`` helper resets the override state
between tests.

Thread safety: the override slots are module-level globals and are
not thread-safe. Overrides are expected to be installed once at
plugin-init time, before any worker threads start serving requests
— the same pattern used by ``_factory_extensions`` in
``application/factory.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Each override is a callable that receives the same arguments as the
# corresponding ``InfrastructureBuilder`` method. The override is
# expected to return an instance with the same protocol shape as the
# builder method's default return value.
#
# Iteration 1 introduces overrides for the three stores the enterprise
# plugin needs first (agent registry, state manager, gateway
# components). Additional overrides (e.g. wiki store) will be added in
# later iterations as required, once their call sites are routed
# through ``InfrastructureBuilder`` consistently.
_agent_registry_override: Callable[[], Any] | None = None
_state_manager_override: Callable[[dict[str, Any], str | None], Any] | None = None
_gateway_components_override: Callable[[str], Any] | None = None
_recipient_resolver_override: Callable[[], Any] | None = None
_workspace_context_provider: Callable[[], Any] | None = None


def set_agent_registry_override(
    provider: Callable[[], Any] | None,
) -> None:
    """Install (or clear) an override for ``build_agent_registry``."""
    global _agent_registry_override
    _agent_registry_override = provider


def get_agent_registry_override() -> Callable[[], Any] | None:
    """Return the currently installed agent-registry override, if any."""
    return _agent_registry_override


def set_state_manager_override(
    provider: Callable[[dict[str, Any], str | None], Any] | None,
) -> None:
    """Install (or clear) an override for ``build_state_manager``.

    The provider receives the same ``(config, work_dir_override)``
    arguments as the builder method.
    """
    global _state_manager_override
    _state_manager_override = provider


def get_state_manager_override() -> Callable[[dict[str, Any], str | None], Any] | None:
    """Return the currently installed state-manager override, if any."""
    return _state_manager_override


def set_gateway_components_override(
    provider: Callable[[str], Any] | None,
) -> None:
    """Install (or clear) an override for ``build_gateway_components``."""
    global _gateway_components_override
    _gateway_components_override = provider


def get_gateway_components_override() -> Callable[[str], Any] | None:
    """Return the currently installed gateway-components override, if any."""
    return _gateway_components_override


def set_recipient_resolver_override(
    provider: Callable[[], Any] | None,
) -> None:
    """Install (or clear) a provider for the gateway's recipient resolver.

    The provider is called once when the global ``CommunicationGateway``
    instance is built (via ``api.dependencies.get_gateway``) and is
    expected to return a ``RecipientResolverProtocol`` implementation.
    When no override is installed the gateway falls back to its built-in
    pass-through resolver (which never refuses a message), preserving
    legacy behaviour.

    External packages use this hook to inject identity-aware resolvers
    (for example, the enterprise plugin's ``ConfigBackedRecipientResolver``
    which maps channel-specific identities to logical recipients and
    binds tenant context for downstream per-tenant routing).
    """
    global _recipient_resolver_override
    _recipient_resolver_override = provider


def get_recipient_resolver_override() -> Callable[[], Any] | None:
    """Return the currently installed recipient-resolver provider, if any."""
    return _recipient_resolver_override


def set_workspace_context_provider(
    provider: Callable[[], Any] | None,
) -> None:
    """Install (or clear) a per-request workspace-context factory.

    Unlike the store-related overrides above, the workspace provider
    is **not** consulted by ``InfrastructureBuilder``. It is consumed
    by the agent execution path (typically before each tool call) to
    populate :func:`taskforce.core.interfaces.workspace.set_workspace_context`
    so path-aware tools (``file_read``, ``file_write``, ``edit``,
    etc.) resolve relative paths against the agent's writable
    workspace and reject ``..`` traversal.

    The provider is a zero-argument callable returning either a
    :class:`taskforce.core.interfaces.workspace.WorkspaceContextProtocol`
    instance or ``None``. Returning ``None`` keeps the framework's
    default (no scoping) for that call — useful for system agents or
    background jobs that legitimately need the host filesystem.
    """
    global _workspace_context_provider
    _workspace_context_provider = provider


def get_workspace_context_provider() -> Callable[[], Any] | None:
    """Return the currently installed workspace-context provider, if any."""
    return _workspace_context_provider


def clear_infrastructure_overrides() -> None:
    """Reset all installed overrides.

    Intended for test teardown so one test's override does not leak
    into another.
    """
    global _agent_registry_override
    global _state_manager_override
    global _gateway_components_override
    global _recipient_resolver_override
    global _workspace_context_provider
    _agent_registry_override = None
    _state_manager_override = None
    _gateway_components_override = None
    _recipient_resolver_override = None
    _workspace_context_provider = None
