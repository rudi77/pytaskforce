# ADR-003: Enterprise Transformation

**Status:** Accepted
**Date:** 2026-01-22
**Decision Makers:** Architecture Team

## Context

PyTaskforce was a technically mature agent orchestration platform but lacked enterprise-ready capabilities required for production deployments in regulated environments. Organizations needed:

- Multi-tenant isolation and identity management
- Audit trails and compliance evidence
- Secure handling of sensitive data
- Usage tracking and cost attribution
- Governed agent lifecycle management

## Decision

We implemented a comprehensive Enterprise & Compliance Enablement suite consisting of 5 epics and 15 stories:

### Epic 1: Identity, Tenancy & RBAC Foundation
- Tenant and User context models in `core/domain/identity.py`
- JWT/OAuth2 and API Key authentication in `infrastructure/auth/`
- RBAC policy engine in `application/policy/`
- Auth middleware in `api/middleware/auth.py`

### Epic 2: Evidence & Source Tracking
- Evidence model in `core/domain/evidence.py`
- RAG citation support in `infrastructure/tools/rag/citations.py`

### Epic 3: Secure Memory Governance
- Encryption support in `infrastructure/persistence/encryption.py`
- Memory ACL system in `core/domain/memory_acl.py`

### Epic 4: Enterprise Operations
- SLA metrics collector in `infrastructure/metrics/collector.py`
- Usage tracking in `application/reporting/usage.py`
- Cost calculation in `application/reporting/cost.py`
- Compliance evidence export in `application/reporting/compliance.py`

### Epic 5: Productization
- Admin APIs in `api/routes/admin/`
- Agent catalog with versioning in `application/catalog/`
- Approval workflows in `application/workflows/`

## Architecture Principles

All implementations follow the existing Clean Architecture:

1. **Core Layer** - Pure domain models and protocols (Identity, Evidence, MemoryACL)
2. **Infrastructure Layer** - External integrations (Auth providers, Encryption, Metrics)
3. **Application Layer** - Use cases (Policy engine, Reporting, Catalog, Workflows)
4. **API Layer** - Entrypoints (Auth middleware, Admin routes)

Import rules were strictly maintained:
- Core NEVER imports from Infrastructure
- Infrastructure implements Core Protocols
- Application orchestrates all layers
- API depends only on Application

## Consequences

### Positive
- Multi-tenant deployments now supported with proper isolation
- Full audit trail for compliance (SOC2, ISO 27001, GDPR)
- Secure handling of sensitive data with encryption and ACLs
- Clear usage tracking for billing and capacity planning
- Governed agent lifecycle with approval workflows
- 174 new tests ensuring enterprise feature quality

### Negative
- Increased complexity in request handling (auth middleware)
- Additional configuration required for enterprise features
- Storage overhead for audit trails and evidence

### Neutral
- Enterprise features are opt-in via configuration
- No breaking changes to existing API contracts
- Backward compatible with non-enterprise deployments

## References

- [Enterprise Features Documentation](../features/enterprise.md)
- [Epic Index](../epics/index.md)
- [ADR-002: Clean Architecture Layers](adr-002-clean-architecture-layers.md)
