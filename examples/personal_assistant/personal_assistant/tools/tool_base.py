"""Shared tool helpers for the personal assistant plugin."""

from enum import Enum


class ApprovalRiskLevel(str, Enum):
    """Risk level for tool approval prompts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
