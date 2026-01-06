from typing import Any, Callable, Dict

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class OutputFilteringTool:
    """
    A Decorator that wraps any ToolProtocol compliant tool.
    It executes the original tool, then applies a filter function to the output
    before returning it to the agent.
    """

    def __init__(
        self,
        original_tool: ToolProtocol,
        filter_func: Callable[[Dict[str, Any]], Dict[str, Any]],
    ):
        self._original = original_tool
        self._filter_func = filter_func
        self._logger = structlog.get_logger().bind(tool=original_tool.name)

    # Delegate static attributes to the original tool
    @property
    def name(self) -> str:
        return self._original.name

    @property
    def description(self) -> str:
        return self._original.description

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return self._original.parameters_schema

    @property
    def requires_approval(self) -> bool:
        return self._original.requires_approval

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return self._original.approval_risk_level

    @property
    def supports_parallelism(self) -> bool:
        return getattr(self._original, "supports_parallelism", False)

    def get_approval_preview(self, **kwargs: Any) -> str:
        return self._original.get_approval_preview(**kwargs)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        return self._original.validate_params(**kwargs)

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        # 1. Execute the real MCP tool
        raw_result = await self._original.execute(**kwargs)

        # 2. Filter the result immediately (before it hits Agent memory)
        if not isinstance(raw_result, dict):
            tool_error = ToolError(
                f"{self.name} returned non-dict output",
                tool_name=self.name,
                details={"result_type": type(raw_result).__name__},
            )
            self._logger.error("tool_output_invalid", error=str(tool_error))
            return tool_error_payload(tool_error)

        try:
            return self._filter_func(raw_result)
        except Exception as exc:
            tool_error = ToolError(
                f"{self.name} output filter failed: {exc}",
                tool_name=self.name,
                details={"filter": getattr(self._filter_func, "__name__", "unknown")},
            )
            self._logger.error("tool_output_filter_failed", error=str(tool_error))
            return tool_error_payload(tool_error, extra={"raw_result": raw_result})
