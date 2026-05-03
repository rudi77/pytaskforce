"""Public host-integration API.

Stable seam for embedding Taskforce into another Python application — either
as an in-process library or by mounting selected REST routes onto a host
FastAPI app. Everything in this module is part of the public contract; the
underlying internals (``infrastructure.tools.registry``, ``profile_loader``,
etc.) may shift between minor versions, but the symbols re-exported here will
remain stable.

Three integration modes are supported via the same primitives:

1. **Library (in-process)** — import ``AgentFactory`` directly, register
   your tools/profiles/skills via :func:`register_tool`,
   :func:`register_profile_dir`, :func:`register_skill_dir`.

2. **CLI / subprocess** — install ``taskforce-cli`` and run
   ``taskforce serve`` or ``taskforce run mission ...``. Custom tools and
   profiles installed as a Python package are auto-discovered via entry
   points or :func:`register_*` calls in the package's ``__init__``.

3. **Webservice (sidecar)** — run ``taskforce serve`` as a separate process
   or container. Host apps call the REST API at ``/api/v1/...``. To embed
   selected routes inside an existing FastAPI app, use
   :func:`mount_routes` or :func:`create_embedded_app`.

Example — mounting Taskforce inside a host FastAPI app::

    from fastapi import FastAPI
    from taskforce.host import (
        mount_routes,
        register_profile_dir,
        register_skill_dir,
        register_tool,
    )

    app = FastAPI(title="My App")

    register_profile_dir("backend/agents")               # finds maler.yaml
    register_skill_dir("backend/skills")                  # finds /quote etc.
    register_tool(
        "search_materials",
        "SearchMaterialsTool",
        "myapp.tools.search_materials",
    )

    mount_routes(app, prefix="/agent", include=["gateway", "execution", "skills"])

Architecture note:
    ``taskforce.host`` deliberately sits OUTSIDE the four-layer stack
    (Core → Infrastructure → Application → API). It is a public seam that
    re-exports symbols from the layers below; it must not contain any
    business logic of its own. The layer-import rules in CLAUDE.md do not
    apply here precisely because this module's only job is to be the one
    place where layer crossing for external integration is allowed.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    set_agent_registry_override,
    set_gateway_components_override,
    set_state_manager_override,
)
from taskforce.application.profile_loader import (
    register_config_dir as _register_config_dir,
)
from taskforce.application.skill_service import (
    register_skill_dir as _register_skill_dir,
)
from taskforce.infrastructure.tools.registry import (
    is_registered as _is_tool_registered,
)
from taskforce.infrastructure.tools.registry import (
    register_tool as _register_tool,
)
from taskforce.infrastructure.tools.registry import (
    unregister_tool as _unregister_tool,
)

# Sentinel attribute used on FastAPI app instances to record which routers
# this module has already mounted, so a second ``mount_routes`` call (e.g.
# under uvicorn ``--reload``) doesn't register the same paths twice.
_MOUNTED_ATTR = "_taskforce_host_mounted_routers"

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = [
    "register_tool",
    "unregister_tool",
    "is_tool_registered",
    "register_profile_dir",
    "register_skill_dir",
    "mount_routes",
    "create_embedded_app",
    "available_routers",
    "set_agent_registry_override",
    "set_state_manager_override",
    "set_gateway_components_override",
    "clear_infrastructure_overrides",
]


# ------------------------------------------------------------------
# Tool / profile / skill registration (thin re-exports)
# ------------------------------------------------------------------


def register_tool(
    name: str,
    tool_type: str,
    module: str,
    params: dict[str, Any] | None = None,
) -> None:
    """Register a custom tool so profiles can reference it by short name.

    Idempotent: re-registering a tool with the same ``(name, type, module)``
    is a no-op rather than an error. This makes it safe to call from a host
    application's ``__init__`` even when the module is reloaded under
    ``--reload`` or imported by tests multiple times.

    Args:
        name: Short tool name used in profile YAML ``tools:`` lists.
        tool_type: Class name of the tool implementation.
        module: Fully-qualified import path of the module exposing the class.
        params: Optional default constructor kwargs.
    """
    if _is_tool_registered(name):
        return
    _register_tool(name=name, tool_type=tool_type, module=module, params=params)


def unregister_tool(name: str) -> bool:
    """Remove a previously registered tool. Returns True if removed."""
    return _unregister_tool(name)


def is_tool_registered(name: str) -> bool:
    """Return True if a tool with the given short name is registered."""
    return _is_tool_registered(name)


def register_profile_dir(path: str) -> None:
    """Register a directory containing ``*.agent.md`` / ``*.yaml`` profiles.

    The Taskforce ``ProfileLoader`` searches all registered directories in
    addition to the framework-shipped configs, so host apps can supply their
    own profiles without copying files into the Taskforce install tree.

    Duplicate paths are silently ignored.
    """
    _register_config_dir(path)


def register_skill_dir(path: str) -> None:
    """Register a directory containing ``<name>/SKILL.md`` skill folders.

    If the singleton ``SkillService`` has already been initialised the new
    directory is added to its loader and the registry is refreshed so the
    new skills become discoverable immediately.
    """
    _register_skill_dir(path)


# ------------------------------------------------------------------
# Selective route mounting
# ------------------------------------------------------------------

# Built-in router map. Names accepted by ``mount_routes(include=...)``. The
# values are import paths consumed by ``importlib.import_module``; the dict
# is intentionally kept private so callers can never inject arbitrary module
# strings — only string keys are accepted at the public surface.
_BUILTIN_ROUTERS: dict[str, str] = {
    "acp": "taskforce.api.routes.acp",
    "agent_deployments": "taskforce.api.routes.agent_deployments",
    "agent_templates": "taskforce.api.routes.agent_templates",
    "agents": "taskforce.api.routes.agents",
    "analytics": "taskforce.api.routes.analytics",
    "conversations": "taskforce.api.routes.conversations",
    "evals": "taskforce.api.routes.evals",
    "execution": "taskforce.api.routes.execution",
    "files": "taskforce.api.routes.files",
    "gateway": "taskforce.api.routes.gateway",
    "health": "taskforce.api.routes.health",
    "llm": "taskforce.api.routes.llm",
    "mcp": "taskforce.api.routes.mcp",
    "memory": "taskforce.api.routes.memory",
    "planning_strategies": "taskforce.api.routes.planning_strategies",
    "profiles": "taskforce.api.routes.profiles",
    "runs": "taskforce.api.routes.runs",
    "skills": "taskforce.api.routes.skills",
    "tools": "taskforce.api.routes.tools",
    "ui": "taskforce.api.routes.ui",
    "workflows": "taskforce.api.routes.workflows",
}

# ``health`` and ``acp`` ship their own prefix-less paths (e.g. ``/health``);
# mounting them under ``/api/v1`` would change their public URLs. The
# standalone server (``api/server.py``) treats them the same way — keep the
# two lists in sync if a new prefixless router is added.
_PREFIXLESS_ROUTERS: frozenset[str] = frozenset({"health", "acp"})


def available_routers() -> list[str]:
    """Return all router names that can be passed to ``include=`` / ``exclude=``."""
    return sorted(_BUILTIN_ROUTERS)


def _resolve_router_set(
    include: Iterable[str] | None,
    exclude: Iterable[str] | None,
) -> list[str]:
    """Resolve an include/exclude pair into the actual list of router names."""
    if include is None:
        names = list(_BUILTIN_ROUTERS)
    else:
        names = []
        for name in include:
            if name not in _BUILTIN_ROUTERS:
                raise ValueError(f"Unknown router '{name}'. Available: {available_routers()}")
            names.append(name)

    if exclude:
        excluded = set(exclude)
        unknown = excluded - set(_BUILTIN_ROUTERS)
        if unknown:
            raise ValueError(
                f"Unknown router(s) in exclude: {sorted(unknown)}. "
                f"Available: {available_routers()}"
            )
        names = [n for n in names if n not in excluded]

    return names


def mount_routes(
    app: FastAPI,
    *,
    prefix: str = "/api/v1",
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
) -> list[str]:
    """Mount selected Taskforce REST routers onto an existing FastAPI app.

    Use this to embed Taskforce inside a host FastAPI application without
    pulling in the full ``taskforce.api.server:app`` (which always mounts
    every router and registers Taskforce-owned middleware/exception
    handlers).

    Routers whose paths are not under ``/api/v1`` (currently ``health`` and
    ``acp``) are mounted at the app root regardless of ``prefix``.

    Args:
        app: The host FastAPI application.
        prefix: URL prefix for the prefixed routers. Defaults to
            ``/api/v1`` to match the standalone server.
        include: Router names to mount. ``None`` (default) means all.
        exclude: Router names to skip. Applied after ``include``.

    Returns:
        The list of router names that were actually mounted on this call
        (already-mounted routers are skipped silently).

    Raises:
        ValueError: If any ``include`` / ``exclude`` name is unknown.
    """
    import importlib

    names = _resolve_router_set(include, exclude)

    # Idempotency: a second call (e.g. under uvicorn ``--reload`` or in
    # tests that share an app fixture) should not register duplicate
    # routes. We track mounted names per-app on a private attribute.
    already: set[str] = getattr(app, _MOUNTED_ATTR, set())
    mounted: list[str] = []

    for name in names:
        if name in already:
            continue
        module = importlib.import_module(_BUILTIN_ROUTERS[name])
        router = module.router
        if name in _PREFIXLESS_ROUTERS:
            app.include_router(router, tags=[name])
        else:
            app.include_router(router, prefix=prefix, tags=[name])
        already.add(name)
        mounted.append(name)

    setattr(app, _MOUNTED_ATTR, already)
    return mounted


def create_embedded_app(
    *,
    title: str = "Taskforce (embedded)",
    prefix: str = "/api/v1",
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
    register_exception_handler: bool = True,
) -> FastAPI:
    """Build a fresh FastAPI app with only the requested Taskforce routers.

    Unlike the full ``taskforce.api.server:app`` this does NOT install
    plugins, CORS middleware, or the lifespan tracing hooks — host apps
    are expected to own those. The Taskforce HTTP-exception handler is
    registered by default so error payloads stay structured.

    Args:
        title: OpenAPI title.
        prefix: Prefix for non-prefixless routers.
        include / exclude: Same semantics as :func:`mount_routes`.
        register_exception_handler: Install Taskforce's structured error
            handler. Set to False when the host app owns the global
            HTTP-exception handler.

    Returns:
        A FastAPI instance ready to be mounted with ``app.mount(...)`` or
        served standalone via uvicorn.
    """
    from fastapi import FastAPI, HTTPException

    embedded = FastAPI(title=title, docs_url="/docs", redoc_url="/redoc")

    if register_exception_handler:
        # Imported from the dedicated handlers module — NOT from server.py —
        # so we don't trigger the standalone server's plugin discovery and
        # global app construction.
        from taskforce.api.exception_handlers import taskforce_http_exception_handler

        embedded.add_exception_handler(HTTPException, taskforce_http_exception_handler)

    mount_routes(embedded, prefix=prefix, include=include, exclude=exclude)
    return embedded
