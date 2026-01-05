"""
Unit tests for core protocol interfaces.

Tests verify that:
- Protocols can be imported without errors
- Mock implementations can be created
- Type hints are correctly defined
- Protocol contracts are enforceable
"""

from typing import Any

from taskforce.core.interfaces import (
    ApprovalRiskLevel,
    LLMProviderProtocol,
    StateManagerProtocol,
    ToolProtocol,
)


class TestProtocolImports:
    """Test that all protocols can be imported successfully."""

    def test_import_state_manager_protocol(self):
        """Test StateManagerProtocol can be imported."""
        assert StateManagerProtocol is not None

    def test_import_llm_provider_protocol(self):
        """Test LLMProviderProtocol can be imported."""
        assert LLMProviderProtocol is not None

    def test_import_tool_protocol(self):
        """Test ToolProtocol can be imported."""
        assert ToolProtocol is not None

    def test_import_approval_risk_level(self):
        """Test ApprovalRiskLevel enum can be imported."""
        assert ApprovalRiskLevel is not None
        assert ApprovalRiskLevel.LOW == "low"
        assert ApprovalRiskLevel.MEDIUM == "medium"
        assert ApprovalRiskLevel.HIGH == "high"


class TestMockImplementations:
    """Test that mock implementations can be created for protocols."""

    def test_mock_state_manager(self):
        """Test creating a mock StateManager implementation."""

        class MockStateManager:
            async def save_state(
                self, session_id: str, state_data: dict[str, Any]
            ) -> bool:
                return True

            async def load_state(self, session_id: str) -> dict[str, Any] | None:
                return {}

            async def delete_state(self, session_id: str) -> None:
                pass

            async def list_sessions(self) -> list[str]:
                return []

        mock: StateManagerProtocol = MockStateManager()
        assert mock is not None

    def test_mock_llm_provider(self):
        """Test creating a mock LLM provider implementation."""

        class MockLLMProvider:
            async def complete(
                self,
                messages: list[dict[str, Any]],
                model: str | None = None,
                **kwargs: Any,
            ) -> dict[str, Any]:
                return {
                    "success": True,
                    "content": "Test response",
                    "usage": {"total_tokens": 10},
                    "model": "test-model",
                    "latency_ms": 100,
                }

            async def generate(
                self,
                prompt: str,
                context: dict[str, Any] | None = None,
                model: str | None = None,
                **kwargs: Any,
            ) -> dict[str, Any]:
                return {
                    "success": True,
                    "content": "Generated text",
                    "generated_text": "Generated text",
                    "usage": {"total_tokens": 10},
                    "model": "test-model",
                    "latency_ms": 100,
                }

        mock: LLMProviderProtocol = MockLLMProvider()
        assert mock is not None

    def test_mock_tool(self):
        """Test creating a mock Tool implementation."""

        class MockTool:
            @property
            def name(self) -> str:
                return "mock_tool"

            @property
            def description(self) -> str:
                return "A mock tool for testing"

            @property
            def parameters_schema(self) -> dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "Test parameter"}
                    },
                    "required": ["param1"],
                }

            @property
            def requires_approval(self) -> bool:
                return False

            @property
            def approval_risk_level(self) -> ApprovalRiskLevel:
                return ApprovalRiskLevel.LOW

            def get_approval_preview(self, **kwargs: Any) -> str:
                return "Mock tool preview"

            async def execute(self, **kwargs: Any) -> dict[str, Any]:
                return {"success": True, "output": "Mock output"}

            def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
                return True, None

        mock: ToolProtocol = MockTool()
        assert mock is not None
        assert mock.name == "mock_tool"
        assert mock.requires_approval is False


class TestProtocolContracts:
    """Test that protocol contracts are properly defined."""

    def test_protocols_are_importable(self):
        """Test that all protocols can be used in type hints."""
        # This test verifies protocols can be used as types
        def accepts_state_manager(sm: StateManagerProtocol) -> None:
            pass

        def accepts_llm_provider(llm: LLMProviderProtocol) -> None:
            pass

        def accepts_tool(tool: ToolProtocol) -> None:
            pass

        # If we get here without import errors, protocols are properly defined
        assert True
