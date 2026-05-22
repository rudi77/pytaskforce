"""Tests for owner-only secret file writes (#282)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from taskforce.core.utils.secure_file import (
    restrict_to_owner,
    write_private_bytes,
    write_private_text,
)


def _is_owner_only(path: Path) -> bool:
    """True when no group/other permission bits are set (POSIX only)."""
    mode = stat.S_IMODE(path.stat().st_mode)
    return mode & 0o077 == 0


def test_write_private_bytes_writes_content(tmp_path: Path) -> None:
    target = tmp_path / "secret.key"
    write_private_bytes(target, b"fernet-key-bytes")
    assert target.read_bytes() == b"fernet-key-bytes"


def test_write_private_text_writes_content(tmp_path: Path) -> None:
    target = tmp_path / "peers.json"
    write_private_text(target, '{"token": "abc"}')
    assert target.read_text(encoding="utf-8") == '{"token": "abc"}'


def test_write_private_bytes_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "secret.key"
    write_private_bytes(target, b"old-and-longer")
    write_private_bytes(target, b"new")
    assert target.read_bytes() == b"new"


def test_write_private_bytes_is_owner_only(tmp_path: Path) -> None:
    """The created secret file must not be group/other readable (#282)."""
    target = tmp_path / "secret.key"
    write_private_bytes(target, b"k")
    if os.name == "nt":
        # POSIX mode bits don't apply; the icacls ACL path runs instead.
        # We assert the helper completed and produced the file.
        assert target.exists()
    else:
        assert _is_owner_only(target), oct(target.stat().st_mode)


def test_restrict_to_owner_tightens_loose_file(tmp_path: Path) -> None:
    """restrict_to_owner clamps an already-world-readable file."""
    target = tmp_path / "loose.txt"
    target.write_text("data", encoding="utf-8")
    if os.name != "nt":
        os.chmod(target, 0o644)

    restrict_to_owner(target)

    if os.name != "nt":
        assert _is_owner_only(target), oct(target.stat().st_mode)
    else:
        assert target.exists()
