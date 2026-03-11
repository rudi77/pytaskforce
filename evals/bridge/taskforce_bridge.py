"""Taskforce Agent Bridge for Inspect AI.

Wraps the Taskforce AgentExecutor as an Inspect AI solver,
enabling evaluation of Taskforce agents against standardized benchmarks.

Provides two solver variants:

- ``taskforce_solver``      – runs the agent with its normal host tools
  (for custom coding benchmarks, model baselines, etc.)
- ``taskforce_swebench_solver`` – replaces host tools with sandbox-aware
  wrappers so the agent operates *inside* the SWE-bench Docker container.
"""

import logging
from typing import Any

from inspect_ai.solver import Solver, TaskState, solver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared streaming event accumulator
# ---------------------------------------------------------------------------

def _collect_events(update: Any, acc: dict[str, Any]) -> None:
    """Accumulate metrics from a single streaming ProgressUpdate."""
    from taskforce.core.domain.enums import EventType

    evt = update.event_type
    evt_str = evt.value if isinstance(evt, EventType) else str(evt)
    acc["history_types"].append(evt_str)

    if evt_str == EventType.TOOL_CALL.value:
        acc["tool_calls"] += 1
    elif evt_str == EventType.TOOL_RESULT.value:
        acc["tool_results"] += 1
    elif evt_str == EventType.TOKEN_USAGE.value:
        usage = update.details or {}
        acc["prompt_tokens"] += usage.get("prompt_tokens", 0)
        acc["completion_tokens"] += usage.get("completion_tokens", 0)
        acc["total_tokens"] += usage.get("total_tokens", 0)
    elif evt_str == EventType.FINAL_ANSWER.value:
        content = (update.details or {}).get("content", "")
        if content:
            acc["final_message"] = str(content).strip()
    elif evt_str == EventType.COMPLETE.value:
        details = update.details or {}
        acc["status"] = details.get("status", "completed")
        acc["session_id"] = details.get("session_id", "")
        if not acc["final_message"]:
            msg = details.get("final_message") or update.message or ""
            acc["final_message"] = str(msg).strip()

    step_events = {
        EventType.TOOL_CALL.value,
        EventType.TOOL_RESULT.value,
        EventType.PLAN_UPDATED.value,
        EventType.ASK_USER.value,
    }
    if evt_str in step_events:
        acc["total_steps"] += 1


def _new_accumulator() -> dict[str, Any]:
    return {
        "tool_calls": 0,
        "tool_results": 0,
        "total_steps": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "final_message": "",
        "status": "unknown",
        "session_id": "",
        "history_types": [],
    }


def _write_metadata(state: TaskState, acc: dict[str, Any]) -> TaskState:
    """Write accumulated metrics into Inspect state metadata."""
    state.output = state.output.model_copy(
        update={"completion": acc["final_message"]}
    )
    state.metadata = state.metadata or {}
    state.metadata["taskforce_status"] = str(acc["status"])
    state.metadata["taskforce_session_id"] = acc["session_id"]
    state.metadata["taskforce_token_usage"] = {
        "prompt_tokens": acc["prompt_tokens"],
        "completion_tokens": acc["completion_tokens"],
        "total_tokens": acc["total_tokens"],
    }
    state.metadata["taskforce_steps"] = acc["total_steps"]
    state.metadata["taskforce_tool_calls"] = acc["tool_calls"]
    return state


def _write_error_metadata(state: TaskState, error: Exception) -> TaskState:
    """Write error metadata when agent execution fails."""
    state.metadata = state.metadata or {}
    state.metadata["taskforce_status"] = "error"
    state.metadata["taskforce_error"] = str(error)
    state.metadata["taskforce_token_usage"] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    state.metadata["taskforce_steps"] = 0
    state.metadata["taskforce_tool_calls"] = 0
    return state


# ---------------------------------------------------------------------------
# Original solver (host tools)
# ---------------------------------------------------------------------------

@solver
def taskforce_solver(
    profile: str = "coding_agent",
    max_steps: int | None = None,
    planning_strategy: str | None = None,
    work_dir: str | None = None,
) -> Solver:
    """Inspect AI solver that delegates to a Taskforce agent.

    Uses execute_mission_streaming to capture fine-grained execution
    metrics (steps, tool calls, token usage) that the non-streaming
    path discards.

    Args:
        profile: Taskforce profile name (e.g. "coding_agent", "dev").
        max_steps: Override max execution steps (None = use profile default).
        planning_strategy: Override planning strategy (None = use profile default).
        work_dir: Working directory for agent persistence. Defaults to a temp dir.
    """

    async def solve(state: TaskState, generate: Any) -> TaskState:
        from taskforce.application.executor import AgentExecutor
        from taskforce.application.factory import AgentFactory

        prompt = state.input_text
        factory = AgentFactory()
        executor = AgentExecutor(factory)
        acc = _new_accumulator()

        try:
            async for update in executor.execute_mission_streaming(
                mission=prompt,
                profile=profile,
                planning_strategy=planning_strategy,
                planning_strategy_params=None,
            ):
                _collect_events(update, acc)
        except Exception as e:
            logger.error(f"Taskforce agent execution failed: {e}")
            return _write_error_metadata(state, e)

        return _write_metadata(state, acc)

    return solve


# ---------------------------------------------------------------------------
# SWE-bench solver (sandbox tools)
# ---------------------------------------------------------------------------

_SWE_BENCH_SYSTEM_PROMPT = """\
You are an expert software engineer tasked with resolving a GitHub issue.

You are working inside a Docker container with the full repository checked out
at `/testbed`. All your tools (shell, file_read, file_write, edit, grep, glob,
git) operate inside this container.

## MANDATORY FIRST STEP

Run this command FIRST to confirm you can see the repository:
  shell: ls /testbed

All file paths are relative to `/testbed` or absolute starting with `/testbed/`.

## WORKFLOW

1. **Orient yourself**: Run `ls /testbed` and `git log --oneline -5` to see
   the repo structure and recent history.
2. **Understand the issue**: Read the issue description carefully. Identify
   which module/file is likely affected.
3. **Find the relevant test**: Search for existing test files related to the
   issue. Use `grep` with pattern `*.py` (not `**/*.py`) for include filters.
   Read the test to understand expected behavior — this tells you what the fix
   must accomplish.
4. **Find the root cause**: Use `grep` and `file_read` to locate the relevant
   source code. Trace the bug to the EXACT function/line that is wrong.
   Do NOT fix a caller when the bug is in the callee.
5. **Implement the MINIMAL fix**: Use `edit` to change ONLY what is needed.
   Prefer 1-5 line changes. If your fix is more than 10 lines, reconsider
   whether you are targeting the right location.
   Do NOT modify `setup.py`, `setup.cfg`, `pyproject.toml`, or CI configs.
6. **Test your fix** (see REVERT-AND-RETRY below).
7. **Review your diff**: Run `git diff` to confirm your changes are minimal
   and correct. If you changed more than 2 files, reconsider.

## REVERT-AND-RETRY (CRITICAL)

You are a professional software engineer. You test every fix and revert when
tests fail. This is your most important discipline.

After EVERY code change, follow this cycle:

```
LOOP (up to 3 attempts):
  1. Run the specific failing test:
       shell: cd /testbed && python -m pytest <test_file>::<test_name> -xvs
  2. If test PASSES → go to step 5
  3. If test FAILS → REVERT everything:
       shell: cd /testbed && git checkout .
     This gives you a clean slate. Do NOT layer fixes on top of failed fixes.
  4. Re-read the error message. Think about what went wrong. Try a DIFFERENT
     approach (different function, different logic, different file).
     Go back to step 1.
  5. Run broader tests to check for regressions:
       shell: cd /testbed && python -m pytest <test_module> -x --timeout=60
  6. If broader tests FAIL → REVERT and retry with a different approach:
       shell: cd /testbed && git checkout .
  7. When all tests pass → run `git diff` to verify your changes.
```

KEY PRINCIPLES:
- `git checkout .` reverts ALL uncommitted changes. Use it liberally.
- NEVER layer a second fix on top of a failed first fix. Always revert first.
- 2-3 attempts is normal. The first attempt often reveals what the real fix is.
- If after 3 attempts you cannot get tests to pass, step back and re-analyze
  the root cause — you may be fixing the wrong location.

## CRITICAL RULES

- You MUST make code changes to SOURCE files. Do NOT just analyze — implement the fix.
- You MUST run tests after every change. No exceptions.
- If a test still fails after your fix, REVERT with `git checkout .` and try
  a DIFFERENT approach. NEVER layer fixes on top of failed fixes.
- Make MINIMAL changes — fix only what the issue requires. The best fix is
  usually 1-5 lines. If you're writing more, you're probably fixing the wrong
  thing.
- Do NOT modify build/config files (setup.py, pyproject.toml, etc.).
- Use `shell` for command execution (it runs bash in the sandbox).
- For grep include patterns, use `*.py` (not `**/*.py`).
- If `grep` returns no matches, try broader patterns or use
  `shell: find /testbed -name "*.py" -path "*keyword*"` to explore.
- Read the existing test for the feature to understand expected behavior.
- If "Tests that MUST pass" are listed below the issue, run EXACTLY those
  tests — do not guess or substitute different test files.
"""


@solver
def taskforce_swebench_solver(
    profile: str = "coding_agent",
    max_steps: int = 60,
    planning_strategy: str = "spar",
) -> Solver:
    """Inspect AI solver for SWE-bench that uses sandbox-aware tools.

    Creates a Taskforce agent whose tools (shell, file_read, file_write,
    edit, grep, glob, git) all operate inside the SWE-bench Docker
    sandbox rather than on the host filesystem.

    Args:
        profile: Base Taskforce profile for LLM/infra config.
        max_steps: Maximum agent execution steps (default: 60).
        planning_strategy: Planning strategy (default: spar).
    """

    async def solve(state: TaskState, generate: Any) -> TaskState:
        from inspect_ai.util import sandbox

        from taskforce.application.executor import AgentExecutor
        from taskforce.application.factory import AgentFactory
        from taskforce.core.domain.lean_agent_components.tool_executor import (
            ToolExecutor,
        )
        from taskforce.core.tools.tool_converter import tools_to_openai_format

        from evals.bridge.sandbox_tools import create_sandbox_tools

        prompt = state.input_text

        # Inject FAIL_TO_PASS test names into the prompt so the agent
        # knows exactly which test must pass after the fix.
        fail_to_pass = state.metadata.get("FAIL_TO_PASS", "")
        if fail_to_pass:
            if isinstance(fail_to_pass, list):
                test_list = "\n".join(f"  - {t}" for t in fail_to_pass[:5])
            else:
                test_list = f"  - {fail_to_pass}"
            prompt += (
                f"\n\n## Tests that MUST pass after your fix\n"
                f"Run these tests to validate your fix works:\n{test_list}\n"
                f"\nExample: shell: cd /testbed && python -m pytest {fail_to_pass[0] if isinstance(fail_to_pass, list) else fail_to_pass} -xvs"
            )

        # Get the Inspect AI sandbox environment (Docker container)
        sbx = sandbox()

        # Create sandbox-aware tools that operate inside the container
        sandbox_tool_list = create_sandbox_tools(sbx)

        # Create agent via factory to get LLM provider, state manager, etc.
        # Note: factory.create_agent(config=...) does not accept inline
        # params like max_steps — we override them after creation.
        factory = AgentFactory()
        agent = await factory.create_agent(config=profile)

        # Override settings for SWE-bench
        agent._base_system_prompt = _SWE_BENCH_SYSTEM_PROMPT
        agent.prompt_builder._base_system_prompt = _SWE_BENCH_SYSTEM_PROMPT
        agent.max_steps = max_steps

        # Replace host tools with sandbox tools (keep planner tool)
        sandbox_tools_dict = {t.name: t for t in sandbox_tool_list}
        if agent._planner:
            sandbox_tools_dict[agent._planner.name] = agent._planner
        agent.tools = sandbox_tools_dict
        agent._openai_tools = tools_to_openai_format(agent.tools)
        agent.tool_executor = ToolExecutor(
            tools=agent.tools, logger=agent.logger
        )
        agent.message_history_manager._openai_tools = agent._openai_tools

        # Execute the agent
        executor = AgentExecutor(factory)
        acc = _new_accumulator()

        try:
            async for update in executor.execute_mission_streaming(
                mission=prompt,
                profile=profile,
                agent=agent,
                planning_strategy=planning_strategy,
            ):
                _collect_events(update, acc)
        except Exception as e:
            logger.error(f"Taskforce SWE-bench agent failed: {e}", exc_info=True)
            return _write_error_metadata(state, e)

        return _write_metadata(state, acc)

    return solve
