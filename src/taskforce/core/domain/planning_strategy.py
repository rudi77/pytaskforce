"""
Planning Strategy Abstractions for LeanAgent.

Defines the strategy interface and built-in strategy implementations.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING

import structlog

from taskforce.core.domain.models import ExecutionResult, StreamEvent
from taskforce.infrastructure.tools.tool_converter import (
    assistant_tool_calls_to_message,
)

if TYPE_CHECKING:
    from taskforce.core.domain.lean_agent import LeanAgent


@dataclass
class PlanStep:
    """Represents a single plan step for plan-and-execute strategies."""

    index: int
    description: str
    status: str = "PENDING"


class PlanningStrategy(Protocol):
    """Protocol for LeanAgent planning strategies."""

    name: str

    async def execute(
        self, agent: "LeanAgent", mission: str, session_id: str
    ) -> ExecutionResult:
        """Execute a mission using the provided agent."""

    async def execute_stream(
        self, agent: "LeanAgent", mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        """Execute a mission with streaming updates."""


async def _collect_execution_result(
    session_id: str,
    events: AsyncIterator[StreamEvent],
) -> ExecutionResult:
    """Collect stream events into an ExecutionResult."""
    execution_history: list[dict[str, Any]] = []
    final_message = ""
    last_error = ""
    history_event_types = {
        "tool_call",
        "tool_result",
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
        elif event_type == "error":
            last_error = event.data.get("message", "")

    if not final_message and last_error:
        final_message = last_error

    status = "completed"
    if last_error or not final_message:
        status = "failed"

    return ExecutionResult(
        session_id=session_id,
        status=status,
        final_message=final_message,
        execution_history=execution_history,
    )


class NativeReActStrategy:
    """Strategy that owns the native tool calling ReAct loop."""

    name = "native_react"

    async def execute(
        self, agent: "LeanAgent", mission: str, session_id: str
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

    async def execute_stream(
        self, agent: "LeanAgent", mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        agent.logger.info("execute_stream_start", session_id=session_id)

        if not hasattr(agent.llm_provider, "complete_stream"):
            agent.logger.warning("llm_provider_no_streaming", fallback="execute")
            state = await agent.state_manager.load_state(session_id) or {}

            if agent._planner and state.get("planner_state"):
                agent._planner.set_state(state["planner_state"])

            messages = agent._build_initial_messages(mission, state)

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
                            "content": (
                                f"[System Error: {result.get('error')}. Please try again.]"
                            ),
                        }
                    )
                    continue

                tool_calls = result.get("tool_calls")

                if tool_calls:
                    step += 1
                    agent.logger.info(
                        "tool_calls_received",
                        step=step,
                        iteration=loop_iterations,
                        count=len(tool_calls),
                        tools=[tc["function"]["name"] for tc in tool_calls],
                    )

                    messages.append(assistant_tool_calls_to_message(tool_calls))

                    for tool_call in tool_calls:
                        tool_name = tool_call["function"]["name"]
                        tool_call_id = tool_call["id"]

                        try:
                            tool_args = json.loads(tool_call["function"]["arguments"])
                        except json.JSONDecodeError:
                            tool_args = {}
                            agent.logger.warning(
                                "tool_args_parse_failed",
                                tool=tool_name,
                                raw_args=tool_call["function"]["arguments"],
                            )

                        yield StreamEvent(
                            event_type="tool_call",
                            data={"tool": tool_name, "id": tool_call_id, "status": "completed"},
                        )

                        tool_result = await agent._execute_tool(tool_name, tool_args)
                        yield StreamEvent(
                            event_type="tool_result",
                            data={
                                "tool": tool_name,
                                "id": tool_call_id,
                                "success": tool_result.get("success", False),
                                "output": agent._truncate_output(
                                    tool_result.get(
                                        "output", str(tool_result.get("error", ""))
                                    )
                                ),
                                "args": tool_args,
                            },
                        )

                        if tool_name in ("planner", "manage_plan") and tool_result.get(
                            "success"
                        ):
                            yield StreamEvent(
                                event_type="plan_updated",
                                data={"action": tool_args.get("action", "unknown")},
                            )

                        tool_message = await agent._create_tool_message(
                            tool_call_id, tool_name, tool_result, session_id, step
                        )
                        messages.append(tool_message)

                    continue

                content = result.get("content", "")
                if content:
                    step += 1
                    final_message = content
                    yield StreamEvent(
                        event_type="final_answer",
                        data={"content": content},
                    )
                    break

                agent.logger.warning(
                    "empty_response",
                    step=step,
                    iteration=loop_iterations,
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "[System: Your response was empty. Please provide an answer "
                            "or use a tool.]"
                        ),
                    }
                )

            if step >= agent.max_steps and not final_message:
                final_message = f"Exceeded maximum steps ({agent.max_steps})"
                yield StreamEvent(
                    event_type="error",
                    data={"message": final_message, "step": step},
                )

            await agent._save_state(session_id, state)

            agent.logger.info(
                "execute_stream_complete",
                session_id=session_id,
                progress_steps=step,
                total_iterations=loop_iterations,
                overhead_iterations=loop_iterations - step,
            )
            return

        state = await agent.state_manager.load_state(session_id) or {}

        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        messages = agent._build_initial_messages(mission, state)

        step = 0  # Counts meaningful progress steps (tool calls or final answer)
        loop_iterations = 0  # Counts all loop iterations (for debugging)
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
                            yield StreamEvent(
                                event_type="llm_token",
                                data={"content": token_content},
                            )
                            content_accumulated += token_content

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
                            data={
                                "tool": tc_name,
                                "id": tc_id,
                                "status": "starting",
                            },
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

                    elif chunk_type == "error":
                        yield StreamEvent(
                            event_type="error",
                            data={"message": chunk.get("message", "Unknown error"), "step": step},
                        )

            except Exception as e:
                agent.logger.error("stream_error", error=str(e), step=step)
                yield StreamEvent(
                    event_type="error",
                    data={"message": str(e), "step": step},
                )
                continue

            if tool_calls_accumulated:
                step += 1

                tool_calls_list = [
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
                        },
                    )

                    if tool_name in ("planner", "manage_plan") and tool_result.get("success"):
                        yield StreamEvent(
                            event_type="plan_updated",
                            data={"action": tool_args.get("action", "unknown")},
                        )

                    tool_message = await agent._create_tool_message(
                        tool_call_id, tool_name, tool_result, session_id, step
                    )
                    messages.append(tool_message)

            elif content_accumulated:
                step += 1
                final_message = content_accumulated
                agent.logger.info(
                    "stream_final_answer",
                    step=step,
                    iteration=loop_iterations,
                    total_iterations=loop_iterations,
                )

                yield StreamEvent(
                    event_type="final_answer",
                    data={"content": final_message},
                )
                break

            else:
                agent.logger.warning(
                    "stream_empty_response",
                    step=step,
                    iteration=loop_iterations,
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "[System: Empty response. Please provide an answer or use a tool.]"
                        ),
                    }
                )

        if step >= agent.max_steps and not final_message:
            final_message = f"Exceeded maximum steps ({agent.max_steps})"
            yield StreamEvent(
                event_type="error",
                data={"message": final_message, "step": step},
            )

        await agent._save_state(session_id, state)

        agent.logger.info(
            "execute_stream_complete",
            session_id=session_id,
            progress_steps=step,
            total_iterations=loop_iterations,
            overhead_iterations=loop_iterations - step,
        )

        agent.logger.info("execute_stream_complete", session_id=session_id, steps=step)


class PlanAndExecuteStrategy:
    """Generate a plan up-front and execute steps sequentially."""

    name = "plan_and_execute"

    def __init__(
        self,
        max_step_iterations: int = 4,
        max_plan_steps: int = 12,
    ) -> None:
        self.max_step_iterations = max_step_iterations
        self.max_plan_steps = max_plan_steps
        self.logger = structlog.get_logger().bind(component="plan_and_execute_strategy")

    async def execute(
        self, agent: "LeanAgent", mission: str, session_id: str
    ) -> ExecutionResult:
        self.logger.info("execute_start", session_id=session_id, mission=mission[:100])
        result = await _collect_execution_result(
            session_id,
            self.execute_stream(agent, mission, session_id),
        )

        self.logger.info(
            "execute_complete",
            session_id=session_id,
            status=result.status,
        )
        return result

    async def execute_stream(
        self, agent: "LeanAgent", mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        self.logger.info("execute_stream_start", session_id=session_id)

        state = await agent.state_manager.load_state(session_id) or {}

        if agent._planner and state.get("planner_state"):
            agent._planner.set_state(state["planner_state"])

        messages = agent._build_initial_messages(mission, state)

        plan_steps = await self._generate_plan(agent, mission)
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
                data={"action": "create_plan", "steps": list(plan_steps)},
            )

        progress_steps = 0
        loop_iterations = 0
        final_message = ""

        for index, description in enumerate(plan_steps, start=1):
            if progress_steps >= agent.max_steps:
                break

            step_complete = False
            step_iterations = 0

            while not step_complete and step_iterations < self.max_step_iterations:
                if progress_steps >= agent.max_steps:
                    break

                step_iterations += 1
                loop_iterations += 1

                current_system_prompt = agent._build_system_prompt(
                    mission=mission, state=state, messages=messages
                )
                messages[0] = {"role": "system", "content": current_system_prompt}

                step_instruction = (
                    f"Execute plan step {index}: {description}\n"
                    "Call tools when needed. When the step is complete, respond with "
                    "a short completion note."
                )
                messages.append({"role": "user", "content": step_instruction})

                result = await agent.llm_provider.complete(
                    messages=messages,
                    model=agent.model_alias,
                    tools=agent._openai_tools,
                    tool_choice="auto",
                    temperature=0.2,
                )

                if not result.get("success"):
                    self.logger.error(
                        "llm_call_failed",
                        error=result.get("error"),
                        iteration=loop_iterations,
                        step=progress_steps,
                        plan_step=index,
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"[System Error: {result.get('error')}. Please try again.]"
                            ),
                        }
                    )
                    continue

                tool_calls = result.get("tool_calls")
                if tool_calls:
                    progress_steps += 1
                    messages.append(assistant_tool_calls_to_message(tool_calls))

                    for tool_call in tool_calls:
                        tool_name = tool_call["function"]["name"]
                        tool_call_id = tool_call["id"]

                        try:
                            tool_args = json.loads(tool_call["function"]["arguments"])
                        except json.JSONDecodeError:
                            tool_args = {}
                            self.logger.warning(
                                "tool_args_parse_failed",
                                tool=tool_name,
                                raw_args=tool_call["function"]["arguments"],
                            )

                        yield StreamEvent(
                            event_type="tool_call",
                            data={
                                "tool": tool_name,
                                "id": tool_call_id,
                                "status": "completed",
                            },
                        )

                        tool_result = await agent._execute_tool(tool_name, tool_args)
                        yield StreamEvent(
                            event_type="tool_result",
                            data={
                                "tool": tool_name,
                                "id": tool_call_id,
                                "success": tool_result.get("success", False),
                                "output": agent._truncate_output(
                                    tool_result.get(
                                        "output", str(tool_result.get("error", ""))
                                    )
                                ),
                                "args": tool_args,
                            },
                        )

                        if tool_name in ("planner", "manage_plan") and tool_result.get(
                            "success"
                        ):
                            yield StreamEvent(
                                event_type="plan_updated",
                                data={"action": tool_args.get("action", "unknown")},
                            )

                        tool_message = await agent._create_tool_message(
                            tool_call_id, tool_name, tool_result, session_id, progress_steps
                        )
                        messages.append(tool_message)
                    continue

                content = result.get("content", "")
                if content:
                    progress_steps += 1
                    messages.append({"role": "assistant", "content": content})
                    if agent._planner:
                        await agent._planner.execute(action="mark_done", step_index=index)
                    yield StreamEvent(
                        event_type="plan_updated",
                        data={"step": index, "status": "completed"},
                    )
                    step_complete = True
                else:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "[System: Your response was empty. Please provide an answer "
                                "or use a tool.]"
                            ),
                        }
                    )

        if progress_steps < agent.max_steps:
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
                final_message = result.get("content", "") or ""

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

        await agent._save_state(session_id, state)

        self.logger.info(
            "execute_stream_complete",
            session_id=session_id,
            progress_steps=progress_steps,
            total_iterations=loop_iterations,
        )

    async def _generate_plan(self, agent: "LeanAgent", mission: str) -> list[str]:
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
            self.logger.warning("plan_generation_failed", error=result.get("error"))
            return []

        content = result.get("content", "") or ""
        return self._parse_plan_steps(content)

    def _parse_plan_steps(self, content: str) -> list[str]:
        text = content.strip()
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1].strip()

        try:
            data = json.loads(text)
            if isinstance(data, list):
                steps = [str(item).strip() for item in data if str(item).strip()]
                return steps
        except Exception:
            pass

        steps: list[str] = []
        for line in text.splitlines():
            candidate = line.strip().lstrip("-").strip()
            if not candidate:
                continue
            if candidate[0].isdigit() and "." in candidate:
                candidate = candidate.split(".", 1)[1].strip()
            if candidate:
                steps.append(candidate)
        return steps
