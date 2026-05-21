"""Tests for tool-call event emission in LiteLLMService streaming path.

Regression tests for issue #155 (Telegram action gap):

When a streaming provider front-loads ``arguments`` in the first delta and
only emits ``id`` / ``name`` in a later delta, the previous implementation
of :meth:`LiteLLMService._process_tool_call_delta` skipped the
``tool_call_start`` event entirely. The downstream ReAct loop only entered
a tool call into its accumulator on a ``tool_call_start`` event, so the
matching ``tool_call_delta`` and ``tool_call_end`` events were silently
dropped — the agent would commit to an action in chat but the tool never
ran. These tests pin the regression so we never re-introduce it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from taskforce.infrastructure.llm.litellm_service import LiteLLMService


@pytest.fixture
def temp_config_file(tmp_path):
    """Minimal LLM config for streaming tests."""
    config = {
        "default_model": "main",
        "models": {"main": "gpt-4.1"},
        "model_params": {"gpt-4.1": {"temperature": 0.2, "max_tokens": 2000}},
        "default_params": {"temperature": 0.7, "max_tokens": 2000},
        "retry": {"max_attempts": 3, "backoff_multiplier": 2, "timeout": 30},
        "logging": {"log_token_usage": True},
    }
    config_path = tmp_path / "llm_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return str(config_path)


def _make_chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
    chunk = MagicMock()
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls if tool_calls else None
    chunk.choices = [MagicMock(delta=delta, finish_reason=finish_reason)]
    chunk.usage = usage
    return chunk


def _make_tc(index, *, tool_id=None, name=None, arguments=None):
    tc = MagicMock()
    tc.index = index
    # Set ``id`` to a real None when not provided so ``getattr(tc, 'id', None)``
    # in the parser returns None instead of an auto-generated MagicMock.
    tc.id = tool_id

    if name is not None or arguments is not None:
        tc.function = MagicMock()
        tc.function.name = name
        tc.function.arguments = arguments
    else:
        tc.function = None
    return tc


async def _stream(chunks):
    for chunk in chunks:
        yield chunk


@pytest.mark.spec("llm-service.stream_tool_call_start_emits_after_id_or_name_known")
@pytest.mark.asyncio
async def test_tool_call_start_emitted_when_id_arrives_after_arguments(
    temp_config_file,
):
    """Provider sends arguments first, id+name in a later delta.

    The fix must emit ``tool_call_start`` once the id/name become known so
    the downstream ReAct loop registers the tool call in its accumulator
    and the matching ``tool_call_end`` actually fires the tool.
    """
    service = LiteLLMService(config_path=temp_config_file)

    # Chunk 1: first delta has only arguments fragment, no id, no name.
    # Chunk 2: id + name arrive late.
    # Chunk 3: rest of arguments.
    # Chunk 4: finish_reason → tool_call_end synthesised.
    chunks = [
        _make_chunk(tool_calls=[_make_tc(0, tool_id=None, name=None, arguments='{"loc')]),
        _make_chunk(tool_calls=[_make_tc(0, tool_id="call_late", name="calendar_create")]),
        _make_chunk(tool_calls=[_make_tc(0, tool_id=None, name=None, arguments='ation":"home"}')]),
        _make_chunk(finish_reason="tool_calls"),
    ]

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _stream(chunks)
        events = []
        async for event in service.complete_stream(
            messages=[{"role": "user", "content": "Book a meeting"}],
            model="main",
        ):
            events.append(event)

    starts = [e for e in events if e["type"] == "tool_call_start"]
    ends = [e for e in events if e["type"] == "tool_call_end"]

    # Exactly one tool_call_start, carrying the id/name that arrived late.
    assert len(starts) == 1, f"expected one tool_call_start, got {starts}"
    assert starts[0]["id"] == "call_late"
    assert starts[0]["name"] == "calendar_create"
    assert starts[0]["index"] == 0

    # tool_call_end should still fire and carry the full arguments.
    assert len(ends) == 1
    assert ends[0]["id"] == "call_late"
    assert ends[0]["name"] == "calendar_create"
    assert ends[0]["arguments"] == '{"location":"home"}'


@pytest.mark.asyncio
async def test_tool_call_start_not_double_emitted(temp_config_file):
    """Once ``tool_call_start`` is emitted for an index, subsequent deltas
    that re-state the same id/name must NOT re-emit start.
    """
    service = LiteLLMService(config_path=temp_config_file)

    chunks = [
        _make_chunk(tool_calls=[_make_tc(0, tool_id="call_1", name="get_weather")]),
        # Same id/name re-stated in a later delta — should not produce a 2nd start.
        _make_chunk(
            tool_calls=[
                _make_tc(0, tool_id="call_1", name="get_weather", arguments='{"city":"NYC"}')
            ]
        ),
        _make_chunk(finish_reason="tool_calls"),
    ]

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _stream(chunks)
        events = []
        async for event in service.complete_stream(
            messages=[{"role": "user", "content": "Weather"}],
            model="main",
        ):
            events.append(event)

    starts = [e for e in events if e["type"] == "tool_call_start"]
    assert len(starts) == 1, f"start emitted multiple times: {starts}"


@pytest.mark.asyncio
async def test_arguments_preserved_when_id_arrives_late(temp_config_file):
    """The first delta's argument fragment must not be lost when the id /
    name arrive in a later delta. Without the fix the accumulator was reset.
    """
    service = LiteLLMService(config_path=temp_config_file)

    chunks = [
        # Front-loaded arguments, no id/name yet.
        _make_chunk(tool_calls=[_make_tc(0, arguments='{"a":1')]),
        _make_chunk(tool_calls=[_make_tc(0, tool_id="call_x", name="do_thing")]),
        _make_chunk(tool_calls=[_make_tc(0, arguments=',"b":2}')]),
        _make_chunk(finish_reason="tool_calls"),
    ]

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _stream(chunks)
        events = []
        async for event in service.complete_stream(
            messages=[{"role": "user", "content": "..."}],
            model="main",
        ):
            events.append(event)

    end = next(e for e in events if e["type"] == "tool_call_end")
    assert end["arguments"] == '{"a":1,"b":2}'
    assert end["id"] == "call_x"
    assert end["name"] == "do_thing"
