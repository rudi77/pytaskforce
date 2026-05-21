"""Integration test for the generic AgentDaemon (#245 / ADR-027).

Boots an :class:`AgentDaemon` against the butler profile in a temporary
work directory, waits for its ``status.json`` to be written, then stops
it cleanly. Verifies that:

* The daemon's lifecycle (start → status writer → stop) works end-to-end
  using only framework primitives (no ``taskforce_butler`` imports).
* The status file lands at ``{work_dir}/{profile}/status.json`` — proving
  the profile-aware status path (Phase 2 / ADR-027).
* The clean-break import contract holds: ``taskforce_butler.daemon``
  module is gone after the move.

This test is hermetic in spirit but it does load the real butler profile
(via ``ProfileLoader``) to exercise the actual code paths. The Telegram
gateway / executor / persistent-agent-service all fall back to "not
configured" when their dependencies are missing — that's the expected
"degraded" daemon behaviour in CI.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path

import pytest

from taskforce.application.agent_daemon import AgentDaemon


@pytest.mark.asyncio
async def test_agent_daemon_writes_status_under_profile_subdir(
    tmp_path: Path,
) -> None:
    """status.json must land at {work_dir}/{profile}/status.json."""
    daemon = AgentDaemon(
        profile="butler",
        work_dir=str(tmp_path),
        persistent_agent=False,  # avoid spinning up the queue service
    )
    try:
        await daemon.start()
        status_path = tmp_path / "butler" / "status.json"
        # Status loop runs at 30s cadence but writes once on start();
        # poll for up to 10s with backoff so the assertion is robust.
        for _ in range(50):
            if status_path.is_file():
                break
            await asyncio.sleep(0.2)
        assert status_path.is_file(), f"status.json not written at {status_path}"

        data = json.loads(status_path.read_text(encoding="utf-8"))
        assert data["running"] is True
        assert data["profile"] == "butler"
    finally:
        await daemon.stop()


def test_butler_daemon_legacy_import_is_gone() -> None:
    """Phase 2 clean break: the old module path raises ModuleNotFoundError."""
    with pytest.raises(ModuleNotFoundError):
        import taskforce_butler.daemon  # noqa: F401


def test_butler_service_legacy_import_is_gone() -> None:
    """Phase 2 clean break: ButlerService is gone."""
    with pytest.raises(ModuleNotFoundError):
        import taskforce_butler.service  # noqa: F401


def test_butler_role_loader_legacy_import_is_gone() -> None:
    """Phase 2 clean break: ButlerRoleLoader is gone."""
    with pytest.raises(ModuleNotFoundError):
        import taskforce_butler.role_loader  # noqa: F401


def test_daemon_supervisor_legacy_import_is_gone() -> None:
    """Phase 2 clean break: old supervisor path is gone."""
    with pytest.raises(ModuleNotFoundError):
        import taskforce_butler.daemon_supervisor  # noqa: F401


@pytest.mark.spec("standing-goals.daemon_seeds_yaml_goals_idempotent")
@pytest.mark.asyncio
async def test_daemon_seeds_standing_goals_idempotently(tmp_path: Path) -> None:
    """``_setup_proactive_layer`` seeds ``proactive.standing_goals`` from YAML;
    a second run (daemon restart) skips goals that already exist by goal_id, so
    the seed list does not duplicate across restarts."""
    from taskforce.api.dependencies import (
        set_goal_evaluator,
        set_standing_goal_store,
    )
    from taskforce.infrastructure.persistence.file_standing_goal_store import (
        FileStandingGoalStore,
    )

    config = {
        "proactive": {
            "enabled": True,
            "heartbeat_minutes": 100_000,  # never ticks during the test
            "standing_goals": [
                {
                    "goal_id": "seed-weekly",
                    "description": "Weekly summary",
                    "evaluation_prompt": "Prepare a weekly summary.",
                    "frequency": "0 9 * * 1",
                }
            ],
        }
    }

    daemon = AgentDaemon(
        profile="dev", work_dir=str(tmp_path), persistent_agent=False
    )
    tasks: list[asyncio.Task[None] | None] = []
    try:
        # First boot: seeds the goal. Cancel the heartbeat task synchronously
        # (no await in between) so it never runs a tick.
        await daemon._setup_proactive_layer(config)
        tasks.append(daemon._proactive_task)
        if daemon._proactive_task is not None:
            daemon._proactive_task.cancel()

        # Second boot (simulated daemon restart): must not duplicate the seed.
        await daemon._setup_proactive_layer(config)
        tasks.append(daemon._proactive_task)
        if daemon._proactive_task is not None:
            daemon._proactive_task.cancel()

        store = FileStandingGoalStore(work_dir=str(tmp_path))
        goals = await store.list()
        assert len(goals) == 1
        assert goals[0].goal_id == "seed-weekly"
    finally:
        for task in tasks:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        set_standing_goal_store(None)
        set_goal_evaluator(None)
