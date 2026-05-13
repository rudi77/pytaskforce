"""Tests for the butler ReminderTool defensive guards.

The approval gate may bypass validate_params when no approval service
is installed, so the tool must re-check critical fields at execute()
time. Otherwise an empty message or unreachable recipient causes a
silent no-op at fire time (gateway returns success=False, butler logs
it, user sees nothing).
"""

from __future__ import annotations

import pytest

from taskforce.core.domain.schedule import ScheduleJob
from taskforce.infrastructure.tools.native.reminder_tool import ReminderTool


class _FakeScheduler:
    def __init__(self) -> None:
        self.added: list[ScheduleJob] = []

    async def add_job(self, job: ScheduleJob) -> str:
        self.added.append(job)
        return job.job_id


@pytest.mark.asyncio
async def test_missing_message_is_rejected() -> None:
    tool = ReminderTool(scheduler=_FakeScheduler(), default_recipient_id="u1")

    result = await tool.execute(remind_at="2026-05-07T20:00:00")

    assert result["success"] is False
    assert "message" in result["error"].lower()


@pytest.mark.asyncio
async def test_blank_message_is_rejected() -> None:
    scheduler = _FakeScheduler()
    tool = ReminderTool(scheduler=scheduler, default_recipient_id="u1")

    result = await tool.execute(
        remind_at="2026-05-07T20:00:00",
        message="   ",
    )

    assert result["success"] is False
    assert scheduler.added == []


@pytest.mark.asyncio
async def test_missing_recipient_with_no_default_is_rejected() -> None:
    scheduler = _FakeScheduler()
    tool = ReminderTool(scheduler=scheduler, default_recipient_id="")

    result = await tool.execute(
        remind_at="2026-05-07T20:00:00",
        message="Mama anrufen",
    )

    assert result["success"] is False
    assert "recipient" in result["error"].lower()
    assert scheduler.added == []


@pytest.mark.asyncio
async def test_missing_recipient_falls_back_to_default() -> None:
    scheduler = _FakeScheduler()
    tool = ReminderTool(scheduler=scheduler, default_recipient_id="u1")

    result = await tool.execute(
        remind_at="2026-05-07T20:00:00",
        message="Mama anrufen",
    )

    assert result["success"] is True
    assert len(scheduler.added) == 1


@pytest.mark.asyncio
async def test_explicit_recipient_overrides_default() -> None:
    scheduler = _FakeScheduler()
    tool = ReminderTool(scheduler=scheduler, default_recipient_id="default-user")

    result = await tool.execute(
        remind_at="2026-05-07T20:00:00",
        message="Mama anrufen",
        recipient_id="other-user",
    )

    assert result["success"] is True
    job = scheduler.added[0]
    assert job.action.params["recipient_id"] == "other-user"
