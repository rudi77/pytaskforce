"""
Profile Writer
==============

CRUD operations for user-owned profile YAML files. Used by the
management UI to create / edit / delete profiles without going through
the existing :class:`CustomAgentRegistry` (which only handles the
narrow ``CustomAgent…`` shape).

Conventions:

* New profiles are written to ``~/.taskforce/agents/{name}.yaml`` by
  default. Existing profiles are updated **in place** so that
  framework- or package-shipped files keep their original location.
* Round-trip safety is achieved with ``ruamel.yaml`` so comments and
  ordering survive an edit cycle.
* Read-only profiles (anything outside the user-profile directory) can
  still be loaded but updates and deletes are rejected with a
  ``PermissionError``.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

import structlog
from ruamel.yaml import YAML

from taskforce.application.config_schema import (
    ConfigValidationError,
    validate_profile_config,
)
from taskforce.application.profile_loader import ProfileLoader

logger = structlog.get_logger(__name__)


def _round_trip_yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml


def get_user_profiles_dir() -> Path:
    """Return the directory user-created profiles live in.

    Override via ``TASKFORCE_USER_PROFILES_DIR``; defaults to
    ``~/.taskforce/agents``.
    """
    override = os.environ.get("TASKFORCE_USER_PROFILES_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".taskforce" / "agents"


class ProfileWriteError(RuntimeError):
    """Base error for profile write operations."""


class ProfileExists(ProfileWriteError):
    """Raised when creating a profile that already exists."""


class ProfileNotFound(ProfileWriteError):
    """Raised when updating or deleting a missing profile."""


class ProfileReadOnly(ProfileWriteError):
    """Raised when attempting to modify a framework- or package-shipped profile."""


class ProfileWriter:
    """Persist profile definitions as YAML files."""

    def __init__(
        self,
        loader: ProfileLoader | None = None,
        user_dir: Path | None = None,
    ) -> None:
        self._loader = loader or ProfileLoader()
        self._user_dir = user_dir or get_user_profiles_dir()
        self._logger = logger.bind(component="profile_writer")
        # Ensure the user dir is searched by the loader for subsequent reads.
        from taskforce.application.profile_loader import register_config_dir

        if self._user_dir.exists() or True:  # always register; dir is created lazily
            register_config_dir(self._user_dir)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not name.strip():
            raise ValueError("Profile name must not be empty")
        if any(ch in name for ch in ("/", "\\", "..", "\0")):
            raise ValueError("Profile name contains invalid characters")
        if name.startswith("."):
            raise ValueError("Profile name must not start with a dot")

    def _existing_path(self, name: str) -> Path | None:
        """Return path of an existing profile or ``None``."""
        return self._loader._find_profile_path(name)  # type: ignore[attr-defined]

    def _is_user_owned(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._user_dir.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _validate_payload(data: dict[str, Any]) -> None:
        # Profile schema is permissive (legacy dict-style tools are
        # tolerated). User-created profiles should be string-list only —
        # enforce that here so the editor can't smuggle in dict configs.
        tools = data.get("tools")
        if tools is not None:
            if not isinstance(tools, list):
                raise ProfileWriteError("tools must be a list of strings")
            for index, entry in enumerate(tools):
                if not isinstance(entry, str):
                    raise ProfileWriteError(
                        f"tools[{index}] must be a string (got {type(entry).__name__})"
                    )
        try:
            validate_profile_config(data)
        except ConfigValidationError as exc:
            raise ProfileWriteError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Read-with-context helper used by routes
    # ------------------------------------------------------------------

    def get_path(self, name: str) -> Path:
        """Return the on-disk path of a profile or raise ``ProfileNotFound``."""
        path = self._existing_path(name)
        if path is None:
            raise ProfileNotFound(f"Profile '{name}' not found")
        return path

    def is_writable(self, name: str) -> bool:
        path = self._existing_path(name)
        if path is None:
            return True  # creating in user dir
        return self._is_user_owned(path)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, name: str, data: dict[str, Any]) -> Path:
        """Create a new YAML profile under the user profiles directory."""
        self._validate_name(name)
        existing = self._existing_path(name)
        if existing is not None:
            raise ProfileExists(
                f"Profile '{name}' already exists at {existing}"
            )
        self._validate_payload(data)

        target = self._user_dir / f"{name}.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        self._dump(target, data)
        self._logger.info("profile_created", name=name, path=str(target))
        return target

    def update(self, name: str, data: dict[str, Any]) -> Path:
        """Update a user-owned profile in place; framework profiles are read-only."""
        self._validate_name(name)
        path = self._existing_path(name)
        if path is None:
            raise ProfileNotFound(f"Profile '{name}' not found")
        if not self._is_user_owned(path):
            raise ProfileReadOnly(
                f"Profile '{name}' is read-only (lives at {path}). Copy it to "
                f"{self._user_dir} to edit."
            )
        if path.name.endswith(".agent.md"):
            raise ProfileReadOnly(
                "Editing .agent.md profiles is not supported yet — use the "
                "YAML form."
            )
        self._validate_payload(data)
        self._dump(path, data)
        self._logger.info("profile_updated", name=name, path=str(path))
        return path

    def delete(self, name: str) -> Path:
        """Delete a user-owned profile."""
        self._validate_name(name)
        path = self._existing_path(name)
        if path is None:
            raise ProfileNotFound(f"Profile '{name}' not found")
        if not self._is_user_owned(path):
            raise ProfileReadOnly(
                f"Profile '{name}' is read-only (lives at {path})."
            )
        path.unlink()
        self._logger.info("profile_deleted", name=name, path=str(path))
        return path

    # ------------------------------------------------------------------
    # Dump helpers
    # ------------------------------------------------------------------

    def _dump(self, path: Path, data: dict[str, Any]) -> None:
        yaml = _round_trip_yaml()
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                existing = yaml.load(handle)
            if isinstance(existing, dict):
                _merge_preserve(existing, data)
                payload = existing
            else:
                payload = data
        else:
            payload = data

        buffer = io.StringIO()
        yaml.dump(payload, buffer)
        path.write_text(buffer.getvalue(), encoding="utf-8")


def _merge_preserve(target: Any, source: dict[str, Any]) -> None:
    """Patch ``target`` in-place with values from ``source``.

    Top-level keys absent from ``source`` are **kept** so editor forms can
    submit a partial patch without nuking butler-specific fields they don't
    know about (``event_sources``, ``schedule_jobs``, ``trigger_rules``,
    ``learning``, ``notifications``, ``roles``, etc.). Nested dicts merge
    recursively so comments stay attached to surviving keys; lists and
    scalars in ``source`` replace whatever was at ``target[key]``.

    To explicitly delete a key, send ``None``.
    """
    if not isinstance(target, dict):
        return

    for key, value in source.items():
        if value is None and key in target:
            del target[key]
            continue
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(value, dict)
        ):
            _merge_preserve(target[key], value)
        else:
            target[key] = value
