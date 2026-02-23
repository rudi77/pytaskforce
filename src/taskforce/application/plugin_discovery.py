"""Backward-compatibility re-exports for plugin discovery.

All functionality has been consolidated into ``plugin_loader``.
This module re-exports every public name so that existing imports
of the form ``from taskforce.application.plugin_discovery import X``
continue to work without modification.
"""

from taskforce.application.plugin_loader import (  # noqa: F401
    PluginInfo,
    PluginProtocol,
    PluginRegistry,
    discover_plugins,
    get_loaded_plugins,
    get_plugin,
    get_plugin_registry,
    is_enterprise_available,
    load_all_plugins,
    load_plugin,
    shutdown_plugins,
)

__all__ = [
    "PluginProtocol",
    "PluginInfo",
    "PluginRegistry",
    "get_plugin_registry",
    "discover_plugins",
    "load_plugin",
    "load_all_plugins",
    "get_loaded_plugins",
    "get_plugin",
    "shutdown_plugins",
    "is_enterprise_available",
]
