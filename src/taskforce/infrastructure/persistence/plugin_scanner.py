"""
Plugin Scanner
==============

Discovers and loads plugin-based agent definitions from the filesystem.

Scans well-known directories (``src/taskforce_extensions/plugins/``,
``examples/``, ``plugins/``) for valid plugin manifests and converts them
into ``PluginAgentDefinition`` domain objects.

Clean Architecture Notes:
- Infrastructure layer: performs filesystem I/O and plugin discovery
- Depends on core/domain/agent_models.py for PluginAgentDefinition
- Uses application/plugin_loader.py via lazy import to avoid circular deps
"""

from pathlib import Path

import structlog

from taskforce.core.domain.agent_models import PluginAgentDefinition

logger = structlog.get_logger()


def discover_plugin_agents(
    base_path: Path,
) -> list[PluginAgentDefinition]:
    """
    Discover plugin agents from standard plugin directories.

    Scans the following directories (in order):
    - ``<base_path>/src/taskforce_extensions/plugins/``
    - ``<base_path>/examples/``
    - ``<base_path>/plugins/`` (legacy location)

    Hidden directories and ``__*__`` directories are skipped.

    Args:
        base_path: Project root path used to locate plugin directories.

    Returns:
        List of PluginAgentDefinition objects for all valid plugins found.
    """
    plugins: list[PluginAgentDefinition] = []

    plugin_dirs = [
        base_path / "src" / "taskforce_extensions" / "plugins",
        base_path / "examples",
        base_path / "plugins",
    ]

    for plugin_base_dir in plugin_dirs:
        if not plugin_base_dir.exists():
            continue

        for plugin_dir in plugin_base_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            if plugin_dir.name.startswith(".") or plugin_dir.name.startswith("__"):
                continue

            try:
                plugin_agent = load_plugin_agent(plugin_dir, plugin_base_dir, base_path)
                if plugin_agent:
                    plugins.append(plugin_agent)
            except Exception as e:
                logger.debug(
                    "plugin.discovery.skipped",
                    plugin_dir=str(plugin_dir),
                    error=str(e),
                )

    return plugins


def load_plugin_agent(
    plugin_dir: Path,
    plugin_base_dir: Path,
    base_path: Path,
) -> PluginAgentDefinition | None:
    """
    Load a single plugin agent from a plugin directory.

    Uses ``PluginLoader`` to discover and validate the plugin manifest,
    then extracts metadata into a ``PluginAgentDefinition``.

    Args:
        plugin_dir: Path to the individual plugin directory.
        plugin_base_dir: Parent directory that contains multiple plugins.
        base_path: Project root for computing relative paths.

    Returns:
        PluginAgentDefinition if a valid plugin was found, None otherwise.
    """
    try:
        from taskforce.application.plugin_loader import PluginLoader

        loader = PluginLoader()
        manifest = loader.discover_plugin(str(plugin_dir))

        plugin_config = loader.load_config(manifest)

        agent_id = plugin_dir.name

        try:
            plugin_path = plugin_dir.relative_to(base_path)
        except ValueError:
            logger.warning(
                "plugin.path.not_relative",
                plugin_dir=str(plugin_dir),
                base_path=str(base_path),
            )
            plugin_path = plugin_dir

        description = plugin_config.get("description", f"Plugin agent: {manifest.name}")
        specialist = plugin_config.get("specialist")
        mcp_servers = plugin_config.get("mcp_servers", [])

        return PluginAgentDefinition(
            agent_id=agent_id,
            name=manifest.name.replace("_", " ").title(),
            description=description,
            plugin_path=str(plugin_path).replace("\\", "/"),
            tool_classes=manifest.tool_classes,
            specialist=specialist,
            mcp_servers=mcp_servers,
        )

    except (FileNotFoundError, ImportError) as e:
        logger.debug(
            "plugin.load.failed",
            plugin_dir=str(plugin_dir),
            error=str(e),
            error_type=type(e).__name__,
        )
        return None
    except Exception as e:
        # Check for PluginError without hard import at module level
        if type(e).__name__ == "PluginError":
            logger.debug(
                "plugin.load.failed",
                plugin_dir=str(plugin_dir),
                error=str(e),
                error_type=type(e).__name__,
            )
        else:
            logger.warning(
                "plugin.load.unexpected_error",
                plugin_dir=str(plugin_dir),
                error=str(e),
                error_type=type(e).__name__,
            )
        return None


def find_plugin_agent(
    agent_id: str,
    base_path: Path,
) -> PluginAgentDefinition | None:
    """
    Find a specific plugin agent by its identifier.

    Looks for a directory named ``agent_id`` under ``examples/`` and
    ``plugins/`` directories relative to ``base_path``.

    Args:
        agent_id: Agent identifier (matches plugin directory name).
        base_path: Project root path.

    Returns:
        PluginAgentDefinition if found, None otherwise.
    """
    plugin_dirs = [
        base_path / "examples",
        base_path / "plugins",
    ]

    for plugin_base_dir in plugin_dirs:
        if not plugin_base_dir.exists():
            continue

        plugin_dir = plugin_base_dir / agent_id
        if plugin_dir.exists() and plugin_dir.is_dir():
            return load_plugin_agent(plugin_dir, plugin_base_dir, base_path)

    return None
