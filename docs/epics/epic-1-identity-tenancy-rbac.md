# Epic 1: Identity, Tenancy & RBAC Foundation

**Projekt:** PyTaskforce Enterprise Transformation
**Phase:** 1
**Priorität:** Critical
**Status:** Draft

---

## Epic Title

**Multi-Tenant Identity & RBAC Foundation** - Brownfield Enhancement

## Epic Goal

Sichere, isolierte Nutzung der Plattform durch mehrere Organisationen, Teams und Rollen ermöglichen, ohne die bestehende Clean Architecture zu brechen.

## Epic Description

### Existing System Context

- **Current functionality:** Single-tenant Agent-Ausführung mit session-basierter Isolation
- **Technology stack:** Python 3.11, FastAPI, Hexagonal Architecture, Protocol-based DI
- **Integration points:**
  - `src/taskforce/api/server.py` (API Layer)
  - `src/taskforce/application/factory.py` (Agent Creation)
  - `src/taskforce/core/interfaces/state.py` (State Protocol)

### Enhancement Details

- **What's being added:**
  - `TenantContext` und `UserContext` Domain Models
  - JWT/OAuth2 Authentication Middleware
  - RBAC Policy Engine im Application Layer
  - Tenant-isolierte Session-Namespaces

- **How it integrates:**
  - Context-Injection via bestehende Ports (kein Core-Änderung)
  - Auth Middleware in API Layer
  - Policy Enforcement Point in Application Layer

- **Success criteria:**
  - Multi-Tenant API mit JWT Authentication
  - RBAC-konforme Agent Execution
  - Tenant-isolierte Sessions und Memory
  - Audit-Log für Benutzeraktionen

---

## Stories

### Story 1.1: Tenant & User Context Model

**Als** Platform Architect
**möchte ich** ein Tenant- und User-Kontext-Modell einführen
**damit** alle Plattform-Operationen einem Mandanten und Benutzer zugeordnet werden können.

**Acceptance Criteria:**

- [ ] `TenantContext` dataclass mit `tenant_id`, `name`, `settings`
- [ ] `UserContext` dataclass mit `user_id`, `tenant_id`, `roles[]`, `attributes`
- [ ] Protocol `IdentityProviderProtocol` in `core/interfaces/`
- [ ] Context-Propagation durch Application Layer
- [ ] Unit Tests für Context-Modelle

**Technical Notes:**

- Models in `src/taskforce/core/domain/identity.py`
- Protocol in `src/taskforce/core/interfaces/identity.py`
- Keine direkten Infrastructure-Imports im Core

---

### Story 1.2: Authentication Middleware

**Als** API Consumer
**möchte ich** mich sicher via JWT/OAuth2 authentifizieren
**damit** nur autorisierte Benutzer auf die Plattform zugreifen können.

**Acceptance Criteria:**

- [ ] JWT Token Validation Middleware
- [ ] OAuth2/OIDC Provider Integration (konfigurierbar)
- [ ] Entfernung offener CORS-Defaults (`allow_origins=["*"]`)
- [ ] Token-to-UserContext Mapping
- [ ] API Key Fallback für Service-to-Service
- [ ] Integration Tests mit Mock-Tokens

**Technical Notes:**

- Middleware in `src/taskforce/api/middleware/auth.py`
- Config in `configs/security.yaml`
- Dependency Injection via FastAPI `Depends()`

---

### Story 1.3: RBAC Policy Engine

**Als** Platform Administrator
**möchte ich** rollenbasierte Zugriffskontrollen durchsetzen
**damit** Benutzer nur erlaubte Aktionen ausführen können.

**Acceptance Criteria:**

- [ ] RBAC Matrix (Role × Action × Resource)
- [ ] Policy Enforcement Point (PEP) im Application Layer
- [ ] Prüfung bei: Agent-Start, Tool-Aufruf, Memory-Zugriff
- [ ] Vordefinierte Rollen: Admin, Agent Designer, Operator, Auditor
- [ ] Policy-Konfiguration via YAML
- [ ] Integration mit `AgentFactory` und `AgentExecutor`

**Technical Notes:**

- Policy Engine in `src/taskforce/application/policy/`
- Integration via Decorator oder Context Manager
- Logging aller Policy-Entscheidungen

---

## Compatibility Requirements

- [x] Bestehende APIs bleiben funktional (Backward Compatible Mode)
- [x] Core Domain bleibt unverändert (nur neue Protocols)
- [x] Bestehende Configs funktionieren weiterhin
- [ ] Auth kann optional deaktiviert werden (dev mode)

## Risk Mitigation

- **Primary Risk:** Breaking Change für existierende API-Clients
- **Mitigation:** Backward-Compatible Mode mit Warning-Header
- **Rollback Plan:** Feature-Flag `AUTH_ENABLED=false`

## Definition of Done

- [ ] Alle Stories completed mit Acceptance Criteria
- [ ] Bestehende Tests grün (keine Regression)
- [ ] Neue Unit + Integration Tests (≥80% Coverage)
- [ ] API Dokumentation aktualisiert
- [ ] Security Review durchgeführt

---

## Dependencies

- **Depends on:** None (Foundation Epic)
- **Blocks:** Epic 2, Epic 3, Epic 4, Epic 5
