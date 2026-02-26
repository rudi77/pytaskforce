"""
Ask User Tool

Allows the agent to request missing information from a human.

Supports two modes:
- **Default (no channel):** Asks the direct session user (CLI, chat, etc.)
  and pauses execution until they respond.
- **Channel-targeted (channel + recipient_id):** Sends the question to a
  specific person on a specific communication channel (Telegram, Teams, …)
  and pauses until that person responds.
"""

from typing import Any

from taskforce.infrastructure.tools.base_tool import BaseTool


class AskUserTool(BaseTool):
    """Model-invoked prompt to request missing info from a human.

    When ``channel`` and ``recipient_id`` are provided the question is
    routed to an external communication channel (e.g. Telegram) and the
    agent waits for that person's reply.  Otherwise the question goes to
    the current session user (CLI prompt, gateway chat, etc.).
    """

    tool_name = "ask_user"
    tool_description = (
        "Ask a person for missing information needed to proceed. "
        "By default asks the current session user. "
        "Optionally specify 'channel' and 'recipient_id' to ask a specific "
        "person on a specific communication channel (e.g. Telegram, Teams)."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "One clear question to ask the person",
            },
            "missing": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of missing information items",
            },
            "channel": {
                "type": "string",
                "description": (
                    "Target communication channel (e.g. 'telegram', 'teams', "
                    "'slack'). If omitted, asks the current session user."
                ),
            },
            "recipient_id": {
                "type": "string",
                "description": (
                    "User ID of the person to ask on the target channel. "
                    "Required when 'channel' is specified."
                ),
            },
        },
        "required": ["question"],
    }
    tool_requires_approval = False
    tool_supports_parallelism = False

    def get_approval_preview(self, **kwargs: Any) -> str:
        question = kwargs.get("question", "")
        channel = kwargs.get("channel")
        recipient = kwargs.get("recipient_id")
        if channel and recipient:
            return (
                f"Tool: {self.name}\nOperation: Ask user on {channel}\n"
                f"Recipient: {recipient}\nQuestion: {question}"
            )
        return f"Tool: {self.name}\nOperation: Ask user\nQuestion: {question}"

    async def _execute(
        self,
        question: str = "",
        missing: list[str] | None = None,
        channel: str | None = None,
        recipient_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Ask a person for missing information.

        Note: The actual pause/resume and channel routing are handled by
        ``_handle_ask_user`` in the planning helpers layer.  This method
        just returns the structured payload.

        Args:
            question: One clear question to ask.
            missing: Optional list of missing information items.
            channel: Optional target channel for the question.
            recipient_id: Optional recipient on the target channel.

        Returns:
            Dictionary with the question, missing items, and channel info.
        """
        result: dict[str, Any] = {
            "success": True,
            "question": question,
            "missing": missing or [],
        }
        if channel:
            result["channel"] = channel
        if recipient_id:
            result["recipient_id"] = recipient_id
        return result
