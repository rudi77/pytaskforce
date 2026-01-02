from typing import Any, Callable, Dict

from taskforce.core.domain.errors import ToolError
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol

class OutputFilteringTool:
    """
    A Decorator that wraps any ToolProtocol compliant tool.
    It executes the original tool, then applies a filter function to the output
    before returning it to the agent.
    """
    def __init__(self, original_tool: ToolProtocol, filter_func: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self._original = original_tool
        self._filter_func = filter_func

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

    def get_approval_preview(self, **kwargs: Any) -> str:
        return self._original.get_approval_preview(**kwargs)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        return self._original.validate_params(**kwargs)

    async def execute(self, **kwargs) -> Dict[str, Any]:
        # 1. Execute the real MCP tool
        raw_result = await self._original.execute(**kwargs)
        
        # 2. Filter the result immediately (before it hits Agent memory)
        try:
            return self._filter_func(raw_result)
        except Exception as e:
            tool_error = ToolError(
                f"{self.name} output filter failed: {e}",
                tool_name=self.name,
                details={"filter": getattr(self._filter_func, "__name__", "unknown")},
            )
            # Fallback: If filtering fails, return raw result but log warning
            # (You might want to inject a logger here)
            raw_result.setdefault("filter_errors", []).append(str(tool_error))
            return raw_result
