"""Tests for the scheduler → workflow dispatcher (ADR-022 §6 / §7, G4)."""

from __future__ import annotations

from typing import Any

import pytest

from taskforce.application.scheduler_dispatcher import make_scheduler_event_callback


class _FakeEvent:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload


class _RecordingRuntime:
    def __init__(self, raise_value_error: bool = False) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._raise = raise_value_error

    async def run_workflow_id(
        self, workflow_id: str, executor: Any, *, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        if self._raise:
            raise ValueError(f"unknown workflow: {workflow_id}")
        self.calls.append((workflow_id, executor))
        return [{"step_id": "s1", "status": "completed"}]


@pytest.mark.asyncio
async def test_dispatch_runs_execute_workflow_action() -> None:
    runtime = _RecordingRuntime()
    executor = object()
    callback = make_scheduler_event_callback(runtime, executor)

    event = _FakeEvent(
        payload={
            "job_id": "workflow__wf-1",
            "action": {
                "action_type": "execute_workflow",
                "params": {"workflow_id": "wf-1"},
            },
            "tenant_id": "tenant-acme",
        }
    )
    await callback(event)

    assert runtime.calls == [("wf-1", executor)]


@pytest.mark.asyncio
async def test_dispatch_runs_under_tenant_context_when_runner_installed() -> None:
    from taskforce.application.infrastructure_overrides import (
        clear_infrastructure_overrides,
        set_tenant_context_runner,
    )

    runtime = _RecordingRuntime()
    seen: list[str] = []

    async def runner(tenant_id: str, callback):
        seen.append(tenant_id)
        return await callback()

    set_tenant_context_runner(runner)
    try:
        callback = make_scheduler_event_callback(runtime, executor=object())
        await callback(
            _FakeEvent(
                payload={
                    "action": {
                        "action_type": "execute_workflow",
                        "params": {"workflow_id": "wf-1"},
                    },
                    "tenant_id": "tenant-acme",
                }
            )
        )
    finally:
        clear_infrastructure_overrides()

    assert seen == ["tenant-acme"]
    assert runtime.calls


@pytest.mark.asyncio
async def test_dispatch_ignores_non_workflow_actions() -> None:
    runtime = _RecordingRuntime()
    callback = make_scheduler_event_callback(runtime, executor=object())

    event = _FakeEvent(
        payload={
            "action": {"action_type": "send_notification", "params": {}},
        }
    )
    await callback(event)

    assert runtime.calls == []


@pytest.mark.asyncio
async def test_dispatch_skips_when_workflow_id_missing() -> None:
    runtime = _RecordingRuntime()
    callback = make_scheduler_event_callback(runtime, executor=object())

    event = _FakeEvent(
        payload={
            "action": {"action_type": "execute_workflow", "params": {}},
        }
    )
    await callback(event)

    assert runtime.calls == []


@pytest.mark.asyncio
async def test_dispatch_swallows_unknown_workflow() -> None:
    """An unknown workflow id must NOT crash the scheduler's event loop."""
    runtime = _RecordingRuntime(raise_value_error=True)
    callback = make_scheduler_event_callback(runtime, executor=object())

    event = _FakeEvent(
        payload={
            "action": {
                "action_type": "execute_workflow",
                "params": {"workflow_id": "nope"},
            },
        }
    )
    # Must not raise.
    await callback(event)


@pytest.mark.asyncio
async def test_dispatch_handles_missing_payload() -> None:
    runtime = _RecordingRuntime()
    callback = make_scheduler_event_callback(runtime, executor=object())

    class _Empty:
        payload = None

    await callback(_Empty())
    assert runtime.calls == []
