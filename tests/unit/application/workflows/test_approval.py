"""Tests for approval workflows."""

import pytest
from datetime import datetime, timezone, timedelta

from taskforce.application.workflows import (
    ApprovalStatus,
    ApprovalRequest,
    ApprovalWorkflow,
    WorkflowManager,
)
from taskforce.application.workflows.approval import RequestType, ApprovalAction


class TestApprovalStatus:
    """Tests for ApprovalStatus enum."""

    def test_all_statuses_defined(self):
        """Test all expected statuses exist."""
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.CANCELLED.value == "cancelled"
        assert ApprovalStatus.EXPIRED.value == "expired"


class TestRequestType:
    """Tests for RequestType enum."""

    def test_all_types_defined(self):
        """Test all expected types exist."""
        assert RequestType.AGENT_PUBLISH.value == "agent_publish"
        assert RequestType.AGENT_DELETE.value == "agent_delete"
        assert RequestType.ROLE_CHANGE.value == "role_change"
        assert RequestType.CONFIG_CHANGE.value == "config_change"
        assert RequestType.DATA_ACCESS.value == "data_access"
        assert RequestType.CUSTOM.value == "custom"


class TestApprovalAction:
    """Tests for ApprovalAction dataclass."""

    def test_create_action(self):
        """Test creating an action."""
        action = ApprovalAction(
            action_id="a1",
            action="approve",
            user_id="user1",
            comment="Looks good",
        )
        assert action.action_id == "a1"
        assert action.action == "approve"
        assert action.user_id == "user1"
        assert action.comment == "Looks good"
        assert action.timestamp is not None

    def test_to_dict(self):
        """Test serialization to dict."""
        action = ApprovalAction(
            action_id="a1",
            action="reject",
            user_id="user1",
            comment="Needs changes",
            metadata={"reason_code": "quality"},
        )
        data = action.to_dict()
        assert data["action_id"] == "a1"
        assert data["action"] == "reject"
        assert data["user_id"] == "user1"
        assert data["comment"] == "Needs changes"
        assert data["metadata"]["reason_code"] == "quality"


class TestApprovalRequest:
    """Tests for ApprovalRequest dataclass."""

    def test_create_request(self):
        """Test creating a request."""
        request = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Publish agent",
        )
        assert request.request_id == "req1"
        assert request.status == ApprovalStatus.PENDING
        assert request.required_approvers == 1
        assert len(request.current_approvers) == 0
        assert len(request.actions) == 0

    def test_approve_single_approver(self):
        """Test approval with single approver required."""
        request = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            required_approvers=1,
        )

        result = request.approve("admin1", comment="Approved")

        assert result is True
        assert request.status == ApprovalStatus.APPROVED
        assert "admin1" in request.current_approvers
        assert len(request.actions) == 1
        assert request.actions[0].action == "approve"

    def test_approve_multiple_approvers(self):
        """Test approval requiring multiple approvers."""
        request = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_DELETE,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            required_approvers=2,
        )

        # First approval
        result1 = request.approve("admin1")
        assert result1 is False  # Not yet fully approved
        assert request.status == ApprovalStatus.PENDING
        assert len(request.current_approvers) == 1

        # Second approval
        result2 = request.approve("admin2")
        assert result2 is True  # Now fully approved
        assert request.status == ApprovalStatus.APPROVED
        assert len(request.current_approvers) == 2

    def test_approve_by_requester_fails(self):
        """Test that requester cannot approve their own request."""
        request = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
        )

        result = request.approve("user1")  # Same as requester

        assert result is False
        assert request.status == ApprovalStatus.PENDING
        assert "user1" not in request.current_approvers

    def test_approve_non_pending_fails(self):
        """Test that only pending requests can be approved."""
        request = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            status=ApprovalStatus.REJECTED,
        )

        result = request.approve("admin1")

        assert result is False
        assert request.status == ApprovalStatus.REJECTED

    def test_reject_request(self):
        """Test rejecting a request."""
        request = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
        )

        result = request.reject("admin1", reason="Not ready")

        assert result is True
        assert request.status == ApprovalStatus.REJECTED
        assert len(request.actions) == 1
        assert request.actions[0].action == "reject"
        assert request.actions[0].comment == "Not ready"

    def test_reject_non_pending_fails(self):
        """Test that only pending requests can be rejected."""
        request = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            status=ApprovalStatus.APPROVED,
        )

        result = request.reject("admin1")

        assert result is False
        assert request.status == ApprovalStatus.APPROVED

    def test_cancel_request(self):
        """Test cancelling a request."""
        request = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
        )

        result = request.cancel("user1", reason="Changed my mind")

        assert result is True
        assert request.status == ApprovalStatus.CANCELLED
        assert len(request.actions) == 1
        assert request.actions[0].action == "cancel"

    def test_cancel_by_non_requester_fails(self):
        """Test that only requester can cancel."""
        request = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
        )

        result = request.cancel("admin1")  # Not the requester

        assert result is False
        assert request.status == ApprovalStatus.PENDING

    def test_is_expired(self):
        """Test expiry check."""
        # Not expired
        request1 = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert request1.is_expired() is False

        # Expired
        request2 = ApprovalRequest(
            request_id="req2",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert request2.is_expired() is True

        # No expiry
        request3 = ApprovalRequest(
            request_id="req3",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            expires_at=None,
        )
        assert request3.is_expired() is False

    def test_check_expiry_updates_status(self):
        """Test that check_expiry updates status when expired."""
        request = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        result = request.check_expiry()

        assert result is True
        assert request.status == ApprovalStatus.EXPIRED

    def test_to_dict_and_from_dict(self):
        """Test serialization round trip."""
        original = ApprovalRequest(
            request_id="req1",
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Publish my agent",
            description="Ready for production",
            required_approvers=2,
            payload={"version": "1.0.0"},
            metadata={"priority": "high"},
        )
        original.current_approvers.add("admin1")

        data = original.to_dict()
        restored = ApprovalRequest.from_dict(data)

        assert restored.request_id == original.request_id
        assert restored.tenant_id == original.tenant_id
        assert restored.request_type == original.request_type
        assert restored.requester_id == original.requester_id
        assert restored.title == original.title
        assert restored.required_approvers == original.required_approvers
        assert restored.payload == original.payload
        assert "admin1" in restored.current_approvers


class TestApprovalWorkflow:
    """Tests for ApprovalWorkflow dataclass."""

    def test_create_workflow(self):
        """Test creating a workflow."""
        workflow = ApprovalWorkflow(
            workflow_id="wf1",
            tenant_id="tenant1",
            name="Test Workflow",
            description="A test workflow",
            request_type=RequestType.AGENT_PUBLISH,
            required_approvers=2,
            allowed_approver_roles={"admin", "manager"},
            auto_expire_hours=48,
        )
        assert workflow.workflow_id == "wf1"
        assert workflow.name == "Test Workflow"
        assert workflow.required_approvers == 2
        assert "admin" in workflow.allowed_approver_roles
        assert workflow.auto_expire_hours == 48
        assert workflow.enabled is True

    def test_to_dict(self):
        """Test serialization to dict."""
        workflow = ApprovalWorkflow(
            workflow_id="wf1",
            tenant_id="tenant1",
            name="Test Workflow",
            request_type=RequestType.CONFIG_CHANGE,
            allowed_approver_roles={"admin"},
        )
        data = workflow.to_dict()
        assert data["workflow_id"] == "wf1"
        assert data["name"] == "Test Workflow"
        assert data["request_type"] == "config_change"
        assert "admin" in data["allowed_approver_roles"]


class TestWorkflowManager:
    """Tests for WorkflowManager class."""

    def test_default_workflows_created(self):
        """Test that default workflows are created."""
        manager = WorkflowManager()

        agent_publish = manager.get_workflow("tenant1", RequestType.AGENT_PUBLISH)
        assert agent_publish is not None
        assert agent_publish.name == "Agent Publish Approval"

        agent_delete = manager.get_workflow("tenant1", RequestType.AGENT_DELETE)
        assert agent_delete is not None
        assert agent_delete.name == "Agent Deletion Approval"

    def test_register_workflow(self):
        """Test registering a custom workflow."""
        manager = WorkflowManager()
        workflow = ApprovalWorkflow(
            workflow_id="custom_wf",
            tenant_id="tenant1",
            name="Custom Workflow",
            request_type=RequestType.CONFIG_CHANGE,
            required_approvers=3,
        )
        manager.register_workflow(workflow)

        found = manager.get_workflow("tenant1", RequestType.CONFIG_CHANGE)
        assert found == workflow

    def test_tenant_specific_workflow_priority(self):
        """Test that tenant-specific workflows take priority."""
        manager = WorkflowManager()

        # Register tenant-specific workflow
        tenant_workflow = ApprovalWorkflow(
            workflow_id="tenant1_publish",
            tenant_id="tenant1",
            name="Tenant 1 Publish",
            request_type=RequestType.AGENT_PUBLISH,
            required_approvers=3,  # Different from default
        )
        manager.register_workflow(tenant_workflow)

        # Should get tenant-specific
        found = manager.get_workflow("tenant1", RequestType.AGENT_PUBLISH)
        assert found.workflow_id == "tenant1_publish"
        assert found.required_approvers == 3

        # Other tenant should get default
        found2 = manager.get_workflow("tenant2", RequestType.AGENT_PUBLISH)
        assert found2.workflow_id == "default_agent_publish"
        assert found2.required_approvers == 1

    def test_create_request(self):
        """Test creating an approval request."""
        manager = WorkflowManager()

        request = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Publish my agent",
            description="Ready for production",
            payload={"version": "1.0.0"},
        )

        assert request.request_id is not None
        assert request.tenant_id == "tenant1"
        assert request.request_type == RequestType.AGENT_PUBLISH
        assert request.requester_id == "user1"
        assert request.status == ApprovalStatus.PENDING
        assert request.expires_at is not None  # Auto-set from workflow

    def test_get_request(self):
        """Test getting a request by ID."""
        manager = WorkflowManager()
        request = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Test",
        )

        found = manager.get_request(request.request_id)
        assert found == request

        not_found = manager.get_request("nonexistent")
        assert not_found is None

    def test_list_requests(self):
        """Test listing requests for a tenant."""
        manager = WorkflowManager()

        # Create multiple requests
        req1 = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Request 1",
        )
        req2 = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_DELETE,
            resource_type="agent",
            resource_id="agent2",
            requester_id="user2",
            title="Request 2",
        )
        req3 = manager.create_request(
            tenant_id="tenant2",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent3",
            requester_id="user3",
            title="Request 3",
        )

        # List all for tenant1
        requests = manager.list_requests("tenant1")
        assert len(requests) == 2

        # Filter by requester
        requests = manager.list_requests("tenant1", requester_id="user1")
        assert len(requests) == 1
        assert requests[0].request_id == req1.request_id

        # Filter by request type
        requests = manager.list_requests("tenant1", request_type=RequestType.AGENT_DELETE)
        assert len(requests) == 1
        assert requests[0].request_id == req2.request_id

    def test_list_pending_for_approver(self):
        """Test listing requests for an approver."""
        manager = WorkflowManager()

        # User creates requests
        req1 = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Request 1",
        )
        req2 = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent2",
            requester_id="admin1",  # Admin's own request
            title="Request 2",
        )

        # Admin with agent_designer role
        pending = manager.list_pending_for_approver(
            "tenant1", "admin1", {"admin", "agent_designer"}
        )

        # Should see req1 but not req2 (own request)
        assert len(pending) == 1
        assert pending[0].request_id == req1.request_id

    def test_list_pending_for_approver_excludes_already_approved(self):
        """Test that already approved requests are excluded."""
        manager = WorkflowManager()

        # Create request needing 2 approvers
        # First, register a workflow requiring 2 approvers
        workflow = ApprovalWorkflow(
            workflow_id="tenant1_publish",
            tenant_id="tenant1",
            name="Tenant 1 Publish",
            request_type=RequestType.AGENT_PUBLISH,
            required_approvers=2,
            allowed_approver_roles={"admin"},
        )
        manager.register_workflow(workflow)

        req = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Request",
        )

        # Admin1 approves
        manager.approve_request(req.request_id, "admin1")

        # Admin1 should not see it anymore
        pending = manager.list_pending_for_approver("tenant1", "admin1", {"admin"})
        assert len(pending) == 0

        # Admin2 should still see it
        pending = manager.list_pending_for_approver("tenant1", "admin2", {"admin"})
        assert len(pending) == 1

    def test_approve_request(self):
        """Test approving a request through manager."""
        manager = WorkflowManager()

        request = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Test",
        )

        result = manager.approve_request(request.request_id, "admin1", "Approved")

        assert result is True
        assert request.status == ApprovalStatus.APPROVED

    def test_reject_request(self):
        """Test rejecting a request through manager."""
        manager = WorkflowManager()

        request = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Test",
        )

        result = manager.reject_request(request.request_id, "admin1", "Not ready")

        assert result is True
        assert request.status == ApprovalStatus.REJECTED

    def test_cancel_request(self):
        """Test cancelling a request through manager."""
        manager = WorkflowManager()

        request = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Test",
        )

        result = manager.cancel_request(request.request_id, "user1", "Changed mind")

        assert result is True
        assert request.status == ApprovalStatus.CANCELLED

    def test_event_callbacks(self):
        """Test event callback system."""
        manager = WorkflowManager()
        events = []

        def on_created(req):
            events.append(("created", req.request_id))

        def on_approved(req):
            events.append(("approved", req.request_id))

        manager.on_event("request_created", on_created)
        manager.on_event("request_approved", on_approved)

        # Create request
        request = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Test",
        )

        assert ("created", request.request_id) in events

        # Approve request
        manager.approve_request(request.request_id, "admin1")

        assert ("approved", request.request_id) in events

    def test_event_callback_errors_ignored(self):
        """Test that callback errors don't break the flow."""
        manager = WorkflowManager()

        def bad_callback(req):
            raise ValueError("Callback error")

        manager.on_event("request_created", bad_callback)

        # Should not raise
        request = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.AGENT_PUBLISH,
            resource_type="agent",
            resource_id="agent1",
            requester_id="user1",
            title="Test",
        )

        assert request is not None

    def test_request_with_no_matching_workflow(self):
        """Test creating request when no workflow matches."""
        manager = WorkflowManager()

        # DATA_ACCESS has no default workflow
        request = manager.create_request(
            tenant_id="tenant1",
            request_type=RequestType.DATA_ACCESS,
            resource_type="dataset",
            resource_id="data1",
            requester_id="user1",
            title="Access request",
        )

        # Should still create with defaults
        assert request.required_approvers == 1
        assert request.expires_at is None  # No workflow = no auto-expiry

    def test_disabled_workflow_not_used(self):
        """Test that disabled workflows are skipped."""
        manager = WorkflowManager()

        # Disable the default publish workflow
        workflow = manager.get_workflow("*", RequestType.AGENT_PUBLISH)
        if workflow:
            workflow.enabled = False

        # Register a new enabled one
        new_workflow = ApprovalWorkflow(
            workflow_id="new_publish",
            tenant_id="*",
            name="New Publish Workflow",
            request_type=RequestType.AGENT_PUBLISH,
            required_approvers=5,
            enabled=True,
        )
        manager.register_workflow(new_workflow)

        # Should get the enabled one
        found = manager.get_workflow("tenant1", RequestType.AGENT_PUBLISH)
        assert found.workflow_id == "new_publish"
        assert found.required_approvers == 5
