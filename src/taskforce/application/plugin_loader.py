"""
Plugin Loader for External Agent Plugins

This module provides functionality to discover, load, and validate external
agent plugins with custom tools. Plugins are Python packages that contain
tool implementations compatible with ToolProtocol.

Plugin Structure:
    {plugin_path}/
    ├── {package_name}/
    │   ├── __init__.py
    │   └── tools/
    │       └── __init__.py    # Exports tools via __all__
    ├── configs/
    │   └── {package_name}.yaml
    └── requirements.txt

Usage:
    loader = PluginLoader()
    manifest = loader.discover_plugin("examples/accounting_agent")
    tools = loader.load_tools(manifest)
    config = loader.load_config(manifest)
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

from taskforce.core.domain.errors import PluginError
from taskforce.core.interfaces.tools import ToolProtocol

logger = structlog.get_logger(__name__)


@dataclass
class PluginManifest:
    """Metadata about a discovered plugin."""

    name: str
    """Plugin package name."""

    path: Path
    """Absolute path to plugin directory."""

    package_path: Path
    """Path to the Python package directory."""

    tools_module: str
    """Fully qualified module name for tools (e.g., 'accounting_agent.tools')."""

    config_path: Path | None
    """Path to plugin config YAML, or None if not found."""

    tool_classes: list[str] = field(default_factory=list)
    """List of tool class names exported via __all__."""


class PluginLoader:
    """
    Discovers and loads external agent plugins.

    The loader handles:
    - Plugin structure validation
    - Dynamic module importing
    - Tool instantiation and validation
    - Configuration loading
    """

    def discover_plugin(self, plugin_path: str) -> PluginManifest:
        """
        Discover plugin structure and validate it.

        Args:
            plugin_path: Path to the plugin directory (relative or absolute)

        Returns:
            PluginManifest with plugin metadata

        Raises:
            FileNotFoundError: If plugin path doesn't exist
            PluginError: If plugin structure is invalid
        """
        # Resolve to absolute path
        path = Path(plugin_path).resolve()

        if not path.exists():
            raise FileNotFoundError(f"Plugin not found: {plugin_path}")

        if not path.is_dir():
            raise PluginError(
                f"Plugin path is not a directory: {plugin_path}",
                plugin_path=str(path),
            )

        # Find Python package (directory with __init__.py)
        package_path = self._find_package(path)
        if package_path is None:
            raise PluginError(
                f"Invalid plugin: no Python package found in {plugin_path}",
                plugin_path=str(path),
                details={"hint": "Ensure the plugin contains a directory with __init__.py"},
            )

        package_name = package_path.name

        # Find tools module
        tools_path = package_path / "tools" / "__init__.py"
        if not tools_path.exists():
            raise PluginError(
                f"Invalid plugin: no tools module found at {package_name}/tools/__init__.py",
                plugin_path=str(path),
                details={"expected": str(tools_path)},
            )

        # Find config file
        config_path = self._find_config(path, package_name)

        # Get tool classes from __all__
        tools_module_name = f"{package_name}.tools"
        tool_classes = self._get_tool_classes(path, tools_module_name)

        logger.info(
            "plugin.discovered",
            name=package_name,
            path=str(path),
            tools=tool_classes,
            has_config=config_path is not None,
        )

        return PluginManifest(
            name=package_name,
            path=path,
            package_path=package_path,
            tools_module=tools_module_name,
            config_path=config_path,
            tool_classes=tool_classes,
        )

    def load_tools(self, manifest: PluginManifest) -> list[ToolProtocol]:
        """
        Load and instantiate tools from a plugin.

        Args:
            manifest: Plugin manifest from discover_plugin()

        Returns:
            List of instantiated tool objects

        Raises:
            PluginError: If tool import or instantiation fails
        """
        tools: list[ToolProtocol] = []

        # Add plugin path to sys.path for imports
        plugin_path_str = str(manifest.path)
        if plugin_path_str not in sys.path:
            sys.path.insert(0, plugin_path_str)

        try:
            # Import the tools module
            try:
                tools_module = importlib.import_module(manifest.tools_module)
            except ImportError as e:
                # Check for missing dependencies
                error_msg = str(e)
                if "No module named" in error_msg:
                    missing = error_msg.split("'")[1] if "'" in error_msg else error_msg
                    raise PluginError(
                        f"Plugin dependency missing: {missing}",
                        plugin_path=str(manifest.path),
                        details={
                            "missing_dependency": missing,
                            "hint": f"Install with: pip install {missing}",
                        },
                    ) from e
                raise PluginError(
                    f"Failed to import plugin tools: {e}",
                    plugin_path=str(manifest.path),
                ) from e

            # Instantiate each tool class
            for class_name in manifest.tool_classes:
                tool_class = getattr(tools_module, class_name, None)
                if tool_class is None:
                    logger.warning(
                        "plugin.tool_class_not_found",
                        class_name=class_name,
                        module=manifest.tools_module,
                    )
                    continue

                try:
                    # Instantiate the tool
                    tool = tool_class()

                    # Validate it implements ToolProtocol
                    is_valid, error = self.validate_tool(tool)
                    if not is_valid:
                        raise PluginError(
                            f"Tool '{class_name}' doesn't implement ToolProtocol: {error}",
                            plugin_path=str(manifest.path),
                            details={"tool_class": class_name},
                        )

                    tools.append(tool)
                    logger.debug(
                        "plugin.tool_loaded",
                        tool_name=tool.name,
                        class_name=class_name,
                    )

                except TypeError as e:
                    # Constructor requires arguments
                    logger.warning(
                        "plugin.tool_instantiation_failed",
                        class_name=class_name,
                        error=str(e),
                    )
                    raise PluginError(
                        f"Failed to instantiate tool '{class_name}': {e}",
                        plugin_path=str(manifest.path),
                        details={
                            "tool_class": class_name,
                            "hint": "Tool classes should have a no-argument constructor or use defaults",
                        },
                    ) from e

        finally:
            # Remove from sys.path to avoid pollution
            if plugin_path_str in sys.path:
                sys.path.remove(plugin_path_str)

        logger.info(
            "plugin.tools_loaded",
            plugin=manifest.name,
            tool_count=len(tools),
            tool_names=[t.name for t in tools],
        )

        return tools

    def load_config(self, manifest: PluginManifest) -> dict[str, Any]:
        """
        Load plugin configuration from YAML.

        Args:
            manifest: Plugin manifest from discover_plugin()

        Returns:
            Configuration dictionary, or empty dict if no config found
        """
        if manifest.config_path is None:
            logger.debug("plugin.no_config", plugin=manifest.name)
            return {}

        try:
            with open(manifest.config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

            logger.debug(
                "plugin.config_loaded",
                plugin=manifest.name,
                config_path=str(manifest.config_path),
            )
            return config

        except yaml.YAMLError as e:
            raise PluginError(
                f"Invalid plugin config YAML: {e}",
                plugin_path=str(manifest.path),
                details={"config_path": str(manifest.config_path)},
            ) from e

    def validate_tool(self, tool: Any) -> tuple[bool, str | None]:
        """
        Validate that an object implements ToolProtocol.

        Args:
            tool: Object to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check required properties
        required_properties = ["name", "description", "parameters_schema"]
        for prop in required_properties:
            if not hasattr(tool, prop):
                return False, f"Missing required property: {prop}"
            # Check it's accessible (not raising)
            try:
                getattr(tool, prop)
            except Exception as e:
                return False, f"Property '{prop}' raised exception: {e}"

        # Check required methods
        required_methods = ["execute", "validate_params"]
        for method in required_methods:
            if not hasattr(tool, method):
                return False, f"Missing required method: {method}"
            if not callable(getattr(tool, method)):
                return False, f"'{method}' is not callable"

        # Verify execute is async
        execute_method = getattr(tool, "execute")
        if not inspect.iscoroutinefunction(execute_method):
            return False, "execute() must be an async method"

        return True, None

    def _find_package(self, plugin_path: Path) -> Path | None:
        """Find the Python package directory within the plugin."""
        # Check immediate subdirectories for __init__.py
        for item in plugin_path.iterdir():
            if item.is_dir() and (item / "__init__.py").exists():
                # Skip common non-package directories
                if item.name not in {"configs", "tests", "__pycache__", ".git"}:
                    return item

        # Check if plugin_path itself is a package
        if (plugin_path / "__init__.py").exists():
            return plugin_path

        return None

    def _find_config(self, plugin_path: Path, package_name: str) -> Path | None:
        """Find the config YAML file for the plugin."""
        # Try common config locations
        candidates = [
            plugin_path / "configs" / f"{package_name}.yaml",
            plugin_path / "configs" / f"{package_name}.yml",
            plugin_path / "config" / f"{package_name}.yaml",
            plugin_path / "config" / f"{package_name}.yml",
            plugin_path / f"{package_name}.yaml",
            plugin_path / f"{package_name}.yml",
            plugin_path / "config.yaml",
            plugin_path / "config.yml",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    def _get_tool_classes(self, plugin_path: Path, tools_module: str) -> list[str]:
        """Get tool class names from __all__ in tools module."""
        # Temporarily add to path for import
        plugin_path_str = str(plugin_path)
        if plugin_path_str not in sys.path:
            sys.path.insert(0, plugin_path_str)

        try:
            module = importlib.import_module(tools_module)
            tool_classes = getattr(module, "__all__", [])

            # If no __all__, try to find classes that look like tools
            if not tool_classes:
                tool_classes = [
                    name
                    for name, obj in inspect.getmembers(module, inspect.isclass)
                    if name.endswith("Tool") and not name.startswith("_")
                ]

            return list(tool_classes)

        except ImportError as e:
            logger.warning(
                "plugin.tools_module_import_failed",
                module=tools_module,
                error=str(e),
            )
            return []

        finally:
            if plugin_path_str in sys.path:
                sys.path.remove(plugin_path_str)
