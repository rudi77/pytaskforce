"""Structlog + stdlib logging configuration for CLIs and daemons.

Provides a single :func:`configure_logging` helper that wires structlog
through stdlib logging so events go to **both** the console (colored) and a
rotating file (plain, UTF-8).
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Any

import structlog


def configure_logging(
    *,
    log_dir: str | Path,
    log_name: str = "taskforce.log",
    debug: bool = False,
    max_bytes: int = 10_000_000,
    backup_count: int = 5,
    console: bool = True,
) -> Path:
    """Configure structlog + stdlib logging with console and rotating file output.

    Events emitted via ``structlog.get_logger(...)`` flow through stdlib
    logging, which then fans out to:
      * a ``StreamHandler`` on the root logger (colored rendering)
      * a ``RotatingFileHandler`` under ``log_dir / log_name``
        (plain rendering, UTF-8 encoded)

    The console handler inherits ``level`` from the ``debug`` flag; the file
    handler always captures DEBUG so operators can inspect full history even
    when running without ``--debug``.

    Args:
        log_dir: Directory where the log file lives. Created if missing.
        log_name: File name (default ``taskforce.log``). Rotated backups are
            suffixed ``.1`` … ``.N``.
        debug: When ``True`` the console handler is set to DEBUG; otherwise
            INFO.
        max_bytes: Size threshold that triggers file rotation.
        backup_count: Number of rotated backups to keep.
        console: When ``False`` only the file handler is attached — useful
            for detached daemons where console output would be discarded.

    Returns:
        Absolute path to the active log file.
    """
    console_level = logging.DEBUG if debug else logging.INFO

    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)
    log_path = (log_dir_path / log_name).resolve()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
    )
    file_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(console_level)
        root.addHandler(console_handler)

    logging.captureWarnings(True)

    return log_path
