"""Unit tests for the per-conversation action log (issue #157)."""

from __future__ import annotations

from taskforce.core.domain.action_log import (
    ActionLog,
    ActionRecord,
    TurnRecorder,
    format_action_log,
    format_footer,
)
from taskforce.core.domain.enums import EventType


def _tool_call(tool: str, *, call_id: str, args: dict | None = None) -> tuple[str, dict]:
    return EventType.TOOL_CALL.value, {
        "tool": tool,
        "id": call_id,
        "args": args or {},
    }


def _tool_result(
    tool: str,
    *,
    call_id: str,
    success: bool,
    error: str | None = None,
) -> tuple[str, dict]:
    return EventType.TOOL_RESULT.value, {
        "tool": tool,
        "id": call_id,
        "success": success,
        "error": error,
    }


class TestTurnRecorder:
    """``TurnRecorder`` collects tool_call/tool_result events into an ActionLog."""

    def test_records_matched_call_and_result(self) -> None:
        recorder = TurnRecorder(turn_index=0, user_message="Read the file")
        for event_type, data in [
            _tool_call("file_read", call_id="c1", args={"path": "x.txt"}),
            _tool_result("file_read", call_id="c1", success=True),
        ]:
            recorder.observe(event_type, data)

        log = recorder.finalize()
        assert log.turn_index == 0
        assert log.user_message == "Read the file"
        assert log.total == 1
        assert log.success_count == 1
        assert log.failure_count == 0
        record = log.records[0]
        assert record.tool_name == "file_read"
        assert record.success is True
        assert "x.txt" in record.args_summary
        assert record.duration_ms is not None and record.duration_ms >= 0

    def test_records_failure_with_error_message(self) -> None:
        recorder = TurnRecorder(turn_index=1, user_message="run python")
        for event_type, data in [
            _tool_call("python", call_id="c1"),
            _tool_result(
                "python",
                call_id="c1",
                success=False,
                error="ZeroDivisionError: division by zero",
            ),
        ]:
            recorder.observe(event_type, data)

        log = recorder.finalize()
        assert log.failure_count == 1
        assert log.records[0].success is False
        assert log.records[0].error is not None
        assert "ZeroDivisionError" in log.records[0].error

    def test_unmatched_call_marked_as_failed(self) -> None:
        """A tool_call without a matching tool_result becomes success=False."""
        recorder = TurnRecorder(turn_index=2, user_message="abort mid-flight")
        recorder.observe(*_tool_call("web_search", call_id="c1"))
        # No tool_result observed (e.g. execution interrupted).

        log = recorder.finalize()
        assert log.total == 1
        record = log.records[0]
        assert record.tool_name == "web_search"
        assert record.success is False
        assert record.error is not None
        assert record.duration_ms is None

    def test_multiple_calls_preserve_order(self) -> None:
        recorder = TurnRecorder(turn_index=3, user_message="multi-step")
        events = [
            _tool_call("a", call_id="1"),
            _tool_call("b", call_id="2"),
            _tool_result("b", call_id="2", success=True),
            _tool_result("a", call_id="1", success=False, error="boom"),
        ]
        for event_type, data in events:
            recorder.observe(event_type, data)

        log = recorder.finalize()
        assert [r.tool_name for r in log.records] == ["a", "b"]
        assert [r.success for r in log.records] == [False, True]

    def test_fallback_match_when_call_id_missing(self) -> None:
        """If results omit ``id``, FIFO match by tool name is used."""
        recorder = TurnRecorder(turn_index=4, user_message="legacy stream")
        recorder.observe(EventType.TOOL_CALL.value, {"tool": "grep", "args": {"pat": "x"}})
        recorder.observe(EventType.TOOL_RESULT.value, {"tool": "grep", "success": True})

        log = recorder.finalize()
        assert log.total == 1
        assert log.records[0].success is True

    def test_ignores_unrelated_event_types(self) -> None:
        recorder = TurnRecorder(turn_index=5, user_message="unrelated")
        recorder.observe(EventType.LLM_TOKEN.value, {"content": "hello"})
        recorder.observe(EventType.STEP_START.value, {"step": 1})
        log = recorder.finalize()
        assert log.total == 0


class TestFormatActionLog:
    """``format_action_log`` renders a human-readable summary."""

    def test_empty_log_returns_friendly_message(self) -> None:
        rendered = format_action_log(None)
        assert "No prior actions" in rendered

    def test_zero_record_log_returns_friendly_message(self) -> None:
        log = ActionLog(turn_index=0, user_message="test")
        rendered = format_action_log(log)
        assert "No prior actions" in rendered

    def test_single_success_record(self) -> None:
        log = ActionLog(
            turn_index=0,
            user_message="hello",
            records=[
                ActionRecord(
                    tool_name="file_read",
                    args_summary='{"path": "x.txt"}',
                    success=True,
                    duration_ms=42,
                ),
            ],
        )
        rendered = format_action_log(log)
        assert "1 tools" in rendered
        assert "1 ok" in rendered
        assert "0 fail" in rendered
        assert "[ok] file_read" in rendered
        assert "42 ms" in rendered

    def test_failure_record_shows_error(self) -> None:
        log = ActionLog(
            turn_index=0,
            user_message="hello",
            records=[
                ActionRecord(
                    tool_name="python",
                    args_summary="",
                    success=False,
                    error="syntax error",
                    duration_ms=5,
                ),
            ],
        )
        rendered = format_action_log(log)
        assert "[fail] python" in rendered
        assert "syntax error" in rendered

    def test_uses_ascii_markers_not_emoji(self) -> None:
        """Project rule: emoji are opt-in; the default formatter is ASCII."""
        log = ActionLog(
            turn_index=0,
            user_message="hi",
            records=[
                ActionRecord(tool_name="x", args_summary="", success=True),
                ActionRecord(tool_name="y", args_summary="", success=False),
            ],
        )
        rendered = format_action_log(log)
        # No checkmark or cross emoji should leak in.
        for forbidden in ("✓", "✗", "✅", "❌"):
            assert forbidden not in rendered


class TestFormatFooter:
    """``format_footer`` renders the optional outbound-reply footer."""

    def test_empty_log_yields_empty_string(self) -> None:
        assert format_footer(None) == ""
        assert format_footer(ActionLog(turn_index=0, user_message="x")) == ""

    def test_summary_counts(self) -> None:
        log = ActionLog(
            turn_index=0,
            user_message="hi",
            records=[
                ActionRecord(tool_name="a", args_summary="", success=True),
                ActionRecord(tool_name="b", args_summary="", success=True),
                ActionRecord(tool_name="c", args_summary="", success=False),
            ],
        )
        footer = format_footer(log)
        assert footer.startswith("\n\n")
        assert "3 tools" in footer
        assert "2 ok" in footer
        assert "1 fail" in footer

    def test_singular_tool_label(self) -> None:
        log = ActionLog(
            turn_index=0,
            user_message="hi",
            records=[
                ActionRecord(tool_name="a", args_summary="", success=True),
            ],
        )
        footer = format_footer(log)
        # "1 tool" without trailing 's', not "1 tools".
        assert "1 tool " in footer
        assert "1 tools" not in footer
