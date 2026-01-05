"""Lifecycle helpers for Agent resources."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import structlog


class ResourceCloser:
    """Close async resources associated with Agent."""

    def __init__(self, *, logger: structlog.stdlib.BoundLogger) -> None:
        self._logger = logger

    async def close_mcp_contexts(self, contexts: Iterable[Any]) -> None:
        """Close MCP client contexts safely."""
        for ctx in contexts:
            try:
                await ctx.__aexit__(None, None, None)
            except Exception as error:
                self._logger.warning("mcp_context_close_failed", error=str(error))
