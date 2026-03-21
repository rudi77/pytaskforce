"""Token analytics facade for the application layer.

Re-exports the callback singleton accessor so that the API layer
(CLI commands, routes) can consume token analytics without importing
directly from the infrastructure layer.
"""

from __future__ import annotations

from taskforce.core.domain.token_analytics import ExecutionTokenSummary
from taskforce.infrastructure.llm.token_analytics_callback import get_token_analytics


def get_execution_token_summary() -> ExecutionTokenSummary | None:
    """Return the current execution's token summary, or None.

    After reading, the callback's recorded calls are reset so each
    execution gets a fresh summary.

    Returns:
        Aggregated token summary if any LLM calls were recorded, else None.
    """
    cb = get_token_analytics()
    if cb is None or not cb.calls:
        return None
    summary = cb.build_summary()
    cb.reset()
    return summary
