"""
Ask User Tool

Allows the agent to request missing information from the user.
Migrated from Agent V2 with full preservation of functionality.
"""

from typing import Any, Dict, List, Optional

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class AskUserTool(ToolProtocol):
    """Model-invoked prompt to request missing info from a human."""

    @property
    def name(self) -> str:
        return "ask_user"

    @property
    def description(self) -> str:
        return "Ask the user for missing info to proceed. Returns a structured question payload."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
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

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        question = kwargs.get("question", "")
        return f"Tool: {self.name}\nOperation: Ask user\nQuestion: {question}"

    async def execute(
        self, question: str, missing: Optional[List[str]] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        Ask the user for missing information.

        Args:
            question: One clear question to ask the user
            missing: Optional list of missing information items

        Returns:
            Dictionary with:
            - success: True (always succeeds)
            - question: The question to ask
            - missing: List of missing information items
        """
        return {"success": True, "question": question, "missing": missing or []}

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "question" not in kwargs:
            return False, "Missing required parameter: question"
        if not isinstance(kwargs["question"], str):
            return False, "Parameter 'question' must be a string"
        return True, None

