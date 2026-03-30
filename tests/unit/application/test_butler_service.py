"""Tests for ButlerService."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from taskforce.application.butler_service import ButlerService
from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.core.domain.gateway import NotificationResult


class TestButlerService:
    """Tests for the ButlerService orchestrator."""

    @pytest.fixture
    def butler(self, tmp_path) -> ButlerService:
        return ButlerService(
            work_dir=str(tmp_path),
            default_notification_channel="telegram",
            default_recipient_id="42",
        )

    async def test_start_stop(self, butler: ButlerService) -> None:
        assert not butler.is_running
        await butler.start()
        assert butler.is_running
        await butler.stop()
        assert not butler.is_running

    async def test_add_rule_from_config(self, butler: ButlerService) -> None:
        await butler.start()

        rule_id = await butler.add_rule_from_config({
            "name": "test_rule",
            "trigger": {
                "source": "calendar",
                "event_type": "calendar.upcoming",
                "filters": {"minutes_until": {"$lte": 30}},
            },
            "action": {
                "type": "notify",
                "channel": "telegram",
                "template": "Reminder: {{event.title}}",
            },
        })

        assert rule_id
        rules = await butler.rule_engine.list_rules()
        assert len(rules) == 1
        assert rules[0].name == "test_rule"

        await butler.stop()

    async def test_get_status(self, butler: ButlerService) -> None:
        await butler.start()
        status = await butler.get_status()

        assert status["running"] is True
        assert status["events_processed"] == 0
        assert status["actions_dispatched"] == 0
        assert isinstance(status["event_sources"], list)
        assert isinstance(status["scheduler"], dict)

        await butler.stop()

    async def test_event_routing_with_notification(self, butler: ButlerService) -> None:
        """Test that an event triggers a notification through the full pipeline."""
        mock_gateway = AsyncMock()
        mock_gateway.send_notification = AsyncMock(
            return_value=NotificationResult(
                success=True, channel="telegram", recipient_id="42"
            )
        )
        butler.set_gateway(mock_gateway)

        await butler.start()

        await butler.add_rule_from_config({
            "name": "notify_rule",
            "trigger": {"source": "test", "event_type": "*"},
            "action": {
                "type": "notify",
                "params": {"message": "Something happened!"},
            },
        })

        event = AgentEvent(
            source="test",
            event_type=AgentEventType.CUSTOM,
            payload={"detail": "test_data"},
        )
        await butler._on_event(event)

        mock_gateway.send_notification.assert_called_once()
        await butler.stop()

    async def test_event_routing_without_gateway(self, butler: ButlerService) -> None:
        """Test graceful handling when gateway is not configured."""
        await butler.start()

        await butler.add_rule_from_config({
            "name": "notify_no_gw",
            "trigger": {"source": "*"},
            "action": {"type": "notify", "params": {"message": "test"}},
        })

        # Should not raise even without gateway
        event = AgentEvent(source="test", event_type=AgentEventType.CUSTOM)
        await butler._on_event(event)

        await butler.stop()

    async def test_schedule_event_dispatches_notification_directly(
        self, butler: ButlerService
    ) -> None:
        """Scheduler events with send_notification action dispatch without rules."""
        mock_gateway = AsyncMock()
        mock_gateway.send_notification = AsyncMock(
            return_value=NotificationResult(
                success=True, channel="telegram", recipient_id="42"
            )
        )
        butler.set_gateway(mock_gateway)
        await butler.start()

        event = AgentEvent(
            source="scheduler",
            event_type=AgentEventType.SCHEDULE_TRIGGERED,
            payload={
                "job_id": "abc123",
                "job_name": "Daily reminder",
                "action": {
                    "action_type": "send_notification",
                    "params": {
                        "channel": "telegram",
                        "recipient_id": "42",
                        "message": "Hello from scheduler!",
                    },
                },
            },
        )
        await butler._on_event(event)
        await asyncio.sleep(0)  # let fire-and-forget task run

        mock_gateway.send_notification.assert_called_once()
        call_args = mock_gateway.send_notification.call_args[0][0]
        assert call_args.message == "Hello from scheduler!"
        await butler.stop()

    async def test_schedule_event_dispatches_execute_mission(
        self, butler: ButlerService
    ) -> None:
        """Scheduler events with execute_mission action dispatch without rules."""
        mock_agent_service = AsyncMock()
        mock_result = AsyncMock()
        mock_result.status = "completed"
        mock_agent_service.submit = AsyncMock(return_value=mock_result)
        butler.set_agent_service(mock_agent_service)
        await butler.start()

        event = AgentEvent(
            source="scheduler",
            event_type=AgentEventType.SCHEDULE_TRIGGERED,
            payload={
                "job_id": "xyz789",
                "job_name": "E-Mail-Prüfung mit Benachrichtigung",
                "action": {
                    "action_type": "execute_mission",
                    "params": {},
                },
            },
        )
        await butler._on_event(event)
        await asyncio.sleep(0)  # let fire-and-forget task run

        mock_agent_service.submit.assert_called_once()
        submitted_request = mock_agent_service.submit.call_args[0][0]
        assert "E-Mail-Prüfung mit Benachrichtigung" in submitted_request.message
        assert "send_notification" in submitted_request.message
        await butler.stop()

    async def test_schedule_event_with_explicit_mission(
        self, butler: ButlerService
    ) -> None:
        """Scheduler events with explicit mission text use it verbatim."""
        mock_agent_service = AsyncMock()
        mock_result = AsyncMock()
        mock_result.status = "completed"
        mock_agent_service.submit = AsyncMock(return_value=mock_result)
        butler.set_agent_service(mock_agent_service)
        await butler.start()

        event = AgentEvent(
            source="scheduler",
            event_type=AgentEventType.SCHEDULE_TRIGGERED,
            payload={
                "job_id": "m001",
                "job_name": "Custom job",
                "action": {
                    "action_type": "execute_mission",
                    "params": {"mission": "Check emails and notify me"},
                },
            },
        )
        await butler._on_event(event)
        await asyncio.sleep(0)  # let fire-and-forget task run

        submitted_request = mock_agent_service.submit.call_args[0][0]
        assert submitted_request.message == "Check emails and notify me"
        await butler.stop()

    async def test_scheduler_fires_job_and_dispatches_mission(
        self, butler: ButlerService
    ) -> None:
        """End-to-end: scheduler fires a job → _on_event → _dispatch → _execute_mission."""
        from taskforce.core.domain.schedule import (
            ScheduleAction,
            ScheduleActionType,
            ScheduleJob,
            ScheduleType,
        )

        mock_agent_service = AsyncMock()
        mock_result = AsyncMock()
        mock_result.status = "completed"
        mock_agent_service.submit = AsyncMock(return_value=mock_result)
        butler.set_agent_service(mock_agent_service)

        await butler.start()

        # Add a short-interval job that fires almost immediately
        job = ScheduleJob(
            name="Integration email check",
            schedule_type=ScheduleType.ONE_SHOT,
            expression=(
                asyncio.get_event_loop().time().__class__.__module__  # trick: use real datetime
            ),
            action=ScheduleAction(
                action_type=ScheduleActionType.EXECUTE_MISSION,
                params={},
            ),
        )
        # Manually fire the job through the scheduler's internal method
        await butler.scheduler._fire_job(job)

        # Give the fire-and-forget task time to run
        await asyncio.sleep(0.1)

        mock_agent_service.submit.assert_called_once()
        submitted = mock_agent_service.submit.call_args[0][0]
        assert "Integration email check" in submitted.message
        assert "send_notification" in submitted.message

        await butler.stop()

    async def test_add_event_source(self, butler: ButlerService) -> None:
        mock_source = AsyncMock()
        mock_source.source_name = "test_source"
        mock_source.is_running = False
        mock_source._event_callback = None

        butler.add_event_source(mock_source)

        await butler.start()
        mock_source.start.assert_called_once()

        await butler.stop()
        mock_source.stop.assert_called_once()
