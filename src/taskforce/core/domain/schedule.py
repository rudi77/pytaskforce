"""Schedule domain models for the butler scheduler.

Defines job scheduling primitives used by the SchedulerProtocol
to manage time-based triggers (cron, interval, one-shot reminders).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from taskforce.core.utils.time import utc_now


class ScheduleType(str, Enum):
    """Type of schedule trigger."""

    CRON = "cron"
    INTERVAL = "interval"
    ONE_SHOT = "one_shot"


class ScheduleActionType(str, Enum):
    """Type of action to execute when a schedule fires."""

    EXECUTE_MISSION = "execute_mission"
    SEND_NOTIFICATION = "send_notification"
    PUBLISH_EVENT = "publish_event"


@dataclass
class ScheduleAction:
    """Action to perform when a schedule triggers.

    Attributes:
        action_type: What kind of action to perform.
        params: Action-specific parameters (mission text, notification details, etc.).
    """

    action_type: ScheduleActionType
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "action_type": self.action_type.value,
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduleAction:
        """Deserialize from stored dict."""
        return cls(
            action_type=ScheduleActionType(data["action_type"]),
            params=dict(data.get("params", {})),
        )


@dataclass
class ScheduleJob:
    """A scheduled job managed by the butler scheduler.

    Attributes:
        job_id: Unique identifier for the job.
        name: Human-readable job name (e.g. "daily_briefing").
        schedule_type: CRON, INTERVAL, or ONE_SHOT.
        expression: Schedule expression ("0 8 * * *" for cron, "15m" for interval,
                    ISO datetime for one_shot).
        action: What to do when the schedule fires.
        enabled: Whether the job is active.
        created_at: When the job was created.
        last_run: When the job last executed (None if never).
        next_run: When the job will next execute (None if unknown).
    """

    job_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    schedule_type: ScheduleType = ScheduleType.CRON
    expression: str = ""
    action: ScheduleAction = field(
        default_factory=lambda: ScheduleAction(ScheduleActionType.SEND_NOTIFICATION)
    )
    enabled: bool = True
    created_at: datetime = field(default_factory=utc_now)
    last_run: datetime | None = None
    next_run: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "job_id": self.job_id,
            "name": self.name,
            "schedule_type": self.schedule_type.value,
            "expression": self.expression,
            "action": self.action.to_dict(),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduleJob:
        """Deserialize from stored dict."""
        created_raw = data.get("created_at")
        last_raw = data.get("last_run")
        next_raw = data.get("next_run")

        return cls(
            job_id=str(data.get("job_id", uuid4().hex)),
            name=str(data.get("name", "")),
            schedule_type=ScheduleType(data.get("schedule_type", "cron")),
            expression=str(data.get("expression", "")),
            action=ScheduleAction.from_dict(data.get("action", {})),
            enabled=bool(data.get("enabled", True)),
            created_at=datetime.fromisoformat(created_raw) if created_raw else utc_now(),
            last_run=datetime.fromisoformat(last_raw) if last_raw else None,
            next_run=datetime.fromisoformat(next_raw) if next_raw else None,
        )
