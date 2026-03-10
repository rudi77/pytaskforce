"""
Tiktoken-based Token Estimator - Accurate token counting.

Uses the tiktoken library for precise token counting. Requires the
optional ``tokenizer`` dependency group (``uv sync --extra tokenizer``).

Falls back gracefully if tiktoken is not installed — callers should
catch ``ImportError`` and use the heuristic estimator instead.
"""


class TiktokenEstimator:
    """Accurate token estimator using tiktoken.

    Provides exact token counts for OpenAI-compatible models.
    For non-OpenAI models the counts are still a good approximation
    since most modern LLM tokenizers produce similar token counts.
    """

    def __init__(self, model: str = "gpt-4") -> None:
        """Initialize with a model-specific tokenizer.

        Args:
            model: Model name for encoding selection (default: gpt-4).

        Raises:
            ImportError: If tiktoken is not installed.
        """
        import tiktoken

        try:
            self._encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            # Unknown model, fall back to cl100k_base (GPT-4 family)
            self._encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken encoding.

        Args:
            text: The text to count tokens for.

        Returns:
            Exact token count for the configured model.
        """
        return len(self._encoding.encode(text))

    def count_message_overhead(self) -> int:
        """Per-message overhead (exact per OpenAI spec).

        Returns:
            Message overhead token count (4).
        """
        return 4

    def count_tool_schema_overhead(self) -> int:
        """Per-tool-definition overhead (measured empirically).

        Returns:
            Tool schema overhead token count (10).
        """
        return 10

    def count_system_prompt_overhead(self) -> int:
        """System prompt structural overhead.

        Returns:
            System prompt overhead token count (4).
        """
        return 4
