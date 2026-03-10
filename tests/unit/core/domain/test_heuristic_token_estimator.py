"""Unit tests for HeuristicTokenEstimator."""

from taskforce.core.domain.heuristic_token_estimator import HeuristicTokenEstimator


class TestHeuristicTokenEstimator:
    """Test suite for HeuristicTokenEstimator."""

    def test_count_tokens_empty_string(self):
        """Empty string yields zero tokens."""
        estimator = HeuristicTokenEstimator()
        assert estimator.count_tokens("") == 0

    def test_count_tokens_known_text(self):
        """Token count uses calibrated 3.7 chars-per-token ratio."""
        estimator = HeuristicTokenEstimator()
        text = "a" * 37  # 37 chars / 3.7 = 10 tokens
        assert estimator.count_tokens(text) == 10

    def test_count_tokens_shorter_text(self):
        """Short text produces a reasonable estimate."""
        estimator = HeuristicTokenEstimator()
        text = "Hello, world!"  # 13 chars → int(13/3.7) = 3
        assert estimator.count_tokens(text) == 3

    def test_count_tokens_long_text(self):
        """Long text estimate is proportional."""
        estimator = HeuristicTokenEstimator()
        text = "x" * 3700
        assert estimator.count_tokens(text) == 1000

    def test_message_overhead(self):
        """Message overhead returns calibrated value."""
        estimator = HeuristicTokenEstimator()
        assert estimator.count_message_overhead() == 4

    def test_tool_schema_overhead(self):
        """Tool schema overhead returns calibrated value."""
        estimator = HeuristicTokenEstimator()
        assert estimator.count_tool_schema_overhead() == 15

    def test_system_prompt_overhead(self):
        """System prompt overhead returns calibrated value."""
        estimator = HeuristicTokenEstimator()
        assert estimator.count_system_prompt_overhead() == 10

    def test_satisfies_protocol(self):
        """HeuristicTokenEstimator satisfies TokenEstimatorProtocol."""
        from taskforce.core.interfaces.token_estimator import TokenEstimatorProtocol

        estimator = HeuristicTokenEstimator()
        # Structural subtyping: check all protocol methods exist and work
        assert isinstance(estimator.count_tokens("test"), int)
        assert isinstance(estimator.count_message_overhead(), int)
        assert isinstance(estimator.count_tool_schema_overhead(), int)
        assert isinstance(estimator.count_system_prompt_overhead(), int)

        # Also check runtime_checkable if needed (Protocol is not runtime_checkable
        # by default, so just verify duck typing works)
        proto: TokenEstimatorProtocol = estimator  # noqa: F841 - type check
