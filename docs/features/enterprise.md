# Enterprise Features

This document describes the enterprise-ready capabilities for PyTaskforce for multi-tenant deployments, compliance, and governance.

> **Wichtig**: Enterprise-Features sind als separates Paket `taskforce-enterprise` verfügbar.

## Installation

```bash
# Base-Framework (Open Source, MIT License)
pip install taskforce

# Enterprise-Features (Commercial License)
pip install taskforce-enterprise
```

Nach Installation von `taskforce-enterprise` werden alle Enterprise-Features **automatisch aktiviert** via Entry-Point-basiertem Plugin-System. Keine Code-Änderungen erforderlich.

### Prüfen ob Enterprise aktiv ist

```python
from taskforce.application.plugin_discovery import is_enterprise_available

if is_enterprise_available():
    print("Enterprise-Features verfügbar")
    # Admin-API unter /api/v1/admin/*
    # Auth-Middleware aktiv
    # Policy Engine verfügbar
```

## Overview

PyTaskforce Enterprise provides:

- **Multi-Tenant Identity & RBAC** - Tenant isolation, user management, role-based access control
- **Evidence & Audit Trail** - Full traceability of agent actions with source citations
- **Secure Memory Governance** - Encryption, retention policies, access control lists
- **Enterprise Operations** - SLA metrics, usage tracking, cost reporting
- **Productization** - Agent catalog, versioning, approval workflows

---

## 1. Identity, Tenancy & RBAC

### Tenant & User Context

Every request carries tenant and user context:

```python
# Import aus taskforce-enterprise Paket
from taskforce_enterprise.core.interfaces.identity import TenantContext, UserContext

# Tenant context
tenant = TenantContext(
    tenant_id="acme-corp",
    name="Acme Corporation",
    settings={"max_agents": 100, "features": ["enterprise"]}
)

# User context (mit Permission Enum)
from taskforce_enterprise.core.interfaces.identity import Permission, get_permissions_for_roles

user = UserContext(
    user_id="user-123",
    tenant_id="acme-corp",
    username="alice",
    email="alice@acme.com",
    roles={"admin", "agent_designer"},
    permissions=get_permissions_for_roles({"admin", "agent_designer"})
)
```

### Authentication

Two authentication methods are supported:

#### JWT/OAuth2 Authentication

```python
# JWT Authentication (taskforce-enterprise)
from taskforce_enterprise.infrastructure.auth.jwt_provider import JWTProvider

provider = JWTProvider(
    secret_key="your-secret",
    algorithm="HS256",
    issuer="taskforce"
)

# Create token
token = provider.create_token(user_context, expires_in=3600)

# Verify token
user = provider.verify_token(token)
```

#### API Key Authentication

```python
# API Key Authentication (taskforce-enterprise)
from taskforce_enterprise.infrastructure.auth.api_key_provider import APIKeyProvider

provider = APIKeyProvider()

# Create API key
key_info = provider.create_key(
    tenant_id="acme-corp",
    name="Production Key",
    scopes=["agent:execute", "agent:read"]
)

# Verify key
context = provider.verify_key(api_key)
```

### RBAC Policy Engine

The policy engine enforces role-based access control:

```python
# RBAC Policy Engine (taskforce-enterprise)
from taskforce_enterprise.application.policy import PolicyEngine, PolicyConfig
from taskforce_enterprise.core.interfaces.identity import Permission, ResourceType

engine = PolicyEngine(PolicyConfig(enabled=True))

# Evaluate permission
decision = await engine.evaluate(
    user=user_context,
    action=Permission.AGENT_EXECUTE,
    resource_type=ResourceType.AGENT,
)

if decision.allowed:
    # User can execute agents
    pass

# Use decorator for automatic enforcement (in FastAPI routes)
from taskforce_enterprise.api.middleware.auth import require_permission

@require_permission(Permission.AGENT_WRITE)
async def create_agent(request, user: UserContext):
    # Only users with AGENT_WRITE can access
    pass
```

#### System Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| `admin` | Full system access | All permissions |
| `agent_designer` | Create and manage agents | agent:*, memory:read/write |
| `operator` | Execute and monitor agents | agent:execute, agent:read, session:* |
| `viewer` | Read-only access | *:read |
| `auditor` | Compliance and audit access | audit:*, report:* |

---

## 2. Evidence & Source Tracking

### Evidence Model

All agent actions generate evidence records:

```python
from taskforce.core.domain.evidence import Evidence, EvidenceType

evidence = Evidence(
    evidence_id="ev-123",
    session_id="session-456",
    evidence_type=EvidenceType.TOOL_RESULT,
    source="semantic_search",
    content={"query": "...", "results": [...]},
    timestamp=datetime.now(timezone.utc),
    metadata={"confidence": 0.95}
)
```

### RAG Citations

RAG tool results include automatic citation extraction:

```python
from taskforce.infrastructure.tools.rag.citations import (
    RAGCitationExtractor,
    CitationFormatter,
    CitationStyle
)

# Extract citations from search results
citations = RAGCitationExtractor.extract_from_semantic_search(result)

# Format for output
formatter = CitationFormatter(style=CitationStyle.INLINE)
formatted = formatter.format_citations(text, citations)

print(formatted.text)       # Text with [1], [2] markers
print(formatted.references) # List of formatted references
```

---

## 3. Secure Memory Governance

### Memory Encryption

Sensitive data is encrypted at rest:

```python
from taskforce.infrastructure.persistence.encryption import (
    EncryptedStateManager,
    EncryptionConfig
)

config = EncryptionConfig(
    algorithm="AES-256-GCM",
    key_source="env:ENCRYPTION_KEY"
)

manager = EncryptedStateManager(config)
await manager.save_state(session_id, sensitive_data)
```

### Memory Access Control

Fine-grained access control for memory resources:

```python
from taskforce.core.domain.memory_acl import (
    MemoryACLManager,
    MemoryPermission,
    SensitivityLevel,
    MemoryScope
)

acl_manager = MemoryACLManager()

# Create ACL for a memory resource
acl = acl_manager.create_acl(
    resource_id="mem-123",
    resource_type="conversation",
    owner_id="user-456",
    tenant_id="acme-corp",
    sensitivity=SensitivityLevel.CONFIDENTIAL,
    scope=MemoryScope.TENANT
)

# Check access
if acl_manager.check_access(
    resource_id="mem-123",
    user_id="user-789",
    tenant_id="acme-corp",
    roles={"operator"},
    permission=MemoryPermission.READ
):
    # Access granted
    pass
```

---

## 4. Enterprise Operations

### SLA Metrics

Collect and export metrics for SLA monitoring:

```python
from taskforce.infrastructure.metrics import MetricsCollector

collector = MetricsCollector()

# Record metrics
collector.record_latency("agent_execution", 1.5)
collector.record_counter("tool_calls", tags={"tool": "python"})
collector.record_gauge("active_sessions", 42)

# Export to Prometheus
metrics = collector.export_prometheus()
```

### Usage Tracking

Track usage for billing and capacity planning:

```python
from taskforce.application.reporting import UsageTracker

tracker = UsageTracker()

# Record token usage
tracker.record_tokens(
    tenant_id="acme-corp",
    input_tokens=1000,
    output_tokens=500,
    model="gpt-4o",
    session_id="session-123"
)

# Get aggregation
aggregation = tracker.get_aggregation(
    tenant_id="acme-corp",
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 31)
)
```

### Cost Reporting

Calculate costs based on usage:

```python
from taskforce.application.reporting import CostCalculator

calculator = CostCalculator()

# Generate cost report
report = calculator.generate_report(aggregation)

print(f"Total cost: ${report.total_cost}")
for line in report.line_items:
    print(f"  {line.description}: ${line.amount}")
```

---

## 5. Compliance & Audit

### Compliance Evidence Export

Export compliance evidence for audits:

```python
from taskforce.application.reporting import (
    ComplianceEvidenceCollector,
    ComplianceReportGenerator,
    ComplianceFramework
)

collector = ComplianceEvidenceCollector()
generator = ComplianceReportGenerator(collector)

# Generate SOC2 report
report = generator.generate_soc2_report(
    period_start=date(2026, 1, 1),
    period_end=date(2026, 1, 31),
    tenant_id="acme-corp"
)

# Export as package
from taskforce.application.reporting import export_compliance_package

package = export_compliance_package(
    report,
    format="json",
    include_evidence=True
)
```

### GDPR Processing Records

Track data processing for GDPR compliance:

```python
from taskforce.application.reporting import GDPRProcessingRecord

# Generate GDPR records
records = generator.generate_gdpr_records(
    tenant_id="acme-corp",
    data_subjects=["user@example.com"],
    processing_purpose="AI agent execution"
)
```

---

## 6. Agent Catalog & Versioning

### Agent Catalog

Manage agents with versioning and lifecycle:

```python
from taskforce.application.catalog import (
    AgentCatalog,
    VersionStatus
)

catalog = AgentCatalog()

# Create agent
entry = catalog.create_agent(
    tenant_id="acme-corp",
    name="Customer Support Agent",
    category="support",
    tags={"production", "nlp"},
    initial_definition={"tools": ["semantic_search", "send_email"]}
)

# Create new version
version = catalog.create_version(
    agent_id=entry.agent_id,
    version_number="1.1.0",
    definition={"tools": ["semantic_search", "send_email", "create_ticket"]},
    changelog="Added ticket creation capability"
)
```

### Version Lifecycle

Agents follow a governed lifecycle:

```
DRAFT → PENDING_APPROVAL → APPROVED → PUBLISHED → DEPRECATED → ARCHIVED
```

```python
# Submit for approval
catalog.submit_for_approval(agent_id, version_id)

# Approve (requires approver role)
catalog.approve_version(agent_id, version_id, approved_by="admin-1")

# Publish (makes it the current version)
catalog.publish_version(agent_id, version_id)
```

---

## 7. Approval Workflows

### Workflow Manager

Configure approval workflows for governed changes:

```python
from taskforce.application.workflows import (
    WorkflowManager,
    ApprovalWorkflow,
    RequestType
)

manager = WorkflowManager()

# Register custom workflow
workflow = ApprovalWorkflow(
    workflow_id="strict-publish",
    tenant_id="acme-corp",
    name="Strict Agent Publishing",
    request_type=RequestType.AGENT_PUBLISH,
    required_approvers=2,
    allowed_approver_roles={"admin", "agent_designer"},
    auto_expire_hours=48
)
manager.register_workflow(workflow)
```

### Creating Approval Requests

```python
# Create request
request = manager.create_request(
    tenant_id="acme-corp",
    request_type=RequestType.AGENT_PUBLISH,
    resource_type="agent",
    resource_id="agent-123",
    requester_id="user-456",
    title="Publish Customer Support Agent v1.1.0",
    description="Added ticket creation capability"
)

# List pending requests for approver
pending = manager.list_pending_for_approver(
    tenant_id="acme-corp",
    user_id="admin-1",
    user_roles={"admin"}
)

# Approve
manager.approve_request(request.request_id, "admin-1", "Approved after review")
```

### Event Callbacks

React to workflow events:

```python
def on_approved(request):
    # Automatically publish when approved
    catalog.publish_version(request.resource_id, request.payload["version_id"])

manager.on_event("request_approved", on_approved)
```

---

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ENCRYPTION_KEY` | AES-256 encryption key for memory | Yes (prod) |
| `JWT_SECRET` | Secret for JWT token signing | Yes |
| `JWT_ALGORITHM` | JWT algorithm (default: HS256) | No |
| `JWT_ISSUER` | JWT issuer claim | No |

### Profile Configuration

Enable enterprise features in your profile:

```yaml
# configs/enterprise.yaml
profile: enterprise

enterprise:
  multi_tenant: true
  encryption:
    enabled: true
    algorithm: AES-256-GCM
  rbac:
    enabled: true
    default_role: viewer
  audit:
    enabled: true
    retention_days: 365
  compliance:
    frameworks:
      - SOC2
      - ISO27001
      - GDPR
```

---

## See Also

- [API Guide](../api.md) - REST API documentation including Admin APIs
- [Architecture](../architecture.md) - System architecture overview
- [ADR-003: Enterprise Transformation](../adr/adr-003-enterprise-transformation.md) - Decision record
