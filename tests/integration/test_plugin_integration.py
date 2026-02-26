"""Integration tests for plugin system with accounting_agent example."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from taskforce.application.plugin_loader import PluginLoader
from taskforce.core.domain.errors import PluginError

# Get the path to accounting_agent example
EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"
ACCOUNTING_AGENT_PATH = EXAMPLES_DIR / "accounting_agent"


@pytest.mark.integration
class TestAccountingAgentPlugin:
    """Integration tests using the accounting_agent example plugin."""

    @pytest.mark.skipif(
        not ACCOUNTING_AGENT_PATH.exists(),
        reason="accounting_agent example not found"
    )
    def test_discover_accounting_agent_plugin(self):
        """Test discovery of accounting_agent plugin structure."""
        loader = PluginLoader()
        manifest = loader.discover_plugin(str(ACCOUNTING_AGENT_PATH))

        assert manifest.name == "accounting_agent"
        assert manifest.path == ACCOUNTING_AGENT_PATH
        assert manifest.tools_module == "accounting_agent.tools"
        assert manifest.config_path is not None
        assert manifest.config_path.name == "accounting_agent.yaml"

        # Check expected tool classes (SemanticRuleEngineTool supersedes RuleEngineTool)
        expected_tools = [
            "AuditLogTool",
            "ComplianceCheckerTool",
            "DoclingTool",
            "SemanticRuleEngineTool",
            "TaxCalculatorTool",
        ]
        for tool in expected_tools:
            assert tool in manifest.tool_classes, f"Missing tool: {tool}"

    @pytest.mark.skipif(
        not ACCOUNTING_AGENT_PATH.exists(),
        reason="accounting_agent example not found"
    )
    def test_load_accounting_agent_config(self):
        """Test loading accounting_agent plugin configuration."""
        loader = PluginLoader()
        manifest = loader.discover_plugin(str(ACCOUNTING_AGENT_PATH))
        config = loader.load_config(manifest)

        # Check expected config keys
        assert "profile" in config or "specialist" in config or "tools" in config
        # The config should have some content
        assert config, "Config should not be empty"

    @pytest.mark.skipif(
        not ACCOUNTING_AGENT_PATH.exists(),
        reason="accounting_agent example not found"
    )
    def test_load_accounting_agent_tools(self):
        """Test loading tools from accounting_agent plugin.

        Note: This test may fail if plugin dependencies (docling, pyyaml)
        are not installed. That's expected behavior.
        """
        loader = PluginLoader()
        manifest = loader.discover_plugin(str(ACCOUNTING_AGENT_PATH))

        try:
            tools = loader.load_tools(manifest, llm_provider=MagicMock())

            # Verify tools loaded
            assert len(tools) > 0, "Should load at least one tool"

            # Verify tool names
            tool_names = [t.name for t in tools]
            # At least some tools should be loaded
            assert any(
                name in tool_names
                for name in [
                    "docling_extract",
                    "check_compliance",
                    "semantic_rule_engine",
                    "calculate_tax",
                    "audit_log",
                ]
            ), f"Expected accounting tools, got: {tool_names}"

            # Verify tools implement protocol
            for tool in tools:
                assert hasattr(tool, "name")
                assert hasattr(tool, "description")
                assert hasattr(tool, "parameters_schema")
                assert hasattr(tool, "execute")
                assert hasattr(tool, "validate_params")

        except PluginError as e:
            # Plugin dependency missing is acceptable for CI environments
            if "dependency missing" in str(e):
                pytest.skip(f"Plugin dependency missing: {e}")
            raise


@pytest.mark.integration
class TestPluginLoaderWithRealFilesystem:
    """Integration tests for plugin loader with real filesystem operations."""

    def test_plugin_loader_handles_relative_paths(self, tmp_path: Path):
        """Test that plugin loader handles relative paths correctly."""
        # Create plugin structure
        package_dir = tmp_path / "test_plugin"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")

        tools_dir = package_dir / "tools"
        tools_dir.mkdir()
        (tools_dir / "__init__.py").write_text("""
__all__ = ['SimpleTool']

class SimpleTool:
    @property
    def name(self):
        return "simple_tool"

    @property
    def description(self):
        return "A simple test tool"

    @property
    def parameters_schema(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return {"success": True}

    def validate_params(self, **kwargs):
        return True, None
""")

        loader = PluginLoader()

        # Test with string path
        manifest = loader.discover_plugin(str(tmp_path))
        assert manifest.name == "test_plugin"

        # Load tools
        tools = loader.load_tools(manifest)
        assert len(tools) == 1
        assert tools[0].name == "simple_tool"

    def test_plugin_with_nested_tools(self, tmp_path: Path):
        """Test plugin with multiple tools in __all__."""
        package_dir = tmp_path / "multi_tool_plugin"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")

        tools_dir = package_dir / "tools"
        tools_dir.mkdir()
        (tools_dir / "__init__.py").write_text("""
__all__ = ['ToolA', 'ToolB']

class ToolA:
    @property
    def name(self):
        return "tool_a"

    @property
    def description(self):
        return "Tool A"

    @property
    def parameters_schema(self):
        return {"type": "object"}

    async def execute(self, **kwargs):
        return {"success": True}

    def validate_params(self, **kwargs):
        return True, None

class ToolB:
    @property
    def name(self):
        return "tool_b"

    @property
    def description(self):
        return "Tool B"

    @property
    def parameters_schema(self):
        return {"type": "object"}

    async def execute(self, **kwargs):
        return {"success": True}

    def validate_params(self, **kwargs):
        return True, None
""")

        loader = PluginLoader()
        manifest = loader.discover_plugin(str(tmp_path))

        assert len(manifest.tool_classes) == 2
        assert "ToolA" in manifest.tool_classes
        assert "ToolB" in manifest.tool_classes

        tools = loader.load_tools(manifest)
        assert len(tools) == 2
        tool_names = {t.name for t in tools}
        assert tool_names == {"tool_a", "tool_b"}
