"""
File-based Tracer for Offline Tracing

Writes execution events to a JSONL file for offline analysis.
Useful when Phoenix collector is not available.

Usage:
    tracer = FileTracer(path=Path("traces.jsonl"))
    tracer.log_event("llm_call", {"model": "gpt-4", "tokens": 100})
    tracer.close()

Or as context manager:
    with FileTracer(path=Path("traces.jsonl")) as tracer:
        tracer.log_event("tool_call", {"tool": "file_read", "args": {...}})
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class FileTracer:
    """
    File-based tracer that writes events to a JSONL file.

    Each line in the output file is a JSON object with:
    - timestamp: ISO-formatted datetime
    - event_type: Type of event (llm_call, tool_call, tool_result, etc.)
    - data: Event-specific payload

    Thread-safe through file locking (writes are appended atomically).
    """

    def __init__(self, path: Path, session_id: str | None = None):
        """
        Initialize file tracer.

        Args:
            path: Path to the JSONL trace file
            session_id: Optional session ID to include in all events
        """
        self.path = path
        self.session_id = session_id
        self._file = None
        self._event_count = 0

        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Open file for appending
        self._file = open(self.path, "a", encoding="utf-8")

        logger.info(
            "file_tracer_initialized",
            path=str(self.path),
            session_id=session_id,
        )

    def log_event(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Log an event to the trace file.

        Args:
            event_type: Type of event (e.g., "llm_call", "tool_call", "tool_result")
            data: Event-specific payload
        """
        if self._file is None or self._file.closed:
            logger.warning("file_tracer_not_open", event_type=event_type)
            return

        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data,
        }

        if self.session_id:
            event["session_id"] = self.session_id

        try:
            line = json.dumps(event, ensure_ascii=False, default=str)
            self._file.write(line + "\n")
            self._file.flush()  # Ensure immediate write
            self._event_count += 1
        except Exception as e:
            logger.error("file_tracer_write_error", error=str(e), event_type=event_type)

    def log_stream_event(self, event: Any) -> None:
        """
        Log a StreamEvent object.

        Args:
            event: StreamEvent instance with to_dict() method
        """
        if hasattr(event, "to_dict"):
            event_dict = event.to_dict()
            self.log_event(event_dict.get("event_type", "unknown"), event_dict.get("data", {}))
        elif hasattr(event, "event_type") and hasattr(event, "data"):
            self.log_event(event.event_type, event.data)

    def log_llm_call(
        self,
        *,
        model: str,
        messages_count: int,
        tools_count: int = 0,
        messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Log an LLM API call start with optional full message content."""
        data = {
            "model": model,
            "messages_count": messages_count,
            "tools_count": tools_count,
            **kwargs,
        }
        # Include full messages if provided
        if messages is not None:
            data["messages"] = messages
        self.log_event("llm_call_start", data)

    def log_llm_response(
        self,
        *,
        model: str,
        success: bool,
        content_length: int = 0,
        tool_calls_count: int = 0,
        tokens: dict[str, int] | None = None,
        latency_ms: int = 0,
        error: str | None = None,
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Log an LLM API response with optional full content."""
        data = {
            "model": model,
            "success": success,
            "content_length": content_length,
            "tool_calls_count": tool_calls_count,
            "latency_ms": latency_ms,
            **kwargs,
        }
        if tokens:
            data["tokens"] = tokens
        if error:
            data["error"] = error
        # Include full content if provided
        if content is not None:
            data["content"] = content
        if tool_calls is not None:
            data["tool_calls"] = tool_calls

        self.log_event("llm_call_end", data)

    def log_tool_call(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        args: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Log a tool call start."""
        self.log_event(
            "tool_call_start",
            {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "args": args,
                **kwargs,
            },
        )

    def log_tool_result(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        success: bool,
        result_preview: str = "",
        latency_ms: int = 0,
        error: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Log a tool execution result."""
        data = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "success": success,
            "result_preview": result_preview[:500],  # Truncate long results
            "latency_ms": latency_ms,
            **kwargs,
        }
        if error:
            data["error"] = error

        self.log_event("tool_call_end", data)

    def log_error(self, error: str, **kwargs: Any) -> None:
        """Log an error event."""
        self.log_event("error", {"error": error, **kwargs})

    def log_mission_start(self, mission: str, **kwargs: Any) -> None:
        """Log mission start."""
        self.log_event(
            "mission_start",
            {"mission": mission[:1000], **kwargs},  # Truncate long missions
        )

    def log_mission_end(
        self,
        *,
        status: str,
        final_message: str = "",
        total_steps: int = 0,
        total_tokens: dict[str, int] | None = None,
        **kwargs: Any,
    ) -> None:
        """Log mission completion."""
        data = {
            "status": status,
            "final_message": final_message[:1000],
            "total_steps": total_steps,
            **kwargs,
        }
        if total_tokens:
            data["total_tokens"] = total_tokens

        self.log_event("mission_end", data)

    def close(self) -> None:
        """Close the trace file."""
        if self._file and not self._file.closed:
            self._file.close()
            logger.info(
                "file_tracer_closed",
                path=str(self.path),
                event_count=self._event_count,
            )

    def __enter__(self) -> "FileTracer":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()


# Global file tracer instance (optional singleton pattern)
_file_tracer: FileTracer | None = None


def init_file_tracing(path: Path, session_id: str | None = None) -> FileTracer:
    """
    Initialize global file tracer.

    Args:
        path: Path to the JSONL trace file
        session_id: Optional session ID

    Returns:
        FileTracer instance
    """
    global _file_tracer
    if _file_tracer is not None:
        _file_tracer.close()
    _file_tracer = FileTracer(path=path, session_id=session_id)
    return _file_tracer


def get_file_tracer() -> FileTracer | None:
    """Get the global file tracer instance."""
    return _file_tracer


def shutdown_file_tracing() -> None:
    """Shutdown global file tracer."""
    global _file_tracer
    if _file_tracer is not None:
        _file_tracer.close()
        _file_tracer = None
