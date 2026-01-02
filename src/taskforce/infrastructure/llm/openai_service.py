"""
LLM Service for centralized LLM interactions.

This module provides a centralized service for all LLM interactions with support
for model-aware parameter mapping, retry logic, and configuration management.

Supports multiple LLM providers:
- OpenAI: Direct OpenAI API access (default)
- Azure OpenAI: Azure-hosted OpenAI models with deployment-based routing

Key features:
- Model alias resolution with deployment mapping for Azure
- Automatic parameter mapping between GPT-4 and GPT-5 parameter sets
- Configurable retry logic with exponential backoff
- Structured logging with provider-specific context
- Azure-specific error parsing and troubleshooting guidance
- Streaming support for real-time token delivery

For Azure OpenAI setup instructions, see docs/azure-openai-setup.md
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ============================================================================
# CRITICAL: Suppress LiteLLM logging BEFORE importing litellm
# ============================================================================
os.environ["LITELLM_LOGGING"] = "off"
os.environ["LITELLM_LOG_LEVEL"] = "ERROR"
os.environ["HTTPX_LOG_LEVEL"] = "warning"

# Pre-silence loggers before litellm import
for _ln in ["LiteLLM", "litellm", "httpcore", "httpx", "aiohttp", "openai"]:
    logging.getLogger(_ln).setLevel(logging.ERROR)

import aiofiles  # noqa: E402
import litellm  # noqa: E402
import structlog  # noqa: E402
import yaml  # noqa: E402

# After import: ensure litellm's internal flags are off
litellm.set_verbose = False
litellm.suppress_debug_info = True

from taskforce.core.interfaces.llm import LLMProviderProtocol  # noqa: E402


@dataclass
class RetryPolicy:
    """Retry policy configuration."""

    max_attempts: int = 3
    backoff_multiplier: float = 2.0
    timeout: int = 30
    retry_on_errors: list[str] = field(default_factory=list)


class OpenAIService(LLMProviderProtocol):
    """
    Centralized service for LLM interactions with model-aware parameter mapping.

    Supports both GPT-4 (traditional parameters) and GPT-5 (reasoning parameters).
    Provides unified interface for all LLM calls with retry logic and error handling.
    Implements LLMProviderProtocol for dependency injection.
    """

    def __init__(self, config_path: str = "configs/llm_config.yaml"):
        """
        Initialize OpenAIService with configuration.

        Args:
            config_path: Path to YAML configuration file

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        self.logger = structlog.get_logger()
        self._load_config(config_path)
        self._initialize_provider()

        self.logger.info(
            "llm_service_initialized",
            default_model=self.default_model,
            model_aliases=list(self.models.keys()),
        )

    def _load_config(self, config_path: str) -> None:
        """
        Load and validate configuration from YAML file.

        Args:
            config_path: Path to YAML configuration file

        Raises:
            FileNotFoundError: If config file doesn't exist
        """
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"LLM config not found: {config_path}")

        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Validate config structure
        if config is None:
            raise ValueError(f"Config file is empty or invalid: {config_path}")

        # Extract configuration sections
        self.default_model = config.get("default_model", "main")
        self.models = config.get("models", {})
        self.model_params = config.get("model_params", {})
        self.default_params = config.get("default_params", {})

        # Validate essential config
        if not self.models:
            raise ValueError("Config must define at least one model in 'models' section")

        # Retry policy
        retry_config = config.get("retry_policy", {})
        self.retry_policy = RetryPolicy(
            max_attempts=retry_config.get("max_attempts", 3),
            backoff_multiplier=retry_config.get("backoff_multiplier", 2.0),
            timeout=retry_config.get("timeout", 30),
            retry_on_errors=retry_config.get("retry_on_errors", []),
        )

        # Logging preferences
        self.logging_config = config.get("logging", {})

        # Tracing configuration
        self.tracing_config = config.get("tracing", {})

        # Provider configuration
        self.provider_config = config.get("providers", {})

        # Validate Azure configuration if enabled
        self._validate_azure_config()

    def _validate_azure_config(self) -> None:
        """
        Validate Azure configuration if enabled.
        
        Raises:
            ValueError: If Azure is enabled but required fields are missing
        """
        azure_config = self.provider_config.get("azure", {})

        # Skip validation if Azure is not enabled or section doesn't exist
        if not azure_config or not azure_config.get("enabled", False):
            return

        # Required fields when Azure is enabled
        required_fields = ["api_key_env", "endpoint_url_env", "api_version", "deployment_mapping"]
        missing_fields = []

        for field in required_fields:
            if field not in azure_config or azure_config[field] is None:
                missing_fields.append(field)

        if missing_fields:
            raise ValueError(
                f"Azure provider is enabled but missing required fields: {', '.join(missing_fields)}. "
                "Please provide all required fields or set enabled: false."
            )

        # Validate deployment_mapping is a dictionary
        if not isinstance(azure_config["deployment_mapping"], dict):
            raise ValueError(
                "Azure deployment_mapping must be a dictionary mapping model aliases to deployment names"
            )

        self.logger.info(
            "azure_config_validated",
            endpoint_env=azure_config["api_key_env"],
            api_version=azure_config["api_version"],
            deployment_count=len(azure_config["deployment_mapping"]),
        )

    def _initialize_provider(self) -> None:
        """Initialize LLM provider with API keys from environment."""
        # Check if Azure is enabled
        azure_config = self.provider_config.get("azure", {})
        if azure_config.get("enabled", False):
            self._initialize_azure_provider()
            self.logger.info(
                "provider_selected",
                provider="azure",
                api_version=azure_config.get("api_version"),
            )
        else:
            # Log Azure status (disabled)
            if azure_config:
                self.logger.info(
                    "azure_provider_status",
                    provider="azure",
                    enabled=False,
                    reason="Azure provider is disabled in configuration",
                )

            # Default to OpenAI
            openai_config = self.provider_config.get("openai", {})

            # Load API key from environment
            api_key_env = openai_config.get("api_key_env", "OPENAI_API_KEY")
            api_key = os.getenv(api_key_env)

            if not api_key:
                self.logger.warning(
                    "openai_api_key_missing",
                    env_var=api_key_env,
                    hint="Set environment variable for API access",
                )

            self.logger.info("provider_selected", provider="openai")

    def _initialize_azure_provider(self) -> None:
        """
        Initialize Azure OpenAI provider with credentials from environment.
        
        This method sets up Azure OpenAI connectivity by reading credentials from
        environment variables and configuring LiteLLM to route requests through
        Azure's API endpoints with deployment-based model mapping.
        
        Setup Requirements:
        -------------------
        1. Azure OpenAI Resource: Create an Azure OpenAI resource in Azure Portal
        2. Deploy Models: Deploy desired models (e.g., GPT-4) in Azure Portal
        3. Environment Variables:
           - AZURE_OPENAI_API_KEY: API key from Azure Portal → Keys and Endpoint
           - AZURE_OPENAI_ENDPOINT: Full endpoint URL (e.g., https://your-resource.openai.azure.com/)
        4. Configuration: Enable Azure in llm_config.yaml and map model aliases to deployment names
        
        Configuration Format:
        ---------------------
        providers:
          azure:
            enabled: true
            api_key_env: "AZURE_OPENAI_API_KEY"
            endpoint_url_env: "AZURE_OPENAI_ENDPOINT"
            api_version: "2024-02-15-preview"
            deployment_mapping:
              main: "my-gpt4-deployment"
              fast: "my-gpt4-mini-deployment"
        
        Validation:
        -----------
        - Validates endpoint URL uses HTTPS protocol
        - Warns if endpoint doesn't contain expected Azure OpenAI domain patterns
        - Checks for presence of required credentials (non-blocking warnings)
        - Sets LiteLLM environment variables for Azure OpenAI routing
        
        Raises:
            ValueError: If endpoint URL format is invalid (non-HTTPS)
        
        See Also:
            docs/azure-openai-setup.md for complete setup guide
        """
        azure_config = self.provider_config.get("azure", {})

        # Get environment variable names from config
        api_key_env = azure_config.get("api_key_env", "AZURE_OPENAI_API_KEY")
        endpoint_env = azure_config.get("endpoint_url_env", "AZURE_OPENAI_ENDPOINT")

        # Read from environment
        self.azure_api_key = os.getenv(api_key_env)
        self.azure_endpoint = os.getenv(endpoint_env)
        self.azure_api_version = azure_config.get("api_version")

        # Warn if credentials are missing
        if not self.azure_api_key:
            self.logger.warning(
                "azure_api_key_missing",
                env_var=api_key_env,
                hint="Set environment variable for Azure OpenAI API access",
            )

        if not self.azure_endpoint:
            self.logger.warning(
                "azure_endpoint_missing",
                env_var=endpoint_env,
                hint="Set environment variable for Azure OpenAI endpoint URL",
            )

        # Validate endpoint URL format if provided
        if self.azure_endpoint:
            # Azure endpoint should be HTTPS and contain 'openai.azure.com'
            if not self.azure_endpoint.startswith("https://"):
                raise ValueError(
                    f"Azure endpoint must use HTTPS protocol: {self.azure_endpoint}"
                )

            if "openai.azure.com" not in self.azure_endpoint and "api.cognitive.microsoft.com" not in self.azure_endpoint:
                self.logger.warning(
                    "azure_endpoint_format_unusual",
                    endpoint=self.azure_endpoint,
                    hint="Expected endpoint to contain 'openai.azure.com' or 'api.cognitive.microsoft.com'",
                )

        # Set LiteLLM environment variables for Azure OpenAI
        # LiteLLM uses these for Azure OpenAI requests
        if self.azure_api_key:
            os.environ["AZURE_API_KEY"] = self.azure_api_key

        if self.azure_endpoint:
            os.environ["AZURE_API_BASE"] = self.azure_endpoint

        if self.azure_api_version:
            os.environ["AZURE_API_VERSION"] = self.azure_api_version

        # Get deployment count for status logging
        deployment_count = len(azure_config.get("deployment_mapping", {}))
        configured_deployments = list(azure_config.get("deployment_mapping", {}).keys())

        self.logger.info(
            "azure_provider_initialized",
            provider="azure",
            enabled=True,
            endpoint=self.azure_endpoint,
            api_version=self.azure_api_version,
            api_key_set=bool(self.azure_api_key),
            deployment_count=deployment_count,
            configured_deployments=configured_deployments,
        )

    def _resolve_model(self, model_alias: str | None) -> str:
        """
        Resolve model alias to actual model name or Azure deployment name.
        
        When Azure provider is enabled:
        - Resolves model alias through Azure deployment_mapping
        - Falls back to OpenAI model name if alias not in deployment_mapping
        - Raises ValueError if Azure enabled and alias has no deployment mapping (strict mode)
        
        When Azure provider is disabled:
        - Uses traditional OpenAI model name resolution
        
        Args:
            model_alias: Model alias or None (uses default)
        
        Returns:
            Actual model name (OpenAI) or deployment name (Azure)
        
        Raises:
            ValueError: If Azure enabled and alias has no deployment mapping
        """
        if model_alias is None:
            model_alias = self.default_model

        # Check if Azure is enabled
        azure_config = self.provider_config.get("azure", {})
        azure_enabled = azure_config.get("enabled", False)

        if azure_enabled:
            # Azure provider: resolve through deployment_mapping
            deployment_mapping = azure_config.get("deployment_mapping", {})

            # First, resolve alias to OpenAI model name
            openai_model = self.models.get(model_alias, model_alias)

            # Check if deployment mapping exists for this alias
            if model_alias in deployment_mapping:
                deployment_name = deployment_mapping[model_alias]

                self.logger.info(
                    "model_resolved",
                    provider="azure",
                    model_alias=model_alias,
                    deployment_name=deployment_name,
                    openai_model=openai_model,
                )

                return f"azure/{deployment_name}"
            else:
                # No deployment mapping for this alias
                # Check if fallback to OpenAI model name is allowed
                # (For now, we'll be strict and raise an error)
                raise ValueError(
                    f"Azure provider is enabled but no deployment mapping found for model alias '{model_alias}'. "
                    f"Please add '{model_alias}' to deployment_mapping in azure provider configuration, "
                    f"or set azure.enabled to false to use OpenAI models."
                )
        else:
            # OpenAI provider: traditional resolution
            resolved_model = self.models.get(model_alias, model_alias)

            self.logger.info(
                "model_resolved",
                provider="openai",
                model_alias=model_alias,
                resolved_model=resolved_model,
            )

            return resolved_model

    def _parse_azure_error(self, error: Exception) -> dict[str, Any]:
        """
        Parse Azure API error and extract actionable information.
        
        Common Azure error scenarios and troubleshooting:
        
        1. DeploymentNotFound / ResourceNotFound:
           - Cause: Deployment name doesn't exist or is misspelled in Azure
           - Fix: Verify deployment name in Azure Portal matches deployment_mapping config
           - Check: Azure Portal → OpenAI Resource → Model deployments
        
        2. InvalidApiVersion / UnsupportedApiVersion:
           - Cause: API version not supported by Azure endpoint
           - Fix: Update api_version in config to supported version (e.g., "2024-02-15-preview")
           - Check: Azure OpenAI API documentation for supported versions
        
        3. AuthenticationError / InvalidApiKey:
           - Cause: API key is invalid, expired, or missing
           - Fix: Regenerate API key in Azure Portal and update environment variable
           - Check: Environment variable AZURE_OPENAI_API_KEY is set correctly
        
        4. InvalidEndpoint / EndpointNotFound:
           - Cause: Endpoint URL is incorrect or resource doesn't exist
           - Fix: Verify endpoint URL matches Azure resource endpoint
           - Check: Azure Portal → OpenAI Resource → Keys and Endpoint
        
        5. RateLimitError / TooManyRequests:
           - Cause: Exceeded rate limit or quota for deployment
           - Fix: Wait and retry, or increase deployment capacity in Azure
           - Check: Azure Portal → OpenAI Resource → Quotas
        
        Args:
            error: Exception raised by LiteLLM/Azure API
        
        Returns:
            Dict with extracted error information and troubleshooting guidance
        """
        import re

        error_msg = str(error)
        error_type = type(error).__name__

        parsed_info = {
            "error_type": error_type,
            "error_message": error_msg,
            "provider": "azure" if "azure" in error_msg.lower() else "unknown",
        }

        # Extract deployment name if present
        if "deployment" in error_msg.lower():
            # Try to extract deployment name from error message
            deployment_match = re.search(r"deployment[:\s]+['\"]?([a-zA-Z0-9\-_]+)['\"]?", error_msg, re.IGNORECASE)
            if deployment_match:
                parsed_info["deployment_name"] = deployment_match.group(1)
                parsed_info["hint"] = (
                    f"Deployment '{deployment_match.group(1)}' not found. "
                    "Check Azure Portal → OpenAI Resource → Model deployments"
                )

        # Extract API version if present
        if "api" in error_msg.lower() and "version" in error_msg.lower():
            api_version_match = re.search(r"version\s+['\"]([0-9]{4}-[0-9]{2}-[0-9]{2}[a-z\-]*)['\"]", error_msg, re.IGNORECASE)
            if api_version_match:
                parsed_info["api_version"] = api_version_match.group(1)
                parsed_info["hint"] = (
                    f"API version '{api_version_match.group(1)}' may not be supported. "
                    "Try '2024-02-15-preview' or check Azure OpenAI documentation"
                )

        # Extract endpoint if present
        if "endpoint" in error_msg.lower() or "https://" in error_msg:
            endpoint_match = re.search(r"https://[a-zA-Z0-9\-\.]+", error_msg)
            if endpoint_match:
                parsed_info["endpoint_url"] = endpoint_match.group(0)
                parsed_info["hint"] = (
                    f"Check endpoint URL '{endpoint_match.group(0)}' in Azure Portal → "
                    "OpenAI Resource → Keys and Endpoint"
                )

        # Authentication errors
        if any(keyword in error_msg.lower() for keyword in ["auth", "authentication", "api key", "unauthorized"]):
            azure_config = self.provider_config.get("azure", {})
            api_key_env = azure_config.get("api_key_env", "AZURE_OPENAI_API_KEY")
            parsed_info["hint"] = (
                f"Authentication failed. Check that environment variable '{api_key_env}' "
                "is set with a valid Azure OpenAI API key"
            )

        # Rate limit errors
        if any(keyword in error_msg.lower() for keyword in ["rate limit", "quota", "too many requests"]):
            parsed_info["hint"] = (
                "Rate limit exceeded. Wait and retry, or increase deployment capacity "
                "in Azure Portal → OpenAI Resource → Quotas"
            )

        return parsed_info

    async def test_azure_connection(self) -> dict[str, Any]:
        """
        Test Azure OpenAI connection and validate configuration.
        
        This diagnostic method validates:
        - Azure endpoint accessibility
        - API key authentication
        - Deployment availability
        - API version compatibility
        
        Returns:
            Dict with test results:
            - success: bool - overall test result
            - endpoint_reachable: bool - endpoint is accessible
            - authentication_valid: bool - API key is valid
            - deployments_available: List[str] - available deployments tested
            - errors: List[str] - any errors encountered
            - recommendations: List[str] - troubleshooting guidance
        
        Example:
            >>> result = await llm_service.test_azure_connection()
            >>> if not result["success"]:
            ...     print("Issues:", result["errors"])
            ...     print("Try:", result["recommendations"])
        """
        azure_config = self.provider_config.get("azure", {})

        # Check if Azure is enabled
        if not azure_config.get("enabled", False):
            return {
                "success": False,
                "error": "Azure provider is not enabled in configuration",
                "recommendations": ["Set azure.enabled: true in llm_config.yaml"],
            }

        result = {
            "success": True,
            "endpoint_reachable": False,
            "authentication_valid": False,
            "deployments_tested": [],
            "deployments_available": [],
            "errors": [],
            "recommendations": [],
        }

        # Check credentials
        if not self.azure_api_key:
            result["success"] = False
            result["errors"].append(f"Azure API key not found in environment variable '{azure_config.get('api_key_env')}'")
            result["recommendations"].append(f"Set environment variable {azure_config.get('api_key_env')} with your Azure OpenAI API key")

        if not self.azure_endpoint:
            result["success"] = False
            result["errors"].append(f"Azure endpoint not found in environment variable '{azure_config.get('endpoint_url_env')}'")
            result["recommendations"].append(f"Set environment variable {azure_config.get('endpoint_url_env')} with your Azure OpenAI endpoint URL")

        # If credentials missing, return early
        if not self.azure_api_key or not self.azure_endpoint:
            return result

        # Test each configured deployment
        deployment_mapping = azure_config.get("deployment_mapping", {})

        if not deployment_mapping:
            result["success"] = False
            result["errors"].append("No deployments configured in deployment_mapping")
            result["recommendations"].append("Add at least one deployment mapping in azure.deployment_mapping config")
            return result

        # Test a simple completion with each deployment
        test_message = [{"role": "user", "content": "Hello"}]

        for alias, deployment_name in deployment_mapping.items():
            result["deployments_tested"].append(alias)

            try:
                self.logger.info(
                    "testing_azure_deployment",
                    alias=alias,
                    deployment=deployment_name,
                )

                # Attempt a minimal completion
                test_result = await self.complete(
                    messages=test_message,
                    model=alias,
                    max_tokens=5,
                )

                if test_result.get("success"):
                    result["deployments_available"].append(alias)
                    result["endpoint_reachable"] = True
                    result["authentication_valid"] = True

                    self.logger.info(
                        "azure_deployment_test_success",
                        alias=alias,
                        deployment=deployment_name,
                    )
                else:
                    error_msg = test_result.get("error", "Unknown error")
                    result["errors"].append(f"Deployment '{alias}' ({deployment_name}): {error_msg}")

                    # Parse error for guidance
                    parsed = self._parse_azure_error(Exception(error_msg))
                    if "hint" in parsed:
                        result["recommendations"].append(f"{alias}: {parsed['hint']}")

                    self.logger.warning(
                        "azure_deployment_test_failed",
                        alias=alias,
                        deployment=deployment_name,
                        error=error_msg[:200],
                    )

            except Exception as e:
                result["errors"].append(f"Deployment '{alias}' ({deployment_name}): {str(e)}")

                # Parse error for guidance
                parsed = self._parse_azure_error(e)
                if "hint" in parsed:
                    result["recommendations"].append(f"{alias}: {parsed['hint']}")

                self.logger.error(
                    "azure_deployment_test_exception",
                    alias=alias,
                    deployment=deployment_name,
                    error=str(e)[:200],
                )

        # Set overall success based on whether any deployments worked
        if not result["deployments_available"]:
            result["success"] = False
            if not result["recommendations"]:
                result["recommendations"].append(
                    "Check Azure Portal → OpenAI Resource → Model deployments to verify deployment names"
                )

        return result

    def _get_model_parameters(self, model: str) -> dict[str, Any]:
        """
        Get parameters for specific model.

        Args:
            model: Actual model name

        Returns:
            Model-specific parameters or defaults
        """
        # Check for exact model match
        if model in self.model_params:
            return self.model_params[model].copy()

        # Check for model family match (e.g., "gpt-4" matches "gpt-4-turbo")
        for model_key, params in self.model_params.items():
            if model.startswith(model_key):
                return params.copy()

        # Fallback to defaults
        return self.default_params.copy()

    def _map_parameters_for_model(
        self, model: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Map parameters based on model family (GPT-4 vs GPT-5).

        GPT-4 uses traditional parameters: temperature, top_p, max_tokens, etc.
        GPT-5 uses new parameters: effort, reasoning, max_tokens.

        Args:
            model: Actual model name
            params: Input parameters (may contain traditional or new parameters)

        Returns:
            Mapped parameters suitable for the model
        """
        # Detect GPT-5/o1/o3 reasoning models
        # These models don't support traditional parameters like temperature, top_p, etc.
        # Azure OpenAI also doesn't support effort/reasoning_effort parameters
        if "gpt-5" in model.lower() or "o1" in model.lower() or "o3" in model.lower():
            mapped = {}

            # GPT-5 uses max_completion_tokens instead of max_tokens
            if "max_tokens" in params:
                mapped["max_completion_tokens"] = params["max_tokens"]
            if "max_completion_tokens" in params:
                mapped["max_completion_tokens"] = params["max_completion_tokens"]

            # Log ignored parameters for debugging
            ignored = [
                k for k in params.keys()
                if k not in ["max_tokens", "max_completion_tokens"]
            ]
            if ignored and self.logging_config.get("log_parameter_mapping", True):
                self.logger.info(
                    "parameters_ignored_for_reasoning_model",
                    model=model,
                    ignored_params=ignored,
                    hint="GPT-5/o1/o3 models only support max_completion_tokens",
                )

            return mapped
        else:
            # GPT-4 and other models: use traditional parameters
            allowed_params = [
                "temperature",
                "top_p",
                "max_tokens",
                "frequency_penalty",
                "presence_penalty",
                "response_format",
            ]
            filtered = {k: v for k, v in params.items() if k in allowed_params}

            # Ensure response_format is properly formatted for LiteLLM
            # Azure requires response_format as a simple dict, not Pydantic model
            if "response_format" in filtered:
                rf = filtered["response_format"]
                if isinstance(rf, dict):
                    # Ensure it's a clean dict (not a Pydantic model dump)
                    filtered["response_format"] = {"type": rf.get("type", "json_object")}

            return filtered

    async def _trace_interaction(
        self,
        messages: list[dict[str, Any]],
        response_content: str | None,
        model: str,
        token_stats: dict[str, int],
        latency_ms: int,
        success: bool,
        error: str | None = None,
    ) -> None:
        """
        Trace LLM interaction to configured destinations.

        Args:
            messages: Input messages
            response_content: Generated content
            model: Model used
            token_stats: Token usage statistics
            latency_ms: Request latency in milliseconds
            success: Whether the request was successful
            error: Error message if failed
        """
        if not self.tracing_config.get("enabled", False):
            return

        mode = self.tracing_config.get("mode", "file")

        trace_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "model": model,
            "messages": messages,
            "response": response_content,
            "usage": token_stats,
            "latency_ms": latency_ms,
            "success": success,
            "error": error,
        }

        tasks = []
        if mode in ["file", "both"]:
            tasks.append(self._trace_to_file(trace_data))

        if mode in ["phoenix", "both"]:
            tasks.append(self._trace_to_phoenix(trace_data))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _trace_to_file(self, trace_data: dict[str, Any]) -> None:
        """Write trace data to JSONL file."""
        try:
            file_config = self.tracing_config.get("file_config", {})
            file_path = file_config.get("path", "traces/llm_traces.jsonl")

            # Ensure directory exists
            path = Path(file_path)
            if not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(path, mode="a", encoding="utf-8") as f:
                await f.write(json.dumps(trace_data) + "\n")

        except Exception as e:
            self.logger.error("trace_file_write_failed", error=str(e))

    async def _trace_to_phoenix(self, trace_data: dict[str, Any]) -> None:
        """
        Send trace data to Arize Phoenix.

        Note: This implementation checks for the 'phoenix' library availability.
        If not present, it logs a warning.
        """
        try:
            import phoenix as px  # type: ignore # noqa: F401

            # This is a placeholder for manual Phoenix tracing.
            # Since we don't have the library as a dependency, we just check import.
            # Actual implementation would require the library.
            pass

        except ImportError:
            self.logger.warning(
                "phoenix_library_missing",
                hint="Install arize-phoenix to use phoenix tracing",
            )
        except Exception as e:
            self.logger.error("trace_phoenix_failed", error=str(e))

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Perform LLM completion with retry logic and native tool calling support.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model alias or None (uses default)
            tools: Optional list of tool definitions in OpenAI function calling format
            tool_choice: Optional tool choice strategy ("auto", "none", "required", or specific tool)
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Dict with:
            - success: bool
            - content: str | None (if no tool calls)
            - tool_calls: list[dict] | None (if model invoked tools)
            - usage: Dict with token counts
            - error: str (if failed)

        Example:
            >>> result = await llm_service.complete(
            ...     messages=[
            ...         {"role": "system", "content": "You are helpful"},
            ...         {"role": "user", "content": "Hello"}
            ...     ],
            ...     model="main",
            ...     temperature=0.7
            ... )
        """
        # Resolve model and parameters
        actual_model = self._resolve_model(model)
        base_params = self._get_model_parameters(actual_model)

        # Merge with provided kwargs (kwargs override base_params)
        merged_params = {**base_params, **kwargs}

        # Map parameters for model family
        final_params = self._map_parameters_for_model(actual_model, merged_params)

        # Determine provider and display name for logging
        azure_config = self.provider_config.get("azure", {})
        is_azure = azure_config.get("enabled", False)

        if is_azure and actual_model.startswith("azure/"):
            provider = "azure"
            deployment_name = actual_model.replace("azure/", "")
            display_name = deployment_name
        else:
            provider = "openai"
            display_name = actual_model

        # Build LiteLLM call kwargs
        litellm_kwargs = {
            "model": actual_model,
            "messages": messages,
            "timeout": self.retry_policy.timeout,
            "drop_params": True,
            **final_params,
        }

        # Add tools if provided (native tool calling)
        if tools:
            litellm_kwargs["tools"] = tools
            if tool_choice:
                litellm_kwargs["tool_choice"] = tool_choice
            elif tools:
                # Default to "auto" when tools are provided
                litellm_kwargs["tool_choice"] = "auto"

        # Retry logic
        for attempt in range(self.retry_policy.max_attempts):
            try:
                start_time = time.time()

                self.logger.info(
                    "llm_completion_started",
                    provider=provider,
                    model=actual_model,
                    deployment=display_name if is_azure else None,
                    attempt=attempt + 1,
                    message_count=len(messages),
                    tools_count=len(tools) if tools else 0,
                )

                # Call LiteLLM
                response = await litellm.acompletion(**litellm_kwargs)

                # Extract content, tool_calls and usage
                message = response.choices[0].message
                content = message.content

                # Extract tool_calls if present (native tool calling)
                tool_calls_raw = getattr(message, "tool_calls", None)
                tool_calls = None
                if tool_calls_raw:
                    tool_calls = []
                    for tc in tool_calls_raw:
                        tool_calls.append({
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        })

                # For reasoning models (GPT-5, o1, o3), content might be in reasoning_content
                if not content and not tool_calls:
                    reasoning_content = getattr(message, "reasoning_content", None)
                    if reasoning_content:
                        content = reasoning_content
                    elif hasattr(message, "refusal") and message.refusal:
                        content = f"[Model refused: {message.refusal}]"

                usage = getattr(response, "usage", {})

                # Handle both dict and object forms
                if isinstance(usage, dict):
                    token_stats = usage
                else:
                    token_stats = {
                        "total_tokens": getattr(usage, "total_tokens", 0),
                        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(usage, "completion_tokens", 0),
                    }

                latency_ms = int((time.time() - start_time) * 1000)

                # Warn if we have completion tokens but empty content (and no tool calls)
                completion_tokens = token_stats.get("completion_tokens", 0)
                if not content and not tool_calls and completion_tokens > 0:
                    self.logger.warning(
                        "llm_empty_content_with_tokens",
                        model=actual_model,
                        completion_tokens=completion_tokens,
                        hint="Model generated tokens but content is empty. Check for new response format.",
                        message_fields=list(vars(message).keys()) if hasattr(message, "__dict__") else str(type(message)),
                    )

                if self.logging_config.get("log_token_usage", True):
                    self.logger.info(
                        "llm_completion_success",
                        provider=provider,
                        model=actual_model,
                        deployment=display_name if is_azure else None,
                        tokens=token_stats.get("total_tokens", 0),
                        latency_ms=latency_ms,
                        tool_calls_count=len(tool_calls) if tool_calls else 0,
                    )

                # Trace interaction
                asyncio.create_task(
                    self._trace_interaction(
                        messages=messages,
                        response_content=content,
                        model=actual_model,
                        token_stats=token_stats,
                        latency_ms=latency_ms,
                        success=True,
                    )
                )

                return {
                    "success": True,
                    "content": content,
                    "tool_calls": tool_calls,
                    "usage": token_stats,
                    "model": actual_model,
                    "latency_ms": latency_ms,
                }

            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)

                # Parse Azure errors for actionable information
                parsed_error = None
                if is_azure:
                    parsed_error = self._parse_azure_error(e)

                # Check if should retry (check both error type and message)
                should_retry = attempt < self.retry_policy.max_attempts - 1 and any(
                    err_type in error_type or err_type in error_msg
                    for err_type in self.retry_policy.retry_on_errors
                )

                if should_retry:
                    backoff_time = self.retry_policy.backoff_multiplier**attempt

                    log_context = {
                        "provider": provider,
                        "model": actual_model,
                        "deployment": display_name if is_azure else None,
                        "error_type": error_type,
                        "attempt": attempt + 1,
                        "backoff_seconds": backoff_time,
                    }

                    # Add Azure-specific context if available
                    if parsed_error and "hint" in parsed_error:
                        log_context["hint"] = parsed_error["hint"]

                    self.logger.warning("llm_completion_retry", **log_context)
                    await asyncio.sleep(backoff_time)
                else:
                    log_context = {
                        "provider": provider,
                        "model": actual_model,
                        "deployment": display_name if is_azure else None,
                        "error_type": error_type,
                        "error": error_msg[:200],
                        "attempts": attempt + 1,
                    }

                    # Add Azure-specific context for troubleshooting
                    if parsed_error:
                        if "deployment_name" in parsed_error:
                            log_context["azure_deployment"] = parsed_error["deployment_name"]
                        if "api_version" in parsed_error:
                            log_context["azure_api_version"] = parsed_error["api_version"]
                        if "endpoint_url" in parsed_error:
                            log_context["azure_endpoint"] = parsed_error["endpoint_url"]
                        if "hint" in parsed_error:
                            log_context["troubleshooting_hint"] = parsed_error["hint"]

                    self.logger.error("llm_completion_failed", **log_context)

                    # Trace failure
                    asyncio.create_task(
                        self._trace_interaction(
                            messages=messages,
                            response_content=None,
                            model=actual_model,
                            token_stats={},
                            latency_ms=int((time.time() - start_time) * 1000),
                            success=False,
                            error=error_msg,
                        )
                    )

                    error_result = {
                        "success": False,
                        "error": error_msg,
                        "error_type": error_type,
                        "model": actual_model,
                    }

                    # Include parsed error details for Azure
                    if parsed_error:
                        error_result["parsed_error"] = parsed_error

                    return error_result

        # Should not reach here, but handle anyway
        return {
            "success": False,
            "error": "Max retries exceeded",
            "model": actual_model,
        }

    async def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        model: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Generate text from a single prompt (convenience wrapper).

        Args:
            prompt: The prompt text
            context: Optional structured context to include
            model: Model alias or None (uses default)
            **kwargs: Additional parameters

        Returns:
            Same as complete()

        Example:
            >>> result = await llm_service.generate(
            ...     prompt="Explain quantum computing",
            ...     model="fast",
            ...     max_tokens=500
            ... )
        """
        # Format prompt with context if provided
        if context:
            context_str = yaml.dump(context, default_flow_style=False)
            full_prompt = f"""Context:
{context_str}

Task: {prompt}
"""
        else:
            full_prompt = prompt

        # Use complete() method
        messages = [{"role": "user", "content": full_prompt}]
        result = await self.complete(messages, model=model, **kwargs)

        # Alias 'content' to 'generated_text' for compatibility
        if result.get("success"):
            result["generated_text"] = result["content"]

        return result

    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream LLM completion with real-time token delivery.

        Yields normalized events as chunks arrive from the LLM API.
        Errors are yielded as events, NOT raised as exceptions.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model alias or None (uses default)
            tools: Optional list of tool definitions
            tool_choice: Optional tool choice strategy
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Yields:
            Event dictionaries:
            - {"type": "token", "content": "..."} - Text chunk
            - {"type": "tool_call_start", "id": "...", "name": "...", "index": N}
            - {"type": "tool_call_delta", "id": "...", "arguments_delta": "...", "index": N}
            - {"type": "tool_call_end", "id": "...", "name": "...", "arguments": "...", "index": N}
            - {"type": "done", "usage": {...}} - Stream complete
            - {"type": "error", "message": "..."} - Error occurred
        """
        # Resolve model and parameters
        try:
            actual_model = self._resolve_model(model)
        except ValueError as e:
            self.logger.error("stream_model_resolution_failed", error=str(e))
            yield {"type": "error", "message": str(e)}
            return

        base_params = self._get_model_parameters(actual_model)
        merged_params = {**base_params, **kwargs}
        final_params = self._map_parameters_for_model(actual_model, merged_params)

        # Determine provider for logging
        azure_config = self.provider_config.get("azure", {})
        is_azure = azure_config.get("enabled", False)

        if is_azure and actual_model.startswith("azure/"):
            provider = "azure"
            display_name = actual_model.replace("azure/", "")
        else:
            provider = "openai"
            display_name = actual_model

        # Build LiteLLM call kwargs
        litellm_kwargs = {
            "model": actual_model,
            "messages": messages,
            "timeout": self.retry_policy.timeout,
            "stream": True,
            "drop_params": True,
            **final_params,
        }

        # Add tools if provided
        if tools:
            litellm_kwargs["tools"] = tools
            if tool_choice:
                litellm_kwargs["tool_choice"] = tool_choice
            else:
                litellm_kwargs["tool_choice"] = "auto"

        self.logger.debug(
            "llm_stream_started",
            provider=provider,
            model=actual_model,
            deployment=display_name if is_azure else None,
            message_count=len(messages),
            tools_count=len(tools) if tools else 0,
        )

        try:
            # Call LiteLLM with streaming
            response = await litellm.acompletion(**litellm_kwargs)

            # Track tool calls across chunks
            current_tool_calls: dict[int, dict[str, Any]] = {}
            content_accumulated = ""  # Accumulate content for tracing
            start_time = time.time()

            async for chunk in response:
                # Safety check for valid chunk structure
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                # Handle content tokens
                if hasattr(delta, "content") and delta.content:
                    content_accumulated += delta.content  # Accumulate for tracing
                    self.logger.debug(
                        "llm_stream_token",
                        content_length=len(delta.content),
                    )
                    yield {"type": "token", "content": delta.content}

                # Handle tool calls
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index

                        # New tool call starting
                        if idx not in current_tool_calls:
                            tool_id = getattr(tc, "id", None) or ""
                            tool_name = ""
                            if hasattr(tc, "function") and tc.function:
                                tool_name = getattr(tc.function, "name", None) or ""

                            current_tool_calls[idx] = {
                                "id": tool_id,
                                "name": tool_name,
                                "arguments": "",
                            }

                            # Only emit start if we have meaningful data
                            if tool_id or tool_name:
                                self.logger.debug(
                                    "llm_stream_tool_call_start",
                                    tool_id=tool_id,
                                    tool_name=tool_name,
                                    index=idx,
                                )
                                yield {
                                    "type": "tool_call_start",
                                    "id": tool_id,
                                    "name": tool_name,
                                    "index": idx,
                                }

                        # Update tool call id/name if provided in later chunks
                        if hasattr(tc, "id") and tc.id:
                            current_tool_calls[idx]["id"] = tc.id
                        if hasattr(tc, "function") and tc.function:
                            if hasattr(tc.function, "name") and tc.function.name:
                                current_tool_calls[idx]["name"] = tc.function.name

                        # Argument delta
                        if hasattr(tc, "function") and tc.function:
                            args_delta = getattr(tc.function, "arguments", None)
                            if args_delta:
                                current_tool_calls[idx]["arguments"] += args_delta
                                self.logger.debug(
                                    "llm_stream_tool_call_delta",
                                    tool_id=current_tool_calls[idx]["id"],
                                    delta_length=len(args_delta),
                                    index=idx,
                                )
                                yield {
                                    "type": "tool_call_delta",
                                    "id": current_tool_calls[idx]["id"],
                                    "arguments_delta": args_delta,
                                    "index": idx,
                                }

                # Check for finish
                if finish_reason:
                    # Emit tool_call_end for all accumulated tool calls
                    for idx, tc_data in current_tool_calls.items():
                        self.logger.debug(
                            "llm_stream_tool_call_end",
                            tool_id=tc_data["id"],
                            tool_name=tc_data["name"],
                            arguments_length=len(tc_data["arguments"]),
                            index=idx,
                        )
                        yield {
                            "type": "tool_call_end",
                            "id": tc_data["id"],
                            "name": tc_data["name"],
                            "arguments": tc_data["arguments"],
                            "index": idx,
                        }

            # Final done event
            latency_ms = int((time.time() - start_time) * 1000)

            # Try to get usage from the response object
            # Note: Streaming responses may not always have usage data
            usage: dict[str, Any] = {}
            if hasattr(response, "usage") and response.usage:
                raw_usage = response.usage
                if isinstance(raw_usage, dict):
                    usage = raw_usage
                else:
                    usage = {
                        "total_tokens": getattr(raw_usage, "total_tokens", 0),
                        "prompt_tokens": getattr(raw_usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(raw_usage, "completion_tokens", 0),
                    }

            self.logger.info(
                "llm_stream_completed",
                provider=provider,
                model=actual_model,
                deployment=display_name if is_azure else None,
                latency_ms=latency_ms,
                tool_calls_count=len(current_tool_calls),
                usage=usage,
            )

            # Trace interaction (same as non-streaming complete)
            asyncio.create_task(
                self._trace_interaction(
                    messages=messages,
                    response_content=content_accumulated or None,
                    model=actual_model,
                    token_stats=usage,
                    latency_ms=latency_ms,
                    success=True,
                )
            )

            yield {"type": "done", "usage": usage}

        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__

            # Parse Azure errors for actionable information
            parsed_error = None
            if is_azure:
                parsed_error = self._parse_azure_error(e)

            log_context = {
                "provider": provider,
                "model": actual_model,
                "deployment": display_name if is_azure else None,
                "error_type": error_type,
                "error": error_msg[:200],
            }

            if parsed_error and "hint" in parsed_error:
                log_context["troubleshooting_hint"] = parsed_error["hint"]

            self.logger.error("llm_stream_failed", **log_context)

            # Trace failed interaction
            asyncio.create_task(
                self._trace_interaction(
                    messages=messages,
                    response_content=None,
                    model=actual_model,
                    token_stats={},
                    latency_ms=0,
                    success=False,
                    error=error_msg,
                )
            )

            yield {"type": "error", "message": error_msg}

