"""
Context Policy Model

Defines budgeting policies for context pack construction. The policy
ensures that context packs stay within token limits by enforcing hard
caps on item counts, character limits, and total size.

Key Concepts:
- ContextPolicy: Configuration for context pack budgeting
- Hard caps prevent unbounded context growth
- Configuration-driven behavior (no hardcoded limits)
"""

from dataclasses import dataclass, field


@dataclass
class ContextPolicy:
    """
    Configuration for context pack budgeting.

    This policy defines hard limits for context pack construction,
    ensuring that LLM calls stay within token budgets. All limits
    are enforced deterministically by the ContextBuilder.

    Attributes:
        max_items: Maximum number of items in context pack
        max_chars_per_item: Maximum characters per individual item
        max_total_chars: Maximum total characters across all items
        include_latest_tool_previews_n: Number of latest tool previews to include
        allow_tools: Optional whitelist of tool names to include (None = all)
        allow_selectors: Optional list of selector types to use (future feature)
        deduplicate_visible_window: Number of recent messages to check for
            deduplication. Tool previews already visible in this window are
            skipped from the context pack. Set to 0 to disable. Default: 10.
    """

    max_items: int = 6  # AutoOptim: reduced from 10 for less context overhead
    max_chars_per_item: int = 300  # AutoOptim: reduced from 500
    max_total_chars: int = 1800  # AutoOptim: reduced from 3000
    include_latest_tool_previews_n: int = 3  # AutoOptim: reduced from 5
    allow_tools: list[str] | None = None
    allow_selectors: list[str] | None = field(default_factory=lambda: ["first_chars"])
    deduplicate_visible_window: int = 10

    def __post_init__(self) -> None:
        """Validate policy constraints."""
        if self.max_items <= 0:
            raise ValueError("max_items must be positive")
        if self.max_chars_per_item <= 0:
            raise ValueError("max_chars_per_item must be positive")
        if self.max_total_chars <= 0:
            raise ValueError("max_total_chars must be positive")
        if self.include_latest_tool_previews_n < 0:
            raise ValueError("include_latest_tool_previews_n must be non-negative")
        if self.deduplicate_visible_window < 0:
            raise ValueError("deduplicate_visible_window must be non-negative")

        # Ensure max_total_chars is achievable given per-item limit
        if self.max_chars_per_item * self.max_items < self.max_total_chars:
            # Adjust max_total_chars to be achievable
            self.max_total_chars = self.max_chars_per_item * self.max_items

    def is_tool_allowed(self, tool_name: str) -> bool:
        """
        Check if a tool is allowed by this policy.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is allowed (whitelist is None or tool in whitelist)
        """
        if self.allow_tools is None:
            return True
        return tool_name in self.allow_tools

    @classmethod
    def conservative_default(cls) -> "ContextPolicy":
        """
        Create a conservative default policy.

        This policy is used when no explicit policy is configured.
        It provides a small budget to prevent context explosion.

        Returns:
            ContextPolicy with conservative limits
        """
        return cls(
            max_items=5,
            max_chars_per_item=300,
            max_total_chars=1500,
            include_latest_tool_previews_n=3,
            allow_tools=None,
            allow_selectors=["first_chars"],
        )

    @classmethod
    def from_dict(cls, data: dict) -> "ContextPolicy":
        """
        Create policy from configuration dictionary.

        Args:
            data: Configuration dictionary (e.g., from YAML)

        Returns:
            ContextPolicy instance
        """
        return cls(
            max_items=data.get("max_items", 6),
            max_chars_per_item=data.get("max_chars_per_item", 300),
            max_total_chars=data.get("max_total_chars", 1800),
            include_latest_tool_previews_n=data.get("include_latest_tool_previews_n", 3),
            allow_tools=data.get("allow_tools"),
            allow_selectors=data.get("allow_selectors", ["first_chars"]),
            deduplicate_visible_window=data.get("deduplicate_visible_window", 10),
        )

    def to_dict(self) -> dict:
        """
        Convert policy to dictionary for serialization.

        Returns:
            Dictionary representation of policy
        """
        return {
            "max_items": self.max_items,
            "max_chars_per_item": self.max_chars_per_item,
            "max_total_chars": self.max_total_chars,
            "include_latest_tool_previews_n": self.include_latest_tool_previews_n,
            "allow_tools": self.allow_tools,
            "allow_selectors": self.allow_selectors,
            "deduplicate_visible_window": self.deduplicate_visible_window,
        }
