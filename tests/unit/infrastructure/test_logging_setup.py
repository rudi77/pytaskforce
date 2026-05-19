"""Tests for the shared logging configuration helper."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import pytest
import structlog

from taskforce.infrastructure.logging.setup import configure_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> None:
    """Restore root logger state after each test."""
    original_handlers = logging.getLogger().handlers[:]
    original_level = logging.getLogger().level
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    for handler in original_handlers:
        root.addHandler(handler)
    root.setLevel(original_level)


def test_configure_logging_creates_log_directory(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    log_path = configure_logging(log_dir=log_dir, log_name="butler.log")

    assert log_dir.exists()
    assert log_path == (log_dir / "butler.log").resolve()


def test_configure_logging_attaches_file_and_console_handlers(tmp_path: Path) -> None:
    configure_logging(log_dir=tmp_path, log_name="out.log")

    root = logging.getLogger()
    assert any(
        isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers
    )
    assert any(type(h) is logging.StreamHandler for h in root.handlers)


def test_configure_logging_without_console(tmp_path: Path) -> None:
    configure_logging(log_dir=tmp_path, log_name="out.log", console=False)

    root = logging.getLogger()
    assert any(
        isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers
    )
    # Only the file handler should be attached (no StreamHandler).
    assert not any(
        type(h) is logging.StreamHandler  # exact type, not subclass
        for h in root.handlers
    )


def test_configure_logging_writes_structlog_events_to_file(tmp_path: Path) -> None:
    log_path = configure_logging(
        log_dir=tmp_path, log_name="out.log", console=False, debug=True
    )

    logger = structlog.get_logger("test")
    logger.info("tool_execute", tool="powershell", args={"command": "Get-Mailbox"})

    # Flush all handlers.
    for handler in logging.getLogger().handlers:
        handler.flush()

    content = log_path.read_text(encoding="utf-8")
    assert "tool_execute" in content
    assert "powershell" in content
    assert "Get-Mailbox" in content


def test_console_level_follows_debug_flag(tmp_path: Path) -> None:
    configure_logging(log_dir=tmp_path, debug=False)
    root = logging.getLogger()
    console_handlers = [
        h
        for h in root.handlers
        if type(h) is logging.StreamHandler
    ]
    assert console_handlers
    assert console_handlers[0].level == logging.INFO

    configure_logging(log_dir=tmp_path, debug=True)
    root = logging.getLogger()
    console_handlers = [
        h
        for h in root.handlers
        if type(h) is logging.StreamHandler
    ]
    assert console_handlers
    assert console_handlers[0].level == logging.DEBUG


def test_file_handler_always_captures_debug(tmp_path: Path) -> None:
    configure_logging(log_dir=tmp_path, debug=False)
    root = logging.getLogger()
    file_handlers = [
        h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert file_handlers
    assert file_handlers[0].level == logging.DEBUG
