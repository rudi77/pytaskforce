"""Architect tool for configuring the Accounts Payable PoC."""

from __future__ import annotations

from typing import Any

from ap_poc_agent.domain import ConfigValidationError, parse_system_config
from ap_poc_agent.tools.data_loader import load_json_file


class ArchitectConfigTool:
    """Validate and normalize the PoC system configuration."""

    @property
    def name(self) -> str:
        """Return tool name."""
        return "architect_configure_system"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Validates the PoC system configuration for chart of accounts, tax rates, "
            "company profile, vendors, and cost centers. Returns a normalized config "
            "payload for other agents."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "config_path": {
                    "type": "string",
                    "description": "Path to JSON config file",
                },
                "config_payload": {
                    "type": "object",
                    "description": "Configuration payload (JSON object)",
                },
            },
            "required": [],
        }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        has_path = "config_path" in kwargs
        has_payload = "config_payload" in kwargs
        if not has_path and not has_payload:
            return False, "config_path or config_payload is required"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Validate configuration and return normalized payload."""
        try:
            payload = _resolve_payload(kwargs)
            config = parse_system_config(payload)
        except (ConfigValidationError, FileNotFoundError, ValueError) as error:
            return _error_result(error)

        summary = {
            "chart_of_accounts": config.chart_of_accounts,
            "tax_rates": config.tax_rates,
            "vendor_count": len(config.vendors),
            "account_count": len(config.accounts),
            "cost_center_count": len(config.cost_centers),
        }
        return {
            "success": True,
            "system_config": config.to_dict(),
            "summary": summary,
        }


def _resolve_payload(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Resolve config payload from kwargs."""
    if "config_payload" in kwargs:
        if not isinstance(kwargs["config_payload"], dict):
            raise ConfigValidationError("config_payload must be an object")
        return kwargs["config_payload"]
    return load_json_file(str(kwargs["config_path"]))


def _error_result(error: Exception) -> dict[str, Any]:
    """Format an error result."""
    return {
        "success": False,
        "error": str(error),
        "error_type": type(error).__name__,
    }
