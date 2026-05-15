"""Tests for ``_salvage_answer`` content-filter tagging.

When every salvage attempt is rejected by an Azure/OpenAI content
filter, the function used to return an empty string indistinguishable
from any other failure. The react-loop caller then emitted an ERROR
event without an ``error_kind`` tag, which made the gateway fall back
to the generic "no answer available" message instead of the actionable
German content-filter recovery hint from ADR-025.

The fix returns ``(answer, content_filter_blocked: bool)`` so the
caller can tag ``error_kind="content_filter"`` on the ERROR event.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.planning.llm_interactions import (
    _looks_like_content_filter,
    _salvage_answer,
)


def _make_agent(side_effects: list[Any]) -> Any:
    """Stub Agent whose ``llm_provider.complete`` returns / raises the supplied sequence.

    Each element is either a dict (success case — yielded as the result)
    or an Exception (raised). The list is consumed in order, one entry
    per call.
    """
    iterator = iter(side_effects)

    async def _complete(**kwargs: Any) -> dict[str, Any]:
        nxt = next(iterator)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt

    agent = MagicMock()
    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=_complete)
    return agent


def test_looks_like_content_filter_recognises_azure_message() -> None:
    """The keyword detector must match real Azure error strings."""
    err = Exception(
        "litellm.BadRequestError: litellm.ContentPolicyViolationError: "
        "litellm.ContentPolicyViolationError: AzureException - The response "
        "was filtered due to the prompt triggering Azure OpenAI's content manage"
    )
    assert _looks_like_content_filter(err)


def test_looks_like_content_filter_ignores_unrelated_errors() -> None:
    """Other transient failures (rate-limit, timeout) must not be tagged."""
    assert not _looks_like_content_filter(Exception("rate_limit_exceeded"))
    assert not _looks_like_content_filter(Exception("timeout after 30s"))
    assert not _looks_like_content_filter(Exception("connection refused"))


@pytest.mark.asyncio
async def test_returns_answer_and_false_on_success() -> None:
    """Happy path: first attempt yields content → return (answer, False)."""
    agent = _make_agent([{"content": "Hier ist die Antwort."}])
    logger = MagicMock()

    answer, blocked = await _salvage_answer(agent, [], logger)

    assert answer == "Hier ist die Antwort."
    assert blocked is False
    assert agent.llm_provider.complete.await_count == 1


@pytest.mark.asyncio
async def test_returns_empty_and_true_when_all_attempts_content_filtered() -> None:
    """Both summarizing + reasoning hits content filter → flag is set."""
    agent = _make_agent(
        [
            Exception("litellm.ContentPolicyViolationError: filtered prompt"),
            Exception("AzureException - content_filter triggered"),
        ]
    )
    logger = MagicMock()

    answer, blocked = await _salvage_answer(agent, [], logger)

    assert answer == ""
    assert blocked is True, "content_filter rejections must be reported to caller"
    # Both model hints should be tried before giving up.
    assert agent.llm_provider.complete.await_count == 2


@pytest.mark.asyncio
async def test_returns_empty_and_false_for_non_content_filter_failure() -> None:
    """Generic failures (rate-limit, timeout) must NOT set the flag."""
    agent = _make_agent(
        [
            Exception("rate_limit_exceeded"),
            Exception("connection reset"),
        ]
    )
    logger = MagicMock()

    answer, blocked = await _salvage_answer(agent, [], logger)

    assert answer == ""
    assert blocked is False, "non-content-filter failures must NOT trigger the flag"


@pytest.mark.asyncio
async def test_first_attempt_filtered_second_succeeds_returns_false() -> None:
    """If one attempt was filtered but another produced content, do not flag."""
    agent = _make_agent(
        [
            Exception("ContentPolicyViolationError: filtered"),
            {"content": "Recovered answer."},
        ]
    )
    logger = MagicMock()

    answer, blocked = await _salvage_answer(agent, [], logger)

    assert answer == "Recovered answer."
    assert blocked is False, "successful fallback overrides the earlier filter hit"
