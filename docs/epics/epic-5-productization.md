# Epic 5: Productization & Governance UI

**Projekt:** PyTaskforce Enterprise Transformation
**Phase:** 5
**Priorität:** Medium
**Status:** Draft

---

## Epic Title

**Admin Portal & Agent Governance** - Brownfield Enhancement

## Epic Goal

Transformation von Framework zu Produkt mit Admin-UI, Agent-Katalog und Governance-Workflows.

## Epic Description

### Existing System Context

- **Current functionality:** CLI-basierte Administration, YAML Configs, API Endpoints
- **Technology stack:** Typer CLI, FastAPI, Profile-based Configuration
- **Integration points:**
  - `src/taskforce/api/cli/`
  - `src/taskforce/api/routes/`
  - `configs/`

### Enhancement Details

- **What's being added:**
  - Admin Web UI (Tenants, Roles, Policies)
  - Agent Catalog mit Approval Workflows
  - Versioned Agents & Configs
  - Self-Service Portal

- **How it integrates:**
  - Frontend als separates Package/Repo
  - Backend APIs bereits vorhanden (erweitern)
  - Config Storage in DB statt Files

- **Success criteria:**
  - Admin kann Tenants/Roles verwalten
  - Agents können katalogisiert werden
  - Approval Workflows für High-Risk Agents
  - Versionierung für Rollbacks

---

## Stories

### Story 5.1: Admin API Extensions

**Als** Platform Administrator
**möchte ich** Tenants, Roles und Policies via API verwalten
**damit** ich die Plattform ohne direkten DB-Zugriff administrieren kann.

**Acceptance Criteria:**

- [ ] CRUD APIs: /tenants, /users, /roles, /policies
- [ ] Bulk Operations Support
- [ ] Audit Trail für Admin Actions
- [ ] OpenAPI Spec aktualisiert
- [ ] Admin Role Required

**Technical Notes:**

- Routes in `src/taskforce/api/routes/admin/`
- Service Layer in `application/admin/`
- Permissions: Admin-only

---

### Story 5.2: Agent Catalog & Versioning

**Als** Agent Designer
**möchte ich** Agents in einem Katalog veröffentlichen und versionieren
**damit** andere Teams sie nutzen können.

**Acceptance Criteria:**

- [ ] Agent Catalog API: List, Get, Publish
- [ ] Semantic Versioning für Agent Definitions
- [ ] Agent Metadata: Description, Author, Tags
- [ ] Deprecation Support
- [ ] Search & Filter

**Technical Notes:**

- Catalog Storage: DB oder File-based
- Version Format: `agent@1.2.3`
- Migration für bestehende Agent Definitions

---

### Story 5.3: Approval Workflows

**Als** Security Officer
**möchte ich** dass High-Risk Agents vor Deployment genehmigt werden
**damit** wir ungeprüfte Agents verhindern.

**Acceptance Criteria:**

- [ ] Risk Classification für Agents (Low/Medium/High)
- [ ] Approval Workflow: Submit → Review → Approve/Reject
- [ ] Multi-Level Approval für High-Risk
- [ ] Notification System (Email/Webhook)
- [ ] Approval History

**Technical Notes:**

- Workflow Engine in `application/workflows/`
- State Machine Pattern
- Integration mit Notification Service (optional)

---

## Compatibility Requirements

- [x] CLI bleibt funktional
- [x] Bestehende Configs bleiben gültig
- [x] API Backward Compatible
- [ ] UI ist optional (API-first)

## Risk Mitigation

- **Primary Risk:** Scope Creep in UI Development
- **Mitigation:** API-first, UI als separates Projekt
- **Rollback Plan:** CLI-basierte Administration bleibt verfügbar

## Definition of Done

- [ ] Admin APIs verfügbar
- [ ] Agent Catalog funktioniert
- [ ] Approval Workflows implementiert
- [ ] API Dokumentation komplett
- [ ] (Optional) Basic Admin UI

---

## Dependencies

- **Depends on:** Epic 1, Epic 2, Epic 3, Epic 4
- **Blocks:** None (Final Epic)
