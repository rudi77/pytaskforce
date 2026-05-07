"""Default approval service implementations.

The CLI variant prompts the operator on stdin; the auto-approve
variant is a no-op used in tests. Production multi-user deployments
ship the enterprise plugin's REST-backed implementation instead.
"""

from taskforce.infrastructure.approval.auto_approve import AutoApproveService
from taskforce.infrastructure.approval.cli_approval import CLIApprovalService

__all__ = ["AutoApproveService", "CLIApprovalService"]
