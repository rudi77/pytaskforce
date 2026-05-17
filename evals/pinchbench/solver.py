"""Inspect AI solver that runs Taskforce against a single pinchbench task.

Differs from ``evals/bridge/taskforce_bridge.py:taskforce_solver`` in three
ways tailored to pinchbench:

1. Provisions an isolated workspace directory (with any fixture files
   declared in the task frontmatter copied from ``skill/assets/``) and
   ``cd``\\s into it for the duration of the agent run, so the agent's
   file tools land their writes where the grader will look.
2. Augments the prompt with the workspace path so the agent can use it
   in absolute paths if needed.
3. Captures the full Taskforce event stream and converts it into the
   pinchbench transcript shape (see ``transcript.py``), stashing the
   result plus the workspace path in ``state.metadata`` for the scorer.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from inspect_ai.solver import Solver, TaskState, solver

from evals.pinchbench.loader import SKILL_DIR
from evals.pinchbench.transcript import build_transcript

logger = logging.getLogger(__name__)


def _provision_workspace(workspace_files: list[str]) -> Path:
    """Create a temp workspace and copy any required fixture files."""
    workspace = Path(tempfile.mkdtemp(prefix="pinchbench_ws_"))
    assets_dir = SKILL_DIR / "assets"
    for rel in workspace_files or []:
        src = assets_dir / rel
        if not src.exists():
            logger.warning(
                "pinchbench fixture not found: %s (workspace %s)", src, workspace
            )
            continue
        dest = workspace / Path(rel).name
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)
    return workspace


def _augment_prompt(prompt: str, workspace: Path) -> str:
    return (
        f"{prompt}\n\n"
        f"---\nYour task workspace is `{workspace}`. "
        f"Read, write, and create any files inside that directory. "
        f"Treat it as your current working directory."
    )


@solver
def pinchbench_solver(
    profile: str = "pinchbench",
    max_steps: int | None = None,
) -> Solver:
    """Run a Taskforce agent against one pinchbench sample."""

    async def solve(state: TaskState, generate: Any) -> TaskState:  # noqa: ARG001
        from taskforce.application.executor import AgentExecutor
        from taskforce.application.factory import AgentFactory

        meta = state.metadata or {}
        workspace_files: list[str] = list(meta.get("pinchbench_workspace_files") or [])
        workspace = _provision_workspace(workspace_files)

        prompt = _augment_prompt(state.input_text, workspace)

        factory = AgentFactory()
        executor = AgentExecutor(factory)
        events: list[Any] = []

        original_cwd = Path.cwd()
        try:
            os.chdir(workspace)
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
        finally:
            os.chdir(original_cwd)

        transcript = build_transcript(events, prompt)

        # Extract a short final-message for inspect_ai's completion field.
        final_text = ""
        for entry in reversed(transcript):
            msg = entry.get("message") or {}
            if msg.get("role") == "assistant":
                for item in msg.get("content", []) or []:
                    if item.get("type") == "text" and item.get("text"):
                        final_text = item["text"]
                        break
                if final_text:
                    break

        state.output = state.output.model_copy(update={"completion": final_text})
        state.metadata = {
            **meta,
            "pinchbench_status": "completed",
            "pinchbench_workspace": str(workspace),
            "pinchbench_transcript": transcript,
            "pinchbench_event_count": len(events),
        }
        return state

    return solve
