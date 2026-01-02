"""
LLM Tool

Generic LLM tool for natural language text generation.
Migrated from Agent V2 with adaptation for Taskforce LLM service integration.
"""

from typing import Any, Dict, Optional

import structlog

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class LLMTool(ToolProtocol):
    """Generic LLM tool for natural language text generation using LLM service."""

    def __init__(self, llm_service: Any, model_alias: str = "main"):
        """
        Initialize LLMTool with LLM service.

        Args:
            llm_service: The centralized LLM service (implements LLMProviderProtocol)
            model_alias: Model alias from config (default: "main")
        """
        self.llm_service = llm_service
        self.model_alias = model_alias
        self.logger = structlog.get_logger()

    @property
    def name(self) -> str:
        return "llm_generate"

    @property
    def description(self) -> str:
        return (
            "Use the LLM to generate natural language text based on a prompt. "
            "Useful for: formulating user responses, summarizing information, "
            "formatting data, translating content, creative writing."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """Override to provide detailed parameter descriptions."""
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt/instruction for the LLM",
                },
                "context": {
                    "type": "object",
                    "description": "Structured data to include as context (e.g., search results, document lists)",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Maximum response length in tokens (default: 500)",
                },
                "temperature": {
                    "type": "number",
                    "description": "Creativity control from 0.0 (deterministic) to 1.0 (creative) (default: 0.7)",
                },
            },
            "required": ["prompt"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        prompt = kwargs.get("prompt", "")
        prompt_preview = prompt[:100] + "..." if len(prompt) > 100 else prompt
        return f"Tool: {self.name}\nOperation: Generate text\nPrompt: {prompt_preview}"

    async def execute(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute LLM text generation using LLM service.

        Args:
            prompt: The prompt/instruction for the LLM
            context: Optional structured data to include as context
            max_tokens: Maximum response length (default: 500)
            temperature: Creativity control 0.0-1.0 (default: 0.7)

        Returns:
            Dictionary with:
            - success: True if generation succeeded, False otherwise
            - generated_text: The generated text (if successful)
            - tokens_used: Total tokens consumed
            - prompt_tokens: Tokens in the prompt
            - completion_tokens: Tokens in the completion
            - error: Error message (if failed)
            - type: Error type (if failed)
            - hints: Suggestions for fixing errors (if failed)
        """
        self.logger.info(
            "llm_generate_started",
            tool="llm_generate",
            has_context=context is not None,
        )

        try:
            # Use LLMService.generate() method
            result = await self.llm_service.generate(
                prompt=prompt,
                context=context,
                model=self.model_alias,  # Use configured alias
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )

            # Check if generation succeeded
            if not result.get("success"):
                self.logger.error(
                    "llm_generate_failed",
                    error=result.get("error"),
                    error_type=result.get("error_type"),
                )

                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "type": result.get("error_type", "UnknownError"),
                    "hints": self._get_error_hints(
                        result.get("error_type", ""), result.get("error", "")
                    ),
                }

            # Extract data from successful result
            generated_text = result.get("generated_text") or result.get("content")
            usage = result.get("usage", {})

            self.logger.info(
                "llm_generate_completed",
                tokens_used=usage.get("total_tokens", 0),
                latency_ms=result.get("latency_ms", 0),
            )

            return {
                "success": True,
                "generated_text": generated_text,
                "tokens_used": usage.get("total_tokens", 0),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            }

        except Exception as e:
            # Catch any unexpected errors
            error_type = type(e).__name__
            error_msg = str(e)

            self.logger.error(
                "llm_generate_exception", error_type=error_type, error=error_msg[:200]
            )

            return {
                "success": False,
                "error": error_msg,
                "type": error_type,
                "hints": self._get_error_hints(error_type, error_msg),
            }

    def _get_error_hints(self, error_type: str, error_msg: str) -> list:
        """
        Generate helpful hints based on error type.

        Args:
            error_type: The type of exception
            error_msg: The error message

        Returns:
            List of hint strings
        """
        hints = ["Check LLM configuration", "Verify API credentials"]

        # Token limit errors
        if "token" in error_msg.lower() or "length" in error_msg.lower():
            hints.append("Reduce prompt size or increase max_tokens parameter")

        # Network/timeout errors
        if error_type in ["TimeoutError", "ConnectionError", "ClientError"]:
            hints.append("Retry the request")
            hints.append("Check network connectivity")

        # Authentication errors
        if "auth" in error_msg.lower() or "api key" in error_msg.lower():
            hints.append("Verify API key is set correctly")

        return hints

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "prompt" not in kwargs:
            return False, "Missing required parameter: prompt"
        if not isinstance(kwargs["prompt"], str):
            return False, "Parameter 'prompt' must be a string"
        return True, None

