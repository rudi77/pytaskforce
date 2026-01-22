"""Plugin discovery system for Taskforce extensibility.

This module provides entry-point based plugin discovery, allowing external
packages (like taskforce-enterprise) to extend Taskforce functionality
without modifying core code.

Plugin types:
- taskforce.plugins: Main plugin classes that can provide middleware, routers, etc.
- taskforce.middleware: Direct middleware registration
- taskforce.routers: Direct router registration

Example plugin registration in pyproject.toml:
    [project.entry-points."taskforce.plugins"]
    enterprise = "taskforce_enterprise.integration.plugin:EnterprisePlugin"
"""

from typing import Any, Callable, Optional, Protocol, runtime_checkable
from dataclasses import dataclass, field
import structlog

try:
    from importlib.metadata import entry_points
except ImportError:
    from importlib_metadata import entry_points  # type: ignore


logger = structlog.get_logger(__name__)


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
    plugin_class: Optional[type] = None
    instance: Optional[PluginProtocol] = None
    initialized: bool = False
    error: Optional[str] = None


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
_plugin_registry: Optional[PluginRegistry] = None


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

        except Exception as e:
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


def load_plugin(plugin_info: PluginInfo, config: Optional[dict[str, Any]] = None) -> bool:
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
        if hasattr(instance, 'initialize'):
            instance.initialize(config or {})

        plugin_info.initialized = True

        logger.info(
            "plugin.loaded",
            plugin_name=plugin_info.name,
            version=getattr(instance, 'version', 'unknown'),
        )

        return True

    except Exception as e:
        plugin_info.error = str(e)
        logger.error(
            "plugin.load_failed",
            plugin_name=plugin_info.name,
            error=str(e),
            error_type=type(e).__name__,
        )
        return False


def load_all_plugins(config: Optional[dict[str, Any]] = None) -> PluginRegistry:
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
                if hasattr(plugin_info.instance, 'get_middleware'):
                    middleware = plugin_info.instance.get_middleware()
                    if middleware:
                        registry.middleware.extend(middleware)
                        logger.debug(
                            "plugin.middleware_registered",
                            plugin_name=plugin_info.name,
                            middleware_count=len(middleware),
                        )

                if hasattr(plugin_info.instance, 'get_routers'):
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


def get_plugin(name: str) -> Optional[PluginProtocol]:
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
                if hasattr(info.instance, 'shutdown'):
                    info.instance.shutdown()
                logger.debug("plugin.shutdown", plugin_name=name)
            except Exception as e:
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
