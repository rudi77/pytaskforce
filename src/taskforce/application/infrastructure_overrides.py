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

from collections.abc import Awaitable, Callable
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
_deployment_manifest_override: Callable[[], Any] | None = None
_settings_store_override: Callable[[str], Any] | None = None
_token_store_override: Callable[[], Any] | None = None
_state_manager_override: Callable[[dict[str, Any], str | None], Any] | None = None
_conversation_store_override: Callable[[str], Any] | None = None
_agent_state_override: Callable[[str], Any] | None = None
_wiki_store_override: Callable[[str], Any] | None = None
_workflow_definition_store_override: Callable[[str], Any] | None = None
_workflow_checkpoint_store_override: Callable[[str], Any] | None = None
_gateway_components_override: Callable[[str], Any] | None = None
_workspace_context_provider: Callable[[], Any] | None = None
_acp_tenant_id_provider: Callable[[], str] | None = None
_tenant_resolver: Callable[[], str] | None = None
_user_resolver: Callable[[], str | None] | None = None
_tenant_context_runner: Callable[[str, Callable[[], Awaitable[Any]]], Awaitable[Any]] | None = None
_sandboxed_executor: Any | None = None
_multi_tenant_sandbox_warning_emitted: bool = False
_recipient_resolver_override: Callable[[], Any] | None = None
_agent_lookup_override: Callable[[], Any] | None = None
_workflow_lookup_override: Callable[[], Any] | None = None
_webhook_workflow_resolver: Callable[[str], Awaitable[str | None]] | None = None
_cross_tenant_acp_authorizer: Callable[[str, str, Any], bool] | None = None
_mission_lifecycle_hook: Any | None = None
_approval_service: Any | None = None


def set_agent_registry_override(
    provider: Callable[[], Any] | None,
) -> None:
    """Install (or clear) an override for ``build_agent_registry``."""
    global _agent_registry_override
    _agent_registry_override = provider


def get_agent_registry_override() -> Callable[[], Any] | None:
    """Return the currently installed agent-registry override, if any."""
    return _agent_registry_override


def set_deployment_manifest_override(
    provider: Callable[[], Any] | None,
) -> None:
    """Install (or clear) an override for deployment-manifest resolution.

    The provider is a zero-argument callable returning either a
    :class:`taskforce.core.domain.deployment.DeploymentManifest` instance
    or ``None``. Returning ``None`` keeps the framework's legacy
    "show every discovered agent" behaviour.

    Use this seam to scope the visible-agents allowlist per tenant
    from an enterprise plugin (e.g. read the manifest from a tenant-
    specific store). The framework default is no override → the
    builder loads the shipped ``deployment.yaml``.
    """
    global _deployment_manifest_override
    _deployment_manifest_override = provider


def get_deployment_manifest_override() -> Callable[[], Any] | None:
    """Return the currently installed deployment-manifest override, if any."""
    return _deployment_manifest_override


def set_settings_store_override(
    provider: Callable[[str], Any] | None,
) -> None:
    """Install (or clear) an override for ``build_settings_store``.

    The provider receives the same ``work_dir`` argument as the builder
    method and must return an object satisfying
    :class:`taskforce.core.interfaces.settings.SettingsStoreProtocol`.
    Use this to back the settings store with a tenant-scoped store
    (e.g. database-backed) from an enterprise plugin. With nothing
    installed the framework's default file-based, Fernet-encrypted
    store is used — bit-for-bit single-tenant behaviour.
    """
    global _settings_store_override
    _settings_store_override = provider


def get_settings_store_override() -> Callable[[str], Any] | None:
    """Return the currently installed settings-store override, if any."""
    return _settings_store_override


def set_token_store_override(provider: Callable[[], Any] | None) -> None:
    """Install (or clear) an override for ``build_token_store``.

    The provider is a zero-argument callable returning an object
    satisfying :class:`taskforce.core.interfaces.auth.TokenStoreProtocol`.

    Use this to back the token store with a per-(tenant, user) store
    (e.g. an encrypted bucket under ``tenants/<tid>/users/<uid>/auth/``)
    from an enterprise plugin. With nothing installed the framework
    falls back to its process-global ``EncryptedTokenStore`` rooted at
    ``~/.taskforce/auth/`` — the legacy single-user behaviour.

    Note: zero-argument by design. Per-user resolution happens inside
    the enterprise factory by reading tenant + user ContextVars; the
    framework call site has no useful argument to pass. The provider
    is consulted on every ``build_token_store`` call, so plugins that
    need per-request scoping typically return a thin dispatcher
    wrapper that re-resolves on each ``save_token`` / ``load_token``
    call (the framework's ``AuthManager`` is built once per process
    via ``lru_cache``).
    """
    global _token_store_override
    _token_store_override = provider


def get_token_store_override() -> Callable[[], Any] | None:
    """Return the currently installed token-store override, if any."""
    return _token_store_override


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


def set_conversation_store_override(
    provider: Callable[[str], Any] | None,
) -> None:
    """Install (or clear) an override for conversation-store construction."""
    global _conversation_store_override
    _conversation_store_override = provider


def get_conversation_store_override() -> Callable[[str], Any] | None:
    """Return the currently installed conversation-store override, if any."""
    return _conversation_store_override


def set_agent_state_override(
    provider: Callable[[str], Any] | None,
) -> None:
    """Install (or clear) an override for agent-state construction."""
    global _agent_state_override
    _agent_state_override = provider


def get_agent_state_override() -> Callable[[str], Any] | None:
    """Return the currently installed agent-state override, if any."""
    return _agent_state_override


def set_wiki_store_override(
    provider: Callable[[str], Any] | None,
) -> None:
    """Install (or clear) an override for wiki-store construction."""
    global _wiki_store_override
    _wiki_store_override = provider


def get_wiki_store_override() -> Callable[[str], Any] | None:
    """Return the currently installed wiki-store override, if any."""
    return _wiki_store_override


def set_workflow_definition_store_override(
    provider: Callable[[str], Any] | None,
) -> None:
    """Install (or clear) an override for workflow-definition-store construction."""
    global _workflow_definition_store_override
    _workflow_definition_store_override = provider


def get_workflow_definition_store_override() -> Callable[[str], Any] | None:
    """Return the currently installed workflow-definition-store override, if any."""
    return _workflow_definition_store_override


def set_workflow_checkpoint_store_override(
    provider: Callable[[str], Any] | None,
) -> None:
    """Install (or clear) an override for workflow-checkpoint-store construction."""
    global _workflow_checkpoint_store_override
    _workflow_checkpoint_store_override = provider


def get_workflow_checkpoint_store_override() -> Callable[[str], Any] | None:
    """Return the currently installed workflow-checkpoint-store override, if any."""
    return _workflow_checkpoint_store_override


def set_gateway_components_override(
    provider: Callable[[str], Any] | None,
) -> None:
    """Install (or clear) an override for ``build_gateway_components``."""
    global _gateway_components_override
    _gateway_components_override = provider


def get_gateway_components_override() -> Callable[[str], Any] | None:
    """Return the currently installed gateway-components override, if any."""
    return _gateway_components_override


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


def set_acp_tenant_id_provider(provider: Callable[[], str] | None) -> None:
    """Install (or clear) a provider for ACP caller tenant context."""
    global _acp_tenant_id_provider
    _acp_tenant_id_provider = provider


def get_acp_tenant_id_provider() -> Callable[[], str] | None:
    """Return the currently installed ACP tenant provider, if any."""
    return _acp_tenant_id_provider


def set_tenant_resolver(provider: Callable[[], str] | None) -> None:
    """Install (or clear) the framework-wide tenant-id resolver.

    See ADR-022 §1: the resolver is the single seam the framework uses
    to ask "what's the current tenant id?" without knowing anything
    about tenants. An enterprise plugin installs a closure that reads
    its ``TenantContext`` ContextVar. Single-tenant builds leave it
    unset; ``get_current_tenant_id()`` then returns ``"default"``.

    In practice the same callable is also passed to
    :func:`set_acp_tenant_id_provider` — they answer the same question
    from different call sites. The two slots are kept distinct because
    the ACP runtime takes its provider as a constructor argument and
    stores it independently.
    """
    global _tenant_resolver
    _tenant_resolver = provider


def get_tenant_resolver() -> Callable[[], str] | None:
    """Return the currently installed tenant resolver, if any."""
    return _tenant_resolver


def get_current_tenant_id() -> str:
    """Return the current request's tenant id, or ``"default"``.

    Convenience wrapper that lets call sites stay tenant-agnostic
    without scattering ``or "default"`` fallbacks. Adapters that need
    per-tenant scoping read this once at the start of each request /
    operation; ``"default"`` is the bit-for-bit single-tenant
    behaviour.
    """
    if _tenant_resolver is None:
        return "default"
    try:
        resolved = _tenant_resolver()
    except Exception:  # Defensive: a buggy plugin must not break the framework
        return "default"
    return resolved or "default"


def set_user_resolver(provider: Callable[[], str | None] | None) -> None:
    """Install (or clear) the framework-wide user-id resolver.

    Mirror of ``set_tenant_resolver`` for the user dimension. When the
    enterprise plugin is installed it registers a closure that reads
    the current ``UserContext`` ContextVar; without it
    ``get_current_user_id()`` returns ``None`` so per-user filtering
    in framework adapters falls open (the single-tenant single-user
    behaviour).
    """
    global _user_resolver
    _user_resolver = provider


def get_user_resolver() -> Callable[[], str | None] | None:
    """Return the currently installed user resolver, if any."""
    return _user_resolver


def get_current_user_id() -> str | None:
    """Return the current request's user id, or ``None``.

    Returns ``None`` when no resolver is installed (single-tenant
    builds) or when the resolver yields no user (background jobs,
    pre-auth requests). Callers that need per-user scoping should
    treat ``None`` as "no user filter applies" rather than as an
    explicit user.
    """
    if _user_resolver is None:
        return None
    try:
        resolved = _user_resolver()
    except Exception:  # Defensive: a buggy plugin must not break the framework
        return None
    return resolved or None


def set_tenant_context_runner(
    runner: Callable[[str, Callable[[], Awaitable[Any]]], Awaitable[Any]] | None,
) -> None:
    """Install an async runner that executes work under a tenant context.

    Background callbacks, such as scheduler events, do not pass through
    HTTP auth middleware. Enterprise runtimes install this hook so
    those callbacks can resolve tenant-scoped stores for the event's
    tenant before doing work.
    """
    global _tenant_context_runner
    _tenant_context_runner = runner


def get_tenant_context_runner() -> (
    Callable[[str, Callable[[], Awaitable[Any]]], Awaitable[Any]] | None
):
    """Return the installed tenant-context runner, if any."""
    return _tenant_context_runner


def set_sandboxed_executor(executor: Any | None) -> None:
    """Install (or clear) the sandboxed executor for dangerous tools.

    See ADR-022 §5: the framework ships an in-process default that
    preserves single-tenant behaviour; multi-tenant deployments
    install a container-backed implementation that mounts only the
    workspace, drops network capabilities and applies CPU/memory/
    wall-clock limits.

    The slot is typed ``Any`` here to avoid pulling
    ``SandboxedExecutorProtocol`` into the application layer just for
    the type annotation. Callers should pass an implementation of
    :class:`taskforce.core.interfaces.sandbox.SandboxedExecutorProtocol`.
    """
    global _sandboxed_executor
    _sandboxed_executor = executor


def get_sandboxed_executor() -> Any | None:
    """Return the installed sandboxed executor, or ``None``."""
    return _sandboxed_executor


def set_recipient_resolver_override(provider: Callable[[], Any] | None) -> None:
    """Install (or clear) a provider that returns the gateway's recipient resolver.

    The provider is consulted once when the lazy ``get_gateway`` builds
    the ``CommunicationGateway`` singleton. Implementations should
    return an object satisfying
    :class:`taskforce.core.interfaces.gateway.RecipientResolverProtocol`.

    The framework default is no override → the gateway uses its built-in
    pass-through resolver, which makes the legacy single-tenant behaviour
    unchanged.
    """
    global _recipient_resolver_override
    _recipient_resolver_override = provider


def get_recipient_resolver_override() -> Callable[[], Any] | None:
    """Return the installed recipient-resolver provider, if any."""
    return _recipient_resolver_override


def set_agent_lookup_override(provider: Callable[[], Any] | None) -> None:
    """Install (or clear) a provider that returns the gateway's ``@agent`` lookup.

    The provider is consulted once when ``get_gateway`` builds the
    ``CommunicationGateway`` singleton. Implementations should return
    an object satisfying
    :class:`taskforce.core.interfaces.gateway.AgentLookupProtocol`.

    With no override installed the gateway leaves a leading ``@name``
    token as plain text in the message body and falls back to the
    recipient's default agent — see ADR-022 §4.
    """
    global _agent_lookup_override
    _agent_lookup_override = provider


def get_agent_lookup_override() -> Callable[[], Any] | None:
    """Return the installed agent-lookup provider, if any."""
    return _agent_lookup_override


def set_workflow_lookup_override(provider: Callable[[], Any] | None) -> None:
    """Install (or clear) the gateway's @workflow_name lookup (G5).

    Implementations should return an object satisfying
    :class:`taskforce.core.interfaces.gateway.WorkflowLookupProtocol`.
    With nothing installed the gateway only resolves @-mentions to
    agents — no @-workflow routing happens.
    """
    global _workflow_lookup_override
    _workflow_lookup_override = provider


def get_workflow_lookup_override() -> Callable[[], Any] | None:
    """Return the installed workflow-lookup provider, if any."""
    return _workflow_lookup_override


def set_webhook_workflow_resolver(
    resolver: Callable[[str], Awaitable[str | None]] | None,
) -> None:
    """Install (or clear) a global webhook-path → tenant_id resolver.

    The webhook trigger endpoint
    (``POST /api/v1/workflows/webhooks/{path}``) is auth-exempt so it
    has no tenant context when a request lands. Without this resolver
    the route can only see workflows in the framework's *current*
    (default) tenant — webhooks owned by other tenants 404.

    With a resolver installed the route, on a local miss, asks the
    resolver "which tenant owns this path?". When the resolver returns
    a tenant id the route then switches into that tenant via
    :func:`get_tenant_context_runner` and re-runs the lookup + execute
    sequence. Single-tenant builds don't need this — leaving it unset
    is the bit-for-bit-identical behaviour.

    The resolver is async because a Postgres-backed implementation
    will issue a query.
    """
    global _webhook_workflow_resolver
    _webhook_workflow_resolver = resolver


def get_webhook_workflow_resolver() -> Callable[[str], Awaitable[str | None]] | None:
    """Return the installed webhook resolver, if any."""
    return _webhook_workflow_resolver


def set_cross_tenant_acp_authorizer(
    authorizer: Callable[[str, str, Any], bool] | None,
) -> None:
    """Install (or clear) the policy check for cross-tenant ACP calls.

    See ADR-022 §6: when an ACP peer is reachable across tenants
    (``allow_cross_tenant=True`` on the peer record), the framework
    asks an installable authorizer whether the *current* caller may
    actually use it. Returning ``False`` raises ``PermissionError``
    on the call site; returning ``True`` proceeds.

    Signature:
        ``authorizer(caller_tenant_id, peer_tenant_id, peer) -> bool``

    The third arg is the framework's ``AcpPeer`` value object (passed
    untyped here to avoid a core/infra cycle); enterprise authorizers
    use it to log richer audit events. With no authorizer installed
    the framework falls back to "allow" — i.e. the
    ``allow_cross_tenant`` flag alone is the policy, which is the
    legacy single-tenant behaviour.
    """
    global _cross_tenant_acp_authorizer
    _cross_tenant_acp_authorizer = authorizer


def get_cross_tenant_acp_authorizer() -> Callable[[str, str, Any], bool] | None:
    """Return the installed cross-tenant ACP authorizer, if any."""
    return _cross_tenant_acp_authorizer


def set_mission_lifecycle_hook(hook: Any | None) -> None:
    """Install (or clear) a mission lifecycle hook.

    The hook must satisfy
    :class:`taskforce.core.interfaces.mission_lifecycle.MissionLifecycleHookProtocol`
    — its ``on_mission_started`` / ``on_mission_completed`` are called
    by ``AgentExecutor`` around ``execute_mission_streaming``. Hook
    failures are logged but never break the calling mission.

    The framework's default is no hook → no-op. The enterprise plugin
    typically installs a hook that emits AuditEvents.
    """
    global _mission_lifecycle_hook
    _mission_lifecycle_hook = hook


def get_mission_lifecycle_hook() -> Any | None:
    """Return the installed mission-lifecycle hook, if any."""
    return _mission_lifecycle_hook


def set_approval_service(service: Any | None) -> None:
    """Install (or clear) the tool-approval gate.

    The service must satisfy
    :class:`taskforce.core.interfaces.approval.ApprovalServiceProtocol`.
    When installed, ``LeanAgent._execute_tool`` checks each tool's
    ``requires_approval`` flag and calls
    ``request_approval(request)`` before invoking the tool. A denied
    or timed-out decision returns a ``ToolError`` payload from the
    tool call instead of running the tool.

    With no service installed the framework falls back to legacy
    behaviour: ``requires_approval`` metadata is exposed in the tool
    catalog but no gate is applied. This keeps single-user CLI runs
    unchanged from before Phase 2.
    """
    global _approval_service
    _approval_service = service


def get_approval_service() -> Any | None:
    """Return the installed approval service, if any."""
    return _approval_service


def warn_if_multi_tenant_without_sandbox() -> bool:
    """Emit a hard one-shot warning when multi-tenant runs without a sandbox.

    The framework treats a multi-tenant runtime as one where a tenant
    resolver has been installed (i.e. an enterprise plugin sets a
    real ``current_tenant_id`` callable instead of the default
    ``"default"``). In that mode running dangerous tools through the
    in-process default is unsafe: a misbehaving agent in tenant A can
    read tenant B's secrets.

    The warning fires at most once per process so callers can invoke
    it from multiple bootstrap paths (factory, lifespan, plugin init)
    without producing log spam. Returns True if the warning was
    emitted *this* call.
    """
    global _multi_tenant_sandbox_warning_emitted
    if _multi_tenant_sandbox_warning_emitted:
        return False
    if _tenant_resolver is None:
        # Single-tenant build — the in-process executor is the right default.
        return False
    if _sandboxed_executor is not None:
        # Operator wired a real sandbox.
        return False

    import warnings

    warnings.warn(
        "Multi-tenant runtime detected (a tenant resolver is installed) but "
        "no SandboxedExecutorProtocol implementation is registered. "
        "Dangerous tools (bash, shell, powershell) will run in the host "
        "process with full filesystem visibility — a misbehaving or "
        "malicious agent in one tenant can read another tenant's data. "
        "Install a container-backed executor via "
        "taskforce.application.infrastructure_overrides.set_sandboxed_executor(...) "
        "before running untrusted workloads. See ADR-022 §5.",
        category=RuntimeWarning,
        stacklevel=2,
    )
    _multi_tenant_sandbox_warning_emitted = True
    return True


def clear_infrastructure_overrides() -> None:
    """Reset all installed overrides.

    Intended for test teardown so one test's override does not leak
    into another.
    """
    global _agent_registry_override
    global _deployment_manifest_override
    global _settings_store_override
    global _token_store_override
    global _state_manager_override
    global _conversation_store_override
    global _agent_state_override
    global _wiki_store_override
    global _workflow_definition_store_override
    global _workflow_checkpoint_store_override
    global _gateway_components_override
    global _workspace_context_provider
    global _acp_tenant_id_provider
    global _tenant_resolver
    global _user_resolver
    global _tenant_context_runner
    global _sandboxed_executor
    global _multi_tenant_sandbox_warning_emitted
    global _recipient_resolver_override
    global _webhook_workflow_resolver
    global _agent_lookup_override
    global _workflow_lookup_override
    global _cross_tenant_acp_authorizer
    global _mission_lifecycle_hook
    global _approval_service
    _agent_registry_override = None
    _deployment_manifest_override = None
    _settings_store_override = None
    _token_store_override = None
    _state_manager_override = None
    _conversation_store_override = None
    _agent_state_override = None
    _wiki_store_override = None
    _workflow_definition_store_override = None
    _workflow_checkpoint_store_override = None
    _gateway_components_override = None
    _workspace_context_provider = None
    _acp_tenant_id_provider = None
    _tenant_resolver = None
    _user_resolver = None
    _tenant_context_runner = None
    _sandboxed_executor = None
    _multi_tenant_sandbox_warning_emitted = False
    _recipient_resolver_override = None
    _agent_lookup_override = None
    _workflow_lookup_override = None
    _webhook_workflow_resolver = None
    _cross_tenant_acp_authorizer = None
    _mission_lifecycle_hook = None
    _approval_service = None
