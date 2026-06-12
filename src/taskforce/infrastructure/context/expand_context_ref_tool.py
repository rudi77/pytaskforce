"""Native tool that resolves ctxman page faults (expand_context_ref).

ctxman externalizes large/old segments and leaves a summary plus segment
id in the rendered context. The LLM calls this tool to retrieve the full
content; the adapter fetches it via ``GET /v1/sessions/{sid}/refs/{id}``.

Registered by the factory only when the ctxman backend is active. The
context-manager reference is late-bound after agent construction (same
pattern as activate_skill_tool).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol

if TYPE_CHECKING:
    from taskforce.infrastructure.context.ctxman_context_manager import (
        CtxmanContextManager,
    )


class ExpandContextRefTool(ToolProtocol):
    """Retrieve an externalized context segment by its segment id."""

    def __init__(self) -> None:
        self._context_manager: CtxmanContextManager | None = None

    def set_context_manager_ref(self, context_manager: Any) -> None:
        """Late-bind the ctxman context manager after agent construction."""
        self._context_manager = context_manager

    @property
    def name(self) -> str:
        return "expand_context_ref"

    @property
    def description(self) -> str:
        return (
            "Retrieve the full content of an externalized context segment. "
            "Use when the conversation shows a summarized/elided segment "
            "with a segment_id and you need the original content."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "segment_id": {
                    "type": "string",
                    "description": "The id of the externalized context segment",
                },
            },
            "required": ["segment_id"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        segment_id = kwargs.get("segment_id", "")
        return f"Tool: {self.name}\nOperation: Expand context ref\nSegment: {segment_id}"

    async def execute(self, segment_id: str, **kwargs: Any) -> dict[str, Any]:
        if self._context_manager is None:
            return {
                "success": False,
                "error": "expand_context_ref is not bound to a ctxman context manager",
            }
        return await self._context_manager.expand_ref(segment_id)
