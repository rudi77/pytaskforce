"""Utility to suppress stdout during ML library calls.

Prevents MCP protocol corruption from progress bars/download messages.
"""

import contextlib
import os
import sys
from typing import Generator, TextIO


@contextlib.contextmanager
def suppress_stdout() -> Generator[None, None, None]:
    """Suppress stdout/stderr during the context.

    IMPORTANT: When Taskforce connects to an MCP stdio server, the server's
    stderr may not be drained. Redirecting stdout->stderr can therefore
    deadlock if libraries write a lot (progress bars, downloads).

    We do this at the Python level by replacing `sys.stdout` / `sys.stderr`.
    Additionally, on Windows we also redirect **fd=2 (stderr)** to `NUL` to
    prevent native libraries (e.g., Paddle/PaddleOCR) from filling the stderr
    pipe and deadlocking. We intentionally do NOT touch fd=1 (stdout), since
    stdout is the MCP JSON-RPC protocol stream.

    This prevents ML libraries (PaddleOCR, transformers, etc.) from writing
    progress bars or download messages that could corrupt the MCP JSON-RPC
    protocol stream or fill stderr pipes.
    """
    # Save original stdout
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    saved_stderr_fd: int | None = None
    null_fd: int | None = None
    null_text: TextIO | None = None

    try:
        # Python-level redirect
        null_text = open(os.devnull, "w")
        sys.stdout = null_text
        sys.stderr = null_text

        # OS-level redirect for native writes to stderr (fd=2).
        try:
            null_fd = os.open(os.devnull, os.O_WRONLY)
            saved_stderr_fd = os.dup(2)
            os.dup2(null_fd, 2)
        except Exception:
            saved_stderr_fd = None
            null_fd = None

        yield
    finally:
        # Restore Python-level stdout/stderr
        sys.stdout = original_stdout
        sys.stderr = original_stderr

        if null_text is not None:
            try:
                null_text.close()
            except Exception:
                pass

        if saved_stderr_fd is not None:
            try:
                os.dup2(saved_stderr_fd, 2)
            finally:
                os.close(saved_stderr_fd)

        if null_fd is not None:
            try:
                os.close(null_fd)
            except Exception:
                pass
