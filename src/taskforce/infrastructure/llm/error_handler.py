"""
LLM Error Handler

Provides error parsing and troubleshooting guidance for LLM API errors,
with special support for Azure OpenAI error scenarios.
"""

import re
from typing import Any


class LLMErrorHandler:
    """
    Handler for parsing and providing guidance on LLM API errors.

    Supports both OpenAI and Azure OpenAI error scenarios with
    actionable troubleshooting recommendations.
    """

    def __init__(self, provider_config: dict[str, Any] | None = None) -> None:
        """
        Initialize the error handler.

        Args:
            provider_config: Optional provider configuration for context-aware hints
        """
        self._provider_config = provider_config or {}

    def parse_error(self, error: Exception) -> dict[str, Any]:
        """
        Parse an LLM API error and extract actionable information.

        Common error scenarios and troubleshooting:

        1. DeploymentNotFound / ResourceNotFound:
           - Cause: Deployment name doesn't exist or is misspelled
           - Fix: Verify deployment name matches Azure Portal configuration

        2. InvalidApiVersion / UnsupportedApiVersion:
           - Cause: API version not supported by endpoint
           - Fix: Update api_version to a supported version

        3. AuthenticationError / InvalidApiKey:
           - Cause: API key is invalid, expired, or missing
           - Fix: Regenerate API key and update environment variable

        4. RateLimitError / TooManyRequests:
           - Cause: Exceeded rate limit or quota
           - Fix: Wait and retry, or increase capacity

        Args:
            error: Exception raised by LLM API

        Returns:
            Dict with extracted error information and troubleshooting guidance
        """
        error_msg = str(error)
        error_type = type(error).__name__

        parsed_info = {
            "error_type": error_type,
            "error_message": error_msg,
            "provider": self._detect_provider(error_msg),
        }

        # Extract deployment name if present
        self._extract_deployment_info(error_msg, parsed_info)

        # Extract API version if present
        self._extract_api_version_info(error_msg, parsed_info)

        # Extract endpoint if present
        self._extract_endpoint_info(error_msg, parsed_info)

        # Authentication errors
        if self._is_auth_error(error_msg):
            self._add_auth_hint(parsed_info)

        # Rate limit errors
        if self._is_rate_limit_error(error_msg):
            parsed_info["hint"] = (
                "Rate limit exceeded. Wait and retry, or increase deployment capacity "
                "in Azure Portal → OpenAI Resource → Quotas"
            )

        return parsed_info

    def _detect_provider(self, error_msg: str) -> str:
        """Detect which provider the error is from."""
        if "azure" in error_msg.lower():
            return "azure"
        if "openai" in error_msg.lower():
            return "openai"
        return "unknown"

    def _extract_deployment_info(
        self, error_msg: str, parsed_info: dict[str, Any]
    ) -> None:
        """Extract deployment name from error message if present."""
        if "deployment" not in error_msg.lower():
            return

        deployment_match = re.search(
            r"deployment[:\s]+['\"]?([a-zA-Z0-9\-_]+)['\"]?",
            error_msg,
            re.IGNORECASE,
        )
        if deployment_match:
            deployment_name = deployment_match.group(1)
            parsed_info["deployment_name"] = deployment_name
            parsed_info["hint"] = (
                f"Deployment '{deployment_name}' not found. "
                "Check Azure Portal → OpenAI Resource → Model deployments"
            )

    def _extract_api_version_info(
        self, error_msg: str, parsed_info: dict[str, Any]
    ) -> None:
        """Extract API version from error message if present."""
        if "api" not in error_msg.lower() or "version" not in error_msg.lower():
            return

        api_version_match = re.search(
            r"version\s+['\"]([0-9]{4}-[0-9]{2}-[0-9]{2}[a-z\-]*)['\"]",
            error_msg,
            re.IGNORECASE,
        )
        if api_version_match:
            version = api_version_match.group(1)
            parsed_info["api_version"] = version
            parsed_info["hint"] = (
                f"API version '{version}' may not be supported. "
                "Try '2024-02-15-preview' or check Azure OpenAI documentation"
            )

    def _extract_endpoint_info(
        self, error_msg: str, parsed_info: dict[str, Any]
    ) -> None:
        """Extract endpoint URL from error message if present."""
        if "endpoint" not in error_msg.lower() and "https://" not in error_msg:
            return

        endpoint_match = re.search(r"https://[a-zA-Z0-9\-\.]+", error_msg)
        if endpoint_match:
            endpoint = endpoint_match.group(0)
            parsed_info["endpoint_url"] = endpoint
            parsed_info["hint"] = (
                f"Check endpoint URL '{endpoint}' in Azure Portal → "
                "OpenAI Resource → Keys and Endpoint"
            )

    def _is_auth_error(self, error_msg: str) -> bool:
        """Check if error is an authentication error."""
        keywords = ["auth", "authentication", "api key", "unauthorized"]
        return any(keyword in error_msg.lower() for keyword in keywords)

    def _is_rate_limit_error(self, error_msg: str) -> bool:
        """Check if error is a rate limit error."""
        keywords = ["rate limit", "quota", "too many requests"]
        return any(keyword in error_msg.lower() for keyword in keywords)

    def _add_auth_hint(self, parsed_info: dict[str, Any]) -> None:
        """Add authentication error hint."""
        azure_config = self._provider_config.get("azure", {})
        api_key_env = azure_config.get("api_key_env", "AZURE_OPENAI_API_KEY")
        parsed_info["hint"] = (
            f"Authentication failed. Check that environment variable '{api_key_env}' "
            "is set with a valid Azure OpenAI API key"
        )

    def should_retry(self, error: Exception) -> bool:
        """
        Determine if an error is retryable.

        Args:
            error: The exception to check

        Returns:
            True if the error is likely transient and can be retried
        """
        error_msg = str(error).lower()

        # Retryable errors
        retryable_keywords = [
            "rate limit",
            "timeout",
            "connection",
            "temporary",
            "overloaded",
            "503",
            "502",
            "429",
        ]

        # Non-retryable errors
        non_retryable_keywords = [
            "invalid api key",
            "authentication",
            "not found",
            "invalid model",
            "invalid request",
        ]

        # Check non-retryable first
        if any(keyword in error_msg for keyword in non_retryable_keywords):
            return False

        # Check retryable
        return any(keyword in error_msg for keyword in retryable_keywords)
