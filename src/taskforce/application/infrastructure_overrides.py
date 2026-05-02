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


def clear_infrastructure_overrides() -> None:
    """Reset all installed overrides.

    Intended for test teardown so one test's override does not leak
    into another.
    """
    global _agent_registry_override
    global _state_manager_override
    global _gateway_components_override
    _agent_registry_override = None
    _state_manager_override = None
    _gateway_components_override = None
