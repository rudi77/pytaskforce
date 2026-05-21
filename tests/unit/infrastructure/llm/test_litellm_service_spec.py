"""Spec-coverage tests for LiteLLMService (docs/spec/llm-service.md).

These exercise the provider-agnostic service with ``litellm.acompletion``
mocked, so they run without API keys or network. Markers tie each test to
a claim in the spec's *Tests* section.
"""

from __future__ import annotations

import importlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from taskforce.infrastructure.llm.litellm_service import LiteLLMService

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path):
    """Minimal llm_config.yaml — two aliases, layered params, fast retry."""
    config = {
        "default_model": "main",
        "models": {"main": "gpt-4.1", "fast": "gpt-4.1-mini"},
        # Keyed by the resolved model string — model layer overrides default.
        "model_params": {"gpt-4.1": {"temperature": 0.2, "max_tokens": 100}},
        "default_params": {"temperature": 0.7, "max_tokens": 2000},
        "retry": {"max_attempts": 3, "backoff_multiplier": 2, "timeout": 1},
        "logging": {"log_token_usage": True},
    }
    path = tmp_path / "llm_config.yaml"
    path.write_text(yaml.dump(config), encoding="utf-8")
    return str(path)


def _completion_response(content="ok", *, total=30, prompt=20, completion=10):
    """Build a mock non-streaming ``litellm.acompletion`` response."""
    message = MagicMock()
    message.content = content
    message.tool_calls = None
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    response.model = "gpt-4.1"
    response.usage = MagicMock(
        total_tokens=total, prompt_tokens=prompt, completion_tokens=completion
    )
    return response


def _stream_chunk(content=None, finish_reason=None):
    chunk = MagicMock()
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = None
    chunk.choices = [MagicMock(delta=delta, finish_reason=finish_reason)]
    chunk.usage = None
    return chunk


async def _astream(chunks):
    for chunk in chunks:
        yield chunk


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.spec("llm-service.complete_returns_error_dict_on_provider_exception")
@pytest.mark.asyncio
async def test_complete_returns_error_dict_on_provider_exception(config_file):
    """A provider exception is never raised to the caller of complete() —
    it is returned as a {success: false, error, error_type, model} dict."""
    service = LiteLLMService(config_path=config_file)

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
        # Non-retryable (auth keyword) → single attempt, no backoff wait.
        mock_completion.side_effect = Exception("invalid api key")
        result = await service.complete(
            messages=[{"role": "user", "content": "hi"}], model="main"
        )

    assert result["success"] is False
    assert "invalid api key" in result["error"]
    assert result["error_type"] == "Exception"
    assert result["model"] == "gpt-4.1"
    mock_completion.assert_awaited_once()


@pytest.mark.spec("llm-service.retry_exponential_backoff_until_max_attempts")
@pytest.mark.asyncio
async def test_retry_exponential_backoff_until_max_attempts(config_file):
    """A retryable error is retried up to retry.max_attempts with
    backoff_multiplier ** attempt seconds between attempts."""
    service = LiteLLMService(config_path=config_file)

    with (
        patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_completion.side_effect = Exception("503 service unavailable")
        result = await service.complete(
            messages=[{"role": "user", "content": "hi"}], model="main"
        )

    # max_attempts=3 → three calls, two backoff waits between them.
    assert mock_completion.await_count == 3
    backoffs = [c.args[0] for c in mock_sleep.await_args_list]
    assert backoffs == [1, 2]  # backoff_multiplier(2) ** attempt: 2**0, 2**1
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Model alias resolution + parameter merge
# ---------------------------------------------------------------------------


@pytest.mark.spec("llm-service.model_alias_resolves_via_models_map")
@pytest.mark.asyncio
async def test_model_alias_resolves_via_models_map(config_file):
    """A known alias is resolved to its mapped provider model string."""
    service = LiteLLMService(config_path=config_file)

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _completion_response()
        await service.complete(
            messages=[{"role": "user", "content": "hi"}], model="main"
        )

    assert mock_completion.call_args.kwargs["model"] == "gpt-4.1"


@pytest.mark.spec("llm-service.unknown_alias_passes_through_as_literal_model")
@pytest.mark.asyncio
async def test_unknown_alias_passes_through_as_literal_model(config_file):
    """An alias absent from the models map is passed to LiteLLM verbatim."""
    service = LiteLLMService(config_path=config_file)

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _completion_response()
        await service.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="anthropic/claude-haiku-4-5",
        )

    assert mock_completion.call_args.kwargs["model"] == "anthropic/claude-haiku-4-5"


@pytest.mark.spec("llm-service.model_params_merge_order_default_then_model_then_kwargs")
@pytest.mark.asyncio
async def test_model_params_merge_order_default_then_model_then_kwargs(config_file):
    """Params merge default → model → caller kwargs (later wins)."""
    service = LiteLLMService(config_path=config_file)

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _completion_response()

        # No caller kwarg → model_params override default_params.
        await service.complete(
            messages=[{"role": "user", "content": "hi"}], model="main"
        )
        kwargs = mock_completion.call_args.kwargs
        assert kwargs["temperature"] == 0.2   # model (0.2) wins over default (0.7)
        assert kwargs["max_tokens"] == 100    # model (100) wins over default (2000)

        # Caller kwarg → overrides the model layer.
        mock_completion.reset_mock()
        await service.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="main",
            temperature=0.99,
        )
        assert mock_completion.call_args.kwargs["temperature"] == 0.99


@pytest.mark.spec("llm-service.usage_dict_present_on_successful_complete")
@pytest.mark.asyncio
async def test_usage_dict_present_on_successful_complete(config_file):
    """Every successful complete() result carries a usage dict."""
    service = LiteLLMService(config_path=config_file)

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _completion_response(
            content="done", total=30, prompt=20, completion=10
        )
        result = await service.complete(
            messages=[{"role": "user", "content": "hi"}], model="main"
        )

    assert result["success"] is True
    assert isinstance(result["usage"], dict)
    assert result["usage"]["total_tokens"] == 30
    assert result["usage"]["prompt_tokens"] == 20
    assert result["usage"]["completion_tokens"] == 10


# ---------------------------------------------------------------------------
# Azure env-var auto-mapping (module-import-time behaviour)
# ---------------------------------------------------------------------------


@pytest.mark.spec("llm-service.azure_openai_env_vars_are_auto_mapped")
def test_azure_openai_env_vars_are_auto_mapped():
    """``AZURE_OPENAI_*`` env vars are mapped to LiteLLM's ``AZURE_*`` names
    when the module is imported."""
    from taskforce.infrastructure.llm import litellm_service as mod

    keys = (
        "AZURE_API_KEY",
        "AZURE_API_BASE",
        "AZURE_API_VERSION",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_VERSION",
    )
    saved = {k: os.environ.get(k) for k in keys}
    try:
        for k in ("AZURE_API_KEY", "AZURE_API_BASE", "AZURE_API_VERSION"):
            os.environ.pop(k, None)
        os.environ["AZURE_OPENAI_API_KEY"] = "secret-key"
        os.environ["AZURE_OPENAI_ENDPOINT"] = "https://example.openai.azure.com"
        os.environ["AZURE_OPENAI_API_VERSION"] = "2024-10-01"

        importlib.reload(mod)

        assert os.environ["AZURE_API_KEY"] == "secret-key"
        assert os.environ["AZURE_API_BASE"] == "https://example.openai.azure.com/"
        assert os.environ["AZURE_API_VERSION"] == "2024-10-01"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        # Reload once more with the original env restored so the cached
        # module is left in a clean state for other tests.
        importlib.reload(mod)


# ---------------------------------------------------------------------------
# Streaming — per-chunk timeout
# ---------------------------------------------------------------------------


@pytest.mark.spec("llm-service.stream_chunk_timeout_yields_error_event")
@pytest.mark.asyncio
async def test_stream_chunk_timeout_yields_error_event(config_file):
    """A mid-stream stall yields an `error` event instead of hanging."""
    service = LiteLLMService(config_path=config_file)

    chunks = [_stream_chunk(content="Hello"), _stream_chunk(finish_reason="stop")]

    state = {"calls": 0}

    async def fake_wait_for(awaitable, timeout):
        state["calls"] += 1
        if state["calls"] == 1:
            return await awaitable  # first chunk arrives normally
        awaitable.close()  # second chunk: simulate a stall
        raise TimeoutError

    with (
        patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion,
        patch("asyncio.wait_for", side_effect=fake_wait_for),
    ):
        mock_completion.return_value = _astream(chunks)
        events = []
        async for event in service.complete_stream(
            messages=[{"role": "user", "content": "hi"}], model="main"
        ):
            events.append(event)

    assert events[-1]["type"] == "error"
    assert "Stream timed out" in events[-1]["message"]


# ---------------------------------------------------------------------------
# complete_json
# ---------------------------------------------------------------------------


@pytest.mark.spec("llm-service.complete_json_returns_parsed_data_on_success")
@pytest.mark.asyncio
async def test_complete_json_returns_parsed_data_on_success(config_file):
    """complete_json parses a valid JSON response into {success, data}."""
    service = LiteLLMService(config_path=config_file)

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _completion_response(
            content='{"answer": 42, "ok": true}'
        )
        result = await service.complete_json(
            prompt="Return a JSON object.", model="main"
        )

    assert result["success"] is True
    assert result["data"] == {"answer": 42, "ok": True}


@pytest.mark.spec("llm-service.complete_json_returns_parse_error_on_invalid_json")
@pytest.mark.asyncio
async def test_complete_json_returns_parse_error_on_invalid_json(config_file):
    """complete_json returns a structured parse-error dict for non-JSON output."""
    service = LiteLLMService(config_path=config_file)

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _completion_response(content="this is not json")
        result = await service.complete_json(
            prompt="Return a JSON object.", model="main"
        )

    assert result["success"] is False
    assert result["error_type"] == "JSONDecodeError"
    assert result["raw_content"] == "this is not json"
