import logging
import os
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from taskforce.api.routes import agents, execution, health, sessions, tools
from taskforce.infrastructure.tracing import init_tracing, shutdown_tracing

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

    await logger.ainfo(
        "fastapi.startup", message="Taskforce API starting..."
    )
    yield
    await logger.ainfo(
        "fastapi.shutdown", message="Taskforce API shutting down..."
    )

    # Shutdown tracing last (flush all pending spans)
    shutdown_tracing()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

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

    # Include routers
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

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8070)
