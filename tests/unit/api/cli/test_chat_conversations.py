"""Tests for conversation support in SimpleChatRunner (ADR-016)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.api.cli.simple_chat import SimpleChatRunner
from taskforce.core.domain.enums import MessageRole


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.state_manager = MagicMock()
    agent.state_manager.load_state = AsyncMock(return_value={})
    agent.state_manager.save_state = AsyncMock()
    return agent


@pytest.fixture
def mock_conversation_manager():
    mgr = AsyncMock()
    mgr.get_or_create = AsyncMock(return_value="conv-initial")
    mgr.create_new = AsyncMock(return_value="conv-new-123")
    mgr.append_message = AsyncMock()
    return mgr


class TestConversationWiring:
    async def test_run_initializes_conversation(self, mock_agent, mock_conversation_manager):
        """The REPL loop should get_or_create a conversation on startup."""
        runner = SimpleChatRunner(
            session_id="sess-1",
            profile="dev",
            agent=mock_agent,
            stream=True,
            user_context=None,
            conversation_manager=mock_conversation_manager,
        )

        # Simulate immediate exit after initialization.
        with patch.object(runner, "_print_banner"), patch.object(
            runner, "_print_session_info"
        ), patch.object(runner, "_read_input", new_callable=AsyncMock, return_value="/quit"):
            await runner.run()

        mock_conversation_manager.get_or_create.assert_called_once_with("cli")
        assert runner._conversation_id == "conv-initial"

    async def test_new_command_creates_conversation(
        self, mock_agent, mock_conversation_manager
    ):
        """The /new command should create a new conversation."""
        runner = SimpleChatRunner(
            session_id="sess-1",
            profile="dev",
            agent=mock_agent,
            stream=True,
            user_context=None,
            conversation_manager=mock_conversation_manager,
        )
        runner._conversation_id = "conv-old"

        with patch.object(runner, "_print_system"):
            await runner._start_new_conversation()

        mock_conversation_manager.create_new.assert_called_once_with("cli")
        assert runner._conversation_id == "conv-new-123"

    async def test_chat_message_mirrors_to_conversation_manager(
        self, mock_agent, mock_conversation_manager
    ):
        """User messages should be mirrored to the conversation manager."""
        runner = SimpleChatRunner(
            session_id="sess-1",
            profile="dev",
            agent=mock_agent,
            stream=True,
            user_context=None,
            conversation_manager=mock_conversation_manager,
        )
        runner._conversation_id = "conv-123"

        # Mock _stream_response to avoid executor call.
        with patch.object(runner, "_stream_response", new_callable=AsyncMock):
            await runner._handle_chat_message("Hello agent")

        mock_conversation_manager.append_message.assert_called_once_with(
            "conv-123",
            {"role": MessageRole.USER.value, "content": "Hello agent"},
        )

    async def test_no_mirror_without_manager(self, mock_agent):
        """Without a conversation manager, no mirroring should occur."""
        runner = SimpleChatRunner(
            session_id="sess-1",
            profile="dev",
            agent=mock_agent,
            stream=True,
            user_context=None,
        )

        with patch.object(runner, "_stream_response", new_callable=AsyncMock):
            await runner._handle_chat_message("Hello")

        # No exception should occur; state_manager still saves.
        mock_agent.state_manager.save_state.assert_called_once()

    async def test_mirror_assistant_message(self, mock_agent, mock_conversation_manager):
        """Assistant messages should be mirrored to conversation manager."""
        runner = SimpleChatRunner(
            session_id="sess-1",
            profile="dev",
            agent=mock_agent,
            stream=True,
            user_context=None,
            conversation_manager=mock_conversation_manager,
        )
        runner._conversation_id = "conv-123"

        await runner._mirror_assistant_message("Agent reply")

        mock_conversation_manager.append_message.assert_called_once_with(
            "conv-123",
            {"role": MessageRole.ASSISTANT.value, "content": "Agent reply"},
        )
