# Epic 2: Evidence & Source Tracking

**Projekt:** PyTaskforce Enterprise Transformation
**Phase:** 2
**Priorität:** Critical
**Status:** Draft

---

## Epic Title

**Evidence-Based Agent Responses** - Brownfield Enhancement

## Epic Goal

Nachvollziehbare, prüfbare Agentenantworten ermöglichen ("Why did the agent say this?") für Compliance und Trust.

## Epic Description

### Existing System Context

- **Current functionality:** `ExecutionResult` mit `final_message`, `execution_history`, `token_usage`
- **Technology stack:** ToolResultStore mit Handles, OpenTelemetry Tracing
- **Integration points:**
  - `src/taskforce/core/domain/models.py` (ExecutionResult)
  - `src/taskforce/infrastructure/cache/tool_result_store.py`
  - `src/taskforce/core/domain/planning_strategy.py`

### Enhancement Details

- **What's being added:**
  - `EvidenceItem` Model mit Source-Referenzen
  - `evidence: list[EvidenceItem]` in ExecutionResult
  - Tool→Answer Lineage Tracking
  - RAG Citation Support

- **How it integrates:**
  - Evidence Collection in Planning Strategies
  - Automatic Citation Building für RAG Tools
  - Export-Format für Audit (JSON/PDF)

- **Success criteria:**
  - Jede Agent-Antwort enthält Evidence-Chain
  - Tool-Ergebnisse sind mit Final Answer verknüpft
  - RAG-Antworten enthalten Document Citations
  - Audit-Export verfügbar

---

## Stories

### Story 2.1: Evidence Model & Collection

**Als** Compliance Officer
**möchte ich** zu jeder Agentenantwort die verwendeten Quellen sehen
**damit** ich die Herkunft von Informationen nachvollziehen kann.

**Acceptance Criteria:**

- [ ] `EvidenceItem` dataclass: `source_type`, `source_id`, `snippet`, `confidence`
- [ ] `evidence: list[EvidenceItem]` Feld in `ExecutionResult`
- [ ] Evidence Collection in `NativeReActStrategy`
- [ ] Evidence Collection in `PlanAndExecuteStrategy`
- [ ] Evidence Collection in `PlanAndReactStrategy`
- [ ] Unit Tests für Evidence Model

**Technical Notes:**

- Model in `src/taskforce/core/domain/evidence.py`
- Integration in Planning Strategies via Hook-Pattern
- Backward Compatible (evidence = [] default)

---

### Story 2.2: Tool Result Lineage

**Als** Auditor
**möchte ich** nachvollziehen, welche Tool-Ergebnisse zur finalen Antwort beigetragen haben
**damit** ich die Entscheidungskette des Agenten prüfen kann.

**Acceptance Criteria:**

- [ ] ToolResultHandle erhält `used_in_answer: bool` Flag
- [ ] Lineage Tracking während Reasoning Steps
- [ ] Final Answer referenziert verwendete Handles
- [ ] Visualization-Option für Lineage Graph
- [ ] Integration Tests

**Technical Notes:**

- Erweiterung von `ToolResultHandle` in `core/interfaces/tool_result_store.py`
- Tracking in Planning Strategy Loops
- Optional: Mermaid-Export für Visualisierung

---

### Story 2.3: RAG Citation Support

**Als** Knowledge Worker
**möchte ich** automatische Quellenangaben bei RAG-basierten Antworten
**damit** ich die Vertrauenswürdigkeit einschätzen kann.

**Acceptance Criteria:**

- [ ] RAG Tools liefern: `document_id`, `chunk_id`, `score`, `title`
- [ ] Automatische Citation-Bildung aus RAG Results
- [ ] Inline-Zitate oder Appendix-Format (konfigurierbar)
- [ ] Citation-Format: `[1] Title, Section` oder ähnlich
- [ ] Integration Tests mit Sample Documents

**Technical Notes:**

- Erweiterung RAG Tools in `infrastructure/tools/rag/`
- Citation Formatter als Utility
- Config: `citation_style: inline | appendix | none`

---

## Compatibility Requirements

- [x] Bestehende ExecutionResult bleibt kompatibel
- [x] Evidence ist optional (graceful degradation)
- [x] Keine Breaking Changes für Tool Implementations
- [ ] API Response erweitert, nicht geändert

## Risk Mitigation

- **Primary Risk:** Performance-Impact durch Evidence Collection
- **Mitigation:** Lazy Collection, Configurable Detail Level
- **Rollback Plan:** `EVIDENCE_ENABLED=false` Feature Flag

## Definition of Done

- [ ] Alle Stories completed
- [ ] Evidence in ExecutionResult verfügbar
- [ ] RAG Citations funktionieren
- [ ] Performance Benchmark (≤5% Overhead)
- [ ] Dokumentation aktualisiert

---

## Dependencies

- **Depends on:** Epic 1 (Identity & RBAC)
- **Blocks:** Epic 3, Epic 4, Epic 5
