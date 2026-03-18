"""Tests for ButlerDaemon with PersistentAgentService integration (ADR-016)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from taskforce.api.butler_daemon import ButlerDaemon
from taskforce.core.domain.models import ExecutionResult


class FakeExecutor:
    async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
        return ExecutionResult(
            session_id=kwargs.get("session_id", "test"),
            status="completed",
            final_message="OK",
        )


def _patch_executor():
    """Patch AgentExecutor import inside butler_daemon._setup_executor."""
    return patch(
        "taskforce.application.executor.AgentExecutor",
        return_value=FakeExecutor(),
    )


class TestButlerDaemonPersistentAgent:
    """Tests for PersistentAgentService wiring in ButlerDaemon."""

    async def test_persistent_agent_created_when_enabled(self, tmp_path):
        daemon = ButlerDaemon(
            profile="butler",
            work_dir=str(tmp_path),
            persistent_agent=True,
        )

        # Manually build butler + persistent agent (bypassing full start).
        from taskforce.application.butler_service import ButlerService

        daemon._butler = ButlerService(work_dir=str(tmp_path))
        fake_executor = FakeExecutor()
        daemon._butler.set_executor(fake_executor)
        daemon._agent_service = daemon._build_persistent_agent_service(
            fake_executor, {}
        )
        await daemon._butler.start()
        if daemon._agent_service:
            await daemon._agent_service.start()
        daemon._running = True

        try:
            assert daemon.agent_service is not None
            assert daemon.agent_service.running
        finally:
            await daemon.stop()

        assert not daemon.agent_service.running

    async def test_persistent_agent_not_created_when_disabled(self, tmp_path):
        daemon = ButlerDaemon(
            profile="butler",
            work_dir=str(tmp_path),
            persistent_agent=False,
        )

        with patch.object(daemon, "_load_config", return_value={}), patch.object(
            daemon, "_setup_gateway", new_callable=AsyncMock
        ), patch.object(daemon, "_setup_executor", new_callable=AsyncMock), patch.object(
            daemon, "_setup_event_sources", new_callable=AsyncMock
        ), patch.object(daemon, "_load_rules", new_callable=AsyncMock):
            await daemon.start()

        try:
            assert daemon.agent_service is None
        finally:
            await daemon.stop()

    async def test_status_includes_persistent_agent(self, tmp_path):
        from taskforce.application.butler_service import ButlerService

        daemon = ButlerDaemon(
            profile="butler",
            work_dir=str(tmp_path),
            persistent_agent=True,
        )

        daemon._butler = ButlerService(work_dir=str(tmp_path))
        fake_executor = FakeExecutor()
        daemon._butler.set_executor(fake_executor)
        daemon._agent_service = daemon._build_persistent_agent_service(
            fake_executor, {}
        )
        await daemon._butler.start()
        if daemon._agent_service:
            await daemon._agent_service.start()
        daemon._running = True

        try:
            await daemon._write_status()

            import json

            status_path = tmp_path / "butler" / "status.json"
            assert status_path.exists()
            status = json.loads(status_path.read_text())
            assert "persistent_agent" in status
            assert status["persistent_agent"]["running"] is True
        finally:
            await daemon.stop()
