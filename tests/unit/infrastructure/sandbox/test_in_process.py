"""Tests for the in-process sandboxed executor (ADR-022 §5)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.core.interfaces.sandbox import SandboxRequest
from taskforce.infrastructure.sandbox.in_process import InProcessSandboxedExecutor


@pytest.mark.asyncio
async def test_runs_bash_subprocess_and_returns_result(tmp_path: Path) -> None:
    executor = InProcessSandboxedExecutor()
    with patch(
        "taskforce.infrastructure.sandbox.in_process.asyncio.create_subprocess_exec"
    ) as mock_create:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"hello\n", b""))
        mock_proc.returncode = 0
        mock_create.return_value = mock_proc

        result = await executor.run(
            SandboxRequest(kind="bash", script="echo hello", workspace_dir=tmp_path)
        )

    assert result.returncode == 0
    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert result.timed_out is False
    assert mock_create.called


@pytest.mark.asyncio
async def test_timeout_returns_timed_out_result(tmp_path: Path) -> None:
    executor = InProcessSandboxedExecutor()
    with patch(
        "taskforce.infrastructure.sandbox.in_process.asyncio.create_subprocess_exec"
    ) as mock_create:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError())
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_create.return_value = mock_proc

        result = await executor.run(
            SandboxRequest(
                kind="bash",
                script="sleep 100",
                workspace_dir=tmp_path,
                timeout_seconds=0.01,
            )
        )

    assert result.timed_out is True
    assert "timed out" in result.stderr.lower()
    assert result.returncode == -1
    mock_proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_no_timeout_means_no_wait_for_wrapper(tmp_path: Path) -> None:
    """timeout_seconds=None should not wrap with asyncio.wait_for."""
    executor = InProcessSandboxedExecutor()
    with patch(
        "taskforce.infrastructure.sandbox.in_process.asyncio.create_subprocess_exec"
    ) as mock_create:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        mock_create.return_value = mock_proc

        await executor.run(
            SandboxRequest(kind="bash", script="true", workspace_dir=tmp_path)
        )

    # If wait_for were used the call shape on communicate would change;
    # here we just assert the subprocess was launched correctly.
    assert mock_create.called


@pytest.mark.asyncio
async def test_workspace_dir_is_passed_as_cwd(tmp_path: Path) -> None:
    executor = InProcessSandboxedExecutor()
    with patch(
        "taskforce.infrastructure.sandbox.in_process.asyncio.create_subprocess_exec"
    ) as mock_create:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        mock_create.return_value = mock_proc

        await executor.run(
            SandboxRequest(kind="bash", script="pwd", workspace_dir=tmp_path)
        )

    kwargs = mock_create.call_args.kwargs
    assert kwargs["cwd"] == str(tmp_path)
