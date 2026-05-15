"""Verify the agent translates content-filter aborts into a user message.

Before this fix, an Azure ContentPolicyViolationError ended up as
``final_message=""`` in the COMPLETE event, which the gateway then
swapped for the generic ``"Bei der Bearbeitung ist leider ein Problem
aufgetreten"`` line. The user had no clue that Azure had blocked the
prompt or how to recover.

These tests pin two contracts:

* :func:`build_user_message_for_error` returns a content-filter-specific
  German message when ``error_kind == "content_filter"``.
* :class:`LeanAgent.execute_stream` consumes the structured ERROR event
  and emits a COMPLETE event whose ``final_message`` carries that
  message — never an empty string when an error was observed.
"""

from __future__ import annotations

from typing import Any

import pytest

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning.react_loop import build_user_message_for_error


# ---------------------------------------------------------------------------
# build_user_message_for_error
# ---------------------------------------------------------------------------


def test_content_filter_kind_returns_specific_message() -> None:
    msg = build_user_message_for_error("content_filter", "Azure rejected prompt")

    # Substantive German text — not the gateway's generic fallback.
    assert "Inhaltsfilter" in msg
    assert "blockiert" in msg
    # The actionable hint: when recovery fails the user should see at
    # least one concrete next step. ``/compact`` is the cheapest fix
    # because it shrinks the conversation in place; the Azure Foundry
    # tip kicks in when the user's data itself trips the filter (PII
    # on customer records etc.).
    assert "/compact" in msg or "Azure" in msg


def test_unknown_kind_falls_back_to_wrapped_error() -> None:
    msg = build_user_message_for_error("", "upstream timeout")

    assert "upstream timeout" in msg
    assert "noch einmal" in msg


def test_no_error_uses_generic_message() -> None:
    msg = build_user_message_for_error("", "")

    assert "keine Antwort" in msg


# ---------------------------------------------------------------------------
# LeanAgent.execute_stream — propagation through the COMPLETE event
# ---------------------------------------------------------------------------


class _FakeContentFilterStrategy:
    """Planning strategy stub that immediately yields a content-filter ERROR."""

    async def execute_stream(self, _agent: Any, _mission: str, _session_id: str):
        yield StreamEvent(
            event_type=EventType.ERROR,
            data={
                "message": (
                    "LLM call rejected (content_filter): "
                    "litellm.ContentPolicyViolationError. Aborting to "
                    "avoid retrying the same blocked request."
                ),
                "error_kind": "content_filter",
                "non_retryable": True,
            },
        )


@pytest.mark.asyncio
async def test_execute_stream_complete_event_carries_user_message(monkeypatch) -> None:
    agent = LeanAgent.__new__(LeanAgent)
    agent.planning_strategy = _FakeContentFilterStrategy()  # type: ignore[assignment]

    async def _noop(*_args, **_kwargs) -> None:
        return None

    # execute_stream calls record_heartbeat + mark_finished; stub them out
    # so the test stays focused on the event-translation contract instead
    # of the full agent runtime wiring.
    agent.record_heartbeat = _noop  # type: ignore[method-assign]
    agent.mark_finished = _noop  # type: ignore[method-assign]

    events = []
    async for evt in agent.execute_stream(
        mission="Recherchiere Körpergröße deutscher Männer",
        session_id="test-session",
    ):
        events.append(evt)

    # First event is the ERROR, last event is COMPLETE — pin both.
    assert events[0].event_type == EventType.ERROR
    complete = events[-1]
    assert complete.event_type == EventType.COMPLETE
    assert complete.data["status"] == "failed"
    assert complete.data["error_kind"] == "content_filter"

    final_message = complete.data["final_message"]
    assert final_message  # never empty when an error happened
    assert "Inhaltsfilter" in final_message
    # Must NOT be the generic gateway fallback.
    assert "Bei der Bearbeitung" not in final_message
