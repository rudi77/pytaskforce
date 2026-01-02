"""
Agent Execution API Routes
==========================

This module provides HTTP endpoints for executing agent missions.
Supports synchronous and streaming (SSE) execution modes.

Endpoints:
- POST /execute - Synchronous mission execution
- POST /execute/stream - Streaming mission execution via SSE

Both endpoints support:
- Legacy Agent (ReAct loop with TodoList planning)
- LeanAgent (native tool calling with PlannerTool) via `lean: true`
- RAG-enabled execution with user context filtering
"""

import json
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from taskforce.application.executor import AgentExecutor

router = APIRouter()
executor = AgentExecutor()


class ExecuteMissionRequest(BaseModel):
    """Request body for mission execution.

    Used by both `/execute` and `/execute/stream` endpoints.

    Attributes:
        mission: The task description for the agent to execute.
        profile: Configuration profile name (dev/staging/prod).
            Controls LLM settings, tool availability, and logging.
        session_id: Optional session identifier. If provided, agent
            attempts to resume existing session. If omitted, new UUID.
        conversation_history: Optional prior conversation for context.
            Useful for chat integrations.
        user_id: User identifier for RAG security filtering (optional).
        org_id: Organization identifier for RAG security filtering.
        scope: Access scope for RAG security filtering (optional).
        lean: If true, uses LeanAgent with native OpenAI tool calling.
            If false (default), uses legacy Agent with ReAct loop.

    Example::

        {
            "mission": "Search for recent news about AI",
            "profile": "dev",
            "lean": true,
            "conversation_history": [
                {"role": "user", "content": "I'm interested in AI"},
                {"role": "assistant", "content": "What to know?"}
            ]
        }
    """

    mission: str = Field(
        ...,
        description="The task description for the agent to execute.",
        examples=["Search for recent news about AI and summarize findings"]
    )
    profile: str = Field(
        default="dev",
        description="Configuration profile (dev/staging/prod).",
        examples=["dev", "staging", "prod"]
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID to resume. Auto-generated if omitted.",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
    conversation_history: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional conversation history for chat context.",
        examples=[[
            {"role": "user", "content": "Previous user message"},
            {"role": "assistant", "content": "Previous assistant response"}
        ]]
    )
    user_id: Optional[str] = Field(
        default=None,
        description="User ID for RAG security filtering."
    )
    org_id: Optional[str] = Field(
        default=None,
        description="Organization ID for RAG security filtering."
    )
    scope: Optional[str] = Field(
        default=None,
        description="Access scope for RAG security filtering."
    )
    lean: bool = Field(
        default=False,
        description="Use LeanAgent (native tool calling) instead of legacy."
    )
    agent_id: Optional[str] = Field(
        default=None,
        description="Custom agent ID to use (forces LeanAgent). If provided, loads agent from configs/custom/{agent_id}.yaml"
    )


class ExecuteMissionResponse(BaseModel):
    """Response from synchronous mission execution.

    Attributes:
        session_id: Unique identifier for this execution session.
        status: Execution status. Possible values:
            - "completed": Mission finished successfully
            - "failed": Mission execution failed
            - "paused": Waiting for user input (ask_user action)
            - "pending": Execution incomplete (timeout/max steps)
        message: Human-readable summary of the execution result.

    Example::

        {
            "session_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "completed",
            "message": "Found 5 recent AI news articles..."
        }
    """

    session_id: str = Field(
        ...,
        description="Unique session identifier."
    )
    status: str = Field(
        ...,
        description="Execution status: completed, failed, paused, or pending."
    )
    message: str = Field(
        ...,
        description="Human-readable execution result summary."
    )


@router.post("/execute", response_model=ExecuteMissionResponse)
async def execute_mission(request: ExecuteMissionRequest):
    """Execute agent mission synchronously.

    Executes the given mission and returns the final result when complete.
    This endpoint blocks until execution finishes or fails.

    **Agent Types:**

    - `lean: false` (default): Legacy Agent with ReAct loop
    - `lean: true`: LeanAgent with native OpenAI tool calling

    **RAG Mode:**

    When `user_id`, `org_id`, or `scope` is provided, the agent
    operates in RAG mode with security-filtered document access.

    **Returns:**

    - `session_id`: Can be used to resume or reference this session
    - `status`: Final execution status
    - `message`: Summary of what the agent accomplished

    **Error Handling:**

    - Returns HTTP 500 with error details on execution failure
    """
    try:
        # Build user_context if any RAG parameters provided
        user_context = None
        if request.user_id or request.org_id or request.scope:
            user_context = {
                "user_id": request.user_id,
                "org_id": request.org_id,
                "scope": request.scope,
            }

        result = await executor.execute_mission(
            mission=request.mission,
            profile=request.profile,
            session_id=request.session_id,
            conversation_history=request.conversation_history,
            user_context=user_context,
            use_lean_agent=request.lean,
            agent_id=request.agent_id,
        )

        return ExecuteMissionResponse(
            session_id=result.session_id,
            status=result.status,
            message=result.final_message
        )
    except FileNotFoundError as e:
        # agent_id not found -> 404
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        # Invalid agent definition -> 400
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Other errors -> 500
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute/stream")
async def execute_mission_stream(request: ExecuteMissionRequest):
    """Execute mission with streaming progress via Server-Sent Events.

    Streams execution progress as SSE events for real-time UI updates.
    Each event is a JSON-encoded `ProgressUpdate` object.

    **SSE Format:**

    Each event follows the SSE standard format::

        data: {"timestamp": "...", "event_type": "...", ...}

        data: {"timestamp": "...", "event_type": "...", ...}

    **ProgressUpdate Structure:**

    All events share this base structure::

        {
            "timestamp": "2024-01-15T10:30:00.123456",
            "event_type": "<event_type>",
            "message": "Human-readable description",
            "details": { ... event-specific data ... }
        }

    **Event Types:**

    The following event types can be emitted during execution:

    **1. started**

    Emitted once at the beginning of execution::

        {
            "event_type": "started",
            "message": "Starting mission: Search for...",
            "details": {
                "session_id": "550e8400-...",
                "profile": "dev",
                "lean": true
            }
        }

    **2. step_start**

    New execution loop iteration begins::

        {
            "event_type": "step_start",
            "message": "Step 1 starting...",
            "details": {"step": 1}
        }

    **3. llm_token**

    Real-time token from LLM response (LeanAgent streaming only).
    Accumulate `details.content` to build the full response::

        {
            "event_type": "llm_token",
            "message": "The",
            "details": {"content": "The"}
        }

    **4. tool_call**

    Tool invocation starting (before execution)::

        {
            "event_type": "tool_call",
            "message": "Calling: web_search",
            "details": {
                "tool": "web_search",
                "input": {"query": "recent AI news 2024"}
            }
        }

    **5. tool_result**

    Tool execution completed (after execution).

    Success::

        {
            "event_type": "tool_result",
            "message": "web_search: Found 10 results...",
            "details": {
                "tool": "web_search",
                "success": true,
                "output": {"results": [...], "count": 10}
            }
        }

    Failure::

        {
            "event_type": "tool_result",
            "message": "web_search: Connection timeout",
            "details": {
                "tool": "web_search",
                "success": false,
                "error": "Connection timeout after 30s"
            }
        }

    **6. plan_updated**

    PlannerTool modified the execution plan (LeanAgent only).
    Possible actions: add_step, mark_complete, mark_failed, skip_step::

        {
            "event_type": "plan_updated",
            "message": "Plan updated (add_step)",
            "details": {
                "action": "add_step",
                "description": "Added step to verify results",
                "plan_summary": "3 steps total, 1 completed"
            }
        }

    **7. thought**

    Agent's reasoning (legacy Agent, post-hoc streaming)::

        {
            "event_type": "thought",
            "message": "Step 1: Searching for recent AI news",
            "details": {
                "rationale": "Searching for recent AI news articles",
                "step_ref": 1,
                "action": {"type": "tool_call", "tool": "web_search"}
            }
        }

    **8. observation**

    Action result (legacy Agent, post-hoc streaming)::

        {
            "event_type": "observation",
            "message": "Step 1: success",
            "details": {"success": true, "data": {...}}
        }

    **9. final_answer**

    Agent completed with final response::

        {
            "event_type": "final_answer",
            "message": "Based on my research...",
            "details": {"content": "Based on my research..."}
        }

    **10. complete**

    Execution finished (final event)::

        {
            "event_type": "complete",
            "message": "Mission completed successfully.",
            "details": {
                "status": "completed",
                "session_id": "550e8400-...",
                "todolist_id": "plan-abc123"
            }
        }

    **11. error**

    Error occurred during execution::

        {
            "event_type": "error",
            "message": "Error: Rate limit exceeded",
            "details": {
                "error": "Rate limit exceeded",
                "error_type": "RateLimitError"
            }
        }

    **Event Sequence Examples:**

    Successful LeanAgent execution::

        started -> step_start -> tool_call -> tool_result
                -> step_start -> llm_token* -> final_answer -> complete

    Legacy Agent execution::

        started -> thought -> observation -> thought
                -> observation -> complete

    Execution with error::

        started -> step_start -> tool_call
                -> tool_result(success=false) -> error

    **Client Integration (JavaScript):**

    EventSource doesn't support POST, use fetch with ReadableStream::

        const response = await fetch('/api/agent/execute/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mission: 'Find AI news', lean: true })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            for (const line of chunk.split('\\n\\n')) {
                if (line.startsWith('data: ')) {
                    const event = JSON.parse(line.slice(6));
                    console.log(event.event_type, event.message);

                    switch (event.event_type) {
                        case 'started': showSpinner(); break;
                        case 'tool_call':
                            showToolProgress(event.details.tool);
                            break;
                        case 'llm_token':
                            appendToResponse(event.details.content);
                            break;
                        case 'complete':
                        case 'final_answer':
                            hideSpinner();
                            break;
                        case 'error':
                            showError(event.details.error);
                            break;
                    }
                }
            }
        }

    **Client Integration (Python):**

    Using httpx for async streaming::

        import httpx
        import json

        async with httpx.AsyncClient() as client:
            async with client.stream(
                'POST',
                'http://localhost:8000/api/agent/execute/stream',
                json={'mission': 'Find AI news', 'lean': True}
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        event = json.loads(line[6:])
                        print(f"[{event['event_type']}] {event['message']}")
    """
    # Build user_context if any RAG parameters provided
    user_context = None
    if request.user_id or request.org_id or request.scope:
        user_context = {
            "user_id": request.user_id,
            "org_id": request.org_id,
            "scope": request.scope,
        }

    async def event_generator():
        try:
            async for update in executor.execute_mission_streaming(
                mission=request.mission,
                profile=request.profile,
                session_id=request.session_id,
                conversation_history=request.conversation_history,
                user_context=user_context,
                use_lean_agent=request.lean,
                agent_id=request.agent_id,
            ):
                # Serialize dataclass to JSON, handling datetime
                data = json.dumps(asdict(update), default=str)
                yield f"data: {data}\n\n"
        except FileNotFoundError as e:
            # agent_id not found -> send error event
            error_data = json.dumps({
                "timestamp": datetime.now().isoformat(),
                "event_type": "error",
                "message": f"Agent not found: {str(e)}",
                "details": {"error": str(e), "error_type": "FileNotFoundError", "status_code": 404}
            })
            yield f"data: {error_data}\n\n"
        except ValueError as e:
            # Invalid agent definition -> send error event
            error_data = json.dumps({
                "timestamp": datetime.now().isoformat(),
                "event_type": "error",
                "message": f"Invalid agent definition: {str(e)}",
                "details": {"error": str(e), "error_type": "ValueError", "status_code": 400}
            })
            yield f"data: {error_data}\n\n"
        except Exception as e:
            # Other errors -> send error event
            error_data = json.dumps({
                "timestamp": datetime.now().isoformat(),
                "event_type": "error",
                "message": f"Execution failed: {str(e)}",
                "details": {"error": str(e), "error_type": type(e).__name__, "status_code": 500}
            })
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
