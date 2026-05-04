"""Tests for the infrastructure override hooks.

The framework itself never installs an override; these tests verify
that an external package (e.g. ``taskforce-enterprise``) can replace
the default behaviour of selected ``InfrastructureBuilder`` methods
without subclassing or forking the builder.
"""

from __future__ import annotations

from typing import Any

import pytest

from taskforce.application.infrastructure_builder import InfrastructureBuilder
from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    get_acp_tenant_id_provider,
    get_agent_registry_override,
    get_current_tenant_id,
    get_gateway_components_override,
    get_state_manager_override,
    get_tenant_resolver,
    get_workspace_context_provider,
    set_acp_tenant_id_provider,
    set_agent_registry_override,
    set_gateway_components_override,
    set_state_manager_override,
    set_tenant_resolver,
    set_workspace_context_provider,
)


@pytest.fixture(autouse=True)
def _reset_overrides():
    """Reset overrides before and after each test to prevent leakage."""
    clear_infrastructure_overrides()
    yield
    clear_infrastructure_overrides()


# ---------------------------------------------------------------------------
# Defaults — no override installed
# ---------------------------------------------------------------------------


def test_defaults_are_unset() -> None:
    """No overrides are installed by default."""
    assert get_agent_registry_override() is None
    assert get_state_manager_override() is None
    assert get_gateway_components_override() is None
    assert get_workspace_context_provider() is None
    assert get_acp_tenant_id_provider() is None
    assert get_tenant_resolver() is None


# ---------------------------------------------------------------------------
# Tenant resolver (ADR-022 §1)
# ---------------------------------------------------------------------------


def test_get_current_tenant_id_returns_default_without_resolver() -> None:
    """Single-tenant builds: no resolver installed → ``"default"``."""
    assert get_current_tenant_id() == "default"


def test_get_current_tenant_id_uses_installed_resolver() -> None:
    """When a resolver is installed, its value is returned."""
    set_tenant_resolver(lambda: "tenant-a")
    assert get_current_tenant_id() == "tenant-a"


def test_get_current_tenant_id_falls_back_when_resolver_returns_empty() -> None:
    """An empty / falsy resolver value is treated as the default."""
    set_tenant_resolver(lambda: "")
    assert get_current_tenant_id() == "default"


def test_get_current_tenant_id_falls_back_when_resolver_raises() -> None:
    """A buggy resolver must not break the framework — fall back to default."""
    def boom() -> str:
        raise RuntimeError("boom")

    set_tenant_resolver(boom)
    assert get_current_tenant_id() == "default"


def test_clear_resets_tenant_resolver() -> None:
    set_tenant_resolver(lambda: "tenant-a")
    clear_infrastructure_overrides()
    assert get_tenant_resolver() is None
    assert get_current_tenant_id() == "default"


def test_default_build_agent_registry_returns_file_registry() -> None:
    """With no override installed the builder returns a FileAgentRegistry."""
    from taskforce.infrastructure.persistence.file_agent_registry import (
        FileAgentRegistry,
    )

    builder = InfrastructureBuilder()
    registry = builder.build_agent_registry()
    assert isinstance(registry, FileAgentRegistry)


def test_default_build_state_manager_returns_file_state_manager(tmp_path) -> None:
    """With no override the builder honours profile config."""
    from taskforce.infrastructure.persistence.file_state_manager import (
        FileStateManager,
    )

    builder = InfrastructureBuilder()
    config = {"persistence": {"type": "file", "work_dir": str(tmp_path)}}
    state_manager = builder.build_state_manager(config)
    assert isinstance(state_manager, FileStateManager)


# ---------------------------------------------------------------------------
# Agent registry override
# ---------------------------------------------------------------------------


def test_agent_registry_override_is_invoked() -> None:
    """When an override is installed, build_agent_registry returns its value."""
    sentinel: Any = object()
    calls: list[None] = []

    def my_provider() -> Any:
        calls.append(None)
        return sentinel

    set_agent_registry_override(my_provider)

    builder = InfrastructureBuilder()
    result = builder.build_agent_registry()

    assert result is sentinel
    assert len(calls) == 1


def test_acp_tenant_id_provider_round_trip() -> None:
    """ACP tenant provider can be installed and cleared."""
    set_acp_tenant_id_provider(lambda: "tenant_a")
    assert get_acp_tenant_id_provider()() == "tenant_a"

    clear_infrastructure_overrides()

    assert get_acp_tenant_id_provider() is None


def test_agent_registry_override_invoked_per_call() -> None:
    """Override is consulted on every call (no caching by the builder)."""
    counter = {"n": 0}

    def my_provider() -> Any:
        counter["n"] += 1
        return f"instance-{counter['n']}"

    set_agent_registry_override(my_provider)

    builder = InfrastructureBuilder()
    a = builder.build_agent_registry()
    b = builder.build_agent_registry()

    assert a == "instance-1"
    assert b == "instance-2"
    assert counter["n"] == 2


def test_agent_registry_override_cleared() -> None:
    """Setting the override to None reverts to the default behaviour."""
    set_agent_registry_override(lambda: "first")

    builder = InfrastructureBuilder()
    assert builder.build_agent_registry() == "first"

    set_agent_registry_override(None)

    from taskforce.infrastructure.persistence.file_agent_registry import (
        FileAgentRegistry,
    )

    assert isinstance(builder.build_agent_registry(), FileAgentRegistry)


# ---------------------------------------------------------------------------
# State manager override
# ---------------------------------------------------------------------------


def test_state_manager_override_receives_config_and_work_dir(tmp_path) -> None:
    """The override receives the same arguments as the default method."""
    received: dict[str, Any] = {}

    def my_provider(config: dict[str, Any], work_dir_override: str | None) -> Any:
        received["config"] = config
        received["work_dir_override"] = work_dir_override
        return "stub-state-manager"

    set_state_manager_override(my_provider)

    builder = InfrastructureBuilder()
    config = {"persistence": {"type": "file"}}
    result = builder.build_state_manager(config, work_dir_override=str(tmp_path))

    assert result == "stub-state-manager"
    assert received["config"] == config
    assert received["work_dir_override"] == str(tmp_path)


def test_state_manager_override_does_not_inspect_config() -> None:
    """The override is called even when config is malformed for the default path.

    This proves the override truly short-circuits the default's config validation.
    """

    def my_provider(config: dict[str, Any], work_dir_override: str | None) -> Any:
        return "from-override"

    set_state_manager_override(my_provider)

    builder = InfrastructureBuilder()
    # Config that would raise ValueError in the default branch
    bad_config = {"persistence": {"type": "totally-unknown"}}
    result = builder.build_state_manager(bad_config)

    assert result == "from-override"


# ---------------------------------------------------------------------------
# Gateway components override
# ---------------------------------------------------------------------------


def test_gateway_components_override_receives_work_dir() -> None:
    """The override receives the work_dir argument verbatim."""
    received: dict[str, Any] = {}

    def my_provider(work_dir: str) -> Any:
        received["work_dir"] = work_dir
        return "stub-gateway-components"

    set_gateway_components_override(my_provider)

    builder = InfrastructureBuilder()
    result = builder.build_gateway_components(work_dir=".my-work")

    assert result == "stub-gateway-components"
    assert received["work_dir"] == ".my-work"


# ---------------------------------------------------------------------------
# Override exceptions propagate
# ---------------------------------------------------------------------------


def test_agent_registry_override_exception_propagates() -> None:
    """If the override raises, the exception bubbles out unchanged."""

    class BoomError(RuntimeError):
        pass

    def my_provider() -> Any:
        raise BoomError("override blew up")

    set_agent_registry_override(my_provider)

    builder = InfrastructureBuilder()
    with pytest.raises(BoomError, match="override blew up"):
        builder.build_agent_registry()


def test_state_manager_override_exception_propagates() -> None:
    """If the override raises, the exception bubbles out unchanged."""

    class BoomError(RuntimeError):
        pass

    def my_provider(config: dict[str, Any], work_dir_override: str | None) -> Any:
        raise BoomError("state override blew up")

    set_state_manager_override(my_provider)

    builder = InfrastructureBuilder()
    with pytest.raises(BoomError, match="state override blew up"):
        builder.build_state_manager({}, None)


def test_gateway_components_override_exception_propagates() -> None:
    """If the override raises, the exception bubbles out unchanged."""

    class BoomError(RuntimeError):
        pass

    def my_provider(work_dir: str) -> Any:
        raise BoomError("gateway override blew up")

    set_gateway_components_override(my_provider)

    builder = InfrastructureBuilder()
    with pytest.raises(BoomError, match="gateway override blew up"):
        builder.build_gateway_components(work_dir=".x")


# ---------------------------------------------------------------------------
# clear_infrastructure_overrides
# ---------------------------------------------------------------------------


def test_clear_resets_all_overrides() -> None:
    """clear_infrastructure_overrides removes every installed override."""
    set_agent_registry_override(lambda: "a")
    set_state_manager_override(lambda c, w: "s")
    set_gateway_components_override(lambda w: "g")
    set_workspace_context_provider(lambda: "w")

    clear_infrastructure_overrides()

    assert get_agent_registry_override() is None
    assert get_state_manager_override() is None
    assert get_gateway_components_override() is None
    assert get_workspace_context_provider() is None


# ---------------------------------------------------------------------------
# Workspace context provider
# ---------------------------------------------------------------------------


def test_workspace_context_provider_round_trip() -> None:
    sentinel: Any = object()

    def my_provider() -> Any:
        return sentinel

    set_workspace_context_provider(my_provider)
    assert get_workspace_context_provider() is my_provider


def test_workspace_context_provider_cleared_individually() -> None:
    set_agent_registry_override(lambda: "a")
    set_workspace_context_provider(lambda: "w")

    set_workspace_context_provider(None)

    assert get_workspace_context_provider() is None
    assert get_agent_registry_override() is not None


def test_clear_is_idempotent() -> None:
    """Calling clear with no overrides set is a no-op."""
    clear_infrastructure_overrides()
    clear_infrastructure_overrides()  # second call must not raise
    assert get_agent_registry_override() is None


def test_override_can_be_reinstalled_after_clear() -> None:
    """An override can be reinstalled after a clear."""
    set_agent_registry_override(lambda: "first")
    clear_infrastructure_overrides()
    set_agent_registry_override(lambda: "second")

    builder = InfrastructureBuilder()
    assert builder.build_agent_registry() == "second"


# ---------------------------------------------------------------------------
# ADR-022 §5: SandboxedExecutor + multi-tenant startup warning
# ---------------------------------------------------------------------------


from taskforce.application.infrastructure_overrides import (
    get_sandboxed_executor,
    set_sandboxed_executor,
    warn_if_multi_tenant_without_sandbox,
)


def test_sandboxed_executor_round_trip() -> None:
    sentinel = object()
    set_sandboxed_executor(sentinel)
    assert get_sandboxed_executor() is sentinel
    set_sandboxed_executor(None)
    assert get_sandboxed_executor() is None


def test_warn_silent_when_no_tenant_resolver() -> None:
    """Single-tenant build: no resolver → no warning even without a sandbox."""
    import warnings

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        warned = warn_if_multi_tenant_without_sandbox()

    assert warned is False
    assert captured == []


def test_warn_silent_when_sandbox_installed() -> None:
    """Multi-tenant + sandbox installed → no warning."""
    import warnings

    set_tenant_resolver(lambda: "tenant-a")
    set_sandboxed_executor(object())

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        warned = warn_if_multi_tenant_without_sandbox()

    assert warned is False
    assert captured == []


def test_warn_fires_once_in_multi_tenant_without_sandbox() -> None:
    """Multi-tenant resolver, no sandbox → one warning, then silent."""
    import warnings

    set_tenant_resolver(lambda: "tenant-a")
    # No sandbox installed.

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        warned1 = warn_if_multi_tenant_without_sandbox()
        warned2 = warn_if_multi_tenant_without_sandbox()

    assert warned1 is True
    assert warned2 is False
    assert len(captured) == 1
    assert issubclass(captured[0].category, RuntimeWarning)
    assert "multi-tenant" in str(captured[0].message).lower()


# ---------------------------------------------------------------------------
# ADR-022 §4: gateway recipient_resolver + agent_lookup overrides
# ---------------------------------------------------------------------------


from taskforce.application.infrastructure_overrides import (
    get_agent_lookup_override,
    get_recipient_resolver_override,
    set_agent_lookup_override,
    set_recipient_resolver_override,
)


def test_recipient_resolver_override_round_trip() -> None:
    sentinel = object()
    set_recipient_resolver_override(lambda: sentinel)
    assert get_recipient_resolver_override()() is sentinel


def test_agent_lookup_override_round_trip() -> None:
    sentinel = object()
    set_agent_lookup_override(lambda: sentinel)
    assert get_agent_lookup_override()() is sentinel


def test_clear_resets_gateway_overrides() -> None:
    set_recipient_resolver_override(lambda: object())
    set_agent_lookup_override(lambda: object())
    clear_infrastructure_overrides()
    assert get_recipient_resolver_override() is None
    assert get_agent_lookup_override() is None


# ---------------------------------------------------------------------------
# ADR-022 §6: cross-tenant ACP authorizer
# ---------------------------------------------------------------------------


from taskforce.application.infrastructure_overrides import (
    get_cross_tenant_acp_authorizer,
    set_cross_tenant_acp_authorizer,
)


def test_cross_tenant_acp_authorizer_round_trip() -> None:
    def allow_all(caller, peer_t, peer) -> bool:
        return True

    set_cross_tenant_acp_authorizer(allow_all)
    assert get_cross_tenant_acp_authorizer() is allow_all


def test_clear_resets_cross_tenant_acp_authorizer() -> None:
    set_cross_tenant_acp_authorizer(lambda c, p, pe: True)
    clear_infrastructure_overrides()
    assert get_cross_tenant_acp_authorizer() is None
