"""Unit tests for PluginLoader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.application.plugin_loader import PluginLoader, PluginManifest
from taskforce.core.domain.errors import PluginError


class TestPluginLoaderDiscovery:
    """Tests for PluginLoader.discover_plugin()."""

    def test_discover_valid_plugin(self, tmp_path: Path):
        """Test discovery of valid plugin structure."""
        # Create valid plugin structure
        package_dir = tmp_path / "my_plugin"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")

        tools_dir = package_dir / "tools"
        tools_dir.mkdir()
        (tools_dir / "__init__.py").write_text("__all__ = ['MyTool']")

        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        (config_dir / "my_plugin.yaml").write_text("specialist: test")

        loader = PluginLoader()
        manifest = loader.discover_plugin(str(tmp_path))

        assert manifest.name == "my_plugin"
        assert manifest.path == tmp_path
        assert manifest.package_path == package_dir
        assert manifest.tools_module == "my_plugin.tools"
        assert manifest.config_path == config_dir / "my_plugin.yaml"

    def test_discover_plugin_not_found(self):
        """Test error when plugin path doesn't exist."""
        loader = PluginLoader()

        with pytest.raises(FileNotFoundError, match="Plugin not found"):
            loader.discover_plugin("/nonexistent/path")

    def test_discover_plugin_no_package(self, tmp_path: Path):
        """Test error when no Python package found."""
        # Create directory without __init__.py
        (tmp_path / "some_dir").mkdir()

        loader = PluginLoader()

        with pytest.raises(PluginError, match="no Python package found"):
            loader.discover_plugin(str(tmp_path))

    def test_discover_plugin_no_tools_module(self, tmp_path: Path):
        """Test error when tools module missing."""
        # Create package without tools subdirectory
        package_dir = tmp_path / "my_plugin"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")

        loader = PluginLoader()

        with pytest.raises(PluginError, match="no tools module found"):
            loader.discover_plugin(str(tmp_path))

    def test_discover_plugin_without_config(self, tmp_path: Path):
        """Test discovery succeeds without config file."""
        # Create valid plugin structure without config
        package_dir = tmp_path / "my_plugin"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")

        tools_dir = package_dir / "tools"
        tools_dir.mkdir()
        (tools_dir / "__init__.py").write_text("__all__ = ['MyTool']")

        loader = PluginLoader()
        manifest = loader.discover_plugin(str(tmp_path))

        assert manifest.config_path is None

    def test_discover_plugin_path_is_file(self, tmp_path: Path):
        """Test error when path is a file, not directory."""
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("content")

        loader = PluginLoader()

        with pytest.raises(PluginError, match="not a directory"):
            loader.discover_plugin(str(file_path))


class TestPluginLoaderValidation:
    """Tests for PluginLoader.validate_tool()."""

    def test_validate_tool_complete(self):
        """Test validation of complete tool implementation."""
        tool = MagicMock()
        tool.name = "test_tool"
        tool.description = "Test description"
        tool.parameters_schema = {"type": "object"}
        tool.execute = AsyncMock()
        tool.validate_params = MagicMock(return_value=(True, None))

        loader = PluginLoader()
        is_valid, error = loader.validate_tool(tool)

        assert is_valid is True
        assert error is None

    def test_validate_tool_missing_name(self):
        """Test validation failure for missing name property."""
        tool = MagicMock(spec=[])  # Empty spec = no attributes

        loader = PluginLoader()
        is_valid, error = loader.validate_tool(tool)

        assert is_valid is False
        assert "Missing required property: name" in error

    def test_validate_tool_missing_execute(self):
        """Test validation failure for missing execute method."""
        tool = MagicMock()
        tool.name = "test_tool"
        tool.description = "Test description"
        tool.parameters_schema = {"type": "object"}
        del tool.execute  # Remove execute
        tool.validate_params = MagicMock(return_value=(True, None))

        loader = PluginLoader()
        is_valid, error = loader.validate_tool(tool)

        assert is_valid is False
        assert "Missing required method: execute" in error

    def test_validate_tool_sync_execute(self):
        """Test validation failure for non-async execute method."""
        tool = MagicMock()
        tool.name = "test_tool"
        tool.description = "Test description"
        tool.parameters_schema = {"type": "object"}
        tool.execute = MagicMock()  # Sync mock, not AsyncMock
        tool.validate_params = MagicMock(return_value=(True, None))

        loader = PluginLoader()
        is_valid, error = loader.validate_tool(tool)

        assert is_valid is False
        assert "execute() must be an async method" in error


class TestPluginLoaderLoadConfig:
    """Tests for PluginLoader.load_config()."""

    def test_load_config_exists(self, tmp_path: Path):
        """Test loading plugin config from YAML."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
specialist: accounting
agent:
  max_steps: 50
tools:
  - file_read
  - ask_user
""")

        manifest = PluginManifest(
            name="test",
            path=tmp_path,
            package_path=tmp_path / "test",
            tools_module="test.tools",
            config_path=config_path,
            tool_classes=[],
        )

        loader = PluginLoader()
        config = loader.load_config(manifest)

        assert config["specialist"] == "accounting"
        assert config["agent"]["max_steps"] == 50
        assert "file_read" in config["tools"]

    def test_load_config_missing(self, tmp_path: Path):
        """Test handling missing config returns empty dict."""
        manifest = PluginManifest(
            name="test",
            path=tmp_path,
            package_path=tmp_path / "test",
            tools_module="test.tools",
            config_path=None,  # No config
            tool_classes=[],
        )

        loader = PluginLoader()
        config = loader.load_config(manifest)

        assert config == {}

    def test_load_config_invalid_yaml(self, tmp_path: Path):
        """Test error for invalid YAML."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("invalid: yaml: content:")

        manifest = PluginManifest(
            name="test",
            path=tmp_path,
            package_path=tmp_path / "test",
            tools_module="test.tools",
            config_path=config_path,
            tool_classes=[],
        )

        loader = PluginLoader()

        with pytest.raises(PluginError, match="Invalid plugin config YAML"):
            loader.load_config(manifest)


class TestPluginLoaderLoadTools:
    """Tests for PluginLoader.load_tools()."""

    def test_load_tools_success(self, tmp_path: Path):
        """Test successful tool loading."""
        # Create a mock tool class that implements protocol
        class MockTool:
            @property
            def name(self):
                return "mock_tool"

            @property
            def description(self):
                return "Mock tool for testing"

            @property
            def parameters_schema(self):
                return {"type": "object", "properties": {}}

            async def execute(self, **kwargs):
                return {"success": True}

            def validate_params(self, **kwargs):
                return True, None

        # Create plugin structure
        package_dir = tmp_path / "mock_plugin"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")

        tools_dir = package_dir / "tools"
        tools_dir.mkdir()
        (tools_dir / "__init__.py").write_text("""
__all__ = ['MockTool']

class MockTool:
    @property
    def name(self):
        return "mock_tool"

    @property
    def description(self):
        return "Mock tool for testing"

    @property
    def parameters_schema(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return {"success": True}

    def validate_params(self, **kwargs):
        return True, None
""")

        manifest = PluginManifest(
            name="mock_plugin",
            path=tmp_path,
            package_path=package_dir,
            tools_module="mock_plugin.tools",
            config_path=None,
            tool_classes=["MockTool"],
        )

        loader = PluginLoader()
        tools = loader.load_tools(manifest)

        assert len(tools) == 1
        assert tools[0].name == "mock_tool"

    def test_load_tools_import_error(self, tmp_path: Path):
        """Test error handling for missing dependency."""
        # Create plugin with import that will fail
        package_dir = tmp_path / "bad_plugin"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")

        tools_dir = package_dir / "tools"
        tools_dir.mkdir()
        (tools_dir / "__init__.py").write_text("""
import nonexistent_package
__all__ = ['BadTool']
""")

        manifest = PluginManifest(
            name="bad_plugin",
            path=tmp_path,
            package_path=package_dir,
            tools_module="bad_plugin.tools",
            config_path=None,
            tool_classes=["BadTool"],
        )

        loader = PluginLoader()

        with pytest.raises(PluginError, match="dependency missing"):
            loader.load_tools(manifest)

    def test_load_tools_validation_failure(self, tmp_path: Path):
        """Test error when tool fails validation."""
        # Create plugin with tool that doesn't implement protocol
        package_dir = tmp_path / "invalid_plugin"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")

        tools_dir = package_dir / "tools"
        tools_dir.mkdir()
        (tools_dir / "__init__.py").write_text("""
__all__ = ['InvalidTool']

class InvalidTool:
    # Missing required properties and methods
    pass
""")

        manifest = PluginManifest(
            name="invalid_plugin",
            path=tmp_path,
            package_path=package_dir,
            tools_module="invalid_plugin.tools",
            config_path=None,
            tool_classes=["InvalidTool"],
        )

        loader = PluginLoader()

        with pytest.raises(PluginError, match="doesn't implement ToolProtocol"):
            loader.load_tools(manifest)
