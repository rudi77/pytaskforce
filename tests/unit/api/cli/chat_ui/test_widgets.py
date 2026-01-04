"""Unit tests for chat UI widgets."""

import pytest
from textual.app import App

from taskforce.api.cli.chat_ui.widgets import (
    ChatLog,
    ChatMessage,
    Header,
    InputBar,
    MessageType,
    PlanPanel,
)


class TestChatMessage:
    """Test ChatMessage widget."""

    def test_create_user_message(self):
        """Test creating a user message."""
        message = ChatMessage(
            message_type=MessageType.USER,
            content="Hello, world!",
        )
        assert message.message_type == MessageType.USER
        assert message.content == "Hello, world!"
        assert message.timestamp is not None

    def test_create_agent_message(self):
        """Test creating an agent message."""
        message = ChatMessage(
            message_type=MessageType.AGENT,
            content="Hello, user!",
            thought="I should greet the user",
        )
        assert message.message_type == MessageType.AGENT
        assert message.content == "Hello, user!"
        assert message.thought == "I should greet the user"

    def test_create_tool_call_message(self):
        """Test creating a tool call message."""
        message = ChatMessage(
            message_type=MessageType.TOOL_CALL,
            content="",
            tool_name="FileReadTool",
            tool_params={"path": "test.txt"},
        )
        assert message.message_type == MessageType.TOOL_CALL
        assert message.tool_name == "FileReadTool"
        assert message.tool_params == {"path": "test.txt"}

    def test_create_tool_result_message(self):
        """Test creating a tool result message."""
        message = ChatMessage(
            message_type=MessageType.TOOL_RESULT,
            content="File contents",
            tool_name="FileReadTool",
            success=True,
        )
        assert message.message_type == MessageType.TOOL_RESULT
        assert message.content == "File contents"
        assert message.success is True


class TestChatLog:
    """Test ChatLog widget."""

    @pytest.fixture
    def chat_log(self):
        """Create a chat log instance."""
        return ChatLog()

    def test_create_chat_log(self, chat_log):
        """Test creating a chat log."""
        assert chat_log is not None
        assert chat_log.auto_scroll is True
        assert chat_log.message_count == 0

    def test_add_user_message(self, chat_log):
        """Test adding a user message."""
        chat_log.add_user_message("Test message")
        assert chat_log.message_count == 1

    def test_add_agent_message(self, chat_log):
        """Test adding an agent message."""
        chat_log.add_agent_message("Agent response")
        assert chat_log.message_count == 1

    def test_add_system_message(self, chat_log):
        """Test adding a system message."""
        chat_log.add_system_message("System notification")
        assert chat_log.message_count == 1

    def test_add_multiple_messages(self, chat_log):
        """Test adding multiple messages."""
        chat_log.add_user_message("Message 1")
        chat_log.add_agent_message("Response 1")
        chat_log.add_user_message("Message 2")
        assert chat_log.message_count == 3

    def test_clear_messages(self, chat_log):
        """Test clearing all messages."""
        chat_log.add_user_message("Message 1")
        chat_log.add_agent_message("Response 1")
        assert chat_log.message_count == 2

        chat_log.clear_messages()
        assert chat_log.message_count == 0

    def test_toggle_auto_scroll(self, chat_log):
        """Test toggling auto-scroll."""
        assert chat_log.auto_scroll is True
        result = chat_log.toggle_auto_scroll()
        assert result is False
        assert chat_log.auto_scroll is False


class TestHeader:
    """Test Header widget."""

    @pytest.fixture
    def header(self):
        """Create a header instance."""
        return Header(
            session_id="test-session-123",
            profile="dev",
        )

    def test_create_header(self, header):
        """Test creating a header."""
        assert header is not None
        assert header.session_id == "test-session-123"
        assert header.profile == "dev"
        assert header.status == "Idle"
        assert header.token_count == 0

    def test_update_status(self, header):
        """Test updating status."""
        header.update_status("Working")
        assert header.status == "Working"

    def test_update_tokens(self, header):
        """Test updating token count."""
        header.update_tokens(100)
        assert header.token_count == 100

    def test_add_tokens(self, header):
        """Test adding tokens."""
        header.update_tokens(100)
        header.add_tokens(50)
        assert header.token_count == 150


class TestInputBar:
    """Test InputBar widget."""

    @pytest.fixture
    def input_bar(self):
        """Create an input bar instance."""
        return InputBar()

    def test_create_input_bar(self, input_bar):
        """Test creating an input bar."""
        assert input_bar is not None
        assert input_bar.placeholder == "Type your message..."


class TestPlanPanel:
    """Test PlanPanel widget."""

    @pytest.fixture
    def plan_panel(self):
        """Create a plan panel instance."""
        return PlanPanel()

    def test_create_plan_panel(self, plan_panel):
        """Test creating a plan panel."""
        assert plan_panel is not None
        assert plan_panel.visible is False
        assert plan_panel.plan_steps == []
        assert plan_panel.plan_text is None

    def test_update_plan_steps(self, plan_panel):
        """Test updating plan with steps."""
        steps = ["Step 1", "Step 2", "Step 3"]
        plan_panel.update_plan_steps(steps)

        assert plan_panel.visible is True
        assert len(plan_panel.plan_steps) == 3
        assert plan_panel.plan_steps[0]["description"] == "Step 1"
        assert plan_panel.plan_steps[0]["status"] == "PENDING"

    def test_update_plan_text(self, plan_panel):
        """Test updating plan with text."""
        plan_text = "This is a free-form plan"
        plan_panel.update_plan_text(plan_text)

        assert plan_panel.visible is True
        assert plan_panel.plan_text == plan_text
        assert plan_panel.plan_steps == []

    def test_update_step_status(self, plan_panel):
        """Test updating step status."""
        steps = ["Step 1", "Step 2", "Step 3"]
        plan_panel.update_plan_steps(steps)

        plan_panel.update_step_status(1, "IN_PROGRESS")
        assert plan_panel.plan_steps[0]["status"] == "IN_PROGRESS"

        plan_panel.update_step_status(2, "DONE")
        assert plan_panel.plan_steps[1]["status"] == "DONE"

    def test_clear_plan(self, plan_panel):
        """Test clearing the plan."""
        steps = ["Step 1", "Step 2"]
        plan_panel.update_plan_steps(steps)
        assert plan_panel.visible is True

        plan_panel.clear_plan()
        assert plan_panel.visible is False
        assert plan_panel.plan_steps == []
        assert plan_panel.plan_text is None

    def test_toggle_visibility(self, plan_panel):
        """Test toggling visibility."""
        assert plan_panel.visible is False

        result = plan_panel.toggle_visibility()
        assert result is True
        assert plan_panel.visible is True

        result = plan_panel.toggle_visibility()
        assert result is False
        assert plan_panel.visible is False
