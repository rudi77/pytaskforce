"""Tests for ``_build_retry_nudge`` approval-aware branching.

Issue #190 sub-item (a): when a tool fails because approval was
denied or timed out, the LLM must NOT be nudged into retrying the
same or an equivalent action. Instead the nudge must instruct it to
surface the refusal to the user.
"""

from __future__ import annotations

from taskforce.core.domain.planning.utils import _build_retry_nudge


def test_default_nudge_when_no_error_kinds_known() -> None:
    """Without error_kinds info, the existing retry-style nudge runs."""
    msg = _build_retry_nudge(["calendar_create"], attempt=1)
    assert msg["role"] == "user"
    text = msg["content"]
    assert "Try a different tool or approach" in text
    assert "calendar_create" in text
    # Default nudge must NOT mention approval / denial — that would be
    # misleading when the failure was, say, a 500 from the calendar API.
    assert "denied" not in text.lower()
    assert "permitted" not in text.lower()


def test_approval_denied_nudge_tells_llm_to_surface_refusal() -> None:
    """When the failure was approval_denied, the LLM must be told to
    surface the refusal — NOT to retry with a different tool."""
    msg = _build_retry_nudge(
        ["calendar_create"],
        attempt=1,
        error_kinds={"calendar_create": "approval_denied"},
    )
    text = msg["content"]
    assert "denied" in text.lower()
    assert "calendar_create" in text
    assert "Do NOT retry" in text
    # The current "Try a different tool or approach" wording would
    # encourage the LLM to call e.g. shell to achieve the same end —
    # the bug we're fixing. Make sure the default nudge text is gone.
    assert "Try a different tool or approach" not in text
    assert "alternatives" not in text.lower()


def test_approval_timeout_nudge_uses_timeout_label() -> None:
    """A timeout is not the user actively refusing, but functionally
    we still don't want a retry without explicit user input."""
    msg = _build_retry_nudge(
        ["shell"],
        attempt=1,
        error_kinds={"shell": "approval_timeout"},
    )
    text = msg["content"]
    assert "timed out" in text.lower()
    assert "Do NOT retry" in text


def test_mixed_failure_with_approval_still_uses_approval_nudge() -> None:
    """If at least one tool was approval-blocked, the approval nudge
    wins even when other tools failed for non-approval reasons —
    retrying anything that touches the forbidden domain is the bug."""
    msg = _build_retry_nudge(
        ["calendar_create", "shell"],
        attempt=1,
        error_kinds={
            "calendar_create": "approval_denied",
            "shell": "exec_failed",
        },
    )
    text = msg["content"]
    assert "denied" in text.lower()
    assert "calendar_create" in text
    # The non-approval tool isn't named in the approval branch — the
    # message focuses on the refused action so the LLM doesn't reach
    # for the still-permitted-looking shell to do the same thing.
    assert "Do NOT retry" in text


def test_repeated_default_failure_unaffected_by_approval_logic() -> None:
    """On attempt>=2 without any approval failures, the existing
    "STOP retrying" branch still runs."""
    msg = _build_retry_nudge(["web_search"], attempt=3)
    text = msg["content"]
    assert "STOP retrying" in text
    assert "attempt 3" in text
