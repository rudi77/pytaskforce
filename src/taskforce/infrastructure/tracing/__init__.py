"""
Infrastructure Layer - Tracing

This module provides OpenTelemetry-based tracing with Arize Phoenix integration.
Follows hexagonal architecture by keeping observability concerns in infrastructure.
"""

from taskforce.infrastructure.tracing.phoenix_tracer import (
    TracingConfig,
    get_tracer,
    init_tracing,
    shutdown_tracing,
)

__all__ = [
    "init_tracing",
    "shutdown_tracing",
    "get_tracer",
    "TracingConfig",
]

