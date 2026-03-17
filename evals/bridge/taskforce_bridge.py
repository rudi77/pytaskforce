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
You are an expert software engineer. You fix bugs in Python repositories.
You work inside a Docker container. The repo is at `/testbed`.

Your tools: **shell** and **edit** only.
Use shell for everything: cat, grep, find, git, python, pytest.
Use edit for precise find-and-replace edits in source files.

## RULES

- You MUST make source code changes. The bug is REAL.
- NEVER conclude "already fixed" or "no changes needed".
- Do NOT modify setup.py, setup.cfg, pyproject.toml, or test files.
- Most fixes are 1-10 lines. If >20 lines, you're overcomplicating.
- DELETING code is often correct (removing a wrong condition/override).
- Pipe long output through `| tail -60` or `| head -80`.

## SCRATCHPAD

You MUST maintain `/testbed/SCRATCHPAD.md` as your working memory.
Write analysis, baseline, and attempt history there.
Re-read it (`cat /testbed/SCRATCHPAD.md`) before each new attempt.
This file survives context compression — your memory does not.

## WORKFLOW

### PHASE 1: ANALYZE (no code changes!)

1. Read the failing test to understand expected behavior:
   shell: cat /testbed/{test_file_hint} | head -200

2. Note which source files the test imports — ONLY edit files the test imports.

3. Capture baseline — record which tests currently pass:
   shell: cd /testbed && python -m pytest {test_module_hint} --timeout=120 --tb=no -q 2>&1 | tail -40

4. Read the source code that the test imports:
   shell: cat -n /testbed/<source_file.py> | head -300

5. Before editing, TEST YOUR HYPOTHESIS with a quick Python check:
   shell: cd /testbed && python -c "from module import func; print(func(args))"
   If output doesn't match expectations, investigate more before editing.

6. Write analysis + plan to scratchpad:
   shell: cat > /testbed/SCRATCHPAD.md << 'SCRATCHPAD'
   ## Issue Analysis
   - Bug: <what is wrong>
   - Expected: <correct behavior from test assertions>
   - Source file: <path>
   - Function/method: <name>
   - Baseline: X passed, Y failed
   - Passing tests to protect: <list key test names>
   ## Plan
   - Change: <what to change and why>
   - Why safe: <why existing tests won't break>
   SCRATCHPAD

### PHASE 2: IMPLEMENT

7. Apply fix with edit (EXACT strings from cat output, no line numbers).

8. Verify — run full test module:
   shell: cd /testbed && python -m pytest {test_module_hint} --timeout=120 --tb=short -q 2>&1 | tail -60

9. If all tests pass: done! Run `git diff` to confirm.

### PHASE 3: REGRESSION RECOVERY (if any baseline test broke)

**STOP. Do NOT just revert and retry the same thing.**

10. KEEP your fix applied. Understand the regression FIRST:
    shell: cd /testbed && python -m pytest {test_module_hint} --timeout=120 --tb=long 2>&1 | grep -A 25 "FAILED"

11. Read the regressing test to understand what it expects.

12. Update scratchpad with what you learned about the regression.

13. Use git stash to PRESERVE your fix while you investigate:
    shell: cd /testbed && git stash
    (Read the regressing test in original code)
    shell: cd /testbed && git stash pop
    Now make it CONDITIONAL — add if/else to handle both old and new case.

14. Re-read scratchpad: shell: cat /testbed/SCRATCHPAD.md

15. Implement a DIFFERENT approach informed by the regression analysis.
    Do NOT just revert to scratch. Your fix is 90%+ correct — refine it.

### SOLVING REGRESSIONS — KEY STRATEGIES

Your fix must satisfy TWO constraints: new test expects A, old test expects B.
Common solutions:
- Make fix CONDITIONAL: only apply to the specific case the new test covers
- Fix at a DIFFERENT level: caller instead of callee, or vice versa
- Add a parameter with old behavior as default
- Fix the ROOT CAUSE: maybe the real bug is elsewhere
- NARROWER fix: change less code, target only the broken path
"""


@solver
def taskforce_swebench_solver(
    profile: str = "swe_bench",
    max_steps: int = 80,
    planning_strategy: str = "native_react",
) -> Solver:
    """Inspect AI solver for SWE-bench using minimal sandbox tools.

    Uses only shell + edit tools to maximize context budget. The agent
    uses shell for cat, grep, find, git, pytest, etc.

    Args:
        profile: Base Taskforce profile for LLM/infra config.
        max_steps: Maximum agent execution steps.
        planning_strategy: Planning strategy (default: native_react).
    """

    async def solve(state: TaskState, generate: Any) -> TaskState:
        from inspect_ai.util import sandbox

        from taskforce.application.executor import AgentExecutor
        from taskforce.application.factory import AgentFactory
        from taskforce.core.domain.lean_agent_components.tool_executor import (
            ToolExecutor,
        )
        from taskforce.core.tools.tool_converter import tools_to_openai_format

        from evals.bridge.sandbox_tools import create_sandbox_tools_minimal

        prompt = state.input_text

        # Extract test module path from FAIL_TO_PASS for baseline testing.
        fail_to_pass = state.metadata.get("FAIL_TO_PASS", "")
        test_module_hint = ""
        test_file_hint = ""
        first_test = ""
        if fail_to_pass:
            if isinstance(fail_to_pass, list):
                test_list = "\n".join(f"  - {t}" for t in fail_to_pass[:5])
                first_test = fail_to_pass[0]
            else:
                test_list = f"  - {fail_to_pass}"
                first_test = fail_to_pass

            # Extract test module path (everything before ::)
            test_module_hint = (
                first_test.split("::")[0] if "::" in first_test else first_test
            )
            test_file_hint = test_module_hint

            prompt += (
                f"\n\n## Tests that MUST pass after your fix\n"
                f"{test_list}\n"
                f"\nNOTE: These tests may NOT exist yet in the repo (they may be "
                f"added by a test patch later). If a test is not found, you must "
                f"STILL fix the source code based on the issue description above.\n"
                f"\nTo try running: shell: cd /testbed && python -m pytest "
                f"{first_test} -xvs 2>&1 | tail -60"
            )

        # Inject hints_text if available.
        hints_text = state.metadata.get("hints_text", "")
        if hints_text and len(str(hints_text).strip()) > 10:
            prompt += (
                f"\n\n## Hints from maintainers (READ CAREFULLY)\n"
                f"{str(hints_text).strip()[:800]}"
            )

        # Build the system prompt with test module placeholders.
        system_prompt = _SWE_BENCH_SYSTEM_PROMPT.replace(
            "{test_file_hint}", test_file_hint or "<test_file_path>"
        ).replace(
            "{test_module_hint}", test_module_hint or "<test_module>"
        )

        # Get the Inspect AI sandbox environment (Docker container)
        sbx = sandbox()

        # Minimal toolset: shell + edit only (saves ~1500 tokens/iteration)
        sandbox_tool_list = create_sandbox_tools_minimal(sbx)

        # Create agent via factory to get LLM provider, state manager, etc.
        factory = AgentFactory()
        agent = await factory.create_agent(config=profile)

        # Override settings for SWE-bench
        agent._base_system_prompt = system_prompt
        agent.prompt_builder._base_system_prompt = system_prompt
        agent.max_steps = max_steps

        # Replace host tools with sandbox tools only — no planner tool.
        sandbox_tools_dict = {t.name: t for t in sandbox_tool_list}
        agent._planner = None
        agent.tools = sandbox_tools_dict
        agent._openai_tools = tools_to_openai_format(agent.tools)
        agent.tool_executor = ToolExecutor(
            tools=agent.tools, logger=agent.logger
        )
        agent.message_history_manager._openai_tools = agent._openai_tools

        # Monkey-patch _build_system_prompt to inject step-budget warnings.
        _original_build_system_prompt = agent._build_system_prompt

        def _budget_aware_system_prompt(
            mission=None, state=None, messages=None
        ):
            base = _original_build_system_prompt(
                mission=mission, state=state, messages=messages
            )
            if messages:
                tool_calls = sum(
                    1
                    for m in messages
                    if m.get("role") == "assistant" and m.get("tool_calls")
                )
                remaining = max_steps - tool_calls
                if remaining <= 10:
                    base += (
                        "\n\n## URGENT: VERY LOW BUDGET"
                        f"\n{tool_calls}/{max_steps} steps used."
                        f" Only ~{remaining} remain."
                        "\nWrap up NOW. Commit to your best fix."
                        "\nRun: cat /testbed/SCRATCHPAD.md to review"
                        " what you've tried, then finalize."
                    )
                elif remaining <= 25:
                    base += (
                        "\n\n## BUDGET WARNING"
                        f"\n{tool_calls}/{max_steps} steps used."
                        f" ~{remaining} remain."
                        "\nBe efficient. If stuck, read your SCRATCHPAD."
                    )
            return base

        agent._build_system_prompt = _budget_aware_system_prompt

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
            logger.error(
                f"Taskforce SWE-bench agent failed: {e}", exc_info=True
            )
            return _write_error_metadata(state, e)

        return _write_metadata(state, acc)

    return solve
