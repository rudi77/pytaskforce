"""LLM provider implementations."""

from taskforce.infrastructure.llm.litellm_service import LiteLLMService

# Backward-compatible alias: existing code importing OpenAIService will
# get the new LiteLLMService transparently.
OpenAIService = LiteLLMService

__all__ = ["LiteLLMService", "OpenAIService"]
