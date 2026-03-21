"""LiteLLM callback for automatic token analytics collection.

Registers as a LiteLLM ``CustomLogger`` and captures token usage,
model, latency, and tool calls for every LLM completion — both
streaming and non-streaming — without any changes to the agent
execution loop.

Usage::

    from taskforce.infrastructure.llm.token_analytics_callback import (
        TokenAnalyticsCallback,
        get_token_analytics,
    )

    # At startup (once):
    callback = TokenAnalyticsCallback()
    callback.install()

    # ... agent runs ...

    # After execution:
    summary = callback.build_summary()
    callback.reset()
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import litellm
import structlog

from taskforce.core.domain.token_analytics import (
    ExecutionTokenSummary,
    LLMCallRecord,
    build_summary,
)

logger = structlog.get_logger(__name__)

# Module-level singleton for easy access from CLI / executor
_active_callback: TokenAnalyticsCallback | None = None


class TokenAnalyticsCallback(litellm.integrations.custom_logger.CustomLogger):
    """LiteLLM callback that records per-call token analytics.

    Thread-safe: LiteLLM invokes callbacks synchronously from the
    completion call, so no locking is needed.
    """

    def __init__(self) -> None:
        self._calls: list[LLMCallRecord] = []

    # ------------------------------------------------------------------
    # LiteLLM callback interface
    # ------------------------------------------------------------------

    def log_success_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        """Called by LiteLLM after every successful (non-streaming) completion."""
        self._record(kwargs, response_obj, start_time, end_time)

    def log_stream_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        """Called by LiteLLM after a streaming completion finishes."""
        self._record(kwargs, response_obj, start_time, end_time)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        """Extract metrics from a LiteLLM callback invocation."""
        try:
            # Model
            model = str(kwargs.get("model", "unknown"))

            # Usage
            usage = {}
            if hasattr(response_obj, "usage") and response_obj.usage:
                u = response_obj.usage
                usage = {
                    "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(u, "total_tokens", 0) or 0,
                }

            # Latency
            latency_ms = 0
            if start_time and end_time:
                try:
                    delta = end_time - start_time
                    latency_ms = int(delta.total_seconds() * 1000)
                except (TypeError, AttributeError):
                    pass

            # Tool calls
            tool_call_names: list[str] = []
            if hasattr(response_obj, "choices") and response_obj.choices:
                choice = response_obj.choices[0]
                msg = getattr(choice, "message", None)
                if msg and getattr(msg, "tool_calls", None):
                    tool_call_names = [
                        tc.function.name
                        for tc in msg.tool_calls
                        if hasattr(tc, "function") and hasattr(tc.function, "name")
                    ]

            record = LLMCallRecord(
                model=model,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                latency_ms=latency_ms,
                tool_call_names=tool_call_names,
                timestamp=datetime.now(UTC),
            )
            self._calls.append(record)

        except Exception:
            # Never break the LLM call because of analytics
            logger.debug("token_analytics_callback_error", exc_info=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def install(self) -> None:
        """Register this callback with LiteLLM and set as active singleton."""
        global _active_callback
        if self not in litellm.callbacks:
            litellm.callbacks.append(self)  # type: ignore[arg-type]
        _active_callback = self

    def uninstall(self) -> None:
        """Remove this callback from LiteLLM."""
        global _active_callback
        if self in litellm.callbacks:
            litellm.callbacks.remove(self)  # type: ignore[arg-type]
        if _active_callback is self:
            _active_callback = None

    @property
    def calls(self) -> list[LLMCallRecord]:
        """Return all recorded LLM call records."""
        return list(self._calls)

    def build_summary(self) -> ExecutionTokenSummary:
        """Build an aggregated summary from all recorded calls."""
        return build_summary(self._calls)

    def reset(self) -> None:
        """Clear all recorded calls (e.g. between sessions)."""
        self._calls.clear()


def get_token_analytics() -> TokenAnalyticsCallback | None:
    """Return the active callback singleton, if installed."""
    return _active_callback
