"""Google Workspace tools for taskforce agents.

Provides Gmail, Google Drive, and Google Calendar tools that can be
attached to any agent profile via the ``taskforce.tools`` entry-point
group (resolved by :mod:`taskforce.application.agent_plugin_registry`).

See [ADR-027](../../docs/adr/adr-027-generic-agent-daemon.md) for the
broader framework refactor, and the Butler→YAML plan for the migration
that moved these tools out of ``taskforce_butler``.
"""

__version__ = "0.1.0"
