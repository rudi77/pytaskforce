"""Edge-case tests for SchedulerService (issue #158).

Covers:

- Timezone consistency (cron evaluated in IANA zone, not host TZ).
- Catch-up policy (``coalesce=skip`` vs ``coalesce=run_once``).
- One-shot idempotency on scheduler restart.
- Daylight-saving transitions in ``Europe/Vienna``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from taskforce.core.domain.agent_event import AgentEvent
from taskforce.core.domain.schedule import (
    CoalescePolicy,
    ScheduleAction,
    ScheduleActionType,
    ScheduleJob,
    ScheduleType,
)
from taskforce.infrastructure.scheduler.scheduler_service import (
    SchedulerService,
    _next_cron_occurrence,
)

# ---------------------------------------------------------------------------
# Timezone consistency
# ---------------------------------------------------------------------------


class TestCronTimezone:
    @pytest.mark.spec("events-scheduler.cron_respects_job_timezone")
    def test_cron_in_vienna_local_8am_returns_correct_utc(self) -> None:
        """``0 8 * * *`` in Europe/Vienna at standard time fires 07:00 UTC."""
        # 5 February 2026 — Vienna is on CET (UTC+1).
        base = datetime(2026, 2, 5, 6, 30, tzinfo=UTC)
        nxt = _next_cron_occurrence("0 8 * * *", base, "Europe/Vienna")
        assert nxt == datetime(2026, 2, 5, 7, 0, tzinfo=UTC)

    def test_cron_in_vienna_during_summer_uses_cest_offset(self) -> None:
        """The same cron expression rolls forward by an hour in CEST (UTC+2)."""
        # 15 June 2026 — Vienna is on CEST (UTC+2).
        base = datetime(2026, 6, 15, 5, 30, tzinfo=UTC)
        nxt = _next_cron_occurrence("0 8 * * *", base, "Europe/Vienna")
        assert nxt == datetime(2026, 6, 15, 6, 0, tzinfo=UTC)

    def test_cron_returns_aware_utc_regardless_of_input_kind(self) -> None:
        """Naive ``after`` is treated as UTC; result is always tz-aware UTC."""
        naive_utc = datetime(2026, 2, 5, 6, 30)
        nxt = _next_cron_occurrence("0 8 * * *", naive_utc, "Europe/Vienna")
        assert nxt.tzinfo is UTC
        assert nxt == datetime(2026, 2, 5, 7, 0, tzinfo=UTC)

    def test_unknown_timezone_falls_back_to_utc(self) -> None:
        """A bad IANA name does not raise — we silently use UTC."""
        base = datetime(2026, 2, 5, 6, 30, tzinfo=UTC)
        nxt = _next_cron_occurrence("0 8 * * *", base, "Not/A_Zone")
        assert nxt == datetime(2026, 2, 5, 8, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# DST transitions (Europe/Vienna: forward Mar 29 2026, back Oct 25 2026)
# ---------------------------------------------------------------------------


class TestDstTransitions:
    @pytest.mark.spec("events-scheduler.cron_skips_dst_forward_gap")
    def test_forward_jump_skips_nonexistent_local_time(self) -> None:
        """On 29 March 2026 the local clock skips 02:00 → 03:00.

        ``30 2 * * *`` does not exist on that day; the scheduler must move
        the firing to the next valid occurrence (30 March 02:30 local =
        00:30 UTC, since CEST = UTC+2).
        """
        # Just before the jump: 28 March 23:00 UTC = 29 March 00:00 local CET.
        base = datetime(2026, 3, 28, 23, 0, tzinfo=UTC)
        nxt = _next_cron_occurrence("30 2 * * *", base, "Europe/Vienna")
        # Must NOT land in the gap (29 March 02:30 local does not exist).
        # The next existing local 02:30 is 30 March 02:30 CEST = 00:30 UTC.
        assert nxt == datetime(2026, 3, 30, 0, 30, tzinfo=UTC)

    def test_forward_jump_existing_slot_still_fires(self) -> None:
        """A cron that does not target the gap still fires on the DST day."""
        base = datetime(2026, 3, 28, 23, 0, tzinfo=UTC)
        # 09:00 local on 29 March exists in CEST (UTC+2) → 07:00 UTC.
        nxt = _next_cron_occurrence("0 9 * * *", base, "Europe/Vienna")
        assert nxt == datetime(2026, 3, 29, 7, 0, tzinfo=UTC)

    def test_backward_jump_fires_only_once(self) -> None:
        """On 25 October 2026 the local clock repeats 02:00–03:00.

        A cron at 02:30 must yield exactly one UTC instant (the first
        occurrence, ``fold=0``), so the slot fires once not twice.
        """
        # Right before the repeat: 24 October 23:00 UTC.
        base = datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
        first = _next_cron_occurrence("30 2 * * *", base, "Europe/Vienna")
        # CEST 02:30 (first occurrence) = 00:30 UTC on 25 Oct.
        assert first == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)

        # Asking again from just after the first fire must roll forward to
        # the *next* day, NOT to the second 02:30 (CET) on the same day.
        next_after = _next_cron_occurrence("30 2 * * *", first, "Europe/Vienna")
        assert next_after.date() == datetime(2026, 10, 26).date()


# ---------------------------------------------------------------------------
# Coalesce policy on restart (jobs missed during downtime)
# ---------------------------------------------------------------------------


class _StubStore:
    """Minimal job store seeded with pre-existing jobs."""

    def __init__(self, seeded: list[ScheduleJob] | None = None) -> None:
        self.jobs: dict[str, ScheduleJob] = {j.job_id: j for j in (seeded or [])}
        self.deleted: list[str] = []

    async def save(self, job: ScheduleJob) -> None:
        self.jobs[job.job_id] = job

    async def load(self, job_id: str) -> ScheduleJob | None:
        return self.jobs.get(job_id)

    async def load_all(self) -> list[ScheduleJob]:
        return list(self.jobs.values())

    async def delete(self, job_id: str) -> bool:
        self.deleted.append(job_id)
        return self.jobs.pop(job_id, None) is not None


async def _collect_first_event(fired: list[AgentEvent], timeout: float = 1.5) -> AgentEvent | None:
    """Wait up to ``timeout`` seconds for the first event."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if fired:
            return fired[0]
        await asyncio.sleep(0.05)
    return fired[0] if fired else None


class TestCoalescePolicy:
    @pytest.mark.spec("events-scheduler.coalesce_skip_drops_missed_runs")
    async def test_skip_does_not_fire_catch_up_for_interval(self) -> None:
        """``coalesce=skip``: 2 days of missed runs become zero firings."""
        fired: list[AgentEvent] = []

        async def on_event(event: AgentEvent) -> None:
            fired.append(event)

        # Job last ran 2 days ago, interval=1h → ~48 missed runs.
        old = datetime.now(UTC) - timedelta(days=2)
        job = ScheduleJob(
            name="hourly",
            schedule_type=ScheduleType.INTERVAL,
            expression="3600s",
            action=ScheduleAction(ScheduleActionType.SEND_NOTIFICATION),
            coalesce=CoalescePolicy.SKIP,
            last_run=old,
        )

        store = _StubStore([job])
        svc = SchedulerService(job_store=store, event_callback=on_event)
        await svc.start()
        try:
            # Give the loop enough time to evaluate catch-up but not enough
            # to reach the next scheduled tick (1 hour away).
            await asyncio.sleep(0.3)
            assert fired == [], f"SKIP must not fire catch-up events, got {len(fired)}"
        finally:
            await svc.stop()

    @pytest.mark.spec("events-scheduler.coalesce_run_once_fires_single_catchup")
    async def test_run_once_fires_a_single_catch_up(self) -> None:
        """``coalesce=run_once``: any number of missed runs → exactly one fire."""
        fired: list[AgentEvent] = []

        async def on_event(event: AgentEvent) -> None:
            fired.append(event)

        old = datetime.now(UTC) - timedelta(days=2)
        job = ScheduleJob(
            name="hourly_catchup",
            schedule_type=ScheduleType.INTERVAL,
            expression="3600s",
            action=ScheduleAction(ScheduleActionType.SEND_NOTIFICATION),
            coalesce=CoalescePolicy.RUN_ONCE,
            last_run=old,
        )

        store = _StubStore([job])
        svc = SchedulerService(job_store=store, event_callback=on_event)
        await svc.start()
        try:
            event = await _collect_first_event(fired)
            assert event is not None, "RUN_ONCE must fire a catch-up event"
            # Crucially: not 48 events.
            await asyncio.sleep(0.2)
            assert len(fired) == 1, f"RUN_ONCE must fire exactly once on startup, got {len(fired)}"
        finally:
            await svc.stop()


# ---------------------------------------------------------------------------
# One-shot idempotency on restart
# ---------------------------------------------------------------------------


class TestOneShotIdempotency:
    @pytest.mark.spec("events-scheduler.one_shot_already_fired_skipped_on_restart")
    async def test_one_shot_persisted_as_fired_does_not_refire(self, tmp_path: Path) -> None:
        """A one-shot job whose ``last_fired_at`` is set must not fire again
        when the scheduler reloads jobs from disk on startup.
        """
        fired: list[AgentEvent] = []

        async def on_event(event: AgentEvent) -> None:
            fired.append(event)

        # Construct a one-shot job that the previous scheduler instance had
        # already begun firing (last_fired_at set, expression in the past).
        already_fired = ScheduleJob(
            name="reminder",
            schedule_type=ScheduleType.ONE_SHOT,
            expression=(datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            action=ScheduleAction(ScheduleActionType.SEND_NOTIFICATION),
            last_fired_at=datetime.now(UTC) - timedelta(minutes=5),
        )

        store = _StubStore([already_fired])
        svc = SchedulerService(job_store=store, event_callback=on_event)
        await svc.start()
        try:
            await asyncio.sleep(0.3)
            assert fired == [], "One-shot with last_fired_at set must not refire on restart"
            # And it must be removed from the store so it cannot resurface.
            assert already_fired.job_id in store.deleted
            assert await svc.get_job(already_fired.job_id) is None
        finally:
            await svc.stop()

    @pytest.mark.spec("events-scheduler.fire_persists_last_fired_at_before_action")
    async def test_one_shot_persists_last_fired_before_dispatch(self, tmp_path: Path) -> None:
        """``last_fired_at`` is written *before* the event callback runs.

        We assert the job is persisted with ``last_fired_at`` set during the
        callback, so a crash inside the callback would not lose the fact
        that the job already fired.
        """
        captured: dict[str, datetime | None] = {"last_fired": None}

        store = _StubStore()

        async def on_event(event: AgentEvent) -> None:
            # When the callback runs, the persisted store should already
            # contain ``last_fired_at`` (i.e. persistence happened first).
            job_id = event.payload["job_id"]
            captured["last_fired"] = store.jobs[job_id].last_fired_at

        svc = SchedulerService(job_store=store, event_callback=on_event)
        fire_at = (datetime.now(UTC) + timedelta(milliseconds=50)).isoformat()
        job = ScheduleJob(
            name="early-persist",
            schedule_type=ScheduleType.ONE_SHOT,
            expression=fire_at,
            action=ScheduleAction(ScheduleActionType.SEND_NOTIFICATION),
        )

        await svc.start()
        try:
            await svc.add_job(job)
            await asyncio.sleep(0.4)
            assert (
                captured["last_fired"] is not None
            ), "last_fired_at must be persisted before the action callback"
        finally:
            await svc.stop()


# ---------------------------------------------------------------------------
# One-shot with naive ISO datetime + job timezone
# ---------------------------------------------------------------------------


class TestOneShotTimezone:
    async def test_naive_iso_datetime_uses_job_timezone(self, tmp_path: Path) -> None:
        """A naive ISO datetime in ``expression`` is interpreted in
        ``job.timezone`` rather than as UTC."""
        fired: list[AgentEvent] = []

        async def on_event(event: AgentEvent) -> None:
            fired.append(event)

        # 100ms in the future, expressed as a naive Vienna local time.
        zone = ZoneInfo("Europe/Vienna")
        local_target = datetime.now(zone) + timedelta(milliseconds=100)
        naive_iso = local_target.replace(tzinfo=None).isoformat()

        store = _StubStore()
        svc = SchedulerService(job_store=store, event_callback=on_event)
        await svc.start()
        try:
            job = ScheduleJob(
                name="vienna-shot",
                schedule_type=ScheduleType.ONE_SHOT,
                expression=naive_iso,
                action=ScheduleAction(ScheduleActionType.SEND_NOTIFICATION),
                timezone="Europe/Vienna",
            )
            await svc.add_job(job)
            await asyncio.sleep(0.5)
            assert len(fired) == 1
        finally:
            await svc.stop()


# ---------------------------------------------------------------------------
# Domain-model serialization round-trip
# ---------------------------------------------------------------------------


class TestScheduleJobSerialization:
    def test_new_fields_round_trip(self) -> None:
        job = ScheduleJob(
            name="x",
            schedule_type=ScheduleType.CRON,
            expression="0 8 * * *",
            timezone="Europe/Vienna",
            coalesce=CoalescePolicy.RUN_ONCE,
            last_fired_at=datetime(2026, 5, 1, 6, 0, tzinfo=UTC),
        )
        restored = ScheduleJob.from_dict(job.to_dict())
        assert restored.timezone == "Europe/Vienna"
        assert restored.coalesce == CoalescePolicy.RUN_ONCE
        assert restored.last_fired_at == datetime(2026, 5, 1, 6, 0, tzinfo=UTC)

    def test_legacy_dict_without_new_fields_uses_defaults(self) -> None:
        legacy = {
            "job_id": "abc",
            "name": "legacy",
            "schedule_type": "cron",
            "expression": "0 8 * * *",
            "action": {"action_type": "send_notification", "params": {}},
        }
        restored = ScheduleJob.from_dict(legacy)
        assert restored.timezone == "UTC"
        assert restored.coalesce == CoalescePolicy.SKIP
        assert restored.last_fired_at is None


@pytest.fixture(autouse=True)
def _no_external_tz_dep() -> None:
    """Sanity guard: zoneinfo must resolve Europe/Vienna on the test host."""
    ZoneInfo("Europe/Vienna")
