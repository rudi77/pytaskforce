"""
Planning Strategy Abstractions for Agent.

Defines the strategy interface and built-in strategy implementations.
"""

from __future__ import annotations

import json
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING

from taskforce.core.domain.models import ExecutionResult, StreamEvent
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.tools.tool_converter import (
    assistant_tool_calls_to_message,
)

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


@dataclass
class PlanStep:
    """Represents a single plan step for plan-and-execute strategies."""

    index: int
    description: str
    status: str = "PENDING"


@dataclass(frozen=True)
class ToolCallRequest:
    """Parsed tool call request for execution."""

    tool_call_id: str
    tool_name: str
    tool_args: dict[str, Any]


class PlanningStrategy(Protocol):
    """Protocol for Agent planning strategies."""

    name: str

    async def execute(
        self, agent: "Agent", mission: str, session_id: str
    ) -> ExecutionResult:
        """Execute a mission using the provided agent."""

    async def execute_stream(
        self, agent: "Agent", mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        """Execute a mission with streaming updates."""


def _build_plan_update(
    action: str,
    *,
    steps: list[str] | None = None,
    step: int | None = None,
    status: str | None = None,
    plan: str | None = None,
) -> dict[str, Any]:
    """Build a consistent plan update payload."""
    data: dict[str, Any] = {"action": action}
    if steps is not None:
        data["steps"] = list(steps)
    if step is not None:
        data["step"] = step
    if status is not None:
        data["status"] = status
    if plan:
        data["plan"] = plan
    return data


def _parse_tool_args(
    tool_call: dict[str, Any],
    logger: LoggerProtocol,
) -> dict[str, Any]:
    """Parse tool arguments from a tool call payload."""
    raw_args = tool_call["function"]["arguments"]
    try:
        return json.loads(raw_args)
    except json.JSONDecodeError:
        logger.warning(
            "tool_args_parse_failed",
            tool=tool_call["function"]["name"],
            raw_args=raw_args,
        )
        return {}


def _tool_supports_parallelism(agent: "Agent", tool_name: str) -> bool:
    """Return whether a tool is safe to execute in parallel."""
    tool = agent.tools.get(tool_name)
    if not tool:
        return False
    return (
        bool(getattr(tool, "supports_parallelism", False))
        and not tool.requires_approval
    )


async def _execute_with_limit(
    agent: "Agent",
    tool_name: str,
    tool_args: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Execute a tool with concurrency limits applied."""
    async with semaphore:
        return await agent._execute_tool(tool_name, tool_args)


async def _execute_tool_calls(
    agent: "Agent",
    requests: list[ToolCallRequest],
) -> list[tuple[ToolCallRequest, dict[str, Any]]]:
    """Execute tool calls with optional parallelism and ordering."""
    if not requests:
        return []

    max_parallel = max(1, agent.max_parallel_tools)
    semaphore = asyncio.Semaphore(max_parallel)
    results: dict[str, dict[str, Any]] = {}
    parallel_tasks: list[tuple[ToolCallRequest, asyncio.Task[dict[str, Any]]]] = []

    for request in requests:
        if _tool_supports_parallelism(agent, request.tool_name) and max_parallel > 1:
            task = asyncio.create_task(
                _execute_with_limit(
                    agent,
                    request.tool_name,
                    request.tool_args,
                    semaphore,
                )
            )
            parallel_tasks.append((request, task))
        else:
            results[request.tool_call_id] = await agent._execute_tool(
                request.tool_name, request.tool_args
            )

    if parallel_tasks:
        gathered = await asyncio.gather(*(task for _, task in parallel_tasks))
        for (request, _), tool_result in zip(parallel_tasks, gathered):
            results[request.tool_call_id] = tool_result

    return [(request, results[request.tool_call_id]) for request in requests]


async def _collect_execution_result(
    session_id: str,
    events: AsyncIterator[StreamEvent],
) -> ExecutionResult:
    """Collect stream events into an ExecutionResult."""
    execution_history: list[dict[str, Any]] = []
    final_message = ""
    last_error = ""
    pending_question: dict[str, Any] | None = None
    total_token_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    history_event_types = {
        "tool_call",
        "tool_result",
        "ask_user",
        "plan_updated",
        "final_answer",
        "error",
    }

    async for event in events:
        event_type = event.event_type
        if event_type in history_event_types:
            execution_history.append({"type": event_type, **event.data})
        if event_type == "final_answer":
            final_message = event.data.get("content", "")
        elif event_type == "ask_user":
            # Execution pauses until a human provides input.
            pending_question = dict(event.data)
            # Provide a meaningful message for synchronous /execute consumers.
            if not final_message:
                final_message = str(event.data.get("question", "")).strip() or "Waiting for user input"
        elif event_type == "error":
            last_error = event.data.get("message", "")
        elif event_type == "token_usage":
            # Accumulate token usage across all LLM calls
            usage = event.data
            total_token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            total_token_usage["total_tokens"] += usage.get("total_tokens", 0)

    if not final_message and last_error:
        final_message = last_error

    status = "completed"
    if pending_question:
        status = "paused"
    elif last_error or not final_message:
        status = "failed"

    return ExecutionResult(
        session_id=session_id,
        status=status,
        final_message=final_message,
        execution_history=execution_history,
        pending_question=pending_question,
        token_usage=total_token_usage,
    )


async def _generate_plan_steps(
    agent: "Agent",
    mission: str,
    logger: LoggerProtocol,
) -> list[str]:
    """Generate plan steps using the LLM and parse the response."""
    prompt = (
        "Create a concise step-by-step plan for the mission. "
        "Return ONLY a JSON array of short step strings."
    )
    messages = [
        {"role": "system", "content": agent.system_prompt},
        {"role": "user", "content": f"{mission}\n\n{prompt}"},
    ]
    result = await agent.llm_provider.complete(
        messages=messages,
        model=agent.model_alias,
        tools=None,
        tool_choice="none",
        temperature=0.1,
    )

    if not result.get("success"):
        logger.warning("plan_generation_failed", error=result.get("error"))
        return []

    content = result.get("content", "") or ""
    return _parse_plan_steps(content, logger)


def _parse_plan_steps(content: str, logger: LoggerProtocol) -> list[str]:
    """Parse plan steps from LLM response with specific error handling."""
    text = content.strip()
    
    # Try JSON parsing first (with or without code blocks)
    if "```" in text:
        try:
            parts = text.split("```")
            if len(parts) >= 2:
                json_text = parts[1].strip()
                # Remove language identifier if present (e.g., "json\n[...]" -> "[...]")
                if "\n" in json_text:
                    lines = json_text.split("\n", 1)
                    if len(lines) > 1 and not lines[0].strip().startswith("["):
                        json_text = lines[1].strip()
                data = json.loads(json_text)
                if isinstance(data, list):
                    steps = [str(item).strip() for item in data if str(item).strip()]
                    return steps
        except json.JSONDecodeError as e:
            logger.debug("json_parse_failed", error=str(e), content_preview=text[:100])
        except (TypeError, ValueError) as e:
            logger.debug("plan_steps_parse_error", error=str(e))
    else:
        # Try parsing as JSON directly if no code block
        try:
            data = json.loads(text)
            if isinstance(data, list):
                steps = [str(item).strip() for item in data if str(item).strip()]
                return steps
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    
    # Fallback to line-based parsing
    steps: list[str] = []
    for line in text.splitlines():
        candidate = line.strip().lstrip("-").strip()
        if not candidate:
            continue
        # Skip code block markers
        if candidate.startswith("```"):
            continue
        if candidate[0].isdigit() and "." in candidate:
            candidate = candidate.split(".", 1)[1].strip()
        if candidate:
            steps.append(candidate)
    
    return steps


class NativeReActStrategy:
    """Strategy that owns the native tool calling ReAct loop."""

    name = "native_react"

    async def execute(
        self, agent: "Agent", mission: str, session_id: str
    ) -> ExecutionResult:
        agent.logger.info("execute_start", session_id=session_id, mission=mission[:100])

        result = await _collect_execution_result(
            session_id,
            self.execute_stream(agent, mission, session_id),
        )

        agent.logger.info(
            "execute_complete",
            session_id=session_id,
            status=result.status,
        )
        return result

    def _accumulate_tool_calls(
        self, tool_calls_accumulated: dict[int, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert accumulated tool calls to OpenAI format."""
        return [
            {
                "id": tc_data["id"],
                "type": "function",
                "function": {
                    "name": tc_data["name"],
                    "arguments": tc_data["arguments"],
                },
            }
            for tc_data in tool_calls_accumulated.values()
        ]

    async def _emit_plan_update_if_needed(
        self,
        agent: "Agent",
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: dict[str, Any],
    ) -> AsyncIterator[StreamEvent]:
        """Emit plan update event if tool is planner/manage_plan."""
        if tool_name in ("planner", "manage_plan") and tool_result.get("success"):
            plan_output = tool_result.get("output")
            if not plan_output and agent._planner:
                plan_output = agent._planner.get_plan_summary()
            yield StreamEvent(
                event_type="plan_updated",
                data=_build_plan_update(
                    action=tool_args.get("action", "unknown"),
                    plan=plan_output,
                ),
            )

    async def _process_single_tool_call(
        self,
        agent: "Agent",
        tool_call: dict[str, Any],
        session_id: str,
        step: int,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[StreamEvent]:
        """Process a single tool call and emit events."""
        tool_name = tool_call["function"]["name"]
        tool_call_id = tool_call["id"]

        try:
            tool_args = json.loads(tool_call["function"]["arguments"])
        except json.JSONDecodeError:
            tool_args = {}
            agent.logger.warning(
                "stream_tool_args_parse_failed",
                tool=tool_name,
                raw_args=tool_call["function"]["arguments"],
            )

        yield StreamEvent(
            event_type="tool_call",
            data={"tool": tool_name, "id": tool_call_id, "status": "executing", "args": tool_args},
        )

        tool_result = await agent._execute_tool(tool_name, tool_args)

        yield StreamEvent(
            event_type="tool_result",
            data={
                "tool": tool_name,
                "id": tool_call_id,
                "success": tool_result.get("success", False),
                "output": agent._truncate_output(
                    tool_result.get("output", str(tool_result.get("error", "")))
                ),
                "args": tool_args,
            },
        )

        async for event in self._emit_plan_update_if_needed(agent, tool_name, tool_args, tool_result):
            yield event

        tool_message = await agent._create_tool_message(
            tool_call_id, tool_name, tool_result, session_id, step
        )
        messages.append(tool_message)

    async def _emit_tool_events(
        self,
        agent: "Agent",
        tool_calls_list: list[dict[str, Any]],
        session_id: str,
        step: int,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[StreamEvent]:
        """Execute tool calls and emit corresponding events."""
        for tool_call in tool_calls_list:
            async for event in self._process_single_tool_call(
                agent, tool_call, session_id, step, messages
            ):
                yield event

    async def _process_stream_chunk(
        self,
        chunk: dict[str, Any],
        tool_calls_accumulated: dict[int, dict[str, Any]],
        content_accumulated: list[str],
        agent: "Agent",
        step: int,
    ) -> AsyncIterator[StreamEvent]:
        """Process individual streaming chunk, yield events, and update state."""
        chunk_type = chunk.get("type")

        if chunk_type == "token":
            token_content = chunk.get("content", "")
            if token_content:
                yield StreamEvent(event_type="llm_token", data={"content": token_content})
                content_accumulated[0] += token_content

        elif chunk_type == "tool_call_start":
            tc_id = chunk.get("id", "")
            tc_name = chunk.get("name", "")
            tc_index = chunk.get("index", 0)

            tool_calls_accumulated[tc_index] = {
                "id": tc_id,
                "name": tc_name,
                "arguments": "",
            }

            yield StreamEvent(
                event_type="tool_call",
                data={"tool": tc_name, "id": tc_id, "status": "starting"},
            )

        elif chunk_type == "tool_call_delta":
            tc_index = chunk.get("index", 0)
            if tc_index in tool_calls_accumulated:
                tool_calls_accumulated[tc_index]["arguments"] += chunk.get(
                    "arguments_delta", ""
                )

        elif chunk_type == "tool_call_end":
            tc_index = chunk.get("index", 0)
            if tc_index in tool_calls_accumulated:
                tool_calls_accumulated[tc_index]["arguments"] = chunk.get(
                    "arguments", tool_calls_accumulated[tc_index]["arguments"]
                )

        elif chunk_type == "done":
            usage = chunk.get("usage")
            if usage:
                yield StreamEvent(event_type="token_usage", data=usage)

        elif chunk_type == "error":
            yield StreamEvent(
                event_type="error",
                data={"message": chunk.get("message", "Unknown error"), "step": step},
            )

    async def _handle_streaming_completion(
        self,
        agent: "Agent",
        session_id: str,
        step: int,
        final_message: str,
        state: dict[str, Any],
        loop_iterations: int,
    ) -> AsyncIterator[StreamEvent]:
        """Handle final completion logic and state persistence."""
        if step >= agent.max_steps and not final_message:
            final_message = f"Exceeded maximum steps ({agent.max_steps})"
            yield StreamEvent(event_type="error", data={"message": final_message, "step": step})

        await agent.state_store.save(
            session_id=session_id, state=state, planner=agent.planner
        )

        agent.logger.info(
            "execute_stream_complete",
            session_id=session_id,
            progress_steps=step,
            total_iterations=loop_iterations,
            overhead_iterations=loop_iterations - step,
        )

    async def _execute_non_streaming_loop(
        self,
        agent: "Agent",
        mission: str,
        session_id: str,
        messages: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> AsyncIterator[StreamEvent]:
        """Execute using non-streaming LLM calls when streaming unavailable."""
        step = 0
        loop_iterations = 0
        final_message = ""

        while step < agent.max_steps:
            loop_iterations += 1
            agent.logger.debug(
                "loop_iteration",
                session_id=session_id,
                iteration=loop_iterations,
                progress_steps=step,
                max_steps=agent.max_steps,
            )

            current_system_prompt = agent._build_system_prompt(
                mission=mission, state=state, messages=messages
            )
            messages[0] = {"role": "system", "content": current_system_prompt}

            result = await agent.llm_provider.complete(
                messages=messages,
                model=agent.model_alias,
                tools=agent._openai_tools,
                tool_choice="auto",
                temperature=0.2,
            )

            if result.get("usage"):
                yield StreamEvent(event_type="token_usage", data=result["usage"])

            if not result.get("success"):
                agent.logger.error(
                    "llm_call_failed",
                    error=result.get("error"),
                    iteration=loop_iterations,
                    step=step,
                )
                messages.append(
                    {
                        "role": "user",
                        "content": f"[System Error: {result.get('error')}. Please try again.]",
                    }
                )
                continue

            tool_calls = result.get("tool_calls")

            if tool_calls:
                # Special case: ask_user is a control-flow pause, not a normal tool.
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    if tool_name == "ask_user":
                        tool_args = _parse_tool_args(tool_call, agent.logger)
                        question = str(tool_args.get("question", "")).strip()
                        missing = tool_args.get("missing") or []

                        state["pending_question"] = {
                            "question": question,
                            "missing": missing,
                        }
                        await agent.state_store.save(
                            session_id=session_id,
                            state=state,
                            planner=agent.planner,
                        )

                        yield StreamEvent(
                            event_type="ask_user",
                            data={"question": question, "missing": missing},
                        )
                        agent.logger.info(
                            "execute_stream_paused_for_user_input",
                            session_id=session_id,
                            question=question[:200],
                        )
                        return

                step += 1
                agent.logger.info(
                    "tool_calls_received",
                    step=step,
                    iteration=loop_iterations,
                    count=len(tool_calls),
                    tools=[tc["function"]["name"] for tc in tool_calls],
                )

                messages.append(assistant_tool_calls_to_message(tool_calls))

                requests: list[ToolCallRequest] = []
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_call_id = tool_call["id"]
                    tool_args = _parse_tool_args(tool_call, agent.logger)

                    yield StreamEvent(
                        event_type="tool_call",
                        data={
                            "tool": tool_name,
                            "id": tool_call_id,
                            "status": "executing",
                            "args": tool_args,
                        },
                    )

                    requests.append(
                        ToolCallRequest(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            tool_args=tool_args,
                        )
                    )

                tool_results = await _execute_tool_calls(agent, requests)
                for request, tool_result in tool_results:
                    yield StreamEvent(
                        event_type="tool_result",
                        data={
                            "tool": request.tool_name,
                            "id": request.tool_call_id,
                            "success": tool_result.get("success", False),
                            "output": agent._truncate_output(
                                tool_result.get(
                                    "output", str(tool_result.get("error", ""))
                                )
                            ),
                            "args": request.tool_args,
                        },
                    )

                    if request.tool_name in (
                        "planner",
                        "manage_plan",
                    ) and tool_result.get("success"):
                        plan_output = tool_result.get("output")
                        if not plan_output and agent._planner:
                            plan_output = agent._planner.get_plan_summary()
                        yield StreamEvent(
                            event_type="plan_updated",
                            data=_build_plan_update(
                                action=request.tool_args.get("action", "unknown"),
                                plan=plan_output,
                            ),
                        )

                    tool_message = await agent._create_tool_message(
                        request.tool_call_id,
                        request.tool_name,
                        tool_result,
                        session_id,
                        step,
                    )
                    messages.append(tool_message)

                continue

            content = result.get("content", "")
            if content:
                step += 1
                final_message = content
                yield StreamEvent(event_type="final_answer", data={"content": content})
                break

            agent.logger.warning("empty_response", step=step, iteration=loop_iterations)
            messages.append(
                {
                    "role": "user",
                    "content": "[System: Your response was empty. Please provide an answer or use a tool.]",
                }
            )

        async for event in self._handle_streaming_completion(
            agent, session_id, step, final_message, state, loop_iterations
        ):
            yield event

    async def execute_stream(
        self, agent: "Agent", mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        agent.logger.info("execute_stream_start", session_id=session_id)

        state = await agent.state_manager.load_state(session_id) or {}

        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        if not hasattr(agent.llm_provider, "complete_stream"):
            agent.logger.warning("llm_provider_no_streaming", fallback="execute")

            messages = agent._build_initial_messages(mission, state)
            async for event in self._execute_non_streaming_loop(
                agent, mission, session_id, messages, state
            ):
                yield event
            return

        async for event in self._execute_streaming_loop(
            agent, mission, session_id, state
        ):
            yield event

    async def _execute_streaming_loop(
        self,
        agent: "Agent",
        mission: str,
        session_id: str,
        state: dict[str, Any],
    ) -> AsyncIterator[StreamEvent]:
        """Execute using streaming LLM calls for real-time updates."""
        messages = agent._build_initial_messages(mission, state)
        step = 0
        loop_iterations = 0
        final_message = ""

        while step < agent.max_steps:
            loop_iterations += 1
            agent.logger.debug(
                "stream_loop_iteration",
                session_id=session_id,
                iteration=loop_iterations,
                progress_steps=step,
                max_steps=agent.max_steps,
            )

            yield StreamEvent(
                event_type="step_start",
                data={"step": step, "max_steps": agent.max_steps, "iteration": loop_iterations},
            )

            current_system_prompt = agent._build_system_prompt(
                mission=mission, state=state, messages=messages
            )
            messages[0] = {"role": "system", "content": current_system_prompt}

            messages = await agent._compress_messages(messages)
            messages = await agent._preflight_budget_check(messages)

            tool_calls_accumulated: dict[int, dict[str, Any]] = {}
            content_accumulated = [""]

            try:
                async for chunk in agent.llm_provider.complete_stream(
                    messages=messages,
                    model=agent.model_alias,
                    tools=agent._openai_tools,
                    tool_choice="auto",
                    temperature=0.2,
                ):
                    async for event in self._process_stream_chunk(
                        chunk, tool_calls_accumulated, content_accumulated, agent, step
                    ):
                        yield event

            except Exception as e:
                agent.logger.error("stream_error", error=str(e), step=step)
                yield StreamEvent(event_type="error", data={"message": str(e), "step": step})
                continue

            if tool_calls_accumulated:
                step += 1
                tool_calls_list = self._accumulate_tool_calls(tool_calls_accumulated)

                agent.logger.info(
                    "stream_tool_calls_received",
                    step=step,
                    iteration=loop_iterations,
                    count=len(tool_calls_list),
                    tools=[tc["function"]["name"] for tc in tool_calls_list],
                )

                messages.append(assistant_tool_calls_to_message(tool_calls_list))

                for tool_call in tool_calls_list:
                    tool_name = tool_call["function"]["name"]
                    tool_call_id = tool_call["id"]

                    try:
                        tool_args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}
                        agent.logger.warning(
                            "stream_tool_args_parse_failed",
                            tool=tool_name,
                            raw_args=tool_call["function"]["arguments"],
                        )

                    yield StreamEvent(
                        event_type="tool_call",
                        data={
                            "tool": tool_name,
                            "id": tool_call_id,
                            "status": "executing",
                            "args": tool_args,
                        },
                    )

                    # Special case: ask_user is a control-flow pause, not a normal tool.
                    if tool_name == "ask_user":
                        question = str(tool_args.get("question", "")).strip()
                        missing = tool_args.get("missing") or []

                        state["pending_question"] = {
                            "question": question,
                            "missing": missing,
                        }
                        await agent.state_store.save(
                            session_id=session_id,
                            state=state,
                            planner=agent.planner,
                        )

                        yield StreamEvent(
                            event_type="ask_user",
                            data={"question": question, "missing": missing},
                        )
                        agent.logger.info(
                            "execute_stream_paused_for_user_input",
                            session_id=session_id,
                            question=question[:200],
                        )
                        return

                    tool_result = await agent._execute_tool(tool_name, tool_args)

                    yield StreamEvent(
                        event_type="tool_result",
                        data={
                            "tool": tool_name,
                            "id": tool_call_id,
                            "success": tool_result.get("success", False),
                            "output": agent._truncate_output(
                                tool_result.get("output", str(tool_result.get("error", "")))
                            ),
                            "args": tool_args,
                        },
                    )

                    if tool_name in ("planner", "manage_plan") and tool_result.get("success"):
                        plan_output = tool_result.get("output")
                        if not plan_output and agent._planner:
                            plan_output = agent._planner.get_plan_summary()
                        yield StreamEvent(
                            event_type="plan_updated",
                            data=_build_plan_update(
                                action=tool_args.get("action", "unknown"),
                                plan=plan_output,
                            ),
                        )

                    tool_message = await agent._create_tool_message(
                        tool_call_id, tool_name, tool_result, session_id, step
                    )
                    messages.append(tool_message)

            elif content_accumulated[0]:
                step += 1
                final_message = content_accumulated[0]
                agent.logger.info(
                    "stream_final_answer",
                    step=step,
                    iteration=loop_iterations,
                    total_iterations=loop_iterations,
                )

                yield StreamEvent(event_type="final_answer", data={"content": final_message})
                break

            else:
                agent.logger.warning("stream_empty_response", step=step, iteration=loop_iterations)
                messages.append(
                    {
                        "role": "user",
                        "content": "[System: Empty response. Please provide an answer or use a tool.]",
                    }
                )

        async for event in self._handle_streaming_completion(
            agent, session_id, step, final_message, state, loop_iterations
        ):
            yield event


class PlanAndExecuteStrategy:
    """Generate a plan up-front and execute steps sequentially."""

    name = "plan_and_execute"

    def __init__(
        self,
        max_step_iterations: int = 4,
        max_plan_steps: int = 12,
        logger: LoggerProtocol | None = None,
    ) -> None:
        self.max_step_iterations = max_step_iterations
        self.max_plan_steps = max_plan_steps
        self.logger = logger

    async def _initialize_plan(
        self,
        agent: "Agent",
        mission: str,
        logger: LoggerProtocol,
    ) -> list[str]:
        """Generate plan steps using LLM or fallback to default steps."""
        plan_steps = await _generate_plan_steps(agent, mission, logger)
        if not plan_steps:
            plan_steps = [
                "Analyze the mission and identify required actions.",
                "Execute the required actions using available tools.",
                "Summarize the results and provide the final response.",
            ]

        plan_steps = plan_steps[: self.max_plan_steps]
        return plan_steps

    async def _emit_tool_result_events(
        self,
        request: ToolCallRequest,
        tool_result: dict[str, Any],
        agent: "Agent",
    ) -> AsyncIterator[StreamEvent]:
        """Emit tool result and plan update events."""
        yield StreamEvent(
            event_type="tool_result",
            data={
                "tool": request.tool_name,
                "id": request.tool_call_id,
                "success": tool_result.get("success", False),
                "output": agent._truncate_output(
                    tool_result.get(
                        "output", str(tool_result.get("error", ""))
                    )
                ),
                "args": request.tool_args,
            },
        )

        if request.tool_name in ("planner", "manage_plan") and tool_result.get("success"):
            plan_output = tool_result.get("output")
            if not plan_output and agent._planner:
                plan_output = agent._planner.get_plan_summary()
            yield StreamEvent(
                event_type="plan_updated",
                data=_build_plan_update(
                    action=request.tool_args.get("action", "unknown"),
                    plan=plan_output,
                ),
            )

    async def _build_tool_requests(
        self,
        tool_calls: list[dict[str, Any]],
        logger: LoggerProtocol,
    ) -> AsyncIterator[tuple[ToolCallRequest, StreamEvent]]:
        """Build tool requests and emit tool call events."""
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_call_id = tool_call["id"]
            tool_args = _parse_tool_args(tool_call, logger)

            yield (ToolCallRequest(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                tool_args=tool_args,
            ), StreamEvent(
                event_type="tool_call",
                data={
                    "tool": tool_name,
                    "id": tool_call_id,
                    "status": "executing",
                    "args": tool_args,
                },
            ))

    async def _process_step_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        agent: "Agent",
        session_id: str,
        step_index: int,
        messages: list[dict[str, Any]],
        logger: LoggerProtocol,
    ) -> AsyncIterator[StreamEvent]:
        """Process tool calls for a plan step."""
        messages.append(assistant_tool_calls_to_message(tool_calls))

        requests: list[ToolCallRequest] = []
        async for request, event in self._build_tool_requests(tool_calls, logger):
            requests.append(request)
            yield event

        tool_results = await _execute_tool_calls(agent, requests)
        for request, tool_result in tool_results:
            async for event in self._emit_tool_result_events(request, tool_result, agent):
                yield event

            tool_message = await agent._create_tool_message(
                request.tool_call_id,
                request.tool_name,
                tool_result,
                session_id,
                step_index,
            )
            messages.append(tool_message)

    async def _check_step_completion(
        self,
        content: str,
        agent: "Agent",
        step_index: int,
        messages: list[dict[str, Any]],
    ) -> tuple[bool, StreamEvent | None]:
        """Determine if a plan step is complete based on content."""
        if not content:
            return (False, None)

        messages.append({"role": "assistant", "content": content})
        plan_event = None
        if agent._planner:
            await agent._planner.execute(action="mark_done", step_index=step_index)
            plan_event = StreamEvent(
                event_type="plan_updated",
                data=_build_plan_update(
                    action="mark_done",
                    step=step_index,
                    status="completed",
                    plan=agent._planner.get_plan_summary(),
                ),
            )
        return (True, plan_event)

    def _prepare_step_iteration(
        self,
        agent: "Agent",
        step_index: int,
        step_description: str,
        mission: str,
        state: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> None:
        """Prepare messages for a step iteration."""
        current_system_prompt = agent._build_system_prompt(
            mission=mission, state=state, messages=messages
        )
        messages[0] = {"role": "system", "content": current_system_prompt}

        step_instruction = (
            f"Execute plan step {step_index}: {step_description}\n"
            "Call tools when needed. When the step is complete, respond with "
            "a short completion note."
        )
        messages.append({"role": "user", "content": step_instruction})

    def _handle_llm_error(
        self,
        result: dict[str, Any],
        step_index: int,
        step_iterations: int,
        messages: list[dict[str, Any]],
        logger: LoggerProtocol,
    ) -> None:
        """Handle LLM call error."""
        logger.error(
            "llm_call_failed",
            error=result.get("error"),
            iteration=step_iterations,
            plan_step=step_index,
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"[System Error: {result.get('error')}. Please try again.]"
                ),
            }
        )

    async def _handle_step_content(
        self,
        content: str,
        agent: "Agent",
        step_index: int,
        progress_steps: int,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[tuple[StreamEvent, int, bool]]:
        """Handle step content completion."""
        if not content:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "[System: Your response was empty. Please provide an answer "
                        "or use a tool.]"
                    ),
                }
            )
            return

        is_complete, plan_event = await self._check_step_completion(
            content, agent, step_index, messages
        )
        if is_complete and plan_event:
            yield (plan_event, progress_steps + 1, True)

    async def _handle_step_llm_result(
        self,
        result: dict[str, Any],
        agent: "Agent",
        step_index: int,
        step_iterations: int,
        progress_steps: int,
        session_id: str,
        messages: list[dict[str, Any]],
        logger: LoggerProtocol,
    ) -> AsyncIterator[tuple[StreamEvent, int, bool]]:
        """Handle LLM result for a step iteration."""
        if result.get("usage"):
            yield (StreamEvent(
                event_type="token_usage",
                data=result["usage"],
            ), progress_steps, False)

        if not result.get("success"):
            self._handle_llm_error(result, step_index, step_iterations, messages, logger)
            return

        tool_calls = result.get("tool_calls")
        if tool_calls:
            async for event in self._process_step_tool_calls(
                tool_calls, agent, session_id, progress_steps + 1, messages, logger
            ):
                yield (event, progress_steps + 1, False)
            return

        content = result.get("content", "")
        async for event, new_progress, is_complete in self._handle_step_content(
            content, agent, step_index, progress_steps, messages
        ):
            yield (event, new_progress, is_complete)

    async def _execute_step_iteration(
        self,
        agent: "Agent",
        step_index: int,
        step_description: str,
        mission: str,
        state: dict[str, Any],
        messages: list[dict[str, Any]],
        progress_steps: int,
        step_iterations: int,
        session_id: str,
        logger: LoggerProtocol,
    ) -> AsyncIterator[tuple[StreamEvent, int, bool]]:
        """Execute a single iteration of a plan step."""
        self._prepare_step_iteration(
            agent, step_index, step_description, mission, state, messages
        )

        result = await agent.llm_provider.complete(
            messages=messages,
            model=agent.model_alias,
            tools=agent._openai_tools,
            tool_choice="auto",
            temperature=0.2,
        )

        async for event, new_progress, is_complete in self._handle_step_llm_result(
            result, agent, step_index, step_iterations, progress_steps,
            session_id, messages, logger
        ):
            yield (event, new_progress, is_complete)

    async def _execute_plan_step(
        self,
        agent: "Agent",
        step_index: int,
        step_description: str,
        messages: list[dict[str, Any]],
        session_id: str,
        mission: str,
        state: dict[str, Any],
        current_progress: int,
        max_iterations: int,
        logger: LoggerProtocol,
    ) -> AsyncIterator[tuple[StreamEvent, int, int, bool]]:
        """Execute a single plan step with iteration limits."""
        step_complete = False
        step_iterations = 0
        progress_steps = current_progress

        while not step_complete and step_iterations < max_iterations:
            if progress_steps >= agent.max_steps:
                break

            step_iterations += 1
            async for event, new_progress, is_complete in self._execute_step_iteration(
                agent, step_index, step_description, mission, state, messages,
                progress_steps, step_iterations, session_id, logger
            ):
                progress_steps = max(progress_steps, new_progress)
                if is_complete:
                    step_complete = True
                yield (event, progress_steps, step_iterations, is_complete)

    async def _generate_final_response(
        self,
        agent: "Agent",
        messages: list[dict[str, Any]],
    ) -> str:
        """Generate final response after all plan steps complete."""
        messages.append(
            {
                "role": "user",
                "content": (
                    "All planned steps are complete. Provide the final response "
                    "to the mission."
                ),
            }
        )
        result = await agent.llm_provider.complete(
            messages=messages,
            model=agent.model_alias,
            tools=None,
            tool_choice="none",
            temperature=0.2,
        )
        if result.get("success"):
            return result.get("content", "") or ""
        return ""

    async def execute(
        self, agent: "Agent", mission: str, session_id: str
    ) -> ExecutionResult:
        # Use strategy logger or fallback to agent logger
        logger = self.logger or agent.logger
        logger.info("execute_start", session_id=session_id, mission=mission[:100])
        result = await _collect_execution_result(
            session_id,
            self.execute_stream(agent, mission, session_id),
        )

        logger.info(
            "execute_complete",
            session_id=session_id,
            status=result.status,
        )
        return result

    async def execute_stream(
        self, agent: "Agent", mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        # Use strategy logger or fallback to agent logger
        logger = self.logger or agent.logger
        logger.info("execute_stream_start", session_id=session_id)

        state = await agent.state_manager.load_state(session_id) or {}

        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        messages = agent._build_initial_messages(mission, state)

        plan_steps = await self._initialize_plan(agent, mission, logger)

        if agent._planner:
            await agent._planner.execute(action="create_plan", tasks=plan_steps)
            yield StreamEvent(
                event_type="plan_updated",
                data=_build_plan_update(
                    action="create_plan",
                    steps=plan_steps,
                    plan=agent._planner.get_plan_summary(),
                ),
            )

        progress_steps = 0
        loop_iterations = 0
        final_message = ""

        for index, description in enumerate(plan_steps, start=1):
            if progress_steps >= agent.max_steps:
                break

            step_complete = False
            async for event, step_progress, step_iters, is_complete in self._execute_plan_step(
                agent=agent,
                step_index=index,
                step_description=description,
                messages=messages,
                session_id=session_id,
                mission=mission,
                state=state,
                current_progress=progress_steps,
                max_iterations=self.max_step_iterations,
                logger=logger,
            ):
                if progress_steps < agent.max_steps:
                    progress_steps = max(progress_steps, step_progress)
                loop_iterations = max(loop_iterations, step_iters)
                yield event
                if is_complete:
                    step_complete = True

            if progress_steps >= agent.max_steps:
                break

        if progress_steps < agent.max_steps:
            final_message = await self._generate_final_response(agent, messages)

        if progress_steps >= agent.max_steps and not final_message:
            final_message = f"Exceeded maximum steps ({agent.max_steps})"
            yield StreamEvent(
                event_type="error",
                data={"message": final_message, "step": progress_steps},
            )
        elif not final_message:
            final_message = "Plan execution did not produce a final response."
            yield StreamEvent(
                event_type="error",
                data={"message": final_message, "step": progress_steps},
            )

        if final_message:
            yield StreamEvent(
                event_type="final_answer",
                data={"content": final_message},
            )

        await agent.state_store.save(
            session_id=session_id,
            state=state,
            planner=agent.planner,
        )

        logger.info(
            "execute_stream_complete",
            session_id=session_id,
            progress_steps=progress_steps,
            total_iterations=loop_iterations,
        )


class PlanAndReactStrategy:
    """Generate a plan and run the ReAct loop with plan context."""

    name = "plan_and_react"

    def __init__(self, max_plan_steps: int = 12, logger: LoggerProtocol | None = None) -> None:
        self.max_plan_steps = max_plan_steps
        self.logger = logger
        self._react_strategy = NativeReActStrategy()

    async def execute(
        self, agent: "Agent", mission: str, session_id: str
    ) -> ExecutionResult:
        # Use strategy logger or fallback to agent logger
        logger = self.logger or agent.logger
        logger.info("execute_start", session_id=session_id, mission=mission[:100])
        result = await _collect_execution_result(
            session_id,
            self.execute_stream(agent, mission, session_id),
        )
        logger.info(
            "execute_complete",
            session_id=session_id,
            status=result.status,
        )
        return result

    async def execute_stream(
        self, agent: "Agent", mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        # Use strategy logger or fallback to agent logger
        logger = self.logger or agent.logger
        logger.info("execute_stream_start", session_id=session_id)
        state = await agent.state_manager.load_state(session_id) or {}

        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        plan_steps = await _generate_plan_steps(agent, mission, logger)
        if not plan_steps:
            plan_steps = [
                "Analyze the mission and identify required actions.",
                "Execute the required actions using available tools.",
                "Summarize the results and provide the final response.",
            ]

        plan_steps = plan_steps[: self.max_plan_steps]

        if agent._planner:
            await agent._planner.execute(action="create_plan", tasks=plan_steps)
            yield StreamEvent(
                event_type="plan_updated",
                data=_build_plan_update(
                    action="create_plan",
                    steps=plan_steps,
                    plan=agent._planner.get_plan_summary(),
                ),
            )

        await agent.state_store.save(
            session_id=session_id,
            state=state,
            planner=agent.planner,
        )

        async for event in self._react_strategy.execute_stream(
            agent, mission, session_id
        ):
            yield event
