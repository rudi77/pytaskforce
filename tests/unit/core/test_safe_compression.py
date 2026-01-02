"""
Unit tests for Safe Compression in LeanAgent.

Tests that compression does NOT use raw JSON dumps and respects budget constraints.
"""

import json

import pytest

from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.core.domain.token_budgeter import TokenBudgeter


class MockStateManager:
    """Mock state manager for testing."""

    async def load_state(self, session_id: str):
        return {}

    async def save_state(self, session_id: str, state: dict):
        pass


class MockLLMProvider:
    """Mock LLM provider for testing compression."""

    def __init__(self, summary_response: str = "Summary of conversation."):
        self.summary_response = summary_response
        self.last_prompt = None

    async def complete(self, messages, model=None, **kwargs):
        # Capture the prompt for inspection
        if messages:
            self.last_prompt = messages[0].get("content", "")

        return {
            "success": True,
            "content": self.summary_response,
        }


class TestSafeCompression:
    """Test suite for safe compression without raw dumps."""

    def test_compress_messages_no_raw_json_dumps(self):
        """
        CRITICAL TEST: Ensure _compress_messages does NOT use
        json.dumps(old_messages, indent=2) in the summary prompt.
        """
        # Setup
        mock_llm = MockLLMProvider()
        agent = LeanAgent(
            state_manager=MockStateManager(),
            llm_provider=mock_llm,
            tools=[],
        )

        # Create messages that would trigger compression
        messages = [
            {"role": "system", "content": "System prompt"},
        ]

        # Add many messages to trigger compression
        for i in range(25):
            messages.append(
                {
                    "role": "user",
                    "content": f"User message {i}",
                }
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": f"Assistant response {i}",
                }
            )

        # Run compression (async)
        import asyncio

        compressed = asyncio.run(agent._compress_messages(messages))

        # Verify: The LLM prompt should NOT contain raw JSON dump
        assert mock_llm.last_prompt is not None

        # Check that prompt does NOT contain the pattern from old implementation
        # Old pattern: json.dumps(old_messages, indent=2)
        # This would create indented JSON like:
        # [
        #   {
        #     "role": "user",
        #     ...
        assert '"role":' not in mock_llm.last_prompt or (
            # If role appears, it should be in a safe format (not raw JSON array)
            mock_llm.last_prompt.count('"role":') < 5
        )

        # Verify: Prompt should use safe format with message previews
        assert "[Message" in mock_llm.last_prompt

    def test_compress_messages_uses_safe_summary_input(self):
        """Test that compression uses _build_safe_summary_input."""
        mock_llm = MockLLMProvider()
        agent = LeanAgent(
            state_manager=MockStateManager(),
            llm_provider=mock_llm,
            tools=[],
        )

        # Create messages with tool results
        messages = [
            {"role": "system", "content": "System prompt"},
        ]

        for i in range(25):
            messages.append(
                {
                    "role": "user",
                    "content": f"User message {i}",
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "name": "test_tool",
                    "content": json.dumps(
                        {
                            "success": True,
                            "output": f"Tool output {i}" * 100,  # Large output
                        }
                    ),
                }
            )

        import asyncio

        compressed = asyncio.run(agent._compress_messages(messages))

        # Verify: Prompt should contain safe previews, not raw outputs
        assert mock_llm.last_prompt is not None
        assert "[Message" in mock_llm.last_prompt
        assert "Tool:" in mock_llm.last_prompt

        # Should NOT contain the full raw tool output repeated 100 times
        # The preview is capped at MAX_TOOL_OUTPUT_CHARS (20000), so we should
        # see significantly fewer repetitions than the original 100 * 25 messages
        assert mock_llm.last_prompt.count("Tool output") < 2000

    def test_build_safe_summary_input_sanitizes_content(self):
        """Test _build_safe_summary_input sanitizes large content."""
        agent = LeanAgent(
            state_manager=MockStateManager(),
            llm_provider=MockLLMProvider(),
            tools=[],
        )

        # Create messages with very large content
        messages = [
            {
                "role": "user",
                "content": "x" * 100000,  # 100k chars
            },
            {
                "role": "assistant",
                "content": "y" * 100000,  # 100k chars
            },
        ]

        summary_input = agent._build_safe_summary_input(messages)

        # Verify: Summary input should be much smaller than raw content
        assert len(summary_input) < 10000  # Should be capped

        # Verify: Should contain message markers
        assert "[Message 1" in summary_input
        assert "[Message 2" in summary_input

    def test_build_safe_summary_input_handles_tool_calls(self):
        """Test _build_safe_summary_input extracts tool names only."""
        agent = LeanAgent(
            state_manager=MockStateManager(),
            llm_provider=MockLLMProvider(),
            tools=[],
        )

        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "test_tool_1",
                            "arguments": json.dumps(
                                {"arg": "x" * 10000}
                            ),  # Large args
                        },
                    },
                    {
                        "id": "call_456",
                        "type": "function",
                        "function": {
                            "name": "test_tool_2",
                            "arguments": json.dumps({"arg": "y" * 10000}),
                        },
                    },
                ],
            }
        ]

        summary_input = agent._build_safe_summary_input(messages)

        # Verify: Should contain tool names
        assert "test_tool_1" in summary_input
        assert "test_tool_2" in summary_input

        # Verify: Should NOT contain full arguments (10k x's)
        assert summary_input.count("x") < 100

    def test_build_safe_summary_input_handles_tool_results(self):
        """Test _build_safe_summary_input creates previews for tool results."""
        agent = LeanAgent(
            state_manager=MockStateManager(),
            llm_provider=MockLLMProvider(),
            tools=[],
        )

        messages = [
            {
                "role": "tool",
                "name": "test_tool",
                "content": json.dumps(
                    {
                        "success": True,
                        "output": "x" * 50000,  # Very large output
                    }
                ),
            }
        ]

        summary_input = agent._build_safe_summary_input(messages)

        # Verify: Should contain tool name and preview
        assert "test_tool" in summary_input
        assert "Success: True" in summary_input

        # Verify: Should NOT contain full output (50k x's)
        # The preview is capped at MAX_TOOL_OUTPUT_CHARS (20000)
        assert summary_input.count("x") < 25000  # Should be close to 20k, not 50k

    def test_compression_triggered_by_budget(self):
        """Test compression is triggered by budget, not just message count."""
        mock_llm = MockLLMProvider()

        # Create agent with low compression trigger
        agent = LeanAgent(
            state_manager=MockStateManager(),
            llm_provider=mock_llm,
            tools=[],
            compression_trigger=100,  # Very low trigger
        )

        # Create just a few messages with large content
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "x" * 10000},  # Large message
            {"role": "assistant", "content": "y" * 10000},  # Large message
        ]

        import asyncio

        compressed = asyncio.run(agent._compress_messages(messages))

        # Verify: Compression should have been triggered by budget
        # even though message count is low (only 3 messages)
        assert len(compressed) < len(messages) or mock_llm.last_prompt is not None

    def test_compression_respects_message_count_fallback(self):
        """Test compression still respects SUMMARY_THRESHOLD as fallback."""
        mock_llm = MockLLMProvider()

        agent = LeanAgent(
            state_manager=MockStateManager(),
            llm_provider=mock_llm,
            tools=[],
        )

        # Create many small messages (exceeds count threshold but not budget)
        messages = [
            {"role": "system", "content": "System prompt"},
        ]

        for i in range(25):  # Exceeds SUMMARY_THRESHOLD (20)
            messages.append({"role": "user", "content": f"Message {i}"})

        import asyncio

        compressed = asyncio.run(agent._compress_messages(messages))

        # Verify: Compression should have been triggered by message count
        assert mock_llm.last_prompt is not None

    def test_compression_fallback_on_llm_failure(self):
        """Test compression falls back to truncation if LLM fails."""

        class FailingLLMProvider:
            async def complete(self, messages, model=None, **kwargs):
                return {"success": False, "error": "LLM failed"}

        agent = LeanAgent(
            state_manager=MockStateManager(),
            llm_provider=FailingLLMProvider(),
            tools=[],
        )

        messages = [
            {"role": "system", "content": "System prompt"},
        ]

        for i in range(25):
            messages.append({"role": "user", "content": f"Message {i}"})

        import asyncio

        compressed = asyncio.run(agent._compress_messages(messages))

        # Verify: Should have fallen back to simple truncation
        assert len(compressed) < len(messages)
        # Should keep system prompt
        assert compressed[0]["role"] == "system"

    def test_no_compression_when_below_threshold(self):
        """Test no compression when below both budget and count thresholds."""
        mock_llm = MockLLMProvider()

        agent = LeanAgent(
            state_manager=MockStateManager(),
            llm_provider=mock_llm,
            tools=[],
        )

        # Create few small messages
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        import asyncio

        compressed = asyncio.run(agent._compress_messages(messages))

        # Verify: No compression should have occurred
        assert len(compressed) == len(messages)
        assert mock_llm.last_prompt is None  # LLM not called

    def test_safe_summary_input_handles_malformed_tool_content(self):
        """Test _build_safe_summary_input handles non-JSON tool content."""
        agent = LeanAgent(
            state_manager=MockStateManager(),
            llm_provider=MockLLMProvider(),
            tools=[],
        )

        messages = [
            {
                "role": "tool",
                "name": "test_tool",
                "content": "This is not JSON",  # Malformed
            }
        ]

        # Should not raise exception
        summary_input = agent._build_safe_summary_input(messages)

        # Verify: Should handle gracefully
        assert "test_tool" in summary_input
        assert "This is not JSON" in summary_input

    def test_safe_summary_input_empty_messages(self):
        """Test _build_safe_summary_input handles empty message list."""
        agent = LeanAgent(
            state_manager=MockStateManager(),
            llm_provider=MockLLMProvider(),
            tools=[],
        )

        summary_input = agent._build_safe_summary_input([])

        # Should return empty or minimal output
        assert isinstance(summary_input, str)
        assert len(summary_input) == 0

