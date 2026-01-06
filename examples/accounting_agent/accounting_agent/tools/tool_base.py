"""
Tool Base Classes and Protocols

This module defines the base interfaces and enums for accounting tools.
These are compatible with the Taskforce framework but can also be used standalone.
"""

from enum import Enum


class ApprovalRiskLevel(str, Enum):
    """Risk level for tool approval prompts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
