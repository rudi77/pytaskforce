"""
Phoenix OTEL Tracer Setup

Configures OpenTelemetry tracing with Arize Phoenix collector
for LLM observability. Uses auto-instrumentation for LiteLLM
to capture all LLM calls automatically.

Environment Variables:
    PHOENIX_COLLECTOR_ENDPOINT: Phoenix HTTP endpoint
        (default: http://localhost:6006/v1/traces)
    PHOENIX_GRPC_ENDPOINT: Phoenix gRPC endpoint
        (default: http://localhost:4317)
    PHOENIX_PROJECT_NAME: Project name (default: taskforce)
    TRACING_ENABLED: Enable/disable tracing (default: true)

Usage:
    from taskforce.infrastructure.tracing import init_tracing

    # At application startup
    init_tracing()

    # At application shutdown
    shutdown_tracing()
"""

import os
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()

# Global tracer provider reference for lifecycle management
_tracer_provider = None
_tracer = None


@dataclass
class TracingConfig:
    """
    Configuration for Phoenix OTEL tracing.

    Attributes:
        enabled: Whether tracing is enabled
        project_name: Name of the project in Phoenix UI
        collector_endpoint: Phoenix collector HTTP endpoint
        grpc_endpoint: Phoenix collector gRPC endpoint
    """

    enabled: bool = True
    project_name: str = "taskforce"
    collector_endpoint: str = "http://localhost:6006/v1/traces"
    grpc_endpoint: Optional[str] = "http://localhost:4317"

    @classmethod
    def from_env(cls) -> "TracingConfig":
        """
        Create config from environment variables.

        Environment Variables:
            TRACING_ENABLED: "true" or "false" (default: "true")
            PHOENIX_PROJECT_NAME: Project name (default: "taskforce")
            PHOENIX_COLLECTOR_ENDPOINT: HTTP endpoint
            PHOENIX_GRPC_ENDPOINT: gRPC endpoint
        """
        return cls(
            enabled=os.getenv("TRACING_ENABLED", "true").lower() == "true",
            project_name=os.getenv("PHOENIX_PROJECT_NAME", "taskforce"),
            collector_endpoint=os.getenv(
                "PHOENIX_COLLECTOR_ENDPOINT",
                "http://localhost:6006/v1/traces",
            ),
            grpc_endpoint=os.getenv(
                "PHOENIX_GRPC_ENDPOINT",
                "http://localhost:4317",
            ),
        )


def init_tracing(config: Optional[TracingConfig] = None) -> None:
    """
    Initialize OpenTelemetry tracing with Phoenix collector.

    Sets up:
    1. Phoenix OTEL tracer provider
    2. Auto-instrumentation for LiteLLM (captures all LLM calls)

    Args:
        config: Tracing configuration. If None, loads from environment.

    Example:
        # Using default config from environment
        init_tracing()

        # Using custom config
        config = TracingConfig(
            project_name="my-agent",
            collector_endpoint="http://phoenix:6006/v1/traces"
        )
        init_tracing(config)
    """
    global _tracer_provider, _tracer

    if config is None:
        config = TracingConfig.from_env()

    if not config.enabled:
        logger.info(
            "tracing_disabled",
            hint="Set TRACING_ENABLED=true to enable tracing",
        )
        return

    try:
        # Import Phoenix OTEL and register tracer
        from phoenix.otel import register

        logger.info(
            "tracing_initializing",
            project_name=config.project_name,
            collector_endpoint=config.collector_endpoint,
            grpc_endpoint=config.grpc_endpoint,
        )

        # Register Phoenix as the trace provider
        # auto_instrument=True enables auto-instrumentation
        _tracer_provider = register(
            project_name=config.project_name,
            endpoint=config.grpc_endpoint,  # Use gRPC for performance
            auto_instrument=True,
        )

        # Get a tracer instance for custom spans
        _tracer = _tracer_provider.get_tracer(__name__)

        # Explicitly instrument LiteLLM if auto_instrument doesn't cover it
        _instrument_litellm()

        logger.info(
            "tracing_initialized",
            project_name=config.project_name,
            collector_endpoint=config.collector_endpoint,
            auto_instrumented=["litellm"],
        )

    except ImportError as e:
        logger.warning(
            "tracing_import_error",
            error=str(e),
            hint="Install arize-phoenix-otel and "
            "openinference-instrumentation-litellm",
        )
    except Exception as e:
        logger.error(
            "tracing_initialization_failed",
            error=str(e),
            error_type=type(e).__name__,
            hint="Check Phoenix collector is running and accessible",
        )


def _instrument_litellm() -> None:
    """
    Explicitly instrument LiteLLM for tracing.

    This ensures all LiteLLM calls (acompletion, completion) are traced
    with full request/response details including:
    - Model name
    - Input messages
    - Output content
    - Token usage
    - Latency
    """
    try:
        from openinference.instrumentation.litellm import LiteLLMInstrumentor

        # Check if already instrumented
        instrumentor = LiteLLMInstrumentor()
        if not instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.instrument()
            logger.debug("litellm_instrumented")
        else:
            logger.debug("litellm_already_instrumented")

    except ImportError:
        logger.warning(
            "litellm_instrumentor_not_found",
            hint="Install openinference-instrumentation-litellm",
        )
    except Exception as e:
        logger.warning(
            "litellm_instrumentation_failed",
            error=str(e),
        )


def shutdown_tracing() -> None:
    """
    Shutdown tracing and flush pending spans.

    Should be called during application shutdown to ensure
    all traces are sent to the collector before exit.
    """
    global _tracer_provider, _tracer

    if _tracer_provider is None:
        return

    try:
        # Force flush any pending spans
        if hasattr(_tracer_provider, "force_flush"):
            _tracer_provider.force_flush()

        # Shutdown the provider
        if hasattr(_tracer_provider, "shutdown"):
            _tracer_provider.shutdown()

        logger.info("tracing_shutdown_complete")

    except Exception as e:
        logger.warning(
            "tracing_shutdown_error",
            error=str(e),
        )
    finally:
        _tracer_provider = None
        _tracer = None


def get_tracer():
    """
    Get the global tracer instance for creating custom spans.

    Returns:
        Tracer instance or None if tracing not initialized

    Example:
        tracer = get_tracer()
        if tracer:
            with tracer.start_as_current_span("my_operation") as span:
                span.set_attribute("custom.attribute", "value")
                # ... do work ...
    """
    return _tracer
