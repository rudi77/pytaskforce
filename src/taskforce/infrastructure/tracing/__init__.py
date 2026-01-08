"""
Infrastructure Layer - Tracing

This module provides:
- OpenTelemetry-based tracing with Arize Phoenix integration (network)
- File-based tracing for offline analysis (local JSONL files)

Follows hexagonal architecture by keeping observability concerns in infrastructure.
"""

from taskforce.infrastructure.tracing.phoenix_tracer import (
    init_tracing,
    shutdown_tracing,
    get_tracer,
    TracingConfig,
)
from taskforce.infrastructure.tracing.file_tracer import (
    FileTracer,
    init_file_tracing,
    get_file_tracer,
    shutdown_file_tracing,
)

__all__ = [
    # Phoenix OTEL tracing
    "init_tracing",
    "shutdown_tracing",
    "get_tracer",
    "TracingConfig",
    # File-based tracing
    "FileTracer",
    "init_file_tracing",
    "get_file_tracer",
    "shutdown_file_tracing",
]

