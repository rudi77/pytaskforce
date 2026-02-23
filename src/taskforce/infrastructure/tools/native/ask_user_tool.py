"""
Ask User Tool

Allows the agent to request missing information from the user.
Migrated from Agent V2 with full preservation of functionality.
"""

from typing import Any

from taskforce.infrastructure.tools.base_tool import BaseTool


class AskUserTool(BaseTool):
    """Model-invoked prompt to request missing info from a human."""

    tool_name = "ask_user"
    tool_description = (
        "Ask the user for missing info to proceed. Returns a structured question payload."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "One clear question to ask the user",
            },
            "missing": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of missing information items",
            },
        },
        "required": ["question"],
    }
    tool_requires_approval = False
    tool_supports_parallelism = False

    def get_approval_preview(self, **kwargs: Any) -> str:
        question = kwargs.get("question", "")
        return f"Tool: {self.name}\nOperation: Ask user\nQuestion: {question}"

    async def _execute(
        self, question: str = "", missing: list[str] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """Ask the user for missing information.

        Args:
            question: One clear question to ask the user.
            missing: Optional list of missing information items.

        Returns:
            Dictionary with the question and missing information items.
        """
        return {"success": True, "question": question, "missing": missing or []}
