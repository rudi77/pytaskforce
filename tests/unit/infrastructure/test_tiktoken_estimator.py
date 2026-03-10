"""Unit tests for TiktokenEstimator.

These tests require the optional tiktoken dependency.
They are automatically skipped if tiktoken is not installed.
"""

import pytest

tiktoken = pytest.importorskip("tiktoken", reason="tiktoken not installed")

try:
    from taskforce.infrastructure.llm.tiktoken_estimator import TiktokenEstimator  # noqa: E402

    # Force encoding download check at import time
    TiktokenEstimator()
    _TIKTOKEN_AVAILABLE = True
except Exception:
    _TIKTOKEN_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _TIKTOKEN_AVAILABLE,
    reason="tiktoken encoding download not available (network issue)",
)


class TestTiktokenEstimator:
    """Test suite for TiktokenEstimator."""

    def test_count_tokens_empty_string(self):
        """Empty string yields zero tokens."""
        estimator = TiktokenEstimator()
        assert estimator.count_tokens("") == 0

    def test_count_tokens_known_text(self):
        """Token count for a known string is accurate."""
        estimator = TiktokenEstimator()
        # "Hello, world!" is a well-known test string
        tokens = estimator.count_tokens("Hello, world!")
        assert tokens > 0
        # Should be around 4 tokens for GPT-4 tokenizer
        assert 2 <= tokens <= 6

    def test_count_tokens_longer_text(self):
        """Longer text produces proportionally more tokens."""
        estimator = TiktokenEstimator()
        short_count = estimator.count_tokens("Hello")
        long_count = estimator.count_tokens("Hello " * 100)
        assert long_count > short_count

    def test_message_overhead(self):
        """Message overhead is 4 (per OpenAI spec)."""
        estimator = TiktokenEstimator()
        assert estimator.count_message_overhead() == 4

    def test_tool_schema_overhead(self):
        """Tool schema overhead is 10."""
        estimator = TiktokenEstimator()
        assert estimator.count_tool_schema_overhead() == 10

    def test_system_prompt_overhead(self):
        """System prompt overhead is 4."""
        estimator = TiktokenEstimator()
        assert estimator.count_system_prompt_overhead() == 4

    def test_unknown_model_falls_back(self):
        """Unknown model name falls back to cl100k_base encoding."""
        estimator = TiktokenEstimator(model="unknown-model-xyz")
        tokens = estimator.count_tokens("Hello, world!")
        assert tokens > 0

    def test_satisfies_protocol(self):
        """TiktokenEstimator satisfies TokenEstimatorProtocol."""
        from taskforce.core.interfaces.token_estimator import TokenEstimatorProtocol

        estimator = TiktokenEstimator()
        proto: TokenEstimatorProtocol = estimator  # noqa: F841 - type check
        assert isinstance(estimator.count_tokens("test"), int)
