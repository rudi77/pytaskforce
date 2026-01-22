# Epic 3: Secure Memory Governance

**Projekt:** PyTaskforce Enterprise Transformation
**Phase:** 3
**Priorität:** High
**Status:** Draft

---

## Epic Title

**Encrypted Memory & Access Control** - Brownfield Enhancement

## Epic Goal

Sicherer, kontrollierter Umgang mit persistentem Wissen unter Einhaltung von Datenschutz- und Compliance-Anforderungen.

## Epic Description

### Existing System Context

- **Current functionality:** FileStateManager, Tool Result Store, MCP Memory Server
- **Technology stack:** File-based persistence, JSONL format, Session-scoped cleanup
- **Integration points:**
  - `src/taskforce/infrastructure/persistence/`
  - `src/taskforce/infrastructure/cache/tool_result_store.py`
  - MCP Memory Server Integration

### Enhancement Details

- **What's being added:**
  - Encryption at Rest (per Tenant Key)
  - Configurable Retention Policies
  - Fine-grained Memory ACLs
  - Right-to-be-Forgotten Support

- **How it integrates:**
  - Encryption Layer in Persistence Adapters
  - ACL Checks integrated with RBAC (Epic 1)
  - Retention Scheduler als Background Service

- **Success criteria:**
  - Memory verschlüsselt pro Tenant
  - Retention Policies durchgesetzt
  - ACL-basierter Memory-Zugriff
  - Deletion auf Anfrage möglich

---

## Stories

### Story 3.1: Memory Encryption

**Als** Security Officer
**möchte ich** dass alle persistierten Daten verschlüsselt werden
**damit** bei einem Datenleck keine Klartextdaten exponiert werden.

**Acceptance Criteria:**

- [ ] Encryption at Rest für FileStateManager
- [ ] Per-Tenant Encryption Keys (KMS-kompatibel)
- [ ] Transparent Encryption/Decryption
- [ ] Key Rotation Support
- [ ] Performance Benchmark

**Technical Notes:**

- Fernet (AES-128) oder AES-256-GCM
- Key Storage: Environment Variable oder Vault
- Encryption Adapter Pattern für Persistence Layer

---

### Story 3.2: Retention Policies

**Als** Data Protection Officer
**möchte ich** automatische Löschung alter Daten nach definierten Zeiträumen
**damit** wir Compliance-Anforderungen erfüllen (GDPR, etc.).

**Acceptance Criteria:**

- [ ] Configurable Retention per Data Type
- [ ] Automatic Cleanup Scheduler
- [ ] Explicit Delete API (Right-to-be-Forgotten)
- [ ] Audit Log für Löschungen
- [ ] Dry-Run Mode für Testing

**Technical Notes:**

- Config: `retention.session_data: 30d`, `retention.tool_results: 7d`
- Background Task via AsyncIO oder APScheduler
- Soft-Delete Option für Audit Trail

---

### Story 3.3: Memory Access Control

**Als** Platform Administrator
**möchte ich** granulare Zugriffsrechte auf Memory-Objekte setzen
**damit** sensible Daten nur autorisierten Benutzern zugänglich sind.

**Acceptance Criteria:**

- [ ] Memory Objects mit ACL: `read`, `write`, `reference`
- [ ] ACL-Verknüpfung mit RBAC-Rollen (Epic 1)
- [ ] Scope-Policies: Project, Time, Sensitivity
- [ ] ACL-Enforcement im ToolResultStore
- [ ] Integration Tests

**Technical Notes:**

- ACL Model in `core/domain/memory_acl.py`
- Integration mit Policy Engine (Epic 1, Story 1.3)
- Default: Tenant-scoped read/write

---

## Compatibility Requirements

- [x] Bestehende Memory-Formate bleiben lesbar (Migration)
- [x] Unverschlüsselte Legacy-Daten werden on-read migriert
- [x] API bleibt unverändert
- [ ] Performance ≤10% Overhead

## Risk Mitigation

- **Primary Risk:** Data Loss bei Key-Verlust
- **Mitigation:** Key Backup, Key Escrow Option
- **Rollback Plan:** Migration Script zu unverschlüsseltem Format

## Definition of Done

- [ ] Encryption aktiv für neue Daten
- [ ] Retention Scheduler läuft
- [ ] ACLs durchgesetzt
- [ ] Migration für Legacy-Daten
- [ ] Dokumentation aktualisiert

---

## Dependencies

- **Depends on:** Epic 1 (Identity & RBAC), Epic 2 (Evidence Tracking)
- **Blocks:** Epic 4, Epic 5
