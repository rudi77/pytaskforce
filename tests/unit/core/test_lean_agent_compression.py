"""
Unit Tests for LeanAgent Message History Compression

Tests the improved message compression logic with LLM-based summarization.
"""

import json
from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.core.tools.planner_tool import PlannerTool


@pytest.fixture
def mock_state_manager():
    """Mock StateManagerProtocol."""
    mock = AsyncMock()
    mock.load_state.return_value = {"answers": {}}
    mock.save_state.return_value = True
    return mock


@pytest.fixture
def mock_llm_provider():
    """Mock LLMProviderProtocol with native tool calling support."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def lean_agent(mock_state_manager, mock_llm_provider):
    """Create LeanAgent with mocked dependencies."""
    planner = PlannerTool()
    return LeanAgent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools=[planner],
        system_prompt="You are a helpful assistant.",
    )


@pytest.mark.asyncio
async def test_no_compression_below_threshold(lean_agent):
    """Test that messages are not compressed when below threshold."""
    # Create message list below threshold (20 messages)
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Message 1"},
        {"role": "assistant", "content": "Response 1"},
        {"role": "user", "content": "Message 2"},
        {"role": "assistant", "content": "Response 2"},
    ]

    result = await lean_agent._compress_messages(messages)

    # Should return unchanged
    assert len(result) == len(messages)
    assert result == messages


@pytest.mark.asyncio
async def test_compression_with_llm_summary(lean_agent, mock_llm_provider):
    """Test compression with successful LLM summarization."""
    # Create message list exceeding threshold
    messages = [{"role": "system", "content": "System prompt"}]

    # Add 25 messages (exceeds SUMMARY_THRESHOLD of 20)
    for i in range(25):
        messages.append({"role": "user", "content": f"User message {i}"})
        messages.append({"role": "assistant", "content": f"Response {i}"})

    # Mock LLM to return a summary
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": "Summary: User asked 25 questions about various topics.",
    }

    result = await lean_agent._compress_messages(messages)

    # Verify LLM was called for summarization
    assert mock_llm_provider.complete.called
    call_args = mock_llm_provider.complete.call_args
    assert "Summarize this conversation history" in call_args[1]["messages"][0][
        "content"
    ]

    # Verify compressed structure
    assert len(result) < len(messages)
    assert result[0]["role"] == "system"  # System prompt preserved
    assert result[1]["role"] == "system"  # Summary added
    assert "[Previous Context Summary]" in result[1]["content"]
    assert "Summary: User asked 25 questions" in result[1]["content"]

    # Verify recent messages preserved (after threshold)
    # Should have: system + summary + messages after threshold
    expected_count = 1 + 1 + (len(messages) - lean_agent.SUMMARY_THRESHOLD)
    assert len(result) == expected_count


@pytest.mark.asyncio
async def test_compression_fallback_on_llm_failure(
    lean_agent, mock_llm_provider
):
    """Test fallback compression when LLM summarization fails."""
    # Create message list exceeding threshold
    messages = [{"role": "system", "content": "System prompt"}]

    for i in range(25):
        messages.append({"role": "user", "content": f"User message {i}"})
        messages.append({"role": "assistant", "content": f"Response {i}"})

    # Mock LLM to fail
    mock_llm_provider.complete.return_value = {
        "success": False,
        "error": "LLM service unavailable",
    }

    result = await lean_agent._compress_messages(messages)

    # Should use deterministic fallback compression
    assert len(result) < len(messages)
    assert result[0]["role"] == "system"  # System prompt preserved

    # Deterministic compression keeps: system + summary message + last 10 messages
    # (changed from old behavior which kept SUMMARY_THRESHOLD=20)
    assert len(result) <= 12  # system + summary + 10 recent messages
    assert len(result) > 10  # At least some messages kept


@pytest.mark.asyncio
async def test_compression_fallback_on_exception(lean_agent, mock_llm_provider):
    """Test fallback compression when LLM raises exception."""
    # Create message list exceeding threshold
    messages = [{"role": "system", "content": "System prompt"}]

    for i in range(25):
        messages.append({"role": "user", "content": f"User message {i}"})
        messages.append({"role": "assistant", "content": f"Response {i}"})

    # Mock LLM to raise exception
    mock_llm_provider.complete.side_effect = Exception("Network error")

    result = await lean_agent._compress_messages(messages)

    # Should use deterministic fallback compression
    assert len(result) < len(messages)
    assert result[0]["role"] == "system"

    # Deterministic compression keeps: system + summary message + last 10 messages
    assert len(result) <= 12  # system + summary + 10 recent messages
    assert len(result) > 10  # At least some messages kept


@pytest.mark.asyncio
async def test_fallback_compression_directly(lean_agent):
    """Test the fallback compression method directly."""
    # Create message list
    messages = [{"role": "system", "content": "System prompt"}]

    for i in range(30):
        messages.append({"role": "user", "content": f"Message {i}"})

    result = lean_agent._fallback_compression(messages)

    # Now redirects to deterministic compression
    # Keeps: system + summary message + last 10 messages
    assert len(result) <= 12  # system + summary + 10 recent messages
    assert len(result) > 10  # At least some messages kept
    assert result[0] == messages[0]  # System prompt
    # Second message should be the summary
    assert "compressed for token budget" in result[1]["content"]
    # Rest should be recent messages
    assert result[-1] == messages[-1]  # Last message preserved


@pytest.mark.asyncio
async def test_compression_preserves_system_prompt(
    lean_agent, mock_llm_provider
):
    """Test that system prompt is always preserved during compression."""
    messages = [{"role": "system", "content": "Important system prompt"}]

    for i in range(25):
        messages.append({"role": "user", "content": f"Message {i}"})

    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": "Summary of conversation",
    }

    result = await lean_agent._compress_messages(messages)

    # First message should always be the original system prompt
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "Important system prompt"


@pytest.mark.asyncio
async def test_compression_summary_prompt_format(
    lean_agent, mock_llm_provider
):
    """Test that the summary prompt is properly formatted."""
    messages = [{"role": "system", "content": "System"}]

    for i in range(25):
        messages.append({"role": "user", "content": f"Message {i}"})

    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": "Summary",
    }

    await lean_agent._compress_messages(messages)

    # Verify the prompt sent to LLM
    call_args = mock_llm_provider.complete.call_args
    prompt = call_args[1]["messages"][0]["content"]

    # Check prompt contains expected elements
    assert "Summarize this conversation history concisely:" in prompt
    assert "Key decisions made" in prompt
    assert "Important tool results" in prompt
    assert "Context needed" in prompt

    # Verify safe summary format is used (NOT raw JSON dumps)
    # Story 9.3: Safe compression should use [Message N - role] format
    assert "[Message" in prompt
    assert "Content:" in prompt
    # Should NOT contain raw JSON array format
    assert json.dumps(messages[1 : lean_agent.SUMMARY_THRESHOLD], indent=2) not in prompt


@pytest.mark.asyncio
async def test_compression_uses_correct_model(lean_agent, mock_llm_provider):
    """Test that compression uses the agent's configured model."""
    messages = [{"role": "system", "content": "System"}]

    for i in range(25):
        messages.append({"role": "user", "content": f"Message {i}"})

    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": "Summary",
    }

    # Set custom model alias
    lean_agent.model_alias = "custom-model"

    await lean_agent._compress_messages(messages)

    # Verify correct model was used
    call_args = mock_llm_provider.complete.call_args
    assert call_args[1]["model"] == "custom-model"
    assert call_args[1]["temperature"] == 0  # Should use 0 for deterministic

