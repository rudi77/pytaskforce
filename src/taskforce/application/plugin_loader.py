"""
Unified Plugin Loader and Discovery for Taskforce

This module consolidates two plugin mechanisms:

1. **Directory-based plugin loading** (PluginLoader class):
   Discovers, loads, and validates external agent plugins with custom tools.
   Plugins are Python packages that contain tool implementations compatible
   with ToolProtocol.

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

2. **Entry-point-based plugin discovery** (discover_plugins, load_all_plugins, etc.):
   Allows external packages (like taskforce-enterprise) to extend Taskforce
   functionality without modifying core code via setuptools entry points.

   Plugin types:
   - taskforce.plugins: Main plugin classes that can provide middleware, routers, etc.
   - taskforce.middleware: Direct middleware registration
   - taskforce.routers: Direct router registration

   Example plugin registration in pyproject.toml:
       [project.entry-points."taskforce.plugins"]
       enterprise = "taskforce_enterprise.integration.plugin:EnterprisePlugin"
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import structlog
import yaml

from taskforce.core.domain.errors import PluginError
from taskforce.core.interfaces.tools import ToolProtocol

try:
    from importlib.metadata import entry_points
except ImportError:
    from importlib_metadata import entry_points  # type: ignore


logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Directory-based plugin loading (PluginManifest + PluginLoader)
# ---------------------------------------------------------------------------


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

    skills_path: Path | None = None
    """Path to skills directory, or None if not found."""

    skill_names: list[str] = field(default_factory=list)
    """List of discovered skill names in the plugin."""


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
            plugin_path: Path to the plugin directory (relative or absolute).
                        Supports backward compatibility: if path starts with "plugins/",
                        also checks "src/taskforce_extensions/plugins/".

        Returns:
            PluginManifest with plugin metadata

        Raises:
            FileNotFoundError: If plugin path doesn't exist
            PluginError: If plugin structure is invalid
        """
        # Resolve to absolute path
        path = Path(plugin_path).resolve()

        # Backward compatibility: if old plugins/ path doesn't exist, try new location
        if not path.exists() and plugin_path.startswith("plugins/"):
            # Try new location: src/taskforce_extensions/plugins/...
            new_path = Path("src/taskforce_extensions") / plugin_path
            if new_path.exists():
                path = new_path.resolve()
                logger.debug(
                    "plugin_path_migrated",
                    old_path=plugin_path,
                    new_path=str(new_path),
                )

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

        # Find skills directory and discover skills
        skills_path = self._find_skills_path(path)
        skill_names = self._get_skill_names(skills_path) if skills_path else []

        logger.info(
            "plugin.discovered",
            name=package_name,
            path=str(path),
            tools=tool_classes,
            has_config=config_path is not None,
            has_skills=skills_path is not None,
            skill_names=skill_names,
        )

        return PluginManifest(
            name=package_name,
            path=path,
            package_path=package_path,
            tools_module=tools_module_name,
            config_path=config_path,
            tool_classes=tool_classes,
            skills_path=skills_path,
            skill_names=skill_names,
        )

    def load_tools(
        self,
        manifest: PluginManifest,
        tool_configs: list[str | dict[str, Any]] | None = None,
        llm_provider: Any | None = None,
        embedding_service: Any | None = None,
    ) -> list[ToolProtocol]:
        """
        Load and instantiate tools from a plugin.

        Args:
            manifest: Plugin manifest from discover_plugin()
            tool_configs: Optional tool configurations from plugin config.
                Can be a list of strings (tool names) or dicts with 'name' and 'params'.
                Example:
                    [
                        "simple_tool",  # No params
                        {"name": "complex_tool", "params": {"path": "${PLUGIN_PATH}/data"}}
                    ]
            llm_provider: Optional LLM provider to inject into tools that require it.
                Tools with 'llm_provider' in their __init__ signature will receive this.
            embedding_service: Optional embedding service to inject into tools that require it.
                Tools with 'embedding_service' in their __init__ signature will receive this.

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

            # Build tool name to class name mapping by instantiating temporarily
            tool_name_to_class = self._build_tool_name_mapping(tools_module, manifest.tool_classes)

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
                    # Get tool params from config if available
                    tool_params = self._get_tool_params(
                        class_name, tool_name_to_class, tool_configs, manifest
                    )

                    # Initialize params dict if None
                    if tool_params is None:
                        tool_params = {}

                    # Check if tool requires llm_provider and inject it
                    if llm_provider is not None:
                        sig = inspect.signature(tool_class.__init__)
                        if "llm_provider" in sig.parameters:
                            tool_params["llm_provider"] = llm_provider
                            logger.debug(
                                "plugin.tool_llm_provider_injected",
                                class_name=class_name,
                            )

                    # Check if tool requires embedding_service and inject it
                    if embedding_service is not None:
                        sig = inspect.signature(tool_class.__init__)
                        if "embedding_service" in sig.parameters:
                            tool_params["embedding_service"] = embedding_service
                            logger.debug(
                                "plugin.tool_embedding_service_injected",
                                class_name=class_name,
                            )

                    # Instantiate the tool with or without params
                    if tool_params:
                        tool = tool_class(**tool_params)
                        logger.debug(
                            "plugin.tool_instantiated_with_params",
                            class_name=class_name,
                            params=list(tool_params.keys()),
                        )
                    else:
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

    def _build_tool_name_mapping(
        self, tools_module: Any, tool_classes: list[str]
    ) -> dict[str, str]:
        """
        Build a mapping from tool.name to class name.

        This is needed because tool configs reference tools by their runtime name
        (e.g., 'apply_kontierung_rules') but we need to find the class name
        (e.g., 'RuleEngineTool').

        Args:
            tools_module: The imported tools module
            tool_classes: List of tool class names

        Returns:
            Dict mapping tool name to class name
        """
        mapping: dict[str, str] = {}

        for class_name in tool_classes:
            tool_class = getattr(tools_module, class_name, None)
            if tool_class is None:
                continue

            # Try to get the tool name from the class
            # First check if it's a property or attribute
            try:
                # Try instantiating to get the name property
                # This is safe since we're just reading the name
                if hasattr(tool_class, "name"):
                    # Check if name is a property (descriptor)
                    name_attr = getattr(type(tool_class), "name", None)
                    if isinstance(name_attr, property):
                        # Need to instantiate to get property value
                        try:
                            temp_tool = tool_class()
                            mapping[temp_tool.name] = class_name
                        except TypeError:
                            # Can't instantiate without args, skip mapping
                            pass
                    else:
                        # It's a class attribute
                        mapping[tool_class.name] = class_name
            except (AttributeError, TypeError, RuntimeError):
                # Skip if we can't determine the name
                pass

        return mapping

    def _get_tool_params(
        self,
        class_name: str,
        tool_name_to_class: dict[str, str],
        tool_configs: list[str | dict[str, Any]] | None,
        manifest: PluginManifest,
    ) -> dict[str, Any] | None:
        """
        Get parameters for a tool from the tool configs.

        Args:
            class_name: The tool class name (e.g., 'RuleEngineTool')
            tool_name_to_class: Mapping from tool.name to class name
            tool_configs: List of tool configurations
            manifest: Plugin manifest for path resolution

        Returns:
            Dict of parameters or None if no config found
        """
        if not tool_configs:
            return None

        # Find the tool name that maps to this class
        tool_name = None
        for name, cls_name in tool_name_to_class.items():
            if cls_name == class_name:
                tool_name = name
                break

        if not tool_name:
            return None

        # Search for config matching this tool
        for config in tool_configs:
            if isinstance(config, str):
                # Simple string config, no params
                continue

            if isinstance(config, dict):
                config_name = config.get("name")
                if config_name == tool_name:
                    params = config.get("params", {})
                    if params:
                        # Resolve path variables in params
                        return self._resolve_params(params, manifest)

        return None

    def _resolve_params(self, params: dict[str, Any], manifest: PluginManifest) -> dict[str, Any]:
        """
        Resolve variables in parameter values.

        Supports:
            ${PLUGIN_PATH} - Replaced with absolute path to plugin directory

        Args:
            params: Parameter dictionary
            manifest: Plugin manifest for path resolution

        Returns:
            Resolved parameters
        """
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved[key] = self._resolve_path_variables(value, manifest)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_params(value, manifest)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_path_variables(v, manifest) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                resolved[key] = value
        return resolved

    def _resolve_path_variables(self, value: str, manifest: PluginManifest) -> str:
        """
        Replace path variables in a string value.

        Args:
            value: String that may contain variables
            manifest: Plugin manifest for path resolution

        Returns:
            String with variables resolved
        """
        return value.replace("${PLUGIN_PATH}", str(manifest.path))

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
            except (AttributeError, TypeError) as e:
                return False, f"Property '{prop}' raised exception: {e}"

        # Check required methods
        required_methods = ["execute", "validate_params"]
        for method in required_methods:
            if not hasattr(tool, method):
                return False, f"Missing required method: {method}"
            if not callable(getattr(tool, method)):
                return False, f"'{method}' is not callable"

        # Verify execute is async
        execute_method = tool.execute
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

    def _find_skills_path(self, plugin_path: Path) -> Path | None:
        """Find the skills directory within the plugin.

        Looks for a 'skills' directory at the plugin root level.
        Each subdirectory containing a SKILL.md file is considered a skill.

        Args:
            plugin_path: Path to the plugin directory

        Returns:
            Path to skills directory, or None if not found
        """
        skills_path = plugin_path / "skills"
        if skills_path.exists() and skills_path.is_dir():
            return skills_path
        return None

    def _get_skill_names(self, skills_path: Path) -> list[str]:
        """Get list of skill names from the skills directory.

        Each subdirectory containing a SKILL.md file is considered a skill.

        Args:
            skills_path: Path to the skills directory

        Returns:
            List of skill names (directory names)
        """
        skill_names: list[str] = []

        if not skills_path or not skills_path.exists():
            return skill_names

        for item in skills_path.iterdir():
            if item.is_dir():
                skill_md = item / "SKILL.md"
                if skill_md.exists():
                    skill_names.append(item.name)
                    logger.debug(
                        "plugin.skill_discovered",
                        skill_name=item.name,
                        skill_path=str(item),
                    )

        return sorted(skill_names)

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


# ---------------------------------------------------------------------------
# Entry-point-based plugin discovery (PluginProtocol, PluginInfo, etc.)
# ---------------------------------------------------------------------------


@runtime_checkable
class PluginProtocol(Protocol):
    """Protocol that plugins must implement.

    Plugins provide extensibility hooks for:
    - Middleware (authentication, logging, etc.)
    - API routers (admin endpoints, etc.)
    - Factory extensions (additional tools, providers, etc.)
    """

    name: str
    version: str

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the plugin with configuration.

        Args:
            config: Plugin-specific configuration dictionary
        """
        ...

    def get_middleware(self) -> list[Any]:
        """Return middleware classes to add to the application.

        Returns:
            List of middleware classes or instances
        """
        ...

    def get_routers(self) -> list[Any]:
        """Return FastAPI routers to include in the application.

        Returns:
            List of APIRouter instances
        """
        ...

    def extend_factory(self, factory: Any) -> None:
        """Extend the AgentFactory with additional capabilities.

        Args:
            factory: The AgentFactory instance to extend
        """
        ...

    def shutdown(self) -> None:
        """Clean up resources when the plugin is unloaded."""
        ...


@dataclass
class PluginInfo:
    """Information about a discovered plugin.

    Attributes:
        name: Plugin name from entry point
        entry_point: The entry point string
        plugin_class: The loaded plugin class
        instance: Instantiated plugin (after loading)
        initialized: Whether the plugin has been initialized
        error: Any error that occurred during loading
    """

    name: str
    entry_point: str
    plugin_class: type | None = None
    instance: PluginProtocol | None = None
    initialized: bool = False
    error: str | None = None


@dataclass
class PluginRegistry:
    """Registry of discovered and loaded plugins.

    Attributes:
        plugins: Dictionary of plugin name to PluginInfo
        middleware: List of middleware from all plugins
        routers: List of routers from all plugins
    """

    plugins: dict[str, PluginInfo] = field(default_factory=dict)
    middleware: list[Any] = field(default_factory=list)
    routers: list[Any] = field(default_factory=list)


# Global plugin registry
_plugin_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    """Get the global plugin registry, creating if needed.

    Returns:
        The global PluginRegistry instance
    """
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry


def discover_plugins(group: str = "taskforce.plugins") -> list[PluginInfo]:
    """Discover plugins registered via entry points.

    Args:
        group: The entry point group to search

    Returns:
        List of PluginInfo for discovered plugins
    """
    registry = get_plugin_registry()
    discovered = []

    try:
        eps = entry_points(group=group)
    except TypeError:
        # Python < 3.10 compatibility
        all_eps = entry_points()
        eps = all_eps.get(group, [])

    for ep in eps:
        plugin_info = PluginInfo(
            name=ep.name,
            entry_point=f"{ep.value}",
        )

        try:
            # Load the plugin class
            plugin_class = ep.load()
            plugin_info.plugin_class = plugin_class

            logger.info(
                "plugin.discovered",
                plugin_name=ep.name,
                entry_point=ep.value,
            )

        except (ImportError, AttributeError, ModuleNotFoundError) as e:
            plugin_info.error = str(e)
            logger.warning(
                "plugin.discovery_failed",
                plugin_name=ep.name,
                entry_point=ep.value,
                error=str(e),
                error_type=type(e).__name__,
            )

        discovered.append(plugin_info)
        registry.plugins[ep.name] = plugin_info

    return discovered


def load_plugin(plugin_info: PluginInfo, config: dict[str, Any] | None = None) -> bool:
    """Load and initialize a discovered plugin.

    Args:
        plugin_info: The plugin info to load
        config: Optional configuration for the plugin

    Returns:
        True if loaded successfully, False otherwise
    """
    if plugin_info.plugin_class is None:
        logger.warning(
            "plugin.load_failed",
            plugin_name=plugin_info.name,
            reason="no_plugin_class",
        )
        return False

    if plugin_info.initialized:
        logger.debug(
            "plugin.already_initialized",
            plugin_name=plugin_info.name,
        )
        return True

    try:
        # Instantiate the plugin
        instance = plugin_info.plugin_class()
        plugin_info.instance = instance

        # Initialize with config
        if hasattr(instance, "initialize"):
            instance.initialize(config or {})

        plugin_info.initialized = True

        logger.info(
            "plugin.loaded",
            plugin_name=plugin_info.name,
            version=getattr(instance, "version", "unknown"),
        )

        return True

    except (ImportError, AttributeError, TypeError, ModuleNotFoundError) as e:
        plugin_info.error = str(e)
        logger.error(
            "plugin.load_failed",
            plugin_name=plugin_info.name,
            error=str(e),
            error_type=type(e).__name__,
        )
        return False


def load_all_plugins(config: dict[str, Any] | None = None) -> PluginRegistry:
    """Discover and load all plugins.

    Args:
        config: Optional configuration dictionary with plugin-specific sections

    Returns:
        PluginRegistry with all loaded plugins
    """
    registry = get_plugin_registry()

    # Discover plugins
    discovered = discover_plugins()

    # Load each plugin
    for plugin_info in discovered:
        plugin_config = (config or {}).get(plugin_info.name, {})
        if load_plugin(plugin_info, plugin_config):
            # Collect middleware and routers from loaded plugin
            if plugin_info.instance:
                if hasattr(plugin_info.instance, "get_middleware"):
                    middleware = plugin_info.instance.get_middleware()
                    if middleware:
                        registry.middleware.extend(middleware)
                        logger.debug(
                            "plugin.middleware_registered",
                            plugin_name=plugin_info.name,
                            middleware_count=len(middleware),
                        )

                if hasattr(plugin_info.instance, "get_routers"):
                    routers = plugin_info.instance.get_routers()
                    if routers:
                        registry.routers.extend(routers)
                        logger.debug(
                            "plugin.routers_registered",
                            plugin_name=plugin_info.name,
                            router_count=len(routers),
                        )

    logger.info(
        "plugin.all_loaded",
        total_plugins=len([p for p in registry.plugins.values() if p.initialized]),
        total_middleware=len(registry.middleware),
        total_routers=len(registry.routers),
    )

    return registry


def get_loaded_plugins() -> list[PluginProtocol]:
    """Get all successfully loaded plugin instances.

    Returns:
        List of initialized plugin instances
    """
    registry = get_plugin_registry()
    return [
        info.instance
        for info in registry.plugins.values()
        if info.instance is not None and info.initialized
    ]


def get_plugin(name: str) -> PluginProtocol | None:
    """Get a specific plugin by name.

    Args:
        name: The plugin name

    Returns:
        Plugin instance if found and loaded, None otherwise
    """
    registry = get_plugin_registry()
    info = registry.plugins.get(name)
    if info and info.initialized and info.instance:
        return info.instance
    return None


def shutdown_plugins() -> None:
    """Shutdown all loaded plugins."""
    registry = get_plugin_registry()

    for name, info in registry.plugins.items():
        if info.instance and info.initialized:
            try:
                if hasattr(info.instance, "shutdown"):
                    info.instance.shutdown()
                logger.debug("plugin.shutdown", plugin_name=name)
            except Exception as e:  # Broad catch intentional: shutdown must not propagate any error
                logger.warning(
                    "plugin.shutdown_failed",
                    plugin_name=name,
                    error=str(e),
                )

    # Clear the registry
    registry.plugins.clear()
    registry.middleware.clear()
    registry.routers.clear()


def is_enterprise_available() -> bool:
    """Check if taskforce-enterprise is installed and available.

    Returns:
        True if enterprise features are available
    """
    registry = get_plugin_registry()

    # Check if already loaded
    if "enterprise" in registry.plugins:
        return registry.plugins["enterprise"].initialized

    # Try to discover
    discovered = discover_plugins()
    for plugin_info in discovered:
        if plugin_info.name == "enterprise" and plugin_info.plugin_class is not None:
            return True

    return False
