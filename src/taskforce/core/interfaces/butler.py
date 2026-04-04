"""Butler Protocol Interfaces

Consolidated protocols for the Butler event-driven agent daemon.

Contains:
- EventSourceProtocol: External event ingestion (calendars, webhooks, etc.)
- SchedulerProtocol: Time-based job management (cron, interval, one-shot)
- RuleEngineProtocol: Event-to-action trigger rule evaluation
- LearningStrategyProtocol: Automatic knowledge extraction from conversations
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from taskforce.core.domain.agent_event import AgentEvent
    from taskforce.core.domain.memory import MemoryRecord, MemoryScope
    from taskforce.core.domain.schedule import ScheduleJob
    from taskforce.core.domain.trigger_rule import RuleAction, TriggerRule


class EventSourceProtocol(Protocol):
    """Protocol for external event sources that feed into the butler."""

    @property
    def source_name(self) -> str:
        """Unique name identifying this event source."""
        ...

    @property
    def is_running(self) -> bool:
        """Whether the event source is currently active."""
        ...

    async def start(self) -> None:
        """Begin polling or listening for events."""
        ...

    async def stop(self) -> None:
        """Gracefully stop the event source."""
        ...


class SchedulerProtocol(Protocol):
    """Protocol for time-based job scheduling."""

    async def start(self) -> None:
        """Start the scheduler, resuming any persisted jobs."""
        ...

    async def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        ...

    async def add_job(self, job: ScheduleJob) -> str:
        """Add a new scheduled job. Returns the job_id."""
        ...

    async def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job. Returns True if found and removed."""
        ...

    async def get_job(self, job_id: str) -> ScheduleJob | None:
        """Retrieve a job by ID."""
        ...

    async def list_jobs(self) -> list[ScheduleJob]:
        """List all registered jobs."""
        ...

    async def pause_job(self, job_id: str) -> bool:
        """Pause a running job. Returns True if found and paused."""
        ...

    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job. Returns True if found and resumed."""
        ...


class RuleEngineProtocol(Protocol):
    """Protocol for trigger-based rule evaluation."""

    async def add_rule(self, rule: TriggerRule) -> str:
        """Add a new trigger rule. Returns the rule_id."""
        ...

    async def remove_rule(self, rule_id: str) -> bool:
        """Remove a trigger rule. Returns True if found and removed."""
        ...

    async def get_rule(self, rule_id: str) -> TriggerRule | None:
        """Retrieve a rule by ID."""
        ...

    async def list_rules(self) -> list[TriggerRule]:
        """List all registered rules, sorted by priority descending."""
        ...

    async def evaluate(self, event: AgentEvent) -> list[RuleAction]:
        """Evaluate all rules against an event and return matching actions."""
        ...


class LearningStrategyProtocol(Protocol):
    """Protocol for automatic knowledge extraction and memory management."""

    async def extract_learnings(
        self,
        conversation: list[dict],
        session_context: dict,
    ) -> list[MemoryRecord]:
        """Extract facts, preferences, and decisions from a conversation."""
        ...

    async def enrich_context(
        self,
        mission: str,
        user_id: str,
    ) -> list[MemoryRecord]:
        """Retrieve relevant memories for the current mission context."""
        ...

    async def compact_memories(
        self,
        scope: MemoryScope,
        max_age_days: int,
    ) -> int:
        """Summarize and archive old memories. Returns records processed."""
        ...
