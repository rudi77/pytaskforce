"""Planning strategies for Agent execution."""

from __future__ import annotations

import json
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING

from taskforce.core.domain.enums import (
    EventType,
    ExecutionStatus,
    LLMStreamEventType,
    MessageRole,
    PlannerAction,
)
from taskforce.core.domain.models import ExecutionResult, StreamEvent, TokenUsage
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.tools.tool_converter import assistant_tool_calls_to_message

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


@dataclass(frozen=True)
class ToolCallRequest:
    """Parsed tool call request."""
    tool_call_id: str
    tool_name: str
    tool_args: dict[str, Any]


class PlanningStrategy(Protocol):
    """Protocol for planning strategies."""
    name: str

    async def execute(self, agent: "Agent", mission: str, session_id: str) -> ExecutionResult: ...
    async def execute_stream(self, agent: "Agent", mission: str, session_id: str) -> AsyncIterator[StreamEvent]: ...


# --- Helpers ---

def _parse_tool_args(tool_call: dict[str, Any], logger: LoggerProtocol) -> dict[str, Any]:
    try:
        return json.loads(tool_call["function"]["arguments"])
    except json.JSONDecodeError:
        logger.warning("tool_args_parse_failed", tool=tool_call["function"]["name"])
        return {}


def _extract_tool_output(result: dict[str, Any]) -> str:
    if "output" in result:
        out = result["output"]
        return out if isinstance(out, str) else json.dumps(out, default=str)
    return result.get("error", "") or json.dumps(result, default=str)


async def _execute_tool_calls(
    agent: "Agent", requests: list[ToolCallRequest], session_id: str | None = None
) -> list[tuple[ToolCallRequest, dict[str, Any]]]:
    """Execute tools with optional parallelism."""
    if not requests:
        return []

    max_p = max(1, agent.max_parallel_tools)
    sem = asyncio.Semaphore(max_p)
    results: dict[str, dict[str, Any]] = {}
    tasks: list[tuple[ToolCallRequest, asyncio.Task]] = []

    async def run(name: str, args: dict) -> dict:
        async with sem:
            return await agent._execute_tool(name, args, session_id=session_id)

    for req in requests:
        tool = agent.tools.get(req.tool_name)
        can_parallel = tool and getattr(tool, "supports_parallelism", False) and not tool.requires_approval
        if can_parallel and max_p > 1:
            tasks.append((req, asyncio.create_task(run(req.tool_name, req.tool_args))))
        else:
            results[req.tool_call_id] = await agent._execute_tool(req.tool_name, req.tool_args, session_id=session_id)

    if tasks:
        gathered = await asyncio.gather(*(t for _, t in tasks))
        for (req, _), res in zip(tasks, gathered):
            results[req.tool_call_id] = res

    return [(req, results[req.tool_call_id]) for req in requests]


async def _collect_result(session_id: str, events: AsyncIterator[StreamEvent]) -> ExecutionResult:
    """Collect events into ExecutionResult."""
    history: list[dict[str, Any]] = []
    final_msg, error = "", ""
    pending: dict[str, Any] | None = None
    usage = TokenUsage()
    track = {
        EventType.TOOL_CALL, EventType.TOOL_RESULT, EventType.ASK_USER,
        EventType.PLAN_UPDATED, EventType.FINAL_ANSWER, EventType.ERROR,
    }

    async for e in events:
        event_type = e.event_type if isinstance(e.event_type, EventType) else EventType(e.event_type)
        if event_type in track:
            history.append({"type": event_type.value, **e.data})
        if event_type == EventType.FINAL_ANSWER:
            final_msg = e.data.get("content", "")
        elif event_type == EventType.ASK_USER:
            pending = dict(e.data)
            final_msg = final_msg or e.data.get("question", "Waiting for input")
        elif event_type == EventType.ERROR:
            error = e.data.get("message", "")
        elif event_type == EventType.TOKEN_USAGE:
            usage.prompt_tokens += e.data.get("prompt_tokens", 0)
            usage.completion_tokens += e.data.get("completion_tokens", 0)
            usage.total_tokens += e.data.get("total_tokens", 0)

    if pending:
        status = ExecutionStatus.PAUSED
    elif error or not final_msg:
        status = ExecutionStatus.FAILED
    else:
        status = ExecutionStatus.COMPLETED

    return ExecutionResult(
        session_id=session_id,
        status=status,
        final_message=final_msg or error,
        execution_history=history,
        pending_question=pending,
        token_usage=usage,
    )


def _parse_plan_steps(content: str, logger: LoggerProtocol) -> list[str]:
    """Parse plan steps from LLM response."""
    text = content.strip()
    if not text:
        return []

    # Extract JSON from code blocks
    json_text = text
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            json_text = parts[1].strip()
            if "\n" in json_text and not json_text.split("\n")[0].startswith("["):
                json_text = json_text.split("\n", 1)[1].strip()

    try:
        data = json.loads(json_text)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except (json.JSONDecodeError, TypeError):
        logger.debug("json_parse_failed")

    # Fallback: line-based
    steps = []
    for line in text.splitlines():
        c = line.strip().lstrip("-").strip()
        if c and not c.startswith("```"):
            if c[0].isdigit() and "." in c:
                c = c.split(".", 1)[1].strip()
            if c:
                steps.append(c)
    return steps


async def _generate_plan(agent: "Agent", mission: str, logger: LoggerProtocol) -> list[str]:
    """Generate plan steps via LLM."""
    result = await agent.llm_provider.complete(
        messages=[
            {"role": MessageRole.SYSTEM.value, "content": agent.system_prompt},
            {"role": MessageRole.USER.value, "content": f"{mission}\n\nCreate a concise step-by-step plan. Return ONLY a JSON array."},
        ],
        model=agent.model_alias, tools=None, tool_choice="none", temperature=0.1,
    )
    if not result.get("success"):
        return []
    return _parse_plan_steps(result.get("content", ""), logger)


DEFAULT_PLAN = [
    "Analyze the mission and identify required actions.",
    "Execute the required actions using available tools.",
    "Summarize the results and provide the final response.",
]


async def _handle_ask_user(agent: "Agent", args: dict, session_id: str, state: dict, logger: LoggerProtocol) -> AsyncIterator[StreamEvent]:
    """Handle ask_user tool."""
    q, missing = str(args.get("question", "")).strip(), args.get("missing") or []
    state["pending_question"] = {"question": q, "missing": missing}
    await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)
    yield StreamEvent(event_type=EventType.ASK_USER, data={"question": q, "missing": missing})
    logger.info("paused_for_user_input", session_id=session_id)


async def _emit_tool_result(agent: "Agent", req: ToolCallRequest, result: dict) -> AsyncIterator[StreamEvent]:
    """Emit tool result event."""
    yield StreamEvent(event_type=EventType.TOOL_RESULT, data={
        "tool": req.tool_name, "id": req.tool_call_id, "success": result.get("success", False),
        "output": agent._truncate_output(_extract_tool_output(result)), "args": req.tool_args,
    })
    if req.tool_name in ("planner", "manage_plan") and result.get("success"):
        plan = result.get("output") or (agent._planner.get_plan_summary() if agent._planner else None)
        if plan:
            yield StreamEvent(event_type=EventType.PLAN_UPDATED, data={"action": req.tool_args.get("action", "unknown"), "plan": plan})


class ToolCallStatus:
    """Status constants for tool call events."""

    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


async def _process_tool_calls(
    agent: "Agent", tool_calls: list[dict], session_id: str, step: int, state: dict, messages: list, logger: LoggerProtocol
) -> AsyncIterator[StreamEvent]:
    """Process tool calls, yield events, update messages."""
    messages.append(assistant_tool_calls_to_message(tool_calls))
    requests = []

    for tc in tool_calls:
        name, tc_id = tc["function"]["name"], tc["id"]
        args = _parse_tool_args(tc, logger)
        yield StreamEvent(
            event_type=EventType.TOOL_CALL,
            data={"tool": name, "id": tc_id, "status": ToolCallStatus.EXECUTING, "args": args},
        )

        if name == "ask_user":
            async for e in _handle_ask_user(agent, args, session_id, state, logger):
                yield e
            return

        requests.append(ToolCallRequest(tc_id, name, args))

    for req, res in await _execute_tool_calls(agent, requests, session_id):
        async for e in _emit_tool_result(agent, req, res):
            yield e
        messages.append(await agent.tool_result_message_factory.build_message(
            tool_call_id=req.tool_call_id,
            tool_name=req.tool_name,
            tool_result=res,
            session_id=session_id,
            step=step,
        ))


# --- Strategies ---

class NativeReActStrategy:
    """ReAct loop with optional upfront plan generation."""
    name = "native_react"

    def __init__(self, generate_plan_first: bool = False, max_plan_steps: int = 12, logger: LoggerProtocol | None = None):
        self.generate_plan_first = generate_plan_first
        self.max_plan_steps = max_plan_steps
        self._logger = logger

    async def execute(self, agent: "Agent", mission: str, session_id: str) -> ExecutionResult:
        return await _collect_result(session_id, self.execute_stream(agent, mission, session_id))

    async def execute_stream(self, agent: "Agent", mission: str, session_id: str) -> AsyncIterator[StreamEvent]:
        logger = self._logger or agent.logger
        state = await agent.state_manager.load_state(session_id) or {}
        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        # Optional plan generation
        if self.generate_plan_first:
            steps = (await _generate_plan(agent, mission, logger) or DEFAULT_PLAN)[:self.max_plan_steps]
            if agent._planner:
                await agent._planner.execute(action=PlannerAction.CREATE_PLAN.value, tasks=steps)
                yield StreamEvent(
                    event_type=EventType.PLAN_UPDATED,
                    data={"action": PlannerAction.CREATE_PLAN.value, "steps": steps, "plan": agent._planner.get_plan_summary()},
                )
            await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)

        messages = agent._build_initial_messages(mission, state)
        use_stream = hasattr(agent.llm_provider, "complete_stream")
        step, final = 0, ""

        while step < agent.max_steps:
            await agent.record_heartbeat(session_id, ExecutionStatus.PENDING.value, {"step": step})
            messages[0] = {"role": MessageRole.SYSTEM.value, "content": agent._build_system_prompt(mission=mission, state=state, messages=messages)}

            if use_stream:
                messages = await agent.message_history_manager.compress_messages(messages)
                messages = agent.message_history_manager.preflight_budget_check(messages)

            tool_calls, content = [], ""

            if use_stream:
                tc_acc, content_acc = {}, ""
                try:
                    async for chunk in agent.llm_provider.complete_stream(
                        messages=messages, model=agent.model_alias, tools=agent._openai_tools, tool_choice="auto", temperature=0.2
                    ):
                        t = chunk.get("type")
                        if t == LLMStreamEventType.TOKEN.value and chunk.get("content"):
                            yield StreamEvent(event_type=EventType.LLM_TOKEN, data={"content": chunk["content"]})
                            content_acc += chunk["content"]
                        elif t == LLMStreamEventType.TOOL_CALL_START.value:
                            tc_acc[chunk.get("index", 0)] = {"id": chunk.get("id", ""), "name": chunk.get("name", ""), "arguments": ""}
                        elif t == LLMStreamEventType.TOOL_CALL_DELTA.value and chunk.get("index", 0) in tc_acc:
                            tc_acc[chunk["index"]]["arguments"] += chunk.get("arguments_delta", "")
                        elif t == LLMStreamEventType.TOOL_CALL_END.value and chunk.get("index", 0) in tc_acc:
                            tc_acc[chunk["index"]]["arguments"] = chunk.get("arguments", tc_acc[chunk["index"]]["arguments"])
                        elif t == LLMStreamEventType.DONE.value and chunk.get("usage"):
                            yield StreamEvent(event_type=EventType.TOKEN_USAGE, data=chunk["usage"])
                        elif t == "error":
                            yield StreamEvent(event_type=EventType.ERROR, data={"message": chunk.get("message", "Error")})
                except Exception as e:
                    yield StreamEvent(event_type=EventType.ERROR, data={"message": str(e)})
                    continue

                if tc_acc:
                    tool_calls = [{"id": v["id"], "type": "function", "function": {"name": v["name"], "arguments": v["arguments"]}} for v in tc_acc.values()]
                else:
                    content = content_acc
            else:
                result = await agent.llm_provider.complete(messages=messages, model=agent.model_alias, tools=agent._openai_tools, tool_choice="auto", temperature=0.2)
                if result.get("usage"):
                    yield StreamEvent(event_type=EventType.TOKEN_USAGE, data=result["usage"])
                if not result.get("success"):
                    messages.append({"role": MessageRole.USER.value, "content": f"[System Error: {result.get('error')}. Try again.]"})
                    continue
                tool_calls, content = result.get("tool_calls") or [], result.get("content", "")

            if tool_calls:
                paused = False
                async for e in _process_tool_calls(agent, tool_calls, session_id, step + 1, state, messages, logger):
                    event_type = e.event_type if isinstance(e.event_type, EventType) else EventType(e.event_type)
                    if event_type == EventType.ASK_USER:
                        paused = True
                    yield e
                if paused:
                    return
                step += 1
            elif content:
                step += 1
                final = content
                yield StreamEvent(event_type=EventType.FINAL_ANSWER, data={"content": content})
                break
            else:
                messages.append({"role": MessageRole.USER.value, "content": "[System: Empty response. Provide answer or use tool.]"})

        if step >= agent.max_steps and not final:
            yield StreamEvent(event_type=EventType.ERROR, data={"message": f"Exceeded max steps ({agent.max_steps})"})

        await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)


class PlanAndExecuteStrategy:
    """Generate plan, execute steps sequentially."""
    name = "plan_and_execute"

    def __init__(self, max_step_iterations: int = 4, max_plan_steps: int = 12, logger: LoggerProtocol | None = None):
        self.max_step_iterations = max_step_iterations
        self.max_plan_steps = max_plan_steps
        self.logger = logger

    async def execute(self, agent: "Agent", mission: str, session_id: str) -> ExecutionResult:
        return await _collect_result(session_id, self.execute_stream(agent, mission, session_id))

    async def execute_stream(self, agent: "Agent", mission: str, session_id: str) -> AsyncIterator[StreamEvent]:
        logger = self.logger or agent.logger
        state = await agent.state_manager.load_state(session_id) or {}
        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        messages = agent._build_initial_messages(mission, state)
        plan = (await _generate_plan(agent, mission, logger) or DEFAULT_PLAN)[:self.max_plan_steps]

        if agent._planner:
            await agent._planner.execute(action=PlannerAction.CREATE_PLAN.value, tasks=plan)
            yield StreamEvent(
                event_type=EventType.PLAN_UPDATED,
                data={"action": PlannerAction.CREATE_PLAN.value, "steps": plan, "plan": agent._planner.get_plan_summary()},
            )

        progress = 0
        for idx, desc in enumerate(plan, 1):
            if progress >= agent.max_steps:
                break

            for it in range(1, self.max_step_iterations + 1):
                if progress >= agent.max_steps:
                    break

                await agent.record_heartbeat(session_id, ExecutionStatus.PENDING.value, {"plan_step": idx, "iteration": it})
                messages[0] = {"role": MessageRole.SYSTEM.value, "content": agent._build_system_prompt(mission=mission, state=state, messages=messages)}
                messages.append({"role": MessageRole.USER.value, "content": f"Execute step {idx}: {desc}\nCall tools or respond when done."})

                result = await agent.llm_provider.complete(messages=messages, model=agent.model_alias, tools=agent._openai_tools, tool_choice="auto", temperature=0.2)
                if result.get("usage"):
                    yield StreamEvent(event_type=EventType.TOKEN_USAGE, data=result["usage"])

                if not result.get("success"):
                    messages.append({"role": MessageRole.USER.value, "content": f"[Error: {result.get('error')}. Try again.]"})
                    continue

                if result.get("tool_calls"):
                    progress += 1
                    paused = False
                    async for e in _process_tool_calls(agent, result["tool_calls"], session_id, progress, state, messages, logger):
                        event_type = e.event_type if isinstance(e.event_type, EventType) else EventType(e.event_type)
                        if event_type == EventType.ASK_USER:
                            paused = True
                        yield e
                    if paused:
                        return
                elif result.get("content"):
                    messages.append({"role": MessageRole.ASSISTANT.value, "content": result["content"]})
                    if agent._planner:
                        await agent._planner.execute(action=PlannerAction.MARK_DONE.value, step_index=idx)
                        yield StreamEvent(
                            event_type=EventType.PLAN_UPDATED,
                            data={
                                "action": PlannerAction.MARK_DONE.value,
                                "step": idx,
                                "status": ExecutionStatus.COMPLETED.value,
                                "plan": agent._planner.get_plan_summary(),
                            },
                        )
                    break
                else:
                    messages.append({"role": MessageRole.USER.value, "content": "[Empty response. Provide answer or use tool.]"})

        # Final response
        final = ""
        if progress < agent.max_steps:
            messages.append({"role": MessageRole.USER.value, "content": "All steps complete. Provide final response."})
            if hasattr(agent.llm_provider, "complete_stream"):
                async for chunk in agent.llm_provider.complete_stream(messages=messages, model=agent.model_alias, tools=None, tool_choice="none", temperature=0.2):
                    if chunk.get("type") == LLMStreamEventType.TOKEN.value and chunk.get("content"):
                        yield StreamEvent(event_type=EventType.LLM_TOKEN, data={"content": chunk["content"]})
                        final += chunk["content"]
                    elif chunk.get("type") == "usage":
                        yield StreamEvent(event_type=EventType.TOKEN_USAGE, data=chunk.get("usage", {}))
            else:
                r = await agent.llm_provider.complete(messages=messages, model=agent.model_alias, tools=None, tool_choice="none", temperature=0.2)
                final = r.get("content", "") if r.get("success") else ""

        if final:
            yield StreamEvent(event_type=EventType.FINAL_ANSWER, data={"content": final})
        elif progress >= agent.max_steps:
            yield StreamEvent(event_type=EventType.ERROR, data={"message": f"Exceeded max steps ({agent.max_steps})"})
        else:
            yield StreamEvent(event_type=EventType.FINAL_ANSWER, data={"content": "Plan completed."})

        await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)

    async def _generate_final_response(self, agent: "Agent", messages: list) -> str:
        """Non-streaming final response for tests."""
        messages.append({"role": MessageRole.USER.value, "content": "All steps complete. Provide final response."})
        r = await agent.llm_provider.complete(messages=messages, model=agent.model_alias, tools=None, tool_choice="none", temperature=0.2)
        return r.get("content", "") if r.get("success") else ""


# Backwards compatibility alias
class PlanAndReactStrategy:
    """Alias for NativeReActStrategy with generate_plan_first=True."""
    name = "plan_and_react"

    def __init__(self, max_plan_steps: int = 12, logger: LoggerProtocol | None = None):
        self._delegate = NativeReActStrategy(generate_plan_first=True, max_plan_steps=max_plan_steps, logger=logger)

    async def execute(self, agent: "Agent", mission: str, session_id: str) -> ExecutionResult:
        return await self._delegate.execute(agent, mission, session_id)

    async def execute_stream(self, agent: "Agent", mission: str, session_id: str) -> AsyncIterator[StreamEvent]:
        async for e in self._delegate.execute_stream(agent, mission, session_id):
            yield e
