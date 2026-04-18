"""Tool that delegates a mission to a remote ACP agent.

Acts like ``AgentTool`` but targets an external ACP peer instead of
spawning a local sub-agent via ``AgentFactory``. Useful for federating
capabilities across Taskforce instances (or with any ACP-compliant agent
framework such as BeeAI).
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.acp.runtime import AcpRuntime
from taskforce.infrastructure.tools.base_tool import BaseTool

logger = structlog.get_logger(__name__)


class AcpAgentTool(BaseTool):
    """Call a remote ACP agent by peer name."""

    tool_name = "call_acp_agent"
    tool_description = (
        "Delegate a mission to a remote agent exposed via the Agent "
        "Communication Protocol (ACP). Provide the configured peer name "
        "and the mission text; returns the remote agent's final response."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "peer": {
                "type": "string",
                "description": "Peer name as configured in acp.peers",
            },
            "mission": {
                "type": "string",
                "description": "Natural-language instruction for the remote agent",
            },
            "session_id": {
                "type": "string",
                "description": "Optional session ID for multi-turn conversations",
            },
            "stream": {
                "type": "boolean",
                "description": "If true, collect streaming events instead of waiting",
                "default": False,
            },
        },
        "required": ["peer", "mission"],
    }
    tool_approval_risk_level = ApprovalRiskLevel.MEDIUM
    tool_supports_parallelism = True

    def __init__(self, runtime: AcpRuntime) -> None:
        self._runtime = runtime

    async def _execute(self, **params: Any) -> dict[str, Any]:
        peer_name = str(params["peer"])
        mission = str(params["mission"])
        session_id = params.get("session_id")
        stream = bool(params.get("stream", False))

        peer = self._runtime.peers.get(peer_name)
        if peer is None:
            return tool_error_payload(
                ToolError(
                    f"Unknown ACP peer: {peer_name!r}",
                    details={"peer": peer_name},
                )
            )

        try:
            if stream:
                events: list[dict[str, Any]] = []
                async for event in self._runtime.client.run_stream(
                    peer, mission, session_id=session_id
                ):
                    events.append(event)
                final_text = _last_text(events)
                return {
                    "success": True,
                    "peer": peer.name,
                    "agent": peer.agent,
                    "stream": True,
                    "events": events,
                    "output_text": final_text,
                }
            result = await self._runtime.client.run_sync(peer, mission, session_id=session_id)
            return {
                "success": True,
                "peer": peer.name,
                "agent": peer.agent,
                "run_id": result.get("run_id"),
                "status": result.get("status"),
                "output_text": result.get("output_text", ""),
            }
        except Exception as exc:  # pragma: no cover - exercised via mock failure
            logger.warning("acp.tool.call_failed", peer=peer_name, error=str(exc))
            return tool_error_payload(
                ToolError(
                    f"ACP call to {peer_name!r} failed: {exc}",
                    details={"peer": peer_name, "cause": type(exc).__name__},
                )
            )


def _last_text(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        raw = event.get("raw")
        if isinstance(raw, dict):
            text = raw.get("output_text")
            if isinstance(text, str) and text:
                return text
    return ""
