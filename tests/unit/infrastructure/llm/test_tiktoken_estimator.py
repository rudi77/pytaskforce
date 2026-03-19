"""
Unit tests for TiktokenEstimator.

Tests cover:
- __init__: default model, known model, unknown model fallback, missing tiktoken
- count_tokens: normal text, empty string, special characters, long text, unicode
- count_message_overhead: returns 4
- count_tool_schema_overhead: returns 10
- count_system_prompt_overhead: returns 4

Tiktoken is mocked to avoid network calls for downloading encoding data.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from taskforce.infrastructure.llm.tiktoken_estimator import TiktokenEstimator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_mock_tiktoken(*, raise_on_model: bool = False) -> MagicMock:
    """Build a mock tiktoken module with a shared encoding object.

    Args:
        raise_on_model: If True, encoding_for_model raises KeyError.
    """
    encoding = MagicMock()
    # Default: encode returns a list whose length equals the string length.
    # Tests that need a specific return value override return_value AND
    # clear side_effect so the override takes effect.
    encoding.encode.side_effect = lambda text: list(range(len(text))) if text else []

    mock_module = MagicMock()
    if raise_on_model:
        mock_module.encoding_for_model.side_effect = KeyError("unknown")
    else:
        mock_module.encoding_for_model.return_value = encoding
    mock_module.get_encoding.return_value = encoding
    mock_module._encoding = encoding  # stash for test access
    return mock_module


@pytest.fixture()
def mock_tiktoken():
    """Patch tiktoken module; encoding_for_model succeeds."""
    mock_module = _build_mock_tiktoken()
    with patch.dict("sys.modules", {"tiktoken": mock_module}):
        yield mock_module


@pytest.fixture()
def mock_tiktoken_unknown():
    """Patch tiktoken module; encoding_for_model raises KeyError."""
    mock_module = _build_mock_tiktoken(raise_on_model=True)
    with patch.dict("sys.modules", {"tiktoken": mock_module}):
        yield mock_module


def _set_encode_return(encoding: MagicMock, value: list) -> None:
    """Override encode to return a fixed value (clears side_effect)."""
    encoding.encode.side_effect = None
    encoding.encode.return_value = value


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInit:
    """Tests for TiktokenEstimator initialization."""

    def test_default_model(self, mock_tiktoken) -> None:
        """Default model (gpt-4) initializes using encoding_for_model."""
        TiktokenEstimator()
        mock_tiktoken.encoding_for_model.assert_called_once_with("gpt-4")

    def test_custom_model(self, mock_tiktoken) -> None:
        """Custom model name is passed to encoding_for_model."""
        TiktokenEstimator(model="gpt-3.5-turbo")
        mock_tiktoken.encoding_for_model.assert_called_once_with("gpt-3.5-turbo")

    def test_unknown_model_falls_back_to_cl100k(self, mock_tiktoken_unknown) -> None:
        """Unknown model falls back to cl100k_base encoding."""
        TiktokenEstimator(model="totally-unknown-xyz")
        mock_tiktoken_unknown.encoding_for_model.assert_called_once_with("totally-unknown-xyz")
        mock_tiktoken_unknown.get_encoding.assert_called_once_with("cl100k_base")

    def test_import_error_when_tiktoken_missing(self) -> None:
        """Raises ImportError when tiktoken is not installed."""
        with patch.dict("sys.modules", {"tiktoken": None}):
            with pytest.raises(ImportError):
                TiktokenEstimator()


# ---------------------------------------------------------------------------
# count_tokens
# ---------------------------------------------------------------------------


class TestCountTokens:
    """Tests for count_tokens method."""

    def test_delegates_to_encode(self, mock_tiktoken) -> None:
        """count_tokens calls encoding.encode and returns its length."""
        encoding = mock_tiktoken._encoding
        _set_encode_return(encoding, [10, 20, 30])
        estimator = TiktokenEstimator()
        assert estimator.count_tokens("Hello, world!") == 3
        encoding.encode.assert_called_with("Hello, world!")

    def test_empty_string(self, mock_tiktoken) -> None:
        """Empty string produces zero tokens."""
        estimator = TiktokenEstimator()
        assert estimator.count_tokens("") == 0

    def test_whitespace_only(self, mock_tiktoken) -> None:
        """Whitespace-only string is passed to encode as-is."""
        encoding = mock_tiktoken._encoding
        _set_encode_return(encoding, [1, 2])
        estimator = TiktokenEstimator()
        assert estimator.count_tokens("   \n\t  ") == 2

    def test_single_character(self, mock_tiktoken) -> None:
        """Single character produces one token."""
        encoding = mock_tiktoken._encoding
        _set_encode_return(encoding, [42])
        estimator = TiktokenEstimator()
        assert estimator.count_tokens("a") == 1

    def test_special_characters(self, mock_tiktoken) -> None:
        """Special characters are passed through to encode."""
        encoding = mock_tiktoken._encoding
        _set_encode_return(encoding, [1, 2, 3, 4, 5])
        estimator = TiktokenEstimator()
        text = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        assert estimator.count_tokens(text) == 5
        encoding.encode.assert_called_with(text)

    def test_unicode_text(self, mock_tiktoken) -> None:
        """Unicode text is passed through to encode."""
        encoding = mock_tiktoken._encoding
        _set_encode_return(encoding, [1, 2, 3, 4, 5, 6])
        estimator = TiktokenEstimator()
        text = "Hello \u4e16\u754c \U0001f600 \u00e9\u00e0\u00fc"
        assert estimator.count_tokens(text) == 6

    def test_long_text(self, mock_tiktoken) -> None:
        """Long text returns token count equal to len of encode result."""
        encoding = mock_tiktoken._encoding
        _set_encode_return(encoding, list(range(500)))
        estimator = TiktokenEstimator()
        assert estimator.count_tokens("x" * 2000) == 500

    def test_return_type_is_int(self, mock_tiktoken) -> None:
        """count_tokens always returns an int."""
        encoding = mock_tiktoken._encoding
        _set_encode_return(encoding, [1, 2])
        estimator = TiktokenEstimator()
        assert isinstance(estimator.count_tokens("test"), int)

    def test_deterministic(self, mock_tiktoken) -> None:
        """Same input always produces the same token count."""
        estimator = TiktokenEstimator()
        text = "The quick brown fox"
        assert estimator.count_tokens(text) == estimator.count_tokens(text)

    def test_code_snippet(self, mock_tiktoken) -> None:
        """Code text is passed to encode without modification."""
        encoding = mock_tiktoken._encoding
        _set_encode_return(encoding, [1, 2, 3, 4, 5, 6, 7, 8])
        estimator = TiktokenEstimator()
        code = "def foo(x: int) -> int:\n    return x + 1"
        assert estimator.count_tokens(code) == 8
        encoding.encode.assert_called_with(code)

    def test_multiline_text(self, mock_tiktoken) -> None:
        """Multiline text is passed as a single string."""
        encoding = mock_tiktoken._encoding
        _set_encode_return(encoding, [1, 2, 3, 4])
        estimator = TiktokenEstimator()
        text = "line1\nline2\nline3"
        assert estimator.count_tokens(text) == 4
        encoding.encode.assert_called_with(text)

    def test_unknown_model_count_tokens(self, mock_tiktoken_unknown) -> None:
        """Estimator with fallback encoding still counts tokens correctly."""
        encoding = mock_tiktoken_unknown._encoding
        _set_encode_return(encoding, [1, 2])
        estimator = TiktokenEstimator(model="nonexistent-model")
        assert estimator.count_tokens("hello") == 2

    def test_very_long_string(self, mock_tiktoken) -> None:
        """Very long string (100k chars) is handled without error."""
        estimator = TiktokenEstimator()
        text = "a" * 100_000
        # Default side_effect returns list of len(text) items
        result = estimator.count_tokens(text)
        assert result == 100_000

    def test_newlines_and_tabs(self, mock_tiktoken) -> None:
        """Strings with mixed whitespace are tokenized."""
        encoding = mock_tiktoken._encoding
        _set_encode_return(encoding, [1, 2, 3])
        estimator = TiktokenEstimator()
        assert estimator.count_tokens("\t\n\r") == 3

    def test_emoji_text(self, mock_tiktoken) -> None:
        """Emoji characters are passed through to encode."""
        encoding = mock_tiktoken._encoding
        _set_encode_return(encoding, [1, 2, 3])
        estimator = TiktokenEstimator()
        assert estimator.count_tokens("\U0001f600\U0001f680\u2764") == 3


# ---------------------------------------------------------------------------
# Overhead methods
# ---------------------------------------------------------------------------


class TestOverheads:
    """Tests for fixed overhead methods."""

    def test_message_overhead(self, mock_tiktoken) -> None:
        """Per-message overhead is 4."""
        assert TiktokenEstimator().count_message_overhead() == 4

    def test_tool_schema_overhead(self, mock_tiktoken) -> None:
        """Per-tool-definition overhead is 10."""
        assert TiktokenEstimator().count_tool_schema_overhead() == 10

    def test_system_prompt_overhead(self, mock_tiktoken) -> None:
        """System prompt structural overhead is 4."""
        assert TiktokenEstimator().count_system_prompt_overhead() == 4

    def test_overhead_return_types(self, mock_tiktoken) -> None:
        """All overhead methods return int."""
        estimator = TiktokenEstimator()
        assert isinstance(estimator.count_message_overhead(), int)
        assert isinstance(estimator.count_tool_schema_overhead(), int)
        assert isinstance(estimator.count_system_prompt_overhead(), int)
