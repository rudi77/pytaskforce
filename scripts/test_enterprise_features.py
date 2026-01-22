#!/usr/bin/env python
"""Interactive test script for enterprise features."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

def test_agent_catalog():
    """Test Agent Catalog & Versioning."""
    print("\n" + "="*60)
    print("Testing: Agent Catalog & Versioning")
    print("="*60)

    from taskforce.application.catalog import AgentCatalog, VersionStatus

    catalog = AgentCatalog()

    # Create agent
    entry = catalog.create_agent(
        tenant_id="acme-corp",
        name="Customer Support Agent",
        description="Handles customer inquiries",
        category="support",
        tags={"production", "nlp"},
        owner_id="alice",
        initial_definition={
            "tools": ["semantic_search", "send_email"],
            "system_prompt": "You are a helpful customer support agent."
        }
    )
    print(f"[OK] Agent created: {entry.name} ({entry.agent_id})")
    print(f"     Initial version: {entry.versions[0].version_number}")

    # Create new version
    v2 = catalog.create_version(
        agent_id=entry.agent_id,
        version_number="1.0.0",
        definition={
            "tools": ["semantic_search", "send_email", "create_ticket"],
            "system_prompt": "You are a helpful customer support agent."
        },
        created_by="alice",
        changelog="Added ticket creation capability"
    )
    print(f"[OK] Version created: {v2.version_number}")

    # Submit for approval
    catalog.submit_for_approval(entry.agent_id, v2.version_id)
    print(f"[OK] Submitted for approval: {v2.status.value}")

    # Approve
    catalog.approve_version(entry.agent_id, v2.version_id, approved_by="bob")
    print(f"[OK] Approved: {v2.status.value}")

    # Publish
    catalog.publish_version(entry.agent_id, v2.version_id)
    print(f"[OK] Published: {v2.status.value}")
    print(f"     Current version: {entry.current_version}")

    return True


def test_approval_workflows():
    """Test Approval Workflows."""
    print("\n" + "="*60)
    print("Testing: Approval Workflows")
    print("="*60)

    from taskforce.application.workflows import WorkflowManager, ApprovalStatus
    from taskforce.application.workflows.approval import RequestType

    manager = WorkflowManager()

    # Create request
    request = manager.create_request(
        tenant_id="acme-corp",
        request_type=RequestType.AGENT_PUBLISH,
        resource_type="agent",
        resource_id="agent-123",
        requester_id="alice",
        title="Publish Customer Support Agent v1.0.0",
        description="Ready for production deployment"
    )
    print(f"[OK] Request created: {request.request_id[:8]}...")
    print(f"     Status: {request.status.value}")
    print(f"     Expires: {request.expires_at}")

    # List pending for approver
    pending = manager.list_pending_for_approver(
        "acme-corp", "bob", {"admin", "agent_designer"}
    )
    print(f"[OK] Pending requests for Bob: {len(pending)}")

    # Approve
    result = manager.approve_request(request.request_id, "bob", "Looks good!")
    print(f"[OK] Approved by Bob: {result}")
    print(f"     Final status: {request.status.value}")

    return True


def test_usage_and_cost():
    """Test Usage Tracking & Cost Reporting."""
    print("\n" + "="*60)
    print("Testing: Usage Tracking & Cost Reporting")
    print("="*60)

    from taskforce.application.reporting import (
        UsageTracker, CostCalculator
    )
    from taskforce.application.reporting.usage import UsageType

    tracker = UsageTracker()

    # Record some usage
    tracker.record_tokens(
        tenant_id="acme-corp",
        input_tokens=10000,
        output_tokens=5000,
        model="gpt-4o",
        session_id="session-1",
        user_id="alice"
    )
    tracker.record_tokens(
        tenant_id="acme-corp",
        input_tokens=20000,
        output_tokens=10000,
        model="gpt-4o-mini",
        session_id="session-2",
        user_id="bob"
    )
    print(f"[OK] Recorded usage for 2 sessions")

    # Get aggregation - use datetime instead of date
    now = datetime.now(timezone.utc)
    aggregation = tracker.get_aggregation(
        tenant_id="acme-corp",
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1)
    )
    print(f"[OK] Aggregation:")
    input_tokens = aggregation.totals.get(UsageType.INPUT_TOKENS, 0)
    output_tokens = aggregation.totals.get(UsageType.OUTPUT_TOKENS, 0)
    print(f"     Total input tokens: {input_tokens:,}")
    print(f"     Total output tokens: {output_tokens:,}")
    print(f"     Records: {aggregation.record_count}")

    # Calculate cost
    calculator = CostCalculator()
    report = calculator.generate_report(aggregation)
    print(f"[OK] Cost Report:")
    print(f"     Total: ${report.total:.4f}")
    print(f"     Currency: {report.currency}")
    for item in report.line_items:
        print(f"     - {item.description}: ${item.total:.4f}")

    return True


def test_memory_acl():
    """Test Memory Access Control."""
    print("\n" + "="*60)
    print("Testing: Memory Access Control")
    print("="*60)

    from taskforce.core.domain.memory_acl import (
        MemoryACLManager, MemoryPermission, SensitivityLevel, MemoryScope
    )

    manager = MemoryACLManager()

    # Create ACL - use INTERNAL sensitivity (allowed for TENANT scope)
    acl = manager.create_acl(
        resource_id="memory-123",
        resource_type="conversation",
        owner_id="alice",
        tenant_id="acme-corp",
        sensitivity=SensitivityLevel.INTERNAL,  # Not CONFIDENTIAL
        scope=MemoryScope.TENANT
    )
    print(f"[OK] ACL created for: {acl.resource_id}")
    print(f"     Sensitivity: {acl.sensitivity.value}")
    print(f"     Scope: {acl.scope.value}")
    print(f"     Owner: {acl.owner_id}")

    # Check owner access - owner should always have access
    can_read = manager.check_access(
        "memory-123", "alice", "acme-corp", {"user"}, MemoryPermission.READ
    )
    can_admin = manager.check_access(
        "memory-123", "alice", "acme-corp", {"user"}, MemoryPermission.ADMIN
    )
    print(f"[OK] Owner (alice) can READ: {can_read}")
    print(f"[OK] Owner (alice) can ADMIN: {can_admin}")

    # Check other user in same tenant
    bob_can_read = manager.check_access(
        "memory-123", "bob", "acme-corp", {"user"}, MemoryPermission.READ
    )
    print(f"[OK] Bob can READ (tenant scope): {bob_can_read}")

    # Grant specific access to charlie
    manager.grant_access(
        "memory-123",
        principal_type="user",
        principal_id="charlie",
        permissions={MemoryPermission.READ, MemoryPermission.WRITE},
        granted_by="alice"  # Required parameter
    )
    charlie_can_write = manager.check_access(
        "memory-123", "charlie", "acme-corp", {"user"}, MemoryPermission.WRITE
    )
    print(f"[OK] Charlie granted WRITE: {charlie_can_write}")

    return True


def test_compliance_reporting():
    """Test Compliance Evidence Export."""
    print("\n" + "="*60)
    print("Testing: Compliance Evidence Export")
    print("="*60)

    from taskforce.application.reporting import (
        ComplianceEvidenceCollector,
        ComplianceReportGenerator,
        ComplianceFramework
    )

    # Pass tenant_id to collector
    collector = ComplianceEvidenceCollector(tenant_id="acme-corp")
    generator = ComplianceReportGenerator(collector)

    # Generate SOC2 report - uses datetime, not tenant_id
    now = datetime.now(timezone.utc)
    report = generator.generate_soc2_report(
        period_start=now - timedelta(days=30),
        period_end=now,
    )
    print(f"[OK] SOC2 Report generated:")
    print(f"     Framework: {report.framework.value}")
    print(f"     Evidence items: {len(report.evidence_items)}")
    print(f"     Summary: {report.summary[:50] if report.summary else 'N/A'}...")
    print(f"     Generated at: {report.generated_at}")

    # Generate GDPR records
    records = generator.generate_gdpr_records()
    print(f"[OK] GDPR Records: {len(records)}")
    if records:
        print(f"     Processing Purpose: {records[0].processing_purpose}")
        print(f"     Data Categories: {records[0].data_categories}")

    return True


def test_rag_citations():
    """Test RAG Citation Support."""
    print("\n" + "="*60)
    print("Testing: RAG Citation Support")
    print("="*60)

    from taskforce.infrastructure.tools.rag.citations import (
        RAGCitation, CitationFormatter, CitationStyle
    )

    # Create some citations - use correct field names
    citations = [
        RAGCitation(
            document_id="doc-1",  # not citation_id
            title="Company Policy Handbook",
            snippet="Employees are entitled to 25 days of annual leave.",
            score=0.95  # not relevance_score
        ),
        RAGCitation(
            document_id="doc-2",
            title="HR FAQ",
            snippet="Leave requests must be submitted 2 weeks in advance.",
            score=0.87
        )
    ]
    print(f"[OK] Created {len(citations)} citations")

    # Format with inline style
    formatter = CitationFormatter(style=CitationStyle.INLINE)
    text = "According to our policy, you have 25 days leave [1]. Please submit requests early [2]."
    result = formatter.format_citations(text, citations)
    print(f"[OK] Inline formatting:")
    print(f"     Text: {result.formatted_text[:60]}...")
    print(f"     References: {len(result.references)}")

    # Format with appendix style
    formatter_appendix = CitationFormatter(style=CitationStyle.APPENDIX)
    result_appendix = formatter_appendix.format_citations(text, citations)
    print(f"[OK] Appendix formatting:")
    for ref in result_appendix.references:
        print(f"     - {ref[:50]}...")

    return True


def main():
    """Run all tests."""
    print("\n" + "#"*60)
    print("# PyTaskforce Enterprise Features - Interactive Test")
    print("#"*60)

    tests = [
        ("Agent Catalog", test_agent_catalog),
        ("Approval Workflows", test_approval_workflows),
        ("Usage & Cost", test_usage_and_cost),
        ("Memory ACL", test_memory_acl),
        ("Compliance Reporting", test_compliance_reporting),
        ("RAG Citations", test_rag_citations),
    ]

    results = []
    for name, test_fn in tests:
        try:
            success = test_fn()
            results.append((name, success))
        except Exception as e:
            print(f"[ERROR] {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {status} {name}")

    passed = sum(1 for _, s in results if s)
    print(f"\nTotal: {passed}/{len(results)} tests passed")


if __name__ == "__main__":
    main()
