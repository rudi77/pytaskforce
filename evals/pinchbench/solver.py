"""Inspect AI solver that runs Taskforce against a single pinchbench task.

Differs from ``evals/bridge/taskforce_bridge.py:taskforce_solver`` in two
ways tailored to pinchbench:

1. Provisions an isolated workspace directory (with any fixture files
   declared in the task frontmatter copied from ``skill/assets/``) and
   tells the agent to use it via prompt augmentation, so the agent's
   file tools land their writes where the grader will look.
2. Captures the full Taskforce event stream and converts it into the
   pinchbench transcript shape (see ``transcript.py``), stashing the
   result plus the workspace path in ``state.metadata`` for the scorer.

The solver does **not** ``chdir`` into the workspace — Inspect AI runs
samples concurrently and ``os.chdir`` is process-wide, which would let
parallel samples step on each other. The agent gets the workspace path
in the prompt and uses absolute paths.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from inspect_ai.solver import Solver, TaskState, solver

from evals.pinchbench.loader import SKILL_DIR
from evals.pinchbench.transcript import build_transcript

logger = logging.getLogger(__name__)


def _provision_workspace(workspace_files: list[Any]) -> Path:
    """Create a temp workspace and materialise any declared fixture files.

    Supports three ``workspace_files`` shapes in task frontmatter:

    1. ``["data.csv", "fixtures/x.json"]`` — relative paths copied from
       ``skill/assets/`` to ``workspace/<basename>``.
    2. ``[{"path": "data.csv", "content": "..."}]`` — inline file written
       directly into the workspace at the given path.
    3. ``[{"source": "csvs/x.csv", "dest": "x.csv"}]`` — asset copied from
       ``skill/assets/<source>`` to ``workspace/<dest>`` (preserves rename).
    """
    workspace = Path(tempfile.mkdtemp(prefix="pinchbench_ws_"))
    assets_dir = SKILL_DIR / "assets"
    for entry in workspace_files or []:
        if isinstance(entry, dict):
            if "content" in entry and entry.get("path"):
                dest = workspace / entry["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(entry["content"], encoding="utf-8")
                continue
            source = entry.get("source")
            dest_rel = entry.get("dest") or source
            if not source:
                logger.warning(
                    "pinchbench workspace_files dict missing 'source'/'content': %r "
                    "(workspace %s)",
                    entry,
                    workspace,
                )
                continue
            src = assets_dir / source
            if not src.exists():
                logger.warning(
                    "pinchbench fixture not found: %s (workspace %s)", src, workspace
                )
                continue
            dest = workspace / dest_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest)
            continue

        src = assets_dir / entry
        if not src.exists():
            logger.warning(
                "pinchbench fixture not found: %s (workspace %s)", src, workspace
            )
            continue
        dest = workspace / Path(entry).name
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)
    return workspace


def _augment_prompt(prompt: str, workspace: Path) -> str:
    return (
        f"{prompt}\n\n"
        f"---\nYour task workspace is `{workspace}` (absolute path). "
        f"Read, write, and create any files inside that directory using "
        f"absolute paths. Treat it as your working directory; do not assume "
        f"the process CWD points there."
    )


def _extract_final_text(events: list[Any]) -> str:
    """Pull a final assistant message off the COMPLETE event if present."""
    from taskforce.core.domain.enums import EventType

    for evt in reversed(events):
        evt_type = evt.event_type
        evt_str = evt_type.value if hasattr(evt_type, "value") else str(evt_type)
        if evt_str == EventType.COMPLETE.value:
            return getattr(evt, "message", "") or ""
        if evt_str == EventType.FINAL_ANSWER.value:
            return (getattr(evt, "details", {}) or {}).get("content", "") or ""
    return ""


def _derive_run_status(events: list[Any]) -> tuple[str, str]:
    """Derive ``(status, error_kind)`` from the executor's event stream.

    Reads the final COMPLETE event's ``status`` field (which honours
    salvaged finals from ``_react_loop`` — see #407). Returns
    ``("completed", "")`` for a clean run, ``("failed", "<reason>")``
    otherwise. The salvage reason / error message is captured from the
    final FINAL_ANSWER metadata when available (``salvage_reason``,
    ``missing_deliverables``) and falls back to the COMPLETE message.
    """
    from taskforce.core.domain.enums import EventType, ExecutionStatus

    status = "completed"
    error_kind = ""
    for evt in reversed(events):
        evt_str = (
            evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type)
        )
        details = getattr(evt, "details", {}) or {}
        if evt_str == EventType.COMPLETE.value:
            raw_status = str(details.get("status") or "").lower()
            if raw_status == ExecutionStatus.FAILED.value:
                status = "failed"
                error_kind = error_kind or (getattr(evt, "message", "") or "")
            break
    if status == "failed":
        # Walk forward to find the salvage marker on the final answer.
        for evt in events:
            evt_str = (
                evt.event_type.value
                if hasattr(evt.event_type, "value")
                else str(evt.event_type)
            )
            details = getattr(evt, "details", {}) or {}
            if evt_str == EventType.FINAL_ANSWER.value and details.get("salvaged"):
                reason = details.get("salvage_reason") or "salvaged"
                missing = details.get("missing_deliverables")
                error_kind = (
                    f"{reason}: missing {missing}" if missing else str(reason)
                )
                break
    return status, error_kind


@solver
def pinchbench_solver(
    profile: str = "pinchbench",
    max_steps: int | None = None,  # noqa: ARG001
) -> Solver:
    """Run a Taskforce agent against one pinchbench sample."""

    async def solve(state: TaskState, generate: Any) -> TaskState:  # noqa: ARG001
        from taskforce.application.executor import AgentExecutor
        from taskforce.application.factory import AgentFactory

        meta = state.metadata or {}

        if meta.get("pinchbench_multi_session_prompts"):
            logger.warning(
                "pinchbench task %s has multi_session_prompts; running "
                "as a single session (multi-session execution not yet "
                "implemented). Score may underrepresent capability.",
                meta.get("pinchbench_task_id", "<unknown>"),
            )

        workspace_files: list[str] = list(meta.get("pinchbench_workspace_files") or [])
        workspace = _provision_workspace(workspace_files)
        prompt = _augment_prompt(state.input_text, workspace)

        factory = AgentFactory()
        executor = AgentExecutor(factory)
        events: list[Any] = []

        try:
            async for update in executor.execute_mission_streaming(
                mission=prompt,
                profile=profile,
                planning_strategy=None,
                planning_strategy_params=None,
            ):
                events.append(update)
        except Exception as exc:  # noqa: BLE001
            logger.error("pinchbench solver: agent execution failed: %s", exc)
            state.metadata = {
                **meta,
                "pinchbench_status": "error",
                "pinchbench_error": str(exc),
                "pinchbench_workspace": str(workspace),
                "pinchbench_transcript": build_transcript(events, prompt),
            }
            return state

        transcript = build_transcript(events, prompt)
        final_text = _extract_final_text(events)
        run_status, run_error = _derive_run_status(events)

        state.output = state.output.model_copy(update={"completion": final_text})
        state.metadata = {
            **meta,
            # #407: honour the executor's FAILED status — was always
            # "completed" before, which made mid-run aborts invisible to
            # downstream analysis.
            "pinchbench_status": run_status,
            "pinchbench_error": run_error,
            "pinchbench_workspace": str(workspace),
            "pinchbench_transcript": transcript,
            "pinchbench_event_count": len(events),
        }
        return state

    return solve
