"""Protocol compliance tests.

Verifies that concrete implementations satisfy their declared protocols
using ``isinstance()`` checks with ``runtime_checkable`` protocols and
structural attribute/method presence checks.

These tests act as a safety net against protocol drift: if someone adds
a method to a protocol but forgets to implement it in the concrete class,
these tests will catch it.
"""

from __future__ import annotations

import inspect

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _get_protocol_methods(protocol_cls: type) -> set[str]:
    """Extract public method and property names declared by a protocol."""
    names: set[str] = set()
    for name, obj in inspect.getmembers(protocol_cls):
        if name.startswith("_"):
            continue
        if callable(obj) or isinstance(obj, property):
            names.add(name)
    return names


def _assert_implements(concrete_cls: type, protocol_cls: type) -> None:
    """Assert that *concrete_cls* has all methods/properties of *protocol_cls*."""
    required = _get_protocol_methods(protocol_cls)
    actual = {name for name in dir(concrete_cls) if not name.startswith("_")}
    missing = required - actual
    assert not missing, (
        f"{concrete_cls.__name__} is missing methods/properties from "
        f"{protocol_cls.__name__}: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# ToolProtocol compliance
# ---------------------------------------------------------------------------


class TestToolProtocolCompliance:
    """Verify that all native tools satisfy ToolProtocol."""

    def test_base_tool_satisfies_tool_protocol(self) -> None:
        from taskforce.core.interfaces.tools import ToolProtocol
        from taskforce.infrastructure.tools.base_tool import BaseTool

        _assert_implements(BaseTool, ToolProtocol)

    def test_activate_skill_tool_satisfies_tool_protocol(self) -> None:
        from taskforce.core.interfaces.tools import ToolProtocol
        from taskforce.infrastructure.tools.native.activate_skill_tool import (
            ActivateSkillTool,
        )

        _assert_implements(ActivateSkillTool, ToolProtocol)

    def test_reminder_tool_satisfies_tool_protocol(self) -> None:
        from taskforce.core.interfaces.tools import ToolProtocol
        from taskforce.infrastructure.tools.native.reminder_tool import (
            ReminderTool,
        )

        _assert_implements(ReminderTool, ToolProtocol)

    def test_rule_manager_tool_satisfies_tool_protocol(self) -> None:
        from taskforce.core.interfaces.tools import ToolProtocol
        from taskforce.infrastructure.tools.native.rule_manager_tool import (
            RuleManagerTool,
        )

        _assert_implements(RuleManagerTool, ToolProtocol)

    def test_file_read_tool_satisfies_tool_protocol(self) -> None:
        from taskforce.core.interfaces.tools import ToolProtocol
        from taskforce.infrastructure.tools.native.file_tools import FileReadTool

        _assert_implements(FileReadTool, ToolProtocol)

    def test_python_tool_satisfies_tool_protocol(self) -> None:
        from taskforce.core.interfaces.tools import ToolProtocol
        from taskforce.infrastructure.tools.native.python_tool import PythonTool

        _assert_implements(PythonTool, ToolProtocol)


# ---------------------------------------------------------------------------
# StateManagerProtocol compliance
# ---------------------------------------------------------------------------


class TestStateManagerProtocolCompliance:
    """Verify that FileStateManager satisfies StateManagerProtocol."""

    def test_file_state_manager_satisfies_protocol(self) -> None:
        from taskforce.core.interfaces.state import StateManagerProtocol
        from taskforce.infrastructure.persistence.file_state_manager import (
            FileStateManager,
        )

        _assert_implements(FileStateManager, StateManagerProtocol)


# ---------------------------------------------------------------------------
# LLMProviderProtocol compliance
# ---------------------------------------------------------------------------


class TestLLMProviderProtocolCompliance:
    """Verify that LiteLLMService satisfies LLMProviderProtocol."""

    def test_litellm_service_satisfies_protocol(self) -> None:
        from taskforce.core.interfaces.llm import LLMProviderProtocol
        from taskforce.infrastructure.llm.litellm_service import LiteLLMService

        _assert_implements(LiteLLMService, LLMProviderProtocol)


# ---------------------------------------------------------------------------
# SkillRegistryProtocol compliance
# ---------------------------------------------------------------------------


class TestSkillRegistryProtocolCompliance:
    """Verify that FileSkillRegistry satisfies SkillRegistryProtocol."""

    def test_file_skill_registry_satisfies_protocol(self) -> None:
        from taskforce.core.interfaces.skills import SkillRegistryProtocol
        from taskforce.infrastructure.skills.skill_registry import (
            FileSkillRegistry,
        )

        _assert_implements(FileSkillRegistry, SkillRegistryProtocol)


# ---------------------------------------------------------------------------
# MemoryStoreProtocol compliance
# ---------------------------------------------------------------------------


class TestMemoryStoreProtocolCompliance:
    """Verify that FileMemoryStore satisfies MemoryStoreProtocol."""

    def test_file_memory_store_satisfies_protocol(self) -> None:
        from taskforce.core.interfaces.memory_store import MemoryStoreProtocol
        from taskforce.infrastructure.memory.file_memory_store import (
            FileMemoryStore,
        )

        _assert_implements(FileMemoryStore, MemoryStoreProtocol)


# ---------------------------------------------------------------------------
# TokenUsage domain behavior
# ---------------------------------------------------------------------------


class TestTokenUsageBehavior:
    """Test domain behavior added to TokenUsage."""

    def test_exceeds_budget(self) -> None:
        from taskforce.core.domain.models import TokenUsage

        usage = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
        assert usage.exceeds_budget(999)
        assert not usage.exceeds_budget(1000)
        assert not usage.exceeds_budget(1001)

    def test_remaining(self) -> None:
        from taskforce.core.domain.models import TokenUsage

        usage = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=700)
        assert usage.remaining(1000) == 300
        assert usage.remaining(500) == 0
        assert usage.remaining(700) == 0

    def test_add(self) -> None:
        from taskforce.core.domain.models import TokenUsage

        a = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        b = TokenUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300)
        c = a + b
        assert c.prompt_tokens == 300
        assert c.completion_tokens == 150
        assert c.total_tokens == 450
