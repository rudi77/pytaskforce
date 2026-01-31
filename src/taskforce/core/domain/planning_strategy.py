"""
Planning Strategy Abstractions for Agent.

Defines the strategy interface and built-in strategy implementations.
Simplified architecture with two strategies:
- NativeReActStrategy: ReAct loop with optional upfront plan generation
- PlanAndExecuteStrategy: Generate plan, execute steps sequentially
"""

from __future__ import annotations

import json
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING

from taskforce.core.domain.models import ExecutionResult, StreamEvent
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.tools.tool_converter import assistant_tool_calls_to_message

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


# =============================================================================
# Shared Helper Functions
# =============================================================================


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


def _parse_tool_args(tool_call: dict[str, Any], logger: LoggerProtocol) -> dict[str, Any]:
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


def _extract_tool_output(tool_result: dict[str, Any]) -> str:
    """Extract output from tool result for streaming events."""
    if "output" in tool_result:
        output = tool_result["output"]
        return output if isinstance(output, str) else json.dumps(output, default=str, ensure_ascii=False)
    if "error" in tool_result:
        return str(tool_result["error"])
    return json.dumps(tool_result, default=str, ensure_ascii=False)


def _tool_supports_parallelism(agent: "Agent", tool_name: str) -> bool:
    """Return whether a tool is safe to execute in parallel."""
    tool = agent.tools.get(tool_name)
    if not tool:
        return False
    return bool(getattr(tool, "supports_parallelism", False)) and not tool.requires_approval


async def _execute_tool_calls(
    agent: "Agent",
    requests: list[ToolCallRequest],
    session_id: str | None = None,
) -> list[tuple[ToolCallRequest, dict[str, Any]]]:
    """Execute tool calls with optional parallelism and ordering."""
    if not requests:
        return []

    max_parallel = max(1, agent.max_parallel_tools)
    semaphore = asyncio.Semaphore(max_parallel)
    results: dict[str, dict[str, Any]] = {}
    parallel_tasks: list[tuple[ToolCallRequest, asyncio.Task[dict[str, Any]]]] = []

    async def execute_with_limit(name: str, args: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await agent._execute_tool(name, args, session_id=session_id)

    for request in requests:
        if _tool_supports_parallelism(agent, request.tool_name) and max_parallel > 1:
            task = asyncio.create_task(
                execute_with_limit(request.tool_name, request.tool_args)
            )
            parallel_tasks.append((request, task))
        else:
            results[request.tool_call_id] = await agent._execute_tool(
                request.tool_name, request.tool_args, session_id=session_id
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
    total_token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    history_event_types = {"tool_call", "tool_result", "ask_user", "plan_updated", "final_answer", "error"}

    async for event in events:
        event_type = event.event_type
        if event_type in history_event_types:
            execution_history.append({"type": event_type, **event.data})
        if event_type == "final_answer":
            final_message = event.data.get("content", "")
        elif event_type == "ask_user":
            pending_question = dict(event.data)
            if not final_message:
                final_message = str(event.data.get("question", "")).strip() or "Waiting for user input"
        elif event_type == "error":
            last_error = event.data.get("message", "")
        elif event_type == "token_usage":
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

    return _parse_plan_steps(result.get("content", "") or "", logger)


def _parse_plan_steps(content: str, logger: LoggerProtocol) -> list[str]:
    """Parse plan steps from LLM response."""
    text = content.strip()
    if not text:
        return []

    # Try JSON parsing (with or without code blocks)
    json_text = text
    if "```" in text:
        try:
            parts = text.split("```")
            if len(parts) >= 2:
                json_text = parts[1].strip()
                if "\n" in json_text:
                    lines = json_text.split("\n", 1)
                    if len(lines) > 1 and not lines[0].strip().startswith("["):
                        json_text = lines[1].strip()
        except Exception as e:
            logger.debug("code_block_parse_error", error=str(e))

    try:
        data = json.loads(json_text)
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.debug("json_parse_failed", error=str(e), content_preview=text[:100])

    # Fallback to line-based parsing
    steps: list[str] = []
    for line in text.splitlines():
        candidate = line.strip().lstrip("-").strip()
        if not candidate or candidate.startswith("```"):
            continue
        if candidate[0].isdigit() and "." in candidate:
            candidate = candidate.split(".", 1)[1].strip()
        if candidate:
            steps.append(candidate)
    return steps


async def _handle_ask_user(
    agent: "Agent",
    tool_args: dict[str, Any],
    session_id: str,
    state: dict[str, Any],
    logger: LoggerProtocol,
) -> AsyncIterator[StreamEvent]:
    """Handle ask_user tool - pause execution for user input."""
    question = str(tool_args.get("question", "")).strip()
    missing = tool_args.get("missing") or []

    state["pending_question"] = {"question": question, "missing": missing}
    await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)

    yield StreamEvent(event_type="ask_user", data={"question": question, "missing": missing})
    logger.info("execute_stream_paused_for_user_input", session_id=session_id, question=question[:200])


async def _emit_tool_result(
    agent: "Agent",
    request: ToolCallRequest,
    tool_result: dict[str, Any],
) -> AsyncIterator[StreamEvent]:
    """Emit tool result and optional plan update events."""
    yield StreamEvent(
        event_type="tool_result",
        data={
            "tool": request.tool_name,
            "id": request.tool_call_id,
            "success": tool_result.get("success", False),
            "output": agent._truncate_output(_extract_tool_output(tool_result)),
            "args": request.tool_args,
        },
    )

    if request.tool_name in ("planner", "manage_plan") and tool_result.get("success"):
        plan_output = tool_result.get("output")
        if not plan_output and agent._planner:
            plan_output = agent._planner.get_plan_summary()
        yield StreamEvent(
            event_type="plan_updated",
            data=_build_plan_update(action=request.tool_args.get("action", "unknown"), plan=plan_output),
        )


# =============================================================================
# NativeReActStrategy - Main ReAct Loop with optional upfront planning
# =============================================================================


class NativeReActStrategy:
    """Strategy that owns the native tool calling ReAct loop.

    Optionally generates a plan upfront before running the ReAct loop.
    This consolidates the former PlanAndReactStrategy functionality.
    """

    name = "native_react"

    def __init__(
        self,
        generate_plan_first: bool = False,
        max_plan_steps: int = 12,
        logger: LoggerProtocol | None = None,
    ) -> None:
        self.generate_plan_first = generate_plan_first
        self.max_plan_steps = max_plan_steps
        self._logger = logger

    async def execute(
        self, agent: "Agent", mission: str, session_id: str
    ) -> ExecutionResult:
        agent.logger.info("execute_start", session_id=session_id, mission=mission[:100])
        result = await _collect_execution_result(
            session_id, self.execute_stream(agent, mission, session_id)
        )
        agent.logger.info("execute_complete", session_id=session_id, status=result.status)
        return result

    async def execute_stream(
        self, agent: "Agent", mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        logger = self._logger or agent.logger
        logger.info("execute_stream_start", session_id=session_id)

        state = await agent.state_manager.load_state(session_id) or {}
        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        # Optional upfront plan generation (replaces PlanAndReactStrategy)
        if self.generate_plan_first:
            async for event in self._generate_initial_plan(agent, mission, state, session_id, logger):
                yield event

        messages = agent._build_initial_messages(mission, state)
        use_streaming = hasattr(agent.llm_provider, "complete_stream")

        if not use_streaming:
            logger.warning("llm_provider_no_streaming", fallback="execute")

        async for event in self._execute_loop(
            agent, mission, session_id, messages, state, use_streaming, logger
        ):
            yield event

    async def _generate_initial_plan(
        self,
        agent: "Agent",
        mission: str,
        state: dict[str, Any],
        session_id: str,
        logger: LoggerProtocol,
    ) -> AsyncIterator[StreamEvent]:
        """Generate and save initial plan before ReAct loop."""
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

        await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)

    async def _execute_loop(
        self,
        agent: "Agent",
        mission: str,
        session_id: str,
        messages: list[dict[str, Any]],
        state: dict[str, Any],
        use_streaming: bool,
        logger: LoggerProtocol,
    ) -> AsyncIterator[StreamEvent]:
        """Unified execution loop for streaming and non-streaming LLM calls."""
        step = 0
        loop_iterations = 0
        final_message = ""

        while step < agent.max_steps:
            loop_iterations += 1
            logger.debug(
                "loop_iteration",
                session_id=session_id,
                iteration=loop_iterations,
                progress_steps=step,
                max_steps=agent.max_steps,
            )
            await agent.record_heartbeat(session_id, "running", {"step": step, "iteration": loop_iterations})

            yield StreamEvent(
                event_type="step_start",
                data={"step": step, "max_steps": agent.max_steps, "iteration": loop_iterations},
            )

            # Update system prompt
            current_system_prompt = agent._build_system_prompt(mission=mission, state=state, messages=messages)
            messages[0] = {"role": "system", "content": current_system_prompt}

            if use_streaming:
                messages = await agent._compress_messages(messages)
                messages = await agent._preflight_budget_check(messages)

            # Call LLM (streaming or non-streaming)
            tool_calls: list[dict[str, Any]] = []
            content = ""

            if use_streaming:
                async for chunk_event in self._process_streaming_llm(agent, messages, step, logger):
                    if chunk_event.event_type == "_internal_tool_calls":
                        tool_calls = chunk_event.data["tool_calls"]
                    elif chunk_event.event_type == "_internal_content":
                        content = chunk_event.data["content"]
                    else:
                        yield chunk_event
            else:
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
                    logger.error("llm_call_failed", error=result.get("error"), iteration=loop_iterations, step=step)
                    messages.append({"role": "user", "content": f"[System Error: {result.get('error')}. Please try again.]"})
                    continue
                tool_calls = result.get("tool_calls") or []
                content = result.get("content", "")

            # Process tool calls
            if tool_calls:
                should_return = False
                async for event in self._process_tool_calls(
                    agent, tool_calls, session_id, step, state, messages, logger
                ):
                    if event.event_type == "ask_user":
                        should_return = True
                    yield event
                if should_return:
                    return
                step += 1
                continue

            # Process content response
            if content:
                step += 1
                final_message = content
                yield StreamEvent(event_type="final_answer", data={"content": content})
                break

            # Empty response
            logger.warning("empty_response", step=step, iteration=loop_iterations)
            messages.append({
                "role": "user",
                "content": "[System: Your response was empty. Please provide an answer or use a tool.]",
            })

        # Handle completion
        if step >= agent.max_steps and not final_message:
            final_message = f"Exceeded maximum steps ({agent.max_steps})"
            yield StreamEvent(event_type="error", data={"message": final_message, "step": step})

        await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)
        logger.info(
            "execute_stream_complete",
            session_id=session_id,
            progress_steps=step,
            total_iterations=loop_iterations,
        )

    async def _process_streaming_llm(
        self,
        agent: "Agent",
        messages: list[dict[str, Any]],
        step: int,
        logger: LoggerProtocol,
    ) -> AsyncIterator[StreamEvent]:
        """Process streaming LLM call, yield events, return tool_calls/content via internal events."""
        tool_calls_accumulated: dict[int, dict[str, Any]] = {}
        content_accumulated = ""

        try:
            async for chunk in agent.llm_provider.complete_stream(
                messages=messages,
                model=agent.model_alias,
                tools=agent._openai_tools,
                tool_choice="auto",
                temperature=0.2,
            ):
                chunk_type = chunk.get("type")

                if chunk_type == "token":
                    token_content = chunk.get("content", "")
                    if token_content:
                        yield StreamEvent(event_type="llm_token", data={"content": token_content})
                        content_accumulated += token_content

                elif chunk_type == "tool_call_start":
                    tc_index = chunk.get("index", 0)
                    tool_calls_accumulated[tc_index] = {
                        "id": chunk.get("id", ""),
                        "name": chunk.get("name", ""),
                        "arguments": "",
                    }
                    yield StreamEvent(
                        event_type="tool_call",
                        data={"tool": chunk.get("name", ""), "id": chunk.get("id", ""), "status": "starting"},
                    )

                elif chunk_type == "tool_call_delta":
                    tc_index = chunk.get("index", 0)
                    if tc_index in tool_calls_accumulated:
                        tool_calls_accumulated[tc_index]["arguments"] += chunk.get("arguments_delta", "")

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

        except Exception as e:
            logger.error("stream_error", error=str(e), step=step)
            yield StreamEvent(event_type="error", data={"message": str(e), "step": step})
            return

        # Return results via internal events
        if tool_calls_accumulated:
            tool_calls_list = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls_accumulated.values()
            ]
            yield StreamEvent(event_type="_internal_tool_calls", data={"tool_calls": tool_calls_list})
        elif content_accumulated:
            yield StreamEvent(event_type="_internal_content", data={"content": content_accumulated})

    async def _process_tool_calls(
        self,
        agent: "Agent",
        tool_calls: list[dict[str, Any]],
        session_id: str,
        step: int,
        state: dict[str, Any],
        messages: list[dict[str, Any]],
        logger: LoggerProtocol,
    ) -> AsyncIterator[StreamEvent]:
        """Process tool calls and yield events."""
        logger.info(
            "tool_calls_received",
            step=step + 1,
            count=len(tool_calls),
            tools=[tc["function"]["name"] for tc in tool_calls],
        )

        messages.append(assistant_tool_calls_to_message(tool_calls))
        requests: list[ToolCallRequest] = []

        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_call_id = tool_call["id"]
            tool_args = _parse_tool_args(tool_call, logger)

            yield StreamEvent(
                event_type="tool_call",
                data={"tool": tool_name, "id": tool_call_id, "status": "executing", "args": tool_args},
            )

            # Handle ask_user specially - pause execution
            if tool_name == "ask_user":
                async for event in _handle_ask_user(agent, tool_args, session_id, state, logger):
                    yield event
                return

            requests.append(ToolCallRequest(tool_call_id=tool_call_id, tool_name=tool_name, tool_args=tool_args))

        # Execute tools
        tool_results = await _execute_tool_calls(agent, requests, session_id=session_id)
        for request, tool_result in tool_results:
            async for event in _emit_tool_result(agent, request, tool_result):
                yield event

            tool_message = await agent._create_tool_message(
                request.tool_call_id, request.tool_name, tool_result, session_id, step + 1
            )
            messages.append(tool_message)


# =============================================================================
# PlanAndExecuteStrategy - Generate plan, execute steps sequentially
# =============================================================================


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

    async def execute(
        self, agent: "Agent", mission: str, session_id: str
    ) -> ExecutionResult:
        logger = self.logger or agent.logger
        logger.info("execute_start", session_id=session_id, mission=mission[:100])
        result = await _collect_execution_result(
            session_id, self.execute_stream(agent, mission, session_id)
        )
        logger.info("execute_complete", session_id=session_id, status=result.status)
        return result

    async def execute_stream(
        self, agent: "Agent", mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        logger = self.logger or agent.logger
        logger.info("execute_stream_start", session_id=session_id)

        state = await agent.state_manager.load_state(session_id) or {}
        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        messages = agent._build_initial_messages(mission, state)

        # Generate plan
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
                data=_build_plan_update(action="create_plan", steps=plan_steps, plan=agent._planner.get_plan_summary()),
            )

        progress_steps = 0

        # Execute each plan step
        for step_index, step_description in enumerate(plan_steps, start=1):
            if progress_steps >= agent.max_steps:
                break

            async for event, new_progress in self._execute_plan_step(
                agent, step_index, step_description, messages, session_id, mission, state, progress_steps, logger
            ):
                yield event
                progress_steps = max(progress_steps, new_progress)

            if progress_steps >= agent.max_steps:
                break

        # Generate final response
        final_message = ""
        if progress_steps < agent.max_steps:
            async for event in self._generate_final_response_stream(agent, messages):
                yield event
                if event.event_type == "final_answer":
                    final_message = event.data.get("content", "")

        # Handle edge cases
        if progress_steps >= agent.max_steps and not final_message:
            final_message = f"Exceeded maximum steps ({agent.max_steps})"
            yield StreamEvent(event_type="error", data={"message": final_message, "step": progress_steps})
            yield StreamEvent(event_type="final_answer", data={"content": final_message})
        elif not final_message:
            # Try to extract from messages
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and msg.get("content"):
                    final_message = msg.get("content", "").strip()
                    if final_message:
                        break
            if not final_message:
                final_message = "Plan execution completed."
                yield StreamEvent(event_type="final_answer", data={"content": final_message})

        await agent.state_store.save(session_id=session_id, state=state, planner=agent.planner)

        yield StreamEvent(
            event_type="complete",
            data={"status": "completed", "session_id": session_id, "progress_steps": progress_steps},
        )

        logger.info("execute_stream_complete", session_id=session_id, progress_steps=progress_steps)

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
        logger: LoggerProtocol,
    ) -> AsyncIterator[tuple[StreamEvent, int]]:
        """Execute a single plan step with iteration limits."""
        progress = current_progress

        for iteration in range(1, self.max_step_iterations + 1):
            if progress >= agent.max_steps:
                break

            await agent.record_heartbeat(session_id, "running", {"plan_step": step_index, "iteration": iteration})

            # Prepare step instruction
            current_system_prompt = agent._build_system_prompt(mission=mission, state=state, messages=messages)
            messages[0] = {"role": "system", "content": current_system_prompt}
            messages.append({
                "role": "user",
                "content": (
                    f"Execute plan step {step_index}: {step_description}\n"
                    "Call tools when needed. When the step is complete, respond with a short completion note."
                ),
            })

            # Call LLM
            result = await agent.llm_provider.complete(
                messages=messages,
                model=agent.model_alias,
                tools=agent._openai_tools,
                tool_choice="auto",
                temperature=0.2,
            )

            if result.get("usage"):
                yield (StreamEvent(event_type="token_usage", data=result["usage"]), progress)

            if not result.get("success"):
                logger.error("llm_call_failed", error=result.get("error"), plan_step=step_index, iteration=iteration)
                messages.append({"role": "user", "content": f"[System Error: {result.get('error')}. Please try again.]"})
                continue

            tool_calls = result.get("tool_calls")
            if tool_calls:
                progress += 1
                messages.append(assistant_tool_calls_to_message(tool_calls))

                requests: list[ToolCallRequest] = []
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_call_id = tool_call["id"]
                    tool_args = _parse_tool_args(tool_call, logger)

                    yield (StreamEvent(
                        event_type="tool_call",
                        data={"tool": tool_name, "id": tool_call_id, "status": "executing", "args": tool_args},
                    ), progress)

                    # Handle ask_user
                    if tool_name == "ask_user":
                        async for event in _handle_ask_user(agent, tool_args, session_id, state, logger):
                            yield (event, progress)
                        return

                    requests.append(ToolCallRequest(tool_call_id=tool_call_id, tool_name=tool_name, tool_args=tool_args))

                tool_results = await _execute_tool_calls(agent, requests, session_id=session_id)
                for request, tool_result in tool_results:
                    async for event in _emit_tool_result(agent, request, tool_result):
                        yield (event, progress)
                    tool_message = await agent._create_tool_message(
                        request.tool_call_id, request.tool_name, tool_result, session_id, step_index
                    )
                    messages.append(tool_message)
                continue

            # Content response - step complete
            content = result.get("content", "")
            if content:
                messages.append({"role": "assistant", "content": content})
                if agent._planner:
                    await agent._planner.execute(action="mark_done", step_index=step_index)
                    yield (StreamEvent(
                        event_type="plan_updated",
                        data=_build_plan_update(
                            action="mark_done",
                            step=step_index,
                            status="completed",
                            plan=agent._planner.get_plan_summary(),
                        ),
                    ), progress + 1)
                return

            # Empty response
            messages.append({
                "role": "user",
                "content": "[System: Your response was empty. Please provide an answer or use a tool.]",
            })

    async def _generate_final_response_stream(
        self,
        agent: "Agent",
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[StreamEvent]:
        """Generate and stream final response after all plan steps complete."""
        messages.append({
            "role": "user",
            "content": "All planned steps are complete. Provide the final response to the mission.",
        })

        content_accumulated = ""
        async for chunk in agent.llm_provider.complete_stream(
            messages=messages,
            model=agent.model_alias,
            tools=None,
            tool_choice="none",
            temperature=0.2,
        ):
            chunk_type = chunk.get("type", "")
            if chunk_type == "token":
                token_content = chunk.get("content", "")
                if token_content:
                    yield StreamEvent(event_type="llm_token", data={"content": token_content})
                    content_accumulated += token_content
            elif chunk_type == "usage":
                yield StreamEvent(event_type="token_usage", data=chunk.get("usage", {}))
            elif chunk_type == "error":
                yield StreamEvent(
                    event_type="error",
                    data={"message": chunk.get("message", "LLM error"), "error_type": "LLMError"},
                )
                return

        if content_accumulated:
            yield StreamEvent(event_type="final_answer", data={"content": content_accumulated})

    async def _generate_final_response(
        self,
        agent: "Agent",
        messages: list[dict[str, Any]],
    ) -> str:
        """Generate final response (non-streaming, for tests)."""
        messages.append({
            "role": "user",
            "content": "All planned steps are complete. Provide the final response to the mission.",
        })
        result = await agent.llm_provider.complete(
            messages=messages,
            model=agent.model_alias,
            tools=None,
            tool_choice="none",
            temperature=0.2,
        )
        if not result.get("success"):
            return ""
        return result.get("content", "") or ""


# =============================================================================
# PlanAndReactStrategy - Alias for backwards compatibility
# =============================================================================


class PlanAndReactStrategy:
    """Generate a plan and run the ReAct loop with plan context.

    This is now a thin wrapper around NativeReActStrategy with generate_plan_first=True.
    Kept for backwards compatibility with existing configurations.
    """

    name = "plan_and_react"

    def __init__(self, max_plan_steps: int = 12, logger: LoggerProtocol | None = None) -> None:
        self._delegate = NativeReActStrategy(
            generate_plan_first=True,
            max_plan_steps=max_plan_steps,
            logger=logger,
        )

    async def execute(
        self, agent: "Agent", mission: str, session_id: str
    ) -> ExecutionResult:
        return await self._delegate.execute(agent, mission, session_id)

    async def execute_stream(
        self, agent: "Agent", mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        async for event in self._delegate.execute_stream(agent, mission, session_id):
            yield event
