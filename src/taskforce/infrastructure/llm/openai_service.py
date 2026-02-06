"""
Backward-compatibility module.

OpenAIService is now an alias for LiteLLMService, which provides
provider-agnostic LLM access via LiteLLM.

All new code should import from litellm_service directly:
    from taskforce.infrastructure.llm.litellm_service import LiteLLMService
"""

from taskforce.infrastructure.llm.litellm_service import LiteLLMService

# Backward-compatible alias
OpenAIService = LiteLLMService

__all__ = ["OpenAIService"]
