"""SettingsStoreProtocol — UI-driven runtime configuration store.

The settings store is the seam through which the UI mutates runtime
configuration that doesn't fit a profile YAML — LLM provider keys,
channel credentials, default-agent selection, etc. Each "section" is a
free-form JSON document keyed by a stable name (see
:mod:`taskforce.core.domain.settings` for the constants).

Stores are expected to keep secrets at rest using whatever encryption
the deployment provides. The framework's default file-based
implementation uses Fernet-encrypted JSON; alternative backends
(database, vault) just have to satisfy the protocol.

Single-user deployments use the framework's file-based default.
Multi-tenant deployments install a per-tenant store via
``set_settings_store_override`` in
:mod:`taskforce.application.infrastructure_overrides`.

The protocol is intentionally synchronous because callers typically
only touch settings on infrequent admin paths (UI saves, startup hydration).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SettingsStoreProtocol(Protocol):
    """Persisted, opaque key/value store for UI-managed runtime settings."""

    def get(self, section: str) -> dict[str, Any] | None:
        """Return the section's stored payload, or ``None`` if absent."""
        ...

    def put(self, section: str, value: dict[str, Any]) -> None:
        """Replace the section's payload with ``value``.

        Implementations should write atomically so a partial failure
        cannot corrupt the on-disk state.
        """
        ...

    def delete(self, section: str) -> None:
        """Remove the section. No-op if it does not exist."""
        ...

    def list_sections(self) -> list[str]:
        """Return the set of section names currently present."""
        ...
