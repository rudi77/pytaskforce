"""Owner-only file writes for secrets (Fernet keys, token files).

A plain ``write_bytes``/``write_text`` creates files with the process
umask default — typically ``0o644``, i.e. world-readable. For files
holding a master key or bearer tokens that means any local user can
read the secret. ``write_private_*`` creates the file owner-only from
the start and tightens it cross-platform afterwards.

On POSIX ``chmod(0o600)`` is the mechanism. On Windows ``chmod`` only
toggles the read-only bit and does **not** restrict other users, so we
fall back to ``icacls`` to drop ACL inheritance and grant only the
current user. Permission failures are logged loudly — never swallowed
silently — because a failure leaves a secret world-readable.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def restrict_to_owner(path: str | Path) -> None:
    """Restrict *path* to owner-only access (chmod 0600 / Windows ACL)."""
    path = Path(path)
    if os.name == "nt":
        _restrict_windows(path)
        return
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        logger.warning("secure_file.chmod_failed", path=str(path), error=str(exc))


def _restrict_windows(path: Path) -> None:
    """Restrict a file to the current user via ``icacls``."""
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if not user:
        logger.warning("secure_file.windows_acl_skipped_no_user", path=str(path))
        return
    try:
        # /inheritance:r drops inherited ACEs; /grant:r replaces the ACL
        # with a single entry granting the current user full control.
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("secure_file.windows_acl_failed", path=str(path), error=str(exc))


def write_private_bytes(path: str | Path, data: bytes) -> None:
    """Write *data* to *path* with owner-only permissions.

    On POSIX the file is created with mode ``0o600`` directly (no
    world-readable window), then re-tightened. On Windows the create
    mode is largely ignored, so the ACL is applied afterwards.
    """
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    restrict_to_owner(path)


def write_private_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write *text* to *path* with owner-only permissions."""
    write_private_bytes(path, text.encode(encoding))
