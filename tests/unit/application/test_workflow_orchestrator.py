"""Tests for WorkflowOrchestrator."""

from __future__ import annotations

from datetime import UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.application.workflow_orchestrator import WorkflowOrchestrator
from taskforce.core.domain.skill import Skill
from taskforce.core.domain.workflow import (
    HumanInputRequest,
    WorkflowRunRecord,
    WorkflowRunResult,
    WorkflowStatus,
)


def _make_skill(
    script: str = "scripts/workflow.py",
    script_engine: str = "test_engine",
    source_path: str = "/tmp/skills/test-skill",
) -> Skill:
    return Skill(
        name="test-skill",
        description="A test skill with script",
        instructions="Test instructions",
        source_path=source_path,
        script=script,
        script_engine=script_engine,
    )


def _make_engine(
    start_result: WorkflowRunResult | None = None,
    resume_result: WorkflowRunResult | None = None,
) -> MagicMock:
    engine = MagicMock()
    engine.engine_name = "test_engine"
    engine.start = AsyncMock(
        return_value=start_result
        or WorkflowRunResult(
            status=WorkflowStatus.COMPLETED,
            outputs={"booking_id": "B-001"},
        )
    )
    engine.resume = AsyncMock(
        return_value=resume_result
        or WorkflowRunResult(
            status=WorkflowStatus.COMPLETED,
            outputs={"booking_id": "B-002"},
        )
    )
    engine.get_checkpoint = MagicMock(return_value={"step": "test"})
    return engine


def _make_store() -> MagicMock:
    store = MagicMock()
    store.save = AsyncMock()
    store.load = AsyncMock(return_value=None)
    store.load_by_session = AsyncMock(return_value=None)
    store.delete = AsyncMock()
    store.list_waiting = AsyncMock(return_value=[])
    return store


async def _noop_executor(name: str, params: dict[str, Any]) -> Any:
    return {"success": True}


class TestStartWorkflow:
    """Tests for starting a workflow."""

    @pytest.mark.asyncio
    async def test_skill_without_script_fails(self) -> None:
        skill = Skill(
            name="no-script",
            description="No script skill",
            instructions="",
            source_path="/tmp/skills/no-script",
        )
        orchestrator = WorkflowOrchestrator(engines={}, run_store=_make_store())
        result = await orchestrator.start_workflow(
            session_id="s-1",
            skill=skill,
            input_data={},
            tool_executor=_noop_executor,
        )
        assert result.status == WorkflowStatus.FAILED
        assert "no script" in result.error.lower()

    @pytest.mark.asyncio
    async def test_engine_not_available(self) -> None:
        skill = _make_skill(script_engine="nonexistent")
        orchestrator = WorkflowOrchestrator(engines={}, run_store=_make_store())
        # Mock script loading to isolate engine lookup
        orchestrator._load_workflow_definition = MagicMock(return_value="mock_graph")
        result = await orchestrator.start_workflow(
            session_id="s-1",
            skill=skill,
            input_data={},
            tool_executor=_noop_executor,
        )
        assert result.status == WorkflowStatus.FAILED
        assert "not available" in result.error.lower()

    @pytest.mark.asyncio
    async def test_completed_workflow(self) -> None:
        engine = _make_engine()
        store = _make_store()
        orchestrator = WorkflowOrchestrator(
            engines={"test_engine": engine},
            run_store=store,
        )
        # Mock script loading
        orchestrator._load_workflow_definition = MagicMock(return_value="mock_graph")

        result = await orchestrator.start_workflow(
            session_id="s-1",
            skill=_make_skill(),
            input_data={"file_path": "/tmp/test.pdf"},
            tool_executor=_noop_executor,
        )
        assert result.status == WorkflowStatus.COMPLETED
        assert result.outputs == {"booking_id": "B-001"}
        store.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_paused_workflow_persists_state(self) -> None:
        hir = HumanInputRequest(
            question="Missing tax?",
            channel="telegram",
            recipient_id="sup_1",
        )
        engine = _make_engine(
            start_result=WorkflowRunResult(
                status=WorkflowStatus.WAITING_FOR_INPUT,
                human_input_request=hir,
            )
        )
        store = _make_store()
        orchestrator = WorkflowOrchestrator(
            engines={"test_engine": engine},
            run_store=store,
        )
        orchestrator._load_workflow_definition = MagicMock(return_value="mock_graph")

        result = await orchestrator.start_workflow(
            session_id="s-1",
            skill=_make_skill(),
            input_data={"file_path": "/tmp/test.pdf"},
            tool_executor=_noop_executor,
        )
        assert result.status == WorkflowStatus.WAITING_FOR_INPUT
        assert result.human_input_request is not None
        assert result.human_input_request.channel == "telegram"
        store.save.assert_called_once()
        saved_record = store.save.call_args[0][0]
        assert saved_record.status == WorkflowStatus.WAITING_FOR_INPUT


class TestResumeWorkflow:
    """Tests for resuming a paused workflow."""

    @pytest.mark.asyncio
    async def test_resume_nonexistent(self) -> None:
        store = _make_store()
        orchestrator = WorkflowOrchestrator(engines={}, run_store=store)
        result = await orchestrator.resume_workflow(
            run_id="nonexistent",
            response="test",
        )
        assert result.status == WorkflowStatus.FAILED
        assert "no workflow run found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_resume_completes(self) -> None:
        engine = _make_engine()
        store = _make_store()
        record = WorkflowRunRecord(
            run_id="run-1",
            session_id="s-1",
            workflow_name="test",
            status=WorkflowStatus.WAITING_FOR_INPUT,
            engine="test_engine",
            input_data={},
            checkpoint={"step": "compliance"},
        )
        store.load = AsyncMock(return_value=record)

        orchestrator = WorkflowOrchestrator(
            engines={"test_engine": engine},
            run_store=store,
        )
        result = await orchestrator.resume_workflow(
            run_id="run-1",
            response="Steuernummer: DE123456789",
        )
        assert result.status == WorkflowStatus.COMPLETED
        engine.resume.assert_called_once()
        store.delete.assert_called_once_with("run-1")

    @pytest.mark.asyncio
    async def test_resume_pauses_again(self) -> None:
        hir = HumanInputRequest(question="Approve booking?")
        engine = _make_engine(
            resume_result=WorkflowRunResult(
                status=WorkflowStatus.WAITING_FOR_INPUT,
                human_input_request=hir,
            )
        )
        store = _make_store()
        record = WorkflowRunRecord(
            run_id="run-1",
            session_id="s-1",
            workflow_name="test",
            status=WorkflowStatus.WAITING_FOR_INPUT,
            engine="test_engine",
            input_data={},
            checkpoint={"step": "compliance"},
        )
        store.load = AsyncMock(return_value=record)

        orchestrator = WorkflowOrchestrator(
            engines={"test_engine": engine},
            run_store=store,
        )
        result = await orchestrator.resume_workflow(
            run_id="run-1",
            response="Tax: DE123",
        )
        assert result.status == WorkflowStatus.WAITING_FOR_INPUT
        assert result.human_input_request.question == "Approve booking?"
        store.save.assert_called_once()
        store.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_by_session(self) -> None:
        engine = _make_engine()
        store = _make_store()
        record = WorkflowRunRecord(
            run_id="run-1",
            session_id="s-1",
            workflow_name="test",
            status=WorkflowStatus.WAITING_FOR_INPUT,
            engine="test_engine",
            input_data={},
            checkpoint={},
        )
        store.load_by_session = AsyncMock(return_value=record)
        store.load = AsyncMock(return_value=record)

        orchestrator = WorkflowOrchestrator(
            engines={"test_engine": engine},
            run_store=store,
        )
        result = await orchestrator.resume_by_session(
            session_id="s-1",
            response="Approved",
        )
        assert result is not None
        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_resume_by_session_no_match(self) -> None:
        store = _make_store()
        orchestrator = WorkflowOrchestrator(engines={}, run_store=store)
        result = await orchestrator.resume_by_session(
            session_id="unknown",
            response="test",
        )
        assert result is None


class TestCheckTimeouts:
    """Tests for timeout checking."""

    @pytest.mark.asyncio
    async def test_no_timeouts(self) -> None:
        store = _make_store()
        store.list_waiting = AsyncMock(return_value=[])
        orchestrator = WorkflowOrchestrator(engines={}, run_store=store)
        timed_out = await orchestrator.check_timeouts()
        assert timed_out == []

    @pytest.mark.asyncio
    async def test_timed_out_record(self) -> None:
        from datetime import datetime

        store = _make_store()
        old_time = datetime(2020, 1, 1, tzinfo=UTC)
        record = WorkflowRunRecord(
            run_id="run-1",
            session_id="s-1",
            workflow_name="test",
            status=WorkflowStatus.WAITING_FOR_INPUT,
            engine="test_engine",
            input_data={},
            checkpoint={},
            human_input_request=HumanInputRequest(
                question="Missing data?",
                timeout_seconds=60,
            ),
            updated_at=old_time,
        )
        store.list_waiting = AsyncMock(return_value=[record])
        orchestrator = WorkflowOrchestrator(engines={}, run_store=store)
        timed_out = await orchestrator.check_timeouts()
        assert len(timed_out) == 1
        assert timed_out[0].run_id == "run-1"

    @pytest.mark.asyncio
    async def test_not_yet_timed_out(self) -> None:
        from taskforce.core.utils.time import utc_now

        store = _make_store()
        record = WorkflowRunRecord(
            run_id="run-1",
            session_id="s-1",
            workflow_name="test",
            status=WorkflowStatus.WAITING_FOR_INPUT,
            engine="test_engine",
            input_data={},
            checkpoint={},
            human_input_request=HumanInputRequest(
                question="Missing data?",
                timeout_seconds=99999,
            ),
            updated_at=utc_now(),
        )
        store.list_waiting = AsyncMock(return_value=[record])
        orchestrator = WorkflowOrchestrator(engines={}, run_store=store)
        timed_out = await orchestrator.check_timeouts()
        assert timed_out == []

    @pytest.mark.asyncio
    async def test_no_timeout_seconds_excluded(self) -> None:
        store = _make_store()
        record = WorkflowRunRecord(
            run_id="run-1",
            session_id="s-1",
            workflow_name="test",
            status=WorkflowStatus.WAITING_FOR_INPUT,
            engine="test_engine",
            input_data={},
            checkpoint={},
            human_input_request=HumanInputRequest(question="No timeout set"),
        )
        store.list_waiting = AsyncMock(return_value=[record])
        orchestrator = WorkflowOrchestrator(engines={}, run_store=store)
        timed_out = await orchestrator.check_timeouts()
        assert timed_out == []
