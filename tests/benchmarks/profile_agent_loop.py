"""Profile pytaskforce agent-loop framework overhead with a mock LLM.

Runs a scripted N-step ReAct mission against a deterministic, in-memory mock
LLM (zero network latency) so the measured wall-clock is *pure framework
overhead*. Reports:

  * agent BUILD vs RUN wall-clock split,
  * per-step wall-clock (time between consecutive ``step_start`` events),
  * top cProfile cumulative hotspots (where the time actually goes),
  * an fsod-style ~15-line baseline loop driving the same mock + same tool,
    so the delta is the framework overhead on top of a minimal loop.

This is a measurement tool only — it imports the real agent stack and changes
no production code. The mock LLM is injected by patching
``InfrastructureBuilder.build_llm_provider`` (the single method the factory
uses to construct the provider).

Usage:
    uv run python tests/benchmarks/profile_agent_loop.py --steps 10
    uv run python tests/benchmarks/profile_agent_loop.py --steps 10 --no-stream
    uv run python tests/benchmarks/profile_agent_loop.py --steps 10 --runs 5 --top 25

Env toggles worth flipping for the A/B rows in the report:
    TASKFORCE_WORKSPACE_ROOT   set -> exercises the WORKSPACE + CLAUDE.md
                               injection in the system prompt every step.
"""

from __future__ import annotations

import argparse
import asyncio
import cProfile
import io
import json
import pstats
import statistics
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Mock LLM providers (deterministic, zero-latency)
# ---------------------------------------------------------------------------


class ScriptedStreamingLLM:
    """Mock provider with ``complete_stream``.

    Emits ``--steps`` tool-calling turns (one tool call each) followed by a
    final plain-text answer. Latency is configurable to simulate TTFT.
    """

    def __init__(
        self, *, steps: int, tool_name: str, tool_args_list: list[dict[str, Any]], latency_s: float
    ):
        self._steps = steps
        self._tool_name = tool_name
        # One distinct arg dict per step so the agent's repeat/stall detector
        # treats every turn as genuine progress (otherwise identical tool
        # signatures trip nudges/salvage and short-circuit the run).
        self._args = [json.dumps(a) for a in tool_args_list]
        self._latency_s = latency_s
        self._calls = 0
        # Some collaborators introspect ``.models``; keep it present + empty.
        self.models: dict[str, Any] = {}

    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        self._calls += 1
        if self._latency_s:
            await asyncio.sleep(self._latency_s)
        if self._calls <= self._steps:
            cid = f"call_{self._calls}"
            args = self._args[(self._calls - 1) % len(self._args)]
            yield {"type": "token", "content": "Working."}
            yield {"type": "tool_call_start", "id": cid, "name": self._tool_name, "index": 0}
            yield {"type": "tool_call_delta", "id": cid, "arguments_delta": args, "index": 0}
            yield {
                "type": "tool_call_end",
                "id": cid,
                "name": self._tool_name,
                "arguments": args,
                "index": 0,
            }
            yield {"type": "done", "usage": {"prompt_tokens": 100, "completion_tokens": 10}}
        else:
            yield {"type": "token", "content": "All done — final answer."}
            yield {"type": "done", "usage": {"prompt_tokens": 120, "completion_tokens": 12}}

    async def complete(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # Fallback so a salvage attempt (if ever triggered) doesn't crash.
        return {"success": True, "content": "Final answer.", "tool_calls": [], "usage": {}}


class ScriptedNonStreamingLLM:
    """Mock provider with only ``complete`` (forces the non-streaming path)."""

    def __init__(
        self, *, steps: int, tool_name: str, tool_args_list: list[dict[str, Any]], latency_s: float
    ):
        self._steps = steps
        self._tool_name = tool_name
        self._args = [json.dumps(a) for a in tool_args_list]
        self._latency_s = latency_s
        self._calls = 0
        self.models: dict[str, Any] = {}

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self._calls += 1
        if self._latency_s:
            await asyncio.sleep(self._latency_s)
        if self._calls <= self._steps:
            args = self._args[(self._calls - 1) % len(self._args)]
            return {
                "success": True,
                "content": "Working.",
                "tool_calls": [
                    {
                        "id": f"call_{self._calls}",
                        "type": "function",
                        "function": {"name": self._tool_name, "arguments": args},
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            }
        return {
            "success": True,
            "content": "All done — final answer.",
            "tool_calls": [],
            "usage": {"prompt_tokens": 120, "completion_tokens": 12},
        }


def _make_provider(streaming: bool, **kw: Any) -> Any:
    """Build the mock, wrapping the streaming variant in the real LLMRouter.

    The router is included for the streaming path so its decorator hop is part
    of the measured overhead (representative of production). The non-streaming
    variant must NOT be wrapped, because the router always exposes
    ``complete_stream`` and would force the streaming branch.
    """
    if streaming:
        from taskforce.infrastructure.llm.llm_router import build_llm_router

        return build_llm_router(ScriptedStreamingLLM(**kw), {}, "main")
    return ScriptedNonStreamingLLM(**kw)


# ---------------------------------------------------------------------------
# One measured run
# ---------------------------------------------------------------------------


async def run_once(
    *,
    profile: str,
    steps: int,
    streaming: bool,
    tool_name: str,
    tool_args_list: list[dict[str, Any]],
    work_dir: str,
    latency_s: float,
) -> dict[str, Any]:
    """Build an agent (timed) then run the scripted mission (timed)."""
    from taskforce.application.executor import AgentExecutor
    from taskforce.application.factory import AgentFactory
    from taskforce.application.infrastructure_builder import InfrastructureBuilder

    provider = _make_provider(
        streaming,
        steps=steps,
        tool_name=tool_name,
        tool_args_list=tool_args_list,
        latency_s=latency_s,
    )

    with patch.object(InfrastructureBuilder, "build_llm_provider", return_value=provider):
        factory = AgentFactory()
        # max_steps must exceed the scripted tool turns so the agent reaches
        # the final answer rather than hitting the step cap.
        t0 = time.perf_counter()
        agent = await factory.create_agent(profile=profile, work_dir=work_dir)
        build_s = time.perf_counter() - t0
        # Ensure the agent can reach the scripted final answer (the default
        # profile cap may be lower than the requested step count).
        if getattr(agent, "max_steps", 0) < steps + 5:
            agent.max_steps = steps + 5

        executor = AgentExecutor(factory=factory)
        step_marks: list[float] = []
        counts: dict[str, int] = {}
        t1 = time.perf_counter()
        async for update in executor.execute_mission_streaming(
            mission="Read the temp file and report what you found.",
            agent=agent,
            work_dir=work_dir,
        ):
            ev = update.event_type_value
            counts[ev] = counts.get(ev, 0) + 1
            # ``step_start`` is internal and not surfaced to the stream; use
            # ``tool_call`` boundaries as the per-step proxy instead.
            if ev == "tool_call":
                step_marks.append(time.perf_counter())
        run_s = time.perf_counter() - t1

    # Per-step intervals: gap between consecutive tool_call marks.
    intervals = [b - a for a, b in zip(step_marks, step_marks[1:], strict=False)]
    return {
        "build_s": build_s,
        "run_s": run_s,
        "llm_calls": provider_call_count(provider),
        "step_intervals_ms": [round(x * 1000, 2) for x in intervals],
        "event_counts": counts,
    }


def provider_call_count(provider: Any) -> int:
    """Recover the scripted call counter through the (optional) router wrap."""
    inner = getattr(provider, "delegate", provider)
    return getattr(inner, "_calls", getattr(provider, "_calls", -1))


def _resolve_tool_class(tool_name: str) -> Any:
    """Resolve a registry short-name to its tool class (for the baseline)."""
    import importlib

    from taskforce.infrastructure.tools.registry import get_tool_definition

    spec = get_tool_definition(tool_name)
    if not spec or not spec.get("module") or not spec.get("type"):
        raise ValueError(f"cannot resolve tool class for {tool_name!r}")
    module = importlib.import_module(spec["module"])
    return getattr(module, spec["type"])


# ---------------------------------------------------------------------------
# fsod-style minimal baseline (same mock + same real tool)
# ---------------------------------------------------------------------------


async def fsod_baseline(
    *, steps: int, tool_name: str, tool_args_list: list[dict[str, Any]]
) -> float:
    """A ~15-line agent loop, like the fsod teaching examples.

    Uses the same scripted mock and the same *real* tool instance, so the only
    difference vs the pytaskforce run is the framework machinery around the
    loop. Returns wall-clock seconds.
    """
    tool = _resolve_tool_class(tool_name)()
    llm = ScriptedNonStreamingLLM(
        steps=steps, tool_name=tool_name, tool_args_list=tool_args_list, latency_s=0
    )

    messages: list[dict[str, Any]] = [{"role": "user", "content": "Read the temp file."}]
    t0 = time.perf_counter()
    for _ in range(steps + 2):
        resp = await llm.complete(messages=messages)
        messages.append({"role": "assistant", "content": resp["content"]})
        tcs = resp.get("tool_calls") or []
        if not tcs:
            break
        for tc in tcs:
            args = json.loads(tc["function"]["arguments"] or "{}")
            result = await tool.execute(**args)
            messages.append(
                {"role": "tool", "tool_call_id": tc["id"], "content": str(result)[:1500]}
            )
    return time.perf_counter() - t0


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _print_header(args: argparse.Namespace, tmpfile: str) -> None:
    print("=" * 72)
    print("pytaskforce agent-loop overhead profile")
    print("=" * 72)
    print(
        f"profile={args.profile}  steps={args.steps}  streaming={not args.no_stream}  "
        f"runs={args.runs}  latency_s={args.latency}"
    )
    import os

    print(f"TASKFORCE_WORKSPACE_ROOT={os.environ.get('TASKFORCE_WORKSPACE_ROOT', '<unset>')}")
    print(f"temp file read by the mock tool: {tmpfile}")
    print("-" * 72)


async def amain(args: argparse.Namespace) -> None:
    streaming = not args.no_stream
    tmp = tempfile.TemporaryDirectory()
    # One distinct file per step so each tool call has a unique signature.
    tool_args_list: list[dict[str, Any]] = []
    for i in range(max(args.steps, 1)):
        f = Path(tmp.name) / f"input_{i}.txt"
        f.write_text(f"benchmark file {i}\n" * 5, encoding="utf-8")
        tool_args_list.append({"path": str(f)})

    _print_header(args, str(tool_args_list[0]["path"]))

    common = {
        "profile": args.profile,
        "steps": args.steps,
        "streaming": streaming,
        "tool_name": args.tool,
        "tool_args_list": tool_args_list,
        "work_dir": tmp.name,
        "latency_s": args.latency,
    }

    # First run = COLD: process-startup cost (tool imports, plugin discovery,
    # profile YAML load). This is what a fresh `taskforce chat`/`run` pays.
    cold = await run_once(**common)
    print(
        f"[COLD first run] build={cold['build_s']*1000:.1f}ms  run={cold['run_s']*1000:.1f}ms  "
        f"llm_calls={cold['llm_calls']}  events={cold['event_counts']}"
    )

    # Wall-clock stats across N runs (no cProfile — it perturbs timing).
    builds, runs = [], []
    last = cold
    for _ in range(args.runs):
        r = await run_once(**common)
        builds.append(r["build_s"] * 1000)
        runs.append(r["run_s"] * 1000)
        last = r

    def stat(xs: list[float]) -> str:
        return f"mean={statistics.mean(xs):.1f}ms median={statistics.median(xs):.1f}ms"

    per_step_ms = statistics.mean(runs) / max(last["llm_calls"], 1)
    print("-" * 72)
    print(f"COLD build (process startup): {cold['build_s']*1000:.1f}ms")
    print(f"WARM build (agent construction): {stat(builds)}")
    print(f"RUN   ({args.steps} steps, {last['llm_calls']} llm calls): {stat(runs)}")
    print(f"per-step wall-clock (run / llm_calls): {per_step_ms:.2f}ms")
    print(f"tool_call intervals (ms): {last['step_intervals_ms']}")

    # fsod baseline (minimal loop, same tool) for the same step count.
    base = await fsod_baseline(steps=args.steps, tool_name=args.tool, tool_args_list=tool_args_list)
    print("-" * 72)
    print(
        f"fsod-style baseline RUN: {base*1000:.1f}ms  "
        f"({base*1000/max(args.steps,1):.1f}ms/step)"
    )
    overhead = statistics.mean(runs) - base * 1000
    print(
        f"=> framework RUN overhead over minimal loop: {overhead:.1f}ms "
        f"({overhead/max(args.steps,1):.1f}ms/step)"
    )

    # cProfile a single representative run for function-level attribution.
    print("-" * 72)
    print(f"cProfile (cumulative, top {args.top}) — one streaming run:")
    pr = cProfile.Profile()
    pr.enable()
    await run_once(**common)
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).strip_dirs().sort_stats("cumulative").print_stats(args.top)
    # Keep only the table rows for a compact dump.
    for line in s.getvalue().splitlines():
        if line.strip():
            print(line)

    tmp.cleanup()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", default="default", help="agent profile to build")
    p.add_argument("--steps", type=int, default=10, help="scripted tool-calling turns")
    p.add_argument("--runs", type=int, default=3, help="timed runs for wall-clock stats")
    p.add_argument("--tool", default="file_read", help="tool the mock calls each step")
    p.add_argument("--no-stream", action="store_true", help="force the non-streaming path")
    p.add_argument("--latency", type=float, default=0.0, help="simulated per-call TTFT seconds")
    p.add_argument("--top", type=int, default=25, help="cProfile rows to print")
    args = p.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
