"""Tests for the crash-safe atomic file-write helper (#319)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from taskforce.core.utils import atomic_io
from taskforce.core.utils.atomic_io import atomic_write_text


async def test_atomic_write_text_writes_content(tmp_path: Path) -> None:
    """A successful write produces exactly the requested content."""
    target = tmp_path / "state.json"
    await atomic_write_text(target, '{"hello": "world"}')

    assert target.read_text(encoding="utf-8") == '{"hello": "world"}'


async def test_atomic_write_text_overwrites_existing(tmp_path: Path) -> None:
    """An existing file is fully replaced, not appended to."""
    target = tmp_path / "state.json"
    target.write_text("OLD CONTENT THAT IS LONGER", encoding="utf-8")

    await atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"


async def test_atomic_write_text_fsyncs_before_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The temp file is fsync'd before the rename — the durability guarantee.

    Without the fsync a crash can leave a present-but-empty file. We assert
    fsync runs and runs *before* os.replace.
    """
    events: list[str] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def _spy_fsync(fd: int) -> None:
        events.append("fsync")
        real_fsync(fd)

    def _spy_replace(src: object, dst: object) -> None:
        events.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(atomic_io.os, "fsync", _spy_fsync)
    monkeypatch.setattr(atomic_io.os, "replace", _spy_replace)

    await atomic_write_text(tmp_path / "state.json", "payload")

    assert events == ["fsync", "replace"], "fsync must happen before the rename"


async def test_atomic_write_text_failure_leaves_original_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash mid-write leaves the previous contents — never an empty file —
    and no stale temp file behind."""
    target = tmp_path / "state.json"
    target.write_text("ORIGINAL", encoding="utf-8")

    def _boom(src: object, dst: object) -> None:
        raise OSError("simulated crash before rename completes")

    monkeypatch.setattr(atomic_io.os, "replace", _boom)

    with pytest.raises(OSError, match="simulated crash"):
        await atomic_write_text(target, "NEW CONTENT")

    # Original survives untouched ...
    assert target.read_text(encoding="utf-8") == "ORIGINAL"
    # ... and no temp file is left lying around.
    assert list(tmp_path.glob("*.tmp")) == []


async def test_atomic_write_text_concurrent_writes_never_corrupt(
    tmp_path: Path,
) -> None:
    """Concurrent writes to the same path resolve to one complete payload —
    the reader never observes a truncated/interleaved file."""
    target = tmp_path / "state.json"
    payloads = [json.dumps({"writer": i, "data": "x" * 500}) for i in range(20)]

    await asyncio.gather(*(atomic_write_text(target, p) for p in payloads))

    # The final file must be exactly one of the payloads — valid, complete JSON.
    final = target.read_text(encoding="utf-8")
    assert final in payloads
    assert json.loads(final)["data"] == "x" * 500
