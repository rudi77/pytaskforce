"""
Token Estimator Protocol Interface for Core Domain.

Defines the TokenEstimatorProtocol interface to abstract token counting,
allowing the Core domain to use different estimation strategies (heuristic
or tiktoken-based) without coupling to specific implementations.
"""

from typing import Protocol


class TokenEstimatorProtocol(Protocol):
    """Protocol for token counting strategies.

    Implementations can range from simple heuristics (chars/N) to
    accurate tokenizer-based counting (e.g., tiktoken).
    """

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string.

        Args:
            text: The text to count tokens for.

        Returns:
            Estimated or exact token count.
        """
        ...

    def count_message_overhead(self) -> int:
        """Overhead tokens per message (role, structure).

        Returns:
            Token count for per-message structural overhead.
        """
        ...

    def count_tool_schema_overhead(self) -> int:
        """Overhead tokens per tool definition.

        Returns:
            Token count for per-tool structural overhead.
        """
        ...

    def count_system_prompt_overhead(self) -> int:
        """Overhead tokens for system prompt structure.

        Returns:
            Token count for system prompt wrapping overhead.
        """
        ...
