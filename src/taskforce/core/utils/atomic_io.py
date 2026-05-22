"""Crash-safe atomic file writes.

A plain *temp file + rename* is **not** crash-safe. After an OS crash or
power loss the renamed file can be present but empty: the bytes written
to the temp file may still sit in the kernel page cache while the
rename's directory-entry update has already reached disk. The next
start then reads the "last save" as truncated/corrupt — the classic
zero-length-file-after-crash bug from the ext4 mailing list (c. 2008).

``atomic_write_text`` closes that window by ``fsync``-ing the temp
file's descriptor *before* the rename, so the data is on stable storage
when the directory entry flips over.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path


def _replace_with_retry(src: Path, dst: Path) -> None:
    """Atomically rename *src* onto *dst*, retrying transient Windows errors.

    POSIX ``rename`` is atomic and never fails transiently. On Windows
    ``os.replace`` can briefly raise ``PermissionError`` when the
    destination is momentarily held (e.g. by a concurrent replace or an
    open reader), so we retry a few times with a short backoff there.
    """
    delays = (0.001, 0.005, 0.02, 0.05, 0.1)
    for delay in delays:
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if os.name != "nt":
                raise
            time.sleep(delay)
    os.replace(src, dst)  # final attempt — let any error propagate


def _atomic_write_text_sync(path: Path, text: str, encoding: str) -> None:
    """Blocking implementation of :func:`atomic_write_text`."""
    # mkstemp gives a guaranteed-unique temp file in the *same* directory,
    # so the rename stays on one filesystem (atomic) and two concurrent
    # writes to the same target never collide on the temp file.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(tmp, path)
    except BaseException:
        # Never leave a stale temp file behind on failure.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


async def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """Write *text* to *path* atomically and durably.

    Writes to a sibling temp file, ``fsync``s it so the bytes reach
    stable storage, then ``os.replace``s it onto *path* (an atomic
    rename on both POSIX and Windows). A crash mid-write leaves either
    the previous file contents or the complete new contents — never a
    truncated or empty file.

    The blocking file I/O runs in a worker thread so the event loop is
    not stalled. The caller is responsible for ensuring the parent
    directory of *path* already exists.

    Args:
        path: Destination file path.
        text: Full file contents to write.
        encoding: Text encoding (default UTF-8).
    """
    await asyncio.to_thread(_atomic_write_text_sync, Path(path), text, encoding)
