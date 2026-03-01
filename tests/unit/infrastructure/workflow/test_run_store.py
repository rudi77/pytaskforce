"""Tests for FileWorkflowRunStore."""

import pytest

from taskforce.core.domain.workflow import (
    HumanInputRequest,
    WorkflowRunRecord,
    WorkflowStatus,
)
from taskforce.infrastructure.workflow.run_store import FileWorkflowRunStore


def _make_record(
    run_id: str = "run-001",
    session_id: str = "session-001",
    status: WorkflowStatus = WorkflowStatus.WAITING_FOR_INPUT,
) -> WorkflowRunRecord:
    return WorkflowRunRecord(
        run_id=run_id,
        session_id=session_id,
        workflow_name="test-workflow",
        status=status,
        engine="langgraph",
        input_data={"file_path": "/tmp/test.pdf"},
        checkpoint={"thread_id": run_id},
        human_input_request=HumanInputRequest(
            question="Test question?",
            channel="telegram",
            recipient_id="user_1",
        ),
    )


@pytest.mark.asyncio
async def test_save_and_load(tmp_path: str) -> None:
    store = FileWorkflowRunStore(work_dir=tmp_path)
    record = _make_record()

    await store.save(record)
    loaded = await store.load("run-001")

    assert loaded is not None
    assert loaded.run_id == "run-001"
    assert loaded.session_id == "session-001"
    assert loaded.status == WorkflowStatus.WAITING_FOR_INPUT
    assert loaded.engine == "langgraph"
    assert loaded.human_input_request is not None
    assert loaded.human_input_request.channel == "telegram"


@pytest.mark.asyncio
async def test_load_nonexistent(tmp_path: str) -> None:
    store = FileWorkflowRunStore(work_dir=tmp_path)
    result = await store.load("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_delete(tmp_path: str) -> None:
    store = FileWorkflowRunStore(work_dir=tmp_path)
    record = _make_record()

    await store.save(record)
    assert await store.load("run-001") is not None

    await store.delete("run-001")
    assert await store.load("run-001") is None


@pytest.mark.asyncio
async def test_list_waiting(tmp_path: str) -> None:
    store = FileWorkflowRunStore(work_dir=tmp_path)

    await store.save(_make_record("run-1", "s-1", WorkflowStatus.WAITING_FOR_INPUT))
    await store.save(_make_record("run-2", "s-2", WorkflowStatus.COMPLETED))
    await store.save(_make_record("run-3", "s-3", WorkflowStatus.WAITING_FOR_INPUT))

    waiting = await store.list_waiting()
    run_ids = {r.run_id for r in waiting}
    assert run_ids == {"run-1", "run-3"}


@pytest.mark.asyncio
async def test_load_by_session(tmp_path: str) -> None:
    store = FileWorkflowRunStore(work_dir=tmp_path)

    await store.save(_make_record("run-1", "s-1", WorkflowStatus.WAITING_FOR_INPUT))
    await store.save(_make_record("run-2", "s-2", WorkflowStatus.COMPLETED))

    result = await store.load_by_session("s-1")
    assert result is not None
    assert result.run_id == "run-1"

    result = await store.load_by_session("s-2")
    assert result is None  # completed, not waiting

    result = await store.load_by_session("nonexistent")
    assert result is None
