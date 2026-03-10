"""
Heuristic Token Estimator - Calibrated character-based token estimation.

Provides a lightweight token counting strategy that uses empirically
calibrated constants. No external dependencies required.

Calibration notes (based on GPT-4/Claude tokenizer measurements):
- English text averages ~3.5-4.0 chars per token
- Code averages ~3.0-3.5 chars per token
- JSON/structured data averages ~3.0-3.5 chars per token
- We use 3.7 as a balanced default (slightly conservative)
- Message overhead is ~4 tokens per OpenAI/Anthropic spec
- Tool schema overhead is ~10-20 tokens for structural wrapping
- System prompt overhead is ~4 tokens for role wrapper
"""


class HeuristicTokenEstimator:
    """Calibrated heuristic token estimator.

    Uses character-count-based estimation with empirically tuned constants.
    Suitable for budget decisions where exact counts are not critical.
    """

    CHARS_PER_TOKEN = 3.7
    MESSAGE_OVERHEAD = 4
    TOOL_SCHEMA_OVERHEAD = 15
    SYSTEM_PROMPT_OVERHEAD = 10

    def count_tokens(self, text: str) -> int:
        """Count tokens using calibrated chars-per-token ratio.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count.
        """
        return int(len(text) / self.CHARS_PER_TOKEN)

    def count_message_overhead(self) -> int:
        """Per-message overhead (~4 tokens for role/structure).

        Returns:
            Message overhead token count.
        """
        return self.MESSAGE_OVERHEAD

    def count_tool_schema_overhead(self) -> int:
        """Per-tool-definition overhead (~15 tokens for wrapping).

        Returns:
            Tool schema overhead token count.
        """
        return self.TOOL_SCHEMA_OVERHEAD

    def count_system_prompt_overhead(self) -> int:
        """System prompt structural overhead (~10 tokens).

        Returns:
            System prompt overhead token count.
        """
        return self.SYSTEM_PROMPT_OVERHEAD
