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
You are an expert software engineer. Your ONLY job is to resolve the GitHub
issue by editing source code files. You MUST make code changes.

You work inside a Docker container. The repository is at `/testbed`.
Your tools: shell, file_read, file_write, edit, grep, glob, git.

## CRITICAL: YOU MUST ALWAYS MAKE A CODE CHANGE

The issue described below is REAL and NEEDS a fix. Your job is to change
source code to fix it.

NEVER conclude that the bug is "already fixed" or "not present". NEVER say
"no code changes are needed". The bug EXISTS — you must find and fix it.

**Why tests may be misleading:** The test suite is modified AFTER you finish
your work. Some FAIL_TO_PASS tests listed below may not exist yet in the
repo, or may use parametrized values that are added later. If a test is
"not found" or seems to pass, that does NOT mean the bug is fixed. You must
STILL fix the source code based on the issue description.

## BUDGET

You have LIMITED tool calls. Be efficient.
- Max 3-4 tool calls for exploration.
- Move to implementing quickly.
- If an edit fails (old_string mismatch), re-read the file ONCE with
  file_read, then retry. Do NOT retry the same edit more than twice.
- NEVER repeat the same tool call with the same arguments.

## WORKFLOW

### Step 1: UNDERSTAND THE ISSUE (no tool calls needed)
Read the issue description below carefully. Identify:
- What behavior is wrong
- What the correct behavior should be
- Which module/class/function is likely involved

### Step 2: READ THE TEST CODE FIRST (1-2 tool calls) — MANDATORY
{baseline_test_module_section}
Read the FAIL_TO_PASS test file BEFORE doing anything else:
  file_read: path="/testbed/{test_file_hint}"
The test's imports tell you EXACTLY which source file to edit. The assertions
tell you EXACTLY what the correct behavior should be.
**Anti-pattern: NEVER edit a file that the test doesn't import from.**

### Step 2.5: CAPTURE BASELINE (1 tool call) — MANDATORY
Run the FULL test module to see which tests currently PASS:
  shell: cd /testbed && python -m pytest {test_module_hint} -x --timeout=120 2>&1 | tail -80
Record which tests pass. This is your baseline — you must NOT break any of them.

### Step 3: ORIENT & LOCATE (2-4 tool calls)
Use grep to find the relevant code based on imports from the test, then
file_read to see it:
  grep: pattern="function_name", path="/testbed", include="*.py"
  file_read: path="/testbed/path/to/file.py"
Note the EXACT text including whitespace — you need it for the edit tool.

### Step 4: IMPLEMENT THE FIX (1-2 tool calls)
Use edit with the EXACT old_string from file_read (without line number
prefixes). Keep changes minimal (1-5 lines ideal).

### Step 5: VERIFY AGAINST BASELINE (2-3 tool calls)
1. Run the ENTIRE test module (same command as Step 2.5):
     shell: cd /testbed && python -m pytest {test_module_hint} -x --timeout=120 2>&1 | tail -80
2. Compare against your baseline from Step 2.5:
   - ALL previously-passing tests MUST still pass
   - If ANY test regressed (was passing, now failing), REVERT immediately:
       shell: cd /testbed && git checkout .
     Then try a DIFFERENT approach that preserves backward compatibility.
3. After your final fix, run `git diff` to review. Your diff should be small
   and focused. If it looks too complex, simplify.

## WHEN YOUR FIX DOESN'T WORK

If tests still fail after your first attempt:
- Try the OPPOSITE approach (if you added code, try DELETING code instead;
  if you edited file A, try file B)
- Most fixes are 1-10 lines. If your diff is >20 lines, you're overcomplicating it
- DELETING code is often the correct fix (removing a special case, a wrong
  condition, an incorrect override)
- Try the SIMPLEST fix first — often it's a one-line change
- REVERT with `git checkout .` BEFORE each new attempt

## RULES

- You MUST make source code changes. No analysis-only responses.
- NEVER conclude "bug already fixed" or "no changes needed".
- NEVER ask for permission. Just implement the fix.
- Focus on the ISSUE DESCRIPTION and the TEST CODE to understand what the
  correct behavior should be. Tests may not fully exist in the repo yet,
  but if the test file exists, READ IT — it defines the expected behavior.
- ALWAYS run the full test module after editing (not just the single test).
  If ANY previously-passing test now fails, your fix has a regression.
  REVERT immediately with `git checkout .` and try a different approach
  that preserves backward compatibility.
- REVERT with `git checkout .` BEFORE trying any different approach.
- Do NOT modify setup.py, setup.cfg, pyproject.toml, or CI configs.
- Do NOT create new test files — only edit existing source code.
- Pipe long output through `| tail -80`.
- For grep include patterns, use `*.py` (not `**/*.py`).
- If you cannot find source files, try broader searches:
    find /testbed -type f -name "*.py" | grep <keyword> | head -20
    grep -r "class_name" /testbed --include="*.py" -l
"""


@solver
def taskforce_swebench_solver(
    profile: str = "swe_bench",
    max_steps: int = 120,
    planning_strategy: str = "native_react",
) -> Solver:
    """Inspect AI solver for SWE-bench that uses sandbox-aware tools.

    Creates a Taskforce agent whose tools (shell, file_read, file_write,
    edit, grep, glob, git) all operate inside the SWE-bench Docker
    sandbox rather than on the host filesystem.

    Args:
        profile: Base Taskforce profile for LLM/infra config.
        max_steps: Maximum agent execution steps (default: 100).
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

        from evals.bridge.sandbox_tools import create_sandbox_tools

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
            test_module_hint = first_test.split("::")[0] if "::" in first_test else first_test
            test_file_hint = test_module_hint

            prompt += (
                f"\n\n## Tests that MUST pass after your fix\n"
                f"{test_list}\n"
                f"\nNOTE: These tests may NOT exist yet in the repo (they may be "
                f"added by a test patch later). If a test is not found, you must "
                f"STILL fix the source code based on the issue description above.\n"
                f"\nTo try running: shell: cd /testbed && python -m pytest {first_test} -xvs 2>&1 | tail -60"
            )

        # Inject hints_text if available — gives extra context about the fix.
        # Place prominently as these often contain the actual solution approach.
        hints_text = state.metadata.get("hints_text", "")
        if hints_text and len(str(hints_text).strip()) > 10:
            prompt += (
                f"\n\n## Hints from maintainers (READ CAREFULLY — these often describe the solution)\n"
                f"{str(hints_text).strip()[:800]}"
            )

        # Build the system prompt with test module placeholders filled in.
        baseline_section = ""
        if test_module_hint:
            baseline_section = (
                f"BASELINE TEST MODULE: `{test_module_hint}`\n"
                f"You MUST run this module before AND after your fix to detect regressions.\n\n"
            )
        system_prompt = _SWE_BENCH_SYSTEM_PROMPT.format(
            baseline_test_module_section=baseline_section,
            test_file_hint=test_file_hint or "<test_file_path>",
            test_module_hint=test_module_hint or "<test_module>",
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
        agent._base_system_prompt = system_prompt
        agent.prompt_builder._base_system_prompt = system_prompt
        agent.max_steps = max_steps

        # Replace host tools with sandbox tools only — no planner tool.
        # The planner wastes steps on planning instead of acting.
        sandbox_tools_dict = {t.name: t for t in sandbox_tool_list}
        agent._planner = None
        agent.tools = sandbox_tools_dict
        agent._openai_tools = tools_to_openai_format(agent.tools)
        agent.tool_executor = ToolExecutor(
            tools=agent.tools, logger=agent.logger
        )
        agent.message_history_manager._openai_tools = agent._openai_tools

        # Monkey-patch _build_system_prompt to inject step-budget warnings.
        # This gives the agent awareness of how many steps remain so it
        # commits to an approach rather than looping indefinitely.
        _original_build_system_prompt = agent._build_system_prompt

        def _budget_aware_system_prompt(
            mission=None, state=None, messages=None
        ):
            base = _original_build_system_prompt(
                mission=mission, state=state, messages=messages
            )
            if messages:
                tool_calls = sum(
                    1 for m in messages if m.get("role") == "assistant"
                    and m.get("tool_calls")
                )
                remaining = max_steps - tool_calls
                if remaining <= 20:
                    base += (
                        "\n\n## ⚠️ URGENT: VERY LOW BUDGET"
                        f"\nYou have used {tool_calls}/{max_steps} steps."
                        f" Only ~{remaining} remain."
                        "\nYou MUST wrap up NOW:"
                        "\n- If you have a working fix, run final verification and STOP."
                        "\n- If not, commit to your best approach immediately."
                        "\n- Do NOT start over or explore further."
                    )
                elif remaining <= 40:
                    base += (
                        "\n\n## ⚡ BUDGET WARNING"
                        f"\nYou have used {tool_calls}/{max_steps} steps."
                        f" ~{remaining} remain."
                        "\nBe efficient — implement your fix now if you haven't already."
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
            logger.error(f"Taskforce SWE-bench agent failed: {e}", exc_info=True)
            return _write_error_metadata(state, e)

        return _write_metadata(state, acc)

    return solve
