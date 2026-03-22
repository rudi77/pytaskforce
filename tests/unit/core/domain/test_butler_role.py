"""Tests for ButlerRole domain model."""

import pytest

from taskforce.core.domain.butler_role import ButlerRole


class TestButlerRole:
    """Tests for the ButlerRole frozen dataclass."""

    def test_create_minimal(self) -> None:
        role = ButlerRole(name="test")
        assert role.name == "test"
        assert role.description == ""
        assert role.persona_prompt == ""
        assert role.sub_agents == ()
        assert role.tools == ()
        assert role.event_sources == ()
        assert role.rules == ()
        assert role.mcp_servers == ()

    def test_create_with_values(self) -> None:
        role = ButlerRole(
            name="accountant",
            description="Accounting assistant",
            persona_prompt="You are an accountant.",
            sub_agents=({"specialist": "doc-agent", "description": "Documents"},),
            tools=("memory", "ask_user"),
            event_sources=({"type": "calendar"},),
            rules=({"name": "invoice_rule"},),
            mcp_servers=({"type": "stdio", "command": "node"},),
        )
        assert role.name == "accountant"
        assert role.description == "Accounting assistant"
        assert role.persona_prompt == "You are an accountant."
        assert len(role.sub_agents) == 1
        assert role.sub_agents[0]["specialist"] == "doc-agent"
        assert len(role.tools) == 2
        assert len(role.event_sources) == 1
        assert len(role.rules) == 1
        assert len(role.mcp_servers) == 1

    def test_is_frozen(self) -> None:
        role = ButlerRole(name="test")
        with pytest.raises(AttributeError):
            role.name = "changed"  # type: ignore[misc]

    def test_to_dict(self) -> None:
        role = ButlerRole(
            name="accountant",
            description="Accounting",
            persona_prompt="You are an accountant.",
            sub_agents=({"specialist": "doc-agent", "description": "Docs"},),
            tools=("memory",),
        )
        d = role.to_dict()
        assert d["name"] == "accountant"
        assert d["description"] == "Accounting"
        assert d["persona_prompt"] == "You are an accountant."
        assert d["sub_agents"] == [{"specialist": "doc-agent", "description": "Docs"}]
        assert d["tools"] == ["memory"]
        assert d["event_sources"] == []
        assert d["rules"] == []
        assert d["mcp_servers"] == []

    def test_from_dict(self) -> None:
        data = {
            "name": "it_support",
            "description": "IT Support",
            "persona_prompt": "You handle IT issues.",
            "sub_agents": [{"specialist": "pc-agent", "description": "PC ops"}],
            "tools": ["memory", "shell"],
            "event_sources": [{"type": "webhook"}],
            "rules": [{"name": "ticket_rule"}],
            "mcp_servers": [{"type": "sse"}],
        }
        role = ButlerRole.from_dict(data)
        assert role.name == "it_support"
        assert role.description == "IT Support"
        assert role.persona_prompt == "You handle IT issues."
        assert len(role.sub_agents) == 1
        assert role.sub_agents[0]["specialist"] == "pc-agent"
        assert len(role.tools) == 2
        assert len(role.event_sources) == 1
        assert len(role.rules) == 1
        assert len(role.mcp_servers) == 1

    def test_from_dict_defaults(self) -> None:
        data = {"name": "minimal"}
        role = ButlerRole.from_dict(data)
        assert role.name == "minimal"
        assert role.description == ""
        assert role.persona_prompt == ""
        assert role.sub_agents == ()
        assert role.tools == ()

    def test_from_dict_missing_name(self) -> None:
        data = {"description": "No name provided"}
        role = ButlerRole.from_dict(data)
        assert role.name == ""

    def test_roundtrip(self) -> None:
        original = ButlerRole(
            name="accountant",
            description="Accounting assistant",
            persona_prompt="# Accountant\nYou handle invoices.",
            sub_agents=(
                {"specialist": "doc-agent", "description": "Documents"},
                {"specialist": "research_agent", "description": "Research"},
            ),
            tools=("memory", "ask_user", "calendar"),
            event_sources=({"type": "calendar", "poll_interval_minutes": 5},),
            rules=({"name": "invoice_alert", "trigger": {"source": "email"}},),
            mcp_servers=({"type": "stdio", "command": "node", "args": ["-y"]},),
        )
        restored = ButlerRole.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.persona_prompt == original.persona_prompt
        assert restored.sub_agents == original.sub_agents
        assert restored.tools == original.tools
        assert restored.event_sources == original.event_sources
        assert restored.rules == original.rules
        assert restored.mcp_servers == original.mcp_servers
