import logging
import os
from typing import Any, Optional
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from taskforce.api.routes import agents, execution, health, sessions, tools
from taskforce.application.tracing_facade import init_tracing, shutdown_tracing
from taskforce.application.plugin_discovery import (
    load_all_plugins,
    shutdown_plugins,
    get_plugin_registry,
    is_enterprise_available,
)

# Configure logging based on LOGLEVEL environment variable
loglevel = os.getenv("LOGLEVEL", "INFO").upper()
log_level_map = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
log_level = log_level_map.get(loglevel, logging.INFO)

# Configure Python logging
logging.basicConfig(level=log_level, format="%(message)s")

# Configure structlog with the same level
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(log_level),
)

logger = structlog.get_logger()


async def taskforce_http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Return standardized error responses for Taskforce exceptions."""
    if (
        exc.headers
        and exc.headers.get("X-Taskforce-Error") == "1"
        and isinstance(exc.detail, dict)
    ):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return await http_exception_handler(request, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI startup/shutdown events."""
    # Initialize tracing first (before any LLM calls)
    init_tracing()

    # Note: Plugins are already loaded in create_app() before this runs
    # This ensures routers are registered before the app starts
    enterprise_status = "available" if is_enterprise_available() else "not installed"
    await logger.ainfo(
        "fastapi.startup",
        message="Taskforce API starting...",
        enterprise=enterprise_status,
    )
    yield
    await logger.ainfo(
        "fastapi.shutdown", message="Taskforce API shutting down..."
    )

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
        with open(config_path) as f:
            return yaml.safe_load(f) or {}

    # Return empty config - plugins can use their own defaults
    return {}


def create_app(plugin_config: Optional[dict[str, Any]] = None) -> FastAPI:
    """Create and configure FastAPI application.

    Args:
        plugin_config: Optional configuration for plugins

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Taskforce Agent API",
        description=(
            "Production-ready ReAct agent framework "
            "with Clean Architecture"
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_exception_handler(HTTPException, taskforce_http_exception_handler)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure based on environment
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include core routers
    app.include_router(
        execution.router, prefix="/api/v1", tags=["execution"]
    )
    app.include_router(
        sessions.router, prefix="/api/v1", tags=["sessions"]
    )
    app.include_router(
        agents.router, prefix="/api/v1", tags=["agents"]
    )
    app.include_router(
        tools.router, prefix="/api/v1", tags=["tools"]
    )
    app.include_router(health.router, tags=["health"])

    # Load plugins BEFORE registering them (must happen before lifespan)
    # This ensures routers are available for OpenAPI schema generation
    config = plugin_config or _load_plugin_config()
    load_all_plugins(config)

    # Register plugin components (middleware and routers)
    _register_plugins(app)

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
