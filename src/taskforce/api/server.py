import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# On Windows, asyncio.create_subprocess_exec() requires ProactorEventLoop;
# uvicorn defaults to SelectorEventLoop, which raises NotImplementedError
# when Playwright (browser tool) or other tools spawn subprocesses.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Load .env before any module that reads provider credentials at import time
# (LiteLLM, Azure SDKs, MCP server connectors). This makes
# ``uvicorn taskforce.api.server:app`` behave the same as ``taskforce serve``.
from taskforce.api.cli.env_loader import load_dotenv_if_present as _load_dotenv

_load_dotenv()

# Configure structured logging with a rotating file handler so the API
# leaves a trail on disk even when started directly via uvicorn (without
# the CLI wrapper). Console output stays color-rendered for development.
from taskforce.infrastructure.logging.setup import configure_logging as _configure_logging

_LOG_DIR = Path(os.environ.get("TASKFORCE_LOG_DIR", ".taskforce/logs")).expanduser()
_LOG_NAME = os.environ.get("TASKFORCE_LOG_FILE", "api.log")
_LOG_DEBUG = (os.environ.get("LOGLEVEL", "INFO").upper() == "DEBUG") or (
    os.environ.get("TASKFORCE_LOG_DEBUG", "").lower() in {"1", "true", "yes"}
)
_LOG_PATH = _configure_logging(
    log_dir=_LOG_DIR,
    log_name=_LOG_NAME,
    debug=_LOG_DEBUG,
)

# Eagerly import the LiteLLM service so its module-level
# ``AZURE_OPENAI_* -> AZURE_*`` env mapping runs before the first request
# (which would otherwise hit the agent factory with half-mapped credentials).
import taskforce.infrastructure.llm.litellm_service  # noqa: F401

# Install the LiteLLM token-analytics callback so every completion
# lands in ``.taskforce/analytics.db``. Without this the analytics
# endpoints stay empty because nothing ever writes a row.
from taskforce.infrastructure.llm.token_analytics_callback import (  # noqa: E402
    TokenAnalyticsCallback as _TokenAnalyticsCallback,
    get_token_analytics as _get_token_analytics,
)

if _get_token_analytics() is None:
    _TokenAnalyticsCallback().install()

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from taskforce.api.exception_handlers import taskforce_http_exception_handler
from taskforce.api.routes import (
    a2a,
    acp,
    agent_deployments,
    agent_templates,
    agents,
    analytics,
    conversations,
    evals,
    events,
    execution,
    files,
    filesystem,
    gateway,
    missions,
    oauth,
    standing_goals,
    health,
    llm,
    mcp,
    memory,
    planning_strategies,
    profiles,
    projects,
    remote_agents,
    runs,
    settings as settings_route,
    skills,
    tools,
    workspace,
    ui,
    workflows,
)
from taskforce.application.bootstrap_config_dirs import bootstrap_config_dirs
from taskforce.application.plugin_loader import (
    get_plugin_registry,
    is_enterprise_available,
    load_all_plugins,
    shutdown_plugins,
)
from taskforce.application.tracing_facade import init_tracing, shutdown_tracing

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI startup/shutdown events."""
    # Initialize tracing first (before any LLM calls)
    init_tracing()

    # Hydrate UI-managed settings into env vars BEFORE LiteLLM /
    # gateway components are first built; their constructors snapshot
    # env state, so reading the settings store after startup would
    # otherwise miss settings-supplied keys until the next restart.
    try:
        from taskforce.api.dependencies import get_settings_store as _get_settings_store
        from taskforce.application.settings_hydrator import hydrate_all as _hydrate_all

        _hydrate_all(_get_settings_store())
    except Exception as exc:  # pragma: no cover — defensive
        await logger.awarning(
            "fastapi.startup.settings_hydrate_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )

    # Register agent-package config directories so /api/v1/profiles can
    # discover butler / coding-agent / rag-agent profiles regardless of
    # whether the CLI was used to start the server.
    registered_dirs = bootstrap_config_dirs()

    # Note: Plugins are already loaded in create_app() before this runs
    # This ensures routers are registered before the app starts
    enterprise_status = "available" if is_enterprise_available() else "not installed"
    await logger.ainfo(
        "fastapi.startup",
        message="Taskforce API starting...",
        enterprise=enterprise_status,
        agent_config_dirs=[str(d) for d in registered_dirs],
        log_path=str(_LOG_PATH),
    )
    # Start the workflow scheduler so schedule-triggered workflow
    # definitions actually fire on their cron expressions (ADR-022 §7,
    # G3/G4). Lazy import keeps the framework's startup independent of
    # the scheduler's optional deps.
    from taskforce.api.dependencies import (
        get_executor,
        get_gateway,
        get_scheduler,
        get_workflow_runtime_service,
    )
    from taskforce.application.scheduler_dispatcher import (
        make_scheduler_event_callback,
    )

    # Wire the Communication Gateway into the executor and factory at
    # startup so SendNotificationTool always has a gateway reference,
    # regardless of whether a request hits a route that depends on
    # ``get_gateway`` first. Without this, schedule-fired workflows
    # (and any FastAPI route that doesn't ``Depends(get_gateway)``)
    # build agents whose send_notification tool returns
    # "Communication gateway not configured".
    try:
        get_gateway()
    except Exception as exc:  # pragma: no cover — defensive startup wiring
        await logger.awarning(
            "fastapi.startup.gateway_unavailable",
            error=str(exc),
            error_type=type(exc).__name__,
        )

    scheduler = get_scheduler()
    # G4: register the workflow dispatcher so EXECUTE_WORKFLOW jobs
    # actually run their workflow when the cron tick fires.
    scheduler._event_callback = make_scheduler_event_callback(
        workflow_runtime=get_workflow_runtime_service,
        executor=get_executor(),
    )
    await scheduler.start()

    # Start per-bot Telegram pollers (multi-bot hot-reload, issue #227
    # follow-up). The manager owns one ``getUpdates`` task per enabled
    # Telegram bot config and is also consulted by the settings routes
    # after every bot CRUD so changes take effect without restart.
    try:
        from taskforce.api.dependencies import get_bot_poller_manager

        bot_poller_manager = get_bot_poller_manager()
        if bot_poller_manager is not None:
            await bot_poller_manager.start()
    except Exception as exc:  # pragma: no cover — defensive
        bot_poller_manager = None
        await logger.awarning(
            "fastapi.startup.bot_poller_manager_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )

    yield
    await logger.ainfo("fastapi.shutdown", message="Taskforce API shutting down...")

    # Stop pollers before the rest so in-flight gateway dispatches see
    # a still-live executor.
    if bot_poller_manager is not None:
        try:
            await bot_poller_manager.stop()
        except Exception:  # pragma: no cover — defensive
            pass

    # Stop the scheduler before shutting down plugins so any in-flight
    # job that calls into a plugin sees it still loaded.
    try:
        await scheduler.stop()
    except Exception:  # pragma: no cover — defensive
        pass

    # Shutdown plugins
    shutdown_plugins()

    # Shutdown tracing last (flush all pending spans)
    shutdown_tracing()


def _load_plugin_config() -> dict[str, Any]:
    """Load plugin configuration from environment or config file.

    Returns:
        Plugin configuration dictionary
    """
    # Check for plugin config file path in environment
    config_path = os.getenv("TASKFORCE_PLUGIN_CONFIG")
    if config_path and os.path.exists(config_path):
        import yaml

        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    # Return empty config - plugins can use their own defaults
    return {}


def _resolve_ui_dir() -> Path | None:
    """Locate the built web UI directory, or return None if not available.

    Resolution order:
      1. ``TASKFORCE_UI_DIR`` env var (explicit override / container mount)
      2. ``<package>/api/_ui`` — the UI build bundled into the wheel
      3. ``<repo root>/ui/dist`` — a local ``pnpm build`` during development
    """
    candidates: list[Path] = []
    env_dir = os.getenv("TASKFORCE_UI_DIR")
    if env_dir:
        candidates.append(Path(env_dir).expanduser())
    candidates.append(Path(__file__).parent / "_ui")
    candidates.append(Path(__file__).resolve().parents[3] / "ui" / "dist")
    for candidate in candidates:
        if candidate and (candidate / "index.html").is_file():
            return candidate
    return None


def _mount_ui(app: FastAPI) -> None:
    """Serve the bundled single-page web UI from the API process.

    Registered after all API and plugin routers so those always win; the
    SPA catch-all only handles paths the API does not own. Without a built
    UI present this is a no-op and the API still serves ``/api/v1`` + docs.
    """
    ui_dir = _resolve_ui_dir()
    if ui_dir is None:
        logger.info(
            "ui.static.not_found",
            hint="run `pnpm build` in ui/ or set TASKFORCE_UI_DIR to serve the web UI",
        )
        return

    assets_dir = ui_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="ui-assets")

    index_file = ui_dir / "index.html"
    _api_prefixes = ("api/", "health", "docs", "redoc", "openapi.json")

    @app.get("/", include_in_schema=False)
    async def _ui_root() -> FileResponse:
        return FileResponse(index_file)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _ui_spa(full_path: str) -> FileResponse:
        # API/docs/health routes are registered earlier and match first;
        # if we still get one here it is genuinely unknown -> 404 (not the SPA).
        if full_path.startswith(_api_prefixes):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = ui_dir / full_path
        if candidate.is_file() and candidate.resolve().is_relative_to(ui_dir.resolve()):
            return FileResponse(candidate)
        # Unknown path -> hand control to the client-side router.
        return FileResponse(index_file)

    logger.info("ui.static.mounted", ui_dir=str(ui_dir))


def create_app(plugin_config: dict[str, Any] | None = None) -> FastAPI:
    """Create and configure FastAPI application.

    Args:
        plugin_config: Optional configuration for plugins

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Taskforce Agent API",
        description=("Production-ready ReAct agent framework " "with Clean Architecture"),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_exception_handler(HTTPException, taskforce_http_exception_handler)

    # Include core routers
    app.include_router(execution.router, prefix="/api/v1", tags=["execution"])
    app.include_router(agents.router, prefix="/api/v1", tags=["agents"])
    app.include_router(agent_deployments.router, prefix="/api/v1", tags=["agent-deployments"])
    app.include_router(agent_templates.router, prefix="/api/v1", tags=["agent-templates"])
    app.include_router(tools.router, prefix="/api/v1", tags=["tools"])
    app.include_router(gateway.router, prefix="/api/v1", tags=["gateway"])
    app.include_router(missions.router, prefix="/api/v1", tags=["missions"])
    app.include_router(events.router, prefix="/api/v1", tags=["events"])
    app.include_router(
        standing_goals.router, prefix="/api/v1", tags=["standing-goals"]
    )
    app.include_router(health.router, tags=["health"])
    app.include_router(memory.router, prefix="/api/v1", tags=["memory"])
    app.include_router(conversations.router, prefix="/api/v1", tags=["conversations"])
    app.include_router(workflows.router, prefix="/api/v1", tags=["workflows"])
    app.include_router(acp.router, tags=["acp"])
    app.include_router(a2a.router, tags=["a2a"])
    app.include_router(remote_agents.router, tags=["remote-agents"])
    app.include_router(profiles.router, prefix="/api/v1", tags=["profiles"])
    app.include_router(projects.router, prefix="/api/v1", tags=["projects"])
    app.include_router(skills.router, prefix="/api/v1", tags=["skills"])
    app.include_router(llm.router, prefix="/api/v1", tags=["llm"])
    app.include_router(planning_strategies.router, prefix="/api/v1", tags=["planning"])
    app.include_router(files.router, prefix="/api/v1", tags=["files"])
    app.include_router(filesystem.router, prefix="/api/v1", tags=["filesystem"])
    app.include_router(workspace.router, prefix="/api/v1", tags=["workspace"])
    app.include_router(analytics.router, prefix="/api/v1", tags=["analytics"])
    app.include_router(runs.router, prefix="/api/v1", tags=["runs"])
    app.include_router(mcp.router, prefix="/api/v1", tags=["mcp"])
    app.include_router(settings_route.router, prefix="/api/v1", tags=["settings"])
    app.include_router(oauth.router, prefix="/api/v1", tags=["oauth"])
    app.include_router(evals.router, prefix="/api/v1", tags=["evals"])
    app.include_router(ui.router, prefix="/api/v1", tags=["ui"])

    # Load plugins BEFORE registering them (must happen before lifespan)
    # This ensures routers are available for OpenAPI schema generation
    config = plugin_config or _load_plugin_config()
    load_all_plugins(config)

    # Register plugin components (middleware and routers)
    _register_plugins(app)

    # CORS middleware - origins configurable via CORS_ORIGINS env var.
    # Added LAST so it wraps every other middleware (incl. plugin auth) and
    # answers preflight + attaches Access-Control-* headers to error responses.
    cors_origins_raw = os.getenv("CORS_ORIGINS", "*")
    cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]
    # allow_credentials=True is only safe with explicit origins
    allow_creds = cors_origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_creds,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Serve the bundled web UI (when present) so a single process delivers
    # both the REST API and the front-end. Mounted last so API and plugin
    # routes always take precedence over the SPA catch-all.
    _mount_ui(app)

    return app


def _register_plugins(app: FastAPI) -> None:
    """Register middleware and routers from loaded plugins.

    Plugins are discovered via entry points and loaded during app lifespan.
    This function registers their components with the FastAPI app.

    Args:
        app: The FastAPI application
    """
    registry = get_plugin_registry()

    # Register middleware from plugins
    # Note: Middleware is added in reverse order (last added = first executed)
    for middleware in registry.middleware:
        try:
            if callable(middleware):
                # Check if it's a class (needs instantiation) or instance
                if isinstance(middleware, type):
                    # It's a class - will be instantiated by add_middleware
                    app.add_middleware(middleware)
                else:
                    # It's already an instance or a middleware factory
                    app.add_middleware(type(middleware), dispatch=middleware)
            logger.debug(
                "plugin.middleware.added",
                middleware=str(middleware),
            )
        except Exception as e:
            logger.warning(
                "plugin.middleware.add_failed",
                middleware=str(middleware),
                error=str(e),
            )

    # Register routers from plugins
    for router in registry.routers:
        try:
            # Get tags from router, default to ["plugin"]
            tags = getattr(router, "tags", ["plugin"])

            # Plugin routers already have their sub-prefix (e.g., /admin/users)
            # We add the /api/v1 prefix when including them
            app.include_router(router, prefix="/api/v1", tags=tags)

            # Log the full path for debugging
            router_prefix = getattr(router, "prefix", "")
            logger.info(
                "plugin.router.added",
                full_path=f"/api/v1{router_prefix}",
                tags=tags,
            )
        except Exception as e:
            logger.warning(
                "plugin.router.add_failed",
                router=str(router),
                error=str(e),
            )


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8070)
