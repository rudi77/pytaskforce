"""Configuration Schema Validation - Re-export shim.

.. deprecated::
    This module has been relocated to ``taskforce.application.config_schema``
    as its Pydantic validation logic belongs in the application layer, not the
    core domain.  All existing imports via this path continue to work through
    this re-export shim.  New code should import directly from
    ``taskforce.application.config_schema``.
"""

from taskforce.application.config_schema import (  # noqa: F401
    AgentConfigSchema,
    AgentSourceType,
    AutoEpicConfig,
    ConfigValidationError,
    MCPServerConfigSchema,
    ProfileConfigSchema,
    _class_name_to_tool_name,
    extract_tool_names,
    validate_agent_config,
    validate_profile_config,
)

__all__ = [
    "AgentConfigSchema",
    "AgentSourceType",
    "AutoEpicConfig",
    "ConfigValidationError",
    "MCPServerConfigSchema",
    "ProfileConfigSchema",
    "_class_name_to_tool_name",
    "extract_tool_names",
    "validate_agent_config",
    "validate_profile_config",
]
