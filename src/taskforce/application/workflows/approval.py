"""Approval workflows for enterprise governance.

This module provides approval workflow functionality for
managing changes to agents, configurations, and other
governed resources.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timezone
from enum import Enum
import uuid


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class ApprovalStatus(Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RequestType(Enum):
    """Types of approval requests."""

    AGENT_PUBLISH = "agent_publish"
    AGENT_DELETE = "agent_delete"
    ROLE_CHANGE = "role_change"
    CONFIG_CHANGE = "config_change"
    DATA_ACCESS = "data_access"
    CUSTOM = "custom"


@dataclass
class ApprovalAction:
    """An action taken on an approval request.

    Attributes:
        action_id: Unique action identifier
        action: Action taken (approve, reject, comment)
        user_id: User who took the action
        timestamp: When action was taken
        comment: Optional comment
        metadata: Additional metadata
    """

    action_id: str
    action: str  # "approve", "reject", "comment", "escalate"
    user_id: str
    timestamp: datetime = field(default_factory=_utcnow)
    comment: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action_id": self.action_id,
            "action": self.action,
            "user_id": self.user_id,
            "timestamp": self.timestamp.isoformat(),
            "comment": self.comment,
            "metadata": self.metadata,
        }


@dataclass
class ApprovalRequest:
    """An approval request.

    Attributes:
        request_id: Unique request identifier
        tenant_id: Tenant ID
        request_type: Type of request
        resource_type: Type of resource being changed
        resource_id: ID of resource being changed
        requester_id: User who made the request
        status: Current status
        title: Request title
        description: Request description
        required_approvers: Number of approvals required
        current_approvers: Set of users who have approved
        actions: List of actions taken
        created_at: When request was created
        updated_at: When request was last updated
        expires_at: When request expires
        payload: Request-specific payload
        metadata: Additional metadata
    """

    request_id: str
    tenant_id: str
    request_type: RequestType
    resource_type: str
    resource_id: str
    requester_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    title: str = ""
    description: str = ""
    required_approvers: int = 1
    current_approvers: set = field(default_factory=set)
    actions: List[ApprovalAction] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    expires_at: Optional[datetime] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_action(self, action: ApprovalAction) -> None:
        """Add an action to the request.

        Args:
            action: Action to add
        """
        self.actions.append(action)
        self.updated_at = _utcnow()

    def approve(self, user_id: str, comment: str = "") -> bool:
        """Approve the request.

        Args:
            user_id: User approving
            comment: Optional comment

        Returns:
            True if status changed to approved
        """
        if self.status != ApprovalStatus.PENDING:
            return False

        if user_id == self.requester_id:
            return False  # Can't approve own request

        self.current_approvers.add(user_id)
        self.add_action(ApprovalAction(
            action_id=str(uuid.uuid4()),
            action="approve",
            user_id=user_id,
            comment=comment,
        ))

        if len(self.current_approvers) >= self.required_approvers:
            self.status = ApprovalStatus.APPROVED

        return self.status == ApprovalStatus.APPROVED

    def reject(self, user_id: str, reason: str = "") -> bool:
        """Reject the request.

        Args:
            user_id: User rejecting
            reason: Rejection reason

        Returns:
            True if rejected successfully
        """
        if self.status != ApprovalStatus.PENDING:
            return False

        self.status = ApprovalStatus.REJECTED
        self.add_action(ApprovalAction(
            action_id=str(uuid.uuid4()),
            action="reject",
            user_id=user_id,
            comment=reason,
        ))
        return True

    def cancel(self, user_id: str, reason: str = "") -> bool:
        """Cancel the request.

        Args:
            user_id: User cancelling (must be requester)
            reason: Cancellation reason

        Returns:
            True if cancelled successfully
        """
        if self.status != ApprovalStatus.PENDING:
            return False

        if user_id != self.requester_id:
            return False  # Only requester can cancel

        self.status = ApprovalStatus.CANCELLED
        self.add_action(ApprovalAction(
            action_id=str(uuid.uuid4()),
            action="cancel",
            user_id=user_id,
            comment=reason,
        ))
        return True

    def is_expired(self) -> bool:
        """Check if request has expired.

        Returns:
            True if expired
        """
        if self.expires_at is None:
            return False
        return _utcnow() > self.expires_at

    def check_expiry(self) -> bool:
        """Check and update expiry status.

        Returns:
            True if request was marked as expired
        """
        if self.status == ApprovalStatus.PENDING and self.is_expired():
            self.status = ApprovalStatus.EXPIRED
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "request_type": self.request_type.value,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "requester_id": self.requester_id,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "required_approvers": self.required_approvers,
            "current_approvers": list(self.current_approvers),
            "actions": [a.to_dict() for a in self.actions],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "payload": self.payload,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalRequest":
        """Create from dictionary."""
        request = cls(
            request_id=data["request_id"],
            tenant_id=data["tenant_id"],
            request_type=RequestType(data["request_type"]),
            resource_type=data["resource_type"],
            resource_id=data["resource_id"],
            requester_id=data["requester_id"],
            status=ApprovalStatus(data["status"]),
            title=data.get("title", ""),
            description=data.get("description", ""),
            required_approvers=data.get("required_approvers", 1),
            current_approvers=set(data.get("current_approvers", [])),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            payload=data.get("payload", {}),
            metadata=data.get("metadata", {}),
        )
        return request


@dataclass
class ApprovalWorkflow:
    """Definition of an approval workflow.

    Attributes:
        workflow_id: Unique workflow identifier
        tenant_id: Tenant ID
        name: Workflow name
        description: Workflow description
        request_type: Type of request this applies to
        required_approvers: Number of approvals required
        allowed_approver_roles: Roles that can approve
        auto_expire_hours: Hours until auto-expiry (0 = no expiry)
        notify_on_create: Whether to notify on request creation
        notify_on_action: Whether to notify on actions
        enabled: Whether workflow is enabled
        metadata: Additional metadata
    """

    workflow_id: str
    tenant_id: str
    name: str
    description: str = ""
    request_type: RequestType = RequestType.CUSTOM
    required_approvers: int = 1
    allowed_approver_roles: set = field(default_factory=lambda: {"admin"})
    auto_expire_hours: int = 72  # 3 days default
    notify_on_create: bool = True
    notify_on_action: bool = True
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "request_type": self.request_type.value,
            "required_approvers": self.required_approvers,
            "allowed_approver_roles": list(self.allowed_approver_roles),
            "auto_expire_hours": self.auto_expire_hours,
            "notify_on_create": self.notify_on_create,
            "notify_on_action": self.notify_on_action,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


class WorkflowManager:
    """Manages approval workflows and requests.

    This class provides workflow management for approval processes
    including request creation, approval, rejection, and expiry.
    """

    def __init__(self):
        """Initialize the workflow manager."""
        self._workflows: Dict[str, ApprovalWorkflow] = {}
        self._requests: Dict[str, ApprovalRequest] = {}
        self._by_tenant: Dict[str, List[str]] = {}  # tenant_id -> request_ids
        self._callbacks: Dict[str, List[Callable]] = {}  # event -> callbacks

        # Set up default workflows
        self._setup_default_workflows()

    def _setup_default_workflows(self) -> None:
        """Set up default approval workflows."""
        # Agent publish workflow
        self._workflows["default_agent_publish"] = ApprovalWorkflow(
            workflow_id="default_agent_publish",
            tenant_id="*",  # Global
            name="Agent Publish Approval",
            description="Requires approval before publishing an agent",
            request_type=RequestType.AGENT_PUBLISH,
            required_approvers=1,
            allowed_approver_roles={"admin", "agent_designer"},
        )

        # Agent delete workflow
        self._workflows["default_agent_delete"] = ApprovalWorkflow(
            workflow_id="default_agent_delete",
            tenant_id="*",
            name="Agent Deletion Approval",
            description="Requires approval before deleting an agent",
            request_type=RequestType.AGENT_DELETE,
            required_approvers=2,  # Stricter for deletions
            allowed_approver_roles={"admin"},
        )

    def register_workflow(self, workflow: ApprovalWorkflow) -> None:
        """Register a workflow.

        Args:
            workflow: Workflow to register
        """
        self._workflows[workflow.workflow_id] = workflow

    def get_workflow(
        self,
        tenant_id: str,
        request_type: RequestType,
    ) -> Optional[ApprovalWorkflow]:
        """Get applicable workflow for a request type.

        Args:
            tenant_id: Tenant ID
            request_type: Request type

        Returns:
            Applicable workflow if found
        """
        # Check tenant-specific workflows first
        for workflow in self._workflows.values():
            if workflow.tenant_id == tenant_id and workflow.request_type == request_type:
                if workflow.enabled:
                    return workflow

        # Fallback to global workflows
        for workflow in self._workflows.values():
            if workflow.tenant_id == "*" and workflow.request_type == request_type:
                if workflow.enabled:
                    return workflow

        return None

    def create_request(
        self,
        tenant_id: str,
        request_type: RequestType,
        resource_type: str,
        resource_id: str,
        requester_id: str,
        title: str,
        description: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        """Create a new approval request.

        Args:
            tenant_id: Tenant ID
            request_type: Type of request
            resource_type: Type of resource
            resource_id: Resource ID
            requester_id: User making the request
            title: Request title
            description: Request description
            payload: Request-specific payload

        Returns:
            Created approval request
        """
        from datetime import timedelta

        workflow = self.get_workflow(tenant_id, request_type)

        request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            request_type=request_type,
            resource_type=resource_type,
            resource_id=resource_id,
            requester_id=requester_id,
            title=title,
            description=description,
            required_approvers=workflow.required_approvers if workflow else 1,
            payload=payload or {},
        )

        # Set expiry based on workflow
        if workflow and workflow.auto_expire_hours > 0:
            request.expires_at = _utcnow() + timedelta(hours=workflow.auto_expire_hours)

        self._requests[request.request_id] = request

        if tenant_id not in self._by_tenant:
            self._by_tenant[tenant_id] = []
        self._by_tenant[tenant_id].append(request.request_id)

        # Trigger callbacks
        self._trigger_event("request_created", request)

        return request

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get an approval request.

        Args:
            request_id: Request ID

        Returns:
            Request if found
        """
        request = self._requests.get(request_id)
        if request:
            request.check_expiry()
        return request

    def list_requests(
        self,
        tenant_id: str,
        status: Optional[ApprovalStatus] = None,
        requester_id: Optional[str] = None,
        request_type: Optional[RequestType] = None,
    ) -> List[ApprovalRequest]:
        """List approval requests.

        Args:
            tenant_id: Tenant ID
            status: Optional status filter
            requester_id: Optional requester filter
            request_type: Optional request type filter

        Returns:
            List of matching requests
        """
        request_ids = self._by_tenant.get(tenant_id, [])
        requests = [
            self._requests[rid] for rid in request_ids
            if rid in self._requests
        ]

        # Check expirations
        for request in requests:
            request.check_expiry()

        if status:
            requests = [r for r in requests if r.status == status]

        if requester_id:
            requests = [r for r in requests if r.requester_id == requester_id]

        if request_type:
            requests = [r for r in requests if r.request_type == request_type]

        return sorted(requests, key=lambda r: r.created_at, reverse=True)

    def list_pending_for_approver(
        self,
        tenant_id: str,
        user_id: str,
        user_roles: set,
    ) -> List[ApprovalRequest]:
        """List pending requests that a user can approve.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            user_roles: User's roles

        Returns:
            List of requests the user can approve
        """
        pending = self.list_requests(tenant_id, status=ApprovalStatus.PENDING)
        can_approve = []

        for request in pending:
            # Skip own requests
            if request.requester_id == user_id:
                continue

            # Skip already approved by this user
            if user_id in request.current_approvers:
                continue

            # Check if user has approver role
            workflow = self.get_workflow(tenant_id, request.request_type)
            if workflow:
                if user_roles & workflow.allowed_approver_roles:
                    can_approve.append(request)
            else:
                # No workflow - allow admins
                if "admin" in user_roles:
                    can_approve.append(request)

        return can_approve

    def approve_request(
        self,
        request_id: str,
        user_id: str,
        comment: str = "",
    ) -> bool:
        """Approve a request.

        Args:
            request_id: Request ID
            user_id: User approving
            comment: Optional comment

        Returns:
            True if approval completed the request
        """
        request = self.get_request(request_id)
        if not request:
            return False

        result = request.approve(user_id, comment)

        if result:
            self._trigger_event("request_approved", request)
        else:
            self._trigger_event("request_action", request)

        return result

    def reject_request(
        self,
        request_id: str,
        user_id: str,
        reason: str = "",
    ) -> bool:
        """Reject a request.

        Args:
            request_id: Request ID
            user_id: User rejecting
            reason: Rejection reason

        Returns:
            True if rejected successfully
        """
        request = self.get_request(request_id)
        if not request:
            return False

        result = request.reject(user_id, reason)

        if result:
            self._trigger_event("request_rejected", request)

        return result

    def cancel_request(
        self,
        request_id: str,
        user_id: str,
        reason: str = "",
    ) -> bool:
        """Cancel a request.

        Args:
            request_id: Request ID
            user_id: User cancelling
            reason: Cancellation reason

        Returns:
            True if cancelled successfully
        """
        request = self.get_request(request_id)
        if not request:
            return False

        result = request.cancel(user_id, reason)

        if result:
            self._trigger_event("request_cancelled", request)

        return result

    def on_event(self, event: str, callback: Callable) -> None:
        """Register a callback for an event.

        Args:
            event: Event name
            callback: Callback function
        """
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def _trigger_event(self, event: str, request: ApprovalRequest) -> None:
        """Trigger callbacks for an event.

        Args:
            event: Event name
            request: Related request
        """
        for callback in self._callbacks.get(event, []):
            try:
                callback(request)
            except Exception:
                pass  # Don't let callback errors break the flow
