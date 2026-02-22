"""Tests for Schedule domain models."""


from taskforce.core.domain.schedule import (
    ScheduleAction,
    ScheduleActionType,
    ScheduleJob,
    ScheduleType,
)


class TestScheduleType:
    """Tests for ScheduleType enum."""

    def test_values(self) -> None:
        assert ScheduleType.CRON.value == "cron"
        assert ScheduleType.INTERVAL.value == "interval"
        assert ScheduleType.ONE_SHOT.value == "one_shot"


class TestScheduleAction:
    """Tests for ScheduleAction dataclass."""

    def test_create(self) -> None:
        action = ScheduleAction(
            action_type=ScheduleActionType.SEND_NOTIFICATION,
            params={"channel": "telegram", "message": "Hello"},
        )
        assert action.action_type == ScheduleActionType.SEND_NOTIFICATION
        assert action.params["channel"] == "telegram"

    def test_to_dict(self) -> None:
        action = ScheduleAction(
            action_type=ScheduleActionType.EXECUTE_MISSION,
            params={"mission": "Check calendar"},
        )
        d = action.to_dict()
        assert d["action_type"] == "execute_mission"
        assert d["params"]["mission"] == "Check calendar"

    def test_from_dict(self) -> None:
        data = {
            "action_type": "send_notification",
            "params": {"channel": "telegram"},
        }
        action = ScheduleAction.from_dict(data)
        assert action.action_type == ScheduleActionType.SEND_NOTIFICATION


class TestScheduleJob:
    """Tests for ScheduleJob dataclass."""

    def test_create_default(self) -> None:
        job = ScheduleJob()
        assert job.job_id
        assert job.schedule_type == ScheduleType.CRON
        assert job.enabled is True
        assert job.last_run is None

    def test_create_cron_job(self) -> None:
        job = ScheduleJob(
            name="daily_briefing",
            schedule_type=ScheduleType.CRON,
            expression="0 8 * * *",
            action=ScheduleAction(
                action_type=ScheduleActionType.EXECUTE_MISSION,
                params={"mission": "Create daily briefing"},
            ),
        )
        assert job.name == "daily_briefing"
        assert job.expression == "0 8 * * *"

    def test_to_dict(self) -> None:
        job = ScheduleJob(
            job_id="test123",
            name="test",
            schedule_type=ScheduleType.INTERVAL,
            expression="15m",
        )
        d = job.to_dict()
        assert d["job_id"] == "test123"
        assert d["schedule_type"] == "interval"
        assert d["expression"] == "15m"
        assert d["enabled"] is True

    def test_from_dict(self) -> None:
        data = {
            "job_id": "abc",
            "name": "test_job",
            "schedule_type": "one_shot",
            "expression": "2026-02-18T14:00:00",
            "action": {
                "action_type": "send_notification",
                "params": {"message": "Reminder!"},
            },
            "enabled": True,
            "created_at": "2026-02-18T10:00:00+00:00",
        }
        job = ScheduleJob.from_dict(data)
        assert job.job_id == "abc"
        assert job.schedule_type == ScheduleType.ONE_SHOT
        assert job.action.action_type == ScheduleActionType.SEND_NOTIFICATION

    def test_roundtrip(self) -> None:
        original = ScheduleJob(
            name="roundtrip_test",
            schedule_type=ScheduleType.CRON,
            expression="*/5 * * * *",
            action=ScheduleAction(
                action_type=ScheduleActionType.PUBLISH_EVENT,
                params={"topic": "test"},
            ),
        )
        restored = ScheduleJob.from_dict(original.to_dict())
        assert restored.job_id == original.job_id
        assert restored.name == original.name
        assert restored.schedule_type == original.schedule_type
        assert restored.expression == original.expression
