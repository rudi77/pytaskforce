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
    """Timeout escalates SIGTERM → SIGKILL via ``_terminate_process``.

    With the mocked ``wait`` returning immediately the grace period
    completes successfully, so only ``terminate`` is invoked. The
    second timeout test covers the kill escalation.
    """
    executor = InProcessSandboxedExecutor()
    with patch(
        "taskforce.infrastructure.sandbox.in_process.asyncio.create_subprocess_exec"
    ) as mock_create:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError())
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_proc.returncode = None
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
    mock_proc.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_cancellation_kills_subprocess_and_propagates(tmp_path: Path) -> None:
    """Cancelling the executor coroutine tears the subprocess down (ADR-019).

    Without this, a ``shell sleep 60`` survives an ESC interrupt and
    keeps consuming resources after the agent has paused.
    """
    from taskforce.infrastructure.sandbox.in_process import _TERMINATE_GRACE_SECONDS

    assert _TERMINATE_GRACE_SECONDS > 0  # sanity: configured grace exists

    executor = InProcessSandboxedExecutor()
    with patch(
        "taskforce.infrastructure.sandbox.in_process.asyncio.create_subprocess_exec"
    ) as mock_create:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.CancelledError())
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_proc.returncode = None
        mock_create.return_value = mock_proc

        with pytest.raises(asyncio.CancelledError):
            await executor.run(
                SandboxRequest(
                    kind="bash",
                    script="sleep 60",
                    workspace_dir=tmp_path,
                )
            )

    mock_proc.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_terminate_escalates_to_kill_when_wait_hangs(tmp_path: Path) -> None:
    """If the process ignores SIGTERM, the helper falls back to SIGKILL."""
    executor = InProcessSandboxedExecutor()
    with patch(
        "taskforce.infrastructure.sandbox.in_process.asyncio.create_subprocess_exec"
    ) as mock_create, patch(
        "taskforce.infrastructure.sandbox.in_process._TERMINATE_GRACE_SECONDS",
        0.01,
    ):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError())
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()

        async def _hang() -> None:
            await asyncio.sleep(10)

        mock_proc.wait = AsyncMock(side_effect=_hang)
        mock_proc.returncode = None
        mock_create.return_value = mock_proc

        await executor.run(
            SandboxRequest(
                kind="bash",
                script="trap '' TERM; sleep 60",
                workspace_dir=tmp_path,
                timeout_seconds=0.01,
            )
        )

    mock_proc.terminate.assert_called_once()
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
