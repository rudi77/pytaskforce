"""Tool that delegates a mission to a remote A2A agent.

Sibling of ``AcpAgentTool`` — targets an external A2A peer instead of
an ACP peer. Returns task state, artifacts metadata and the final
output text. Artifact blobs are NOT inlined into the result so the
calling agent's context budget stays bounded (ADR-025 policy).
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.a2a.runtime import A2aRuntime
from taskforce.infrastructure.tools.base_tool import BaseTool

logger = structlog.get_logger(__name__)


class A2aAgentTool(BaseTool):
    """Call a remote A2A agent by peer name."""

    tool_name = "call_a2a_agent"
    tool_description = (
        "Delegate a mission to a remote agent exposed via the A2A "
        "(Agent-to-Agent) protocol. Provide the configured peer name "
        "and the mission text; returns the task state, output text and "
        "artifact metadata."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "peer": {
                "type": "string",
                "description": "Peer name as configured in a2a.peers",
            },
            "mission": {
                "type": "string",
                "description": "Natural-language instruction for the remote agent",
            },
            "session_id": {
                "type": "string",
                "description": (
                    "Optional session ID; reused as the A2A message_id for "
                    "deduplication / multi-turn correlation"
                ),
            },
            "stream": {
                "type": "boolean",
                "description": "If true, collect SSE events instead of waiting",
                "default": False,
            },
            "push_callback_url": {
                "type": "string",
                "description": (
                    "Optional webhook URL the remote A2A agent should POST to "
                    "when the task completes asynchronously"
                ),
            },
        },
        "required": ["peer", "mission"],
    }
    tool_approval_risk_level = ApprovalRiskLevel.MEDIUM
    tool_supports_parallelism = True

    def __init__(self, runtime: A2aRuntime) -> None:
        self._runtime = runtime

    async def _execute(self, **params: Any) -> dict[str, Any]:
        peer_name = str(params["peer"])
        mission = str(params["mission"])
        session_id = params.get("session_id")
        stream = bool(params.get("stream", False))
        push_url = params.get("push_callback_url")
        push = None
        if push_url:
            from taskforce.core.domain.a2a import A2aPushConfig

            push = A2aPushConfig(url=str(push_url))

        peer = self._runtime.peers.get(peer_name)
        if peer is None:
            return tool_error_payload(
                ToolError(
                    f"Unknown A2A peer: {peer_name!r}",
                    details={"peer": peer_name},
                )
            )

        try:
            handle = await self._runtime.call(
                peer.name,
                mission,
                session_id=session_id,
                stream=stream,
                push=push,
            )
            state_value = handle.state.value
            needs_user_input = state_value == "input-required"
            needs_auth = state_value == "auth-required"
            return {
                "success": state_value in ("completed", "input-required", "auth-required"),
                "peer": handle.peer,
                "task_id": handle.task_id,
                "state": state_value,
                "needs_user_input": needs_user_input,
                "needs_auth": needs_auth,
                "resume_hint": (
                    f"Call call_a2a_agent again with session_id={handle.task_id!r} "
                    f"and the user's reply as mission to continue."
                    if needs_user_input
                    else None
                ),
                "stream": stream,
                "output_text": handle.output_text,
                "output_artifacts": [
                    {
                        "name": a.name,
                        "mime_type": a.mime_type,
                        "path": a.path,
                        "size": a.size,
                        "description": a.description,
                    }
                    for a in handle.artifacts
                ],
            }
        except Exception as exc:  # pragma: no cover - exercised via mock failure
            logger.warning("a2a.tool.call_failed", peer=peer_name, error=str(exc))
            return tool_error_payload(
                ToolError(
                    f"A2A call to {peer_name!r} failed: {exc}",
                    details={"peer": peer_name, "cause": type(exc).__name__},
                )
            )
