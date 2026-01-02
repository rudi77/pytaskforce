"""
Unit tests for TokenBudgeter.

Tests token estimation, budget enforcement, and message sanitization.
"""

import pytest

from taskforce.core.domain.token_budgeter import TokenBudgeter


class TestTokenBudgeter:
    """Test suite for TokenBudgeter class."""

    def test_initialization_defaults(self):
        """Test TokenBudgeter initializes with default values."""
        budgeter = TokenBudgeter()

        assert budgeter.max_input_tokens == TokenBudgeter.DEFAULT_MAX_INPUT_TOKENS
        assert (
            budgeter.compression_trigger
            == TokenBudgeter.DEFAULT_COMPRESSION_TRIGGER
        )

    def test_initialization_custom_values(self):
        """Test TokenBudgeter initializes with custom values."""
        budgeter = TokenBudgeter(
            max_input_tokens=50000,
            compression_trigger=40000,
        )

        assert budgeter.max_input_tokens == 50000
        assert budgeter.compression_trigger == 40000

    def test_estimate_tokens_simple_messages(self):
        """Test token estimation for simple text messages."""
        budgeter = TokenBudgeter()

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing well, thank you!"},
        ]

        estimated = budgeter.estimate_tokens(messages)

        # Should have some tokens (system overhead + message overhead + content)
        assert estimated > 0
        # Should be reasonable (not millions)
        assert estimated < 1000

    def test_estimate_tokens_with_tools(self):
        """Test token estimation includes tool schemas."""
        budgeter = TokenBudgeter()

        messages = [
            {"role": "system", "content": "System prompt"},
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {
                        "type": "object",
                        "properties": {"arg": {"type": "string"}},
                    },
                },
            }
        ]

        estimated_without_tools = budgeter.estimate_tokens(messages)
        estimated_with_tools = budgeter.estimate_tokens(messages, tools=tools)

        # With tools should be higher
        assert estimated_with_tools > estimated_without_tools

    def test_estimate_tokens_with_context_pack(self):
        """Test token estimation includes context pack."""
        budgeter = TokenBudgeter()

        messages = [
            {"role": "system", "content": "System prompt"},
        ]

        context_pack = "This is additional context information."

        estimated_without_context = budgeter.estimate_tokens(messages)
        estimated_with_context = budgeter.estimate_tokens(
            messages, context_pack=context_pack
        )

        # With context should be higher
        assert estimated_with_context > estimated_without_context

    def test_estimate_tokens_with_tool_calls(self):
        """Test token estimation includes tool calls in messages."""
        budgeter = TokenBudgeter()

        messages = [
            {"role": "system", "content": "System prompt"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "test_tool",
                            "arguments": '{"arg": "value"}',
                        },
                    }
                ],
            },
        ]

        estimated = budgeter.estimate_tokens(messages)

        # Should account for tool call
        assert estimated > 100

    def test_is_over_budget_false(self):
        """Test is_over_budget returns False for small prompts."""
        budgeter = TokenBudgeter(max_input_tokens=10000)

        messages = [
            {"role": "system", "content": "Short prompt"},
        ]

        assert not budgeter.is_over_budget(messages)

    def test_is_over_budget_true(self):
        """Test is_over_budget returns True for large prompts."""
        budgeter = TokenBudgeter(max_input_tokens=100)

        # Create a large message
        large_content = "x" * 10000  # ~2500 tokens
        messages = [
            {"role": "system", "content": large_content},
        ]

        assert budgeter.is_over_budget(messages)

    def test_should_compress_false(self):
        """Test should_compress returns False below trigger."""
        budgeter = TokenBudgeter(compression_trigger=10000)

        messages = [
            {"role": "system", "content": "Short prompt"},
        ]

        assert not budgeter.should_compress(messages)

    def test_should_compress_true(self):
        """Test should_compress returns True above trigger."""
        budgeter = TokenBudgeter(compression_trigger=100)

        # Create a large message
        large_content = "x" * 10000  # ~2500 tokens
        messages = [
            {"role": "system", "content": large_content},
        ]

        assert budgeter.should_compress(messages)

    def test_sanitize_message_short_content(self):
        """Test sanitize_message leaves short content unchanged."""
        budgeter = TokenBudgeter()

        message = {
            "role": "user",
            "content": "This is a short message.",
        }

        sanitized = budgeter.sanitize_message(message)

        assert sanitized["content"] == message["content"]

    def test_sanitize_message_long_content(self):
        """Test sanitize_message truncates long content."""
        budgeter = TokenBudgeter()

        long_content = "x" * 100000  # Exceeds MAX_MESSAGE_CONTENT_CHARS
        message = {
            "role": "user",
            "content": long_content,
        }

        sanitized = budgeter.sanitize_message(message)

        # Should be truncated
        assert len(sanitized["content"]) < len(long_content)
        assert "SANITIZED" in sanitized["content"]

    def test_sanitize_message_custom_max_chars(self):
        """Test sanitize_message with custom max_chars."""
        budgeter = TokenBudgeter()

        message = {
            "role": "user",
            "content": "x" * 1000,
        }

        sanitized = budgeter.sanitize_message(message, max_chars=500)

        # Should be truncated to 500 + truncation message
        assert len(sanitized["content"]) < 1000
        assert "SANITIZED" in sanitized["content"]

    def test_sanitize_message_preserves_role(self):
        """Test sanitize_message preserves message role and structure."""
        budgeter = TokenBudgeter()

        message = {
            "role": "assistant",
            "content": "Some content",
            "extra_field": "extra_value",
        }

        sanitized = budgeter.sanitize_message(message)

        assert sanitized["role"] == "assistant"
        assert "extra_field" in sanitized

    def test_sanitize_message_with_tool_calls(self):
        """Test sanitize_message handles tool_calls."""
        budgeter = TokenBudgeter()

        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "test_tool",
                        "arguments": "x" * 100000,  # Very long arguments
                    },
                }
            ],
        }

        sanitized = budgeter.sanitize_message(message, max_chars=1000)

        # Tool call arguments should be truncated
        args = sanitized["tool_calls"][0]["function"]["arguments"]
        assert len(args) < 100000
        assert "SANITIZED" in args

    def test_sanitize_messages_list(self):
        """Test sanitize_messages processes list of messages."""
        budgeter = TokenBudgeter()

        messages = [
            {"role": "user", "content": "x" * 100000},
            {"role": "assistant", "content": "y" * 100000},
        ]

        sanitized = budgeter.sanitize_messages(messages)

        assert len(sanitized) == 2
        # Both should be truncated
        assert "SANITIZED" in sanitized[0]["content"]
        assert "SANITIZED" in sanitized[1]["content"]

    def test_extract_tool_output_preview_success(self):
        """Test extract_tool_output_preview for successful result."""
        budgeter = TokenBudgeter()

        tool_result = {
            "success": True,
            "output": "This is the tool output.",
        }

        preview = budgeter.extract_tool_output_preview(tool_result)

        assert "Success: True" in preview
        assert "Output: This is the tool output." in preview

    def test_extract_tool_output_preview_error(self):
        """Test extract_tool_output_preview for error result."""
        budgeter = TokenBudgeter()

        tool_result = {
            "success": False,
            "error": "Something went wrong",
        }

        preview = budgeter.extract_tool_output_preview(tool_result)

        assert "Success: False" in preview
        assert "Error: Something went wrong" in preview

    def test_extract_tool_output_preview_truncates_long_output(self):
        """Test extract_tool_output_preview truncates long outputs."""
        budgeter = TokenBudgeter()

        long_output = "x" * 50000
        tool_result = {
            "success": True,
            "output": long_output,
        }

        preview = budgeter.extract_tool_output_preview(
            tool_result, max_chars=1000
        )

        # Should be truncated
        assert len(preview) < len(long_output)
        assert "..." in preview

    def test_extract_tool_output_preview_with_handle(self):
        """Test extract_tool_output_preview includes handle reference."""
        budgeter = TokenBudgeter()

        tool_result = {
            "success": True,
            "output": "Some output",
            "handle": {"id": "handle_123"},
        }

        preview = budgeter.extract_tool_output_preview(tool_result)

        assert "Handle: handle_123" in preview

    def test_get_budget_stats(self):
        """Test get_budget_stats returns comprehensive statistics."""
        budgeter = TokenBudgeter(
            max_input_tokens=10000,
            compression_trigger=8000,
        )

        messages = [
            {"role": "system", "content": "x" * 1000},
        ]

        stats = budgeter.get_budget_stats(messages)

        # Should have all expected fields
        assert "estimated_tokens" in stats
        assert "max_tokens" in stats
        assert "remaining_tokens" in stats
        assert "utilization_percent" in stats
        assert "over_budget" in stats
        assert "should_compress" in stats
        assert "compression_trigger" in stats

        # Values should be reasonable
        assert stats["max_tokens"] == 10000
        assert stats["compression_trigger"] == 8000
        assert stats["estimated_tokens"] > 0
        assert stats["remaining_tokens"] >= 0
        assert 0 <= stats["utilization_percent"] <= 100

    def test_get_budget_stats_over_budget(self):
        """Test get_budget_stats correctly identifies over budget."""
        budgeter = TokenBudgeter(max_input_tokens=100)

        large_content = "x" * 10000
        messages = [
            {"role": "system", "content": large_content},
        ]

        stats = budgeter.get_budget_stats(messages)

        assert stats["over_budget"] is True
        assert stats["utilization_percent"] > 100

    def test_get_budget_stats_should_compress(self):
        """Test get_budget_stats correctly identifies compression trigger."""
        budgeter = TokenBudgeter(
            max_input_tokens=10000,
            compression_trigger=100,
        )

        messages = [
            {"role": "system", "content": "x" * 1000},
        ]

        stats = budgeter.get_budget_stats(messages)

        assert stats["should_compress"] is True

