# Epic 4: Agent Execution Efficiency Optimization - Brownfield Enhancement

## Epic Goal

Optimierung der ReAct-Loop-Performance des Execution Agents durch Eliminierung redundanter LLM-Aufrufe, Implementierung eines kontextbewussten Memory-Patterns und Einführung eines Fast-Path-Routers für einfache Anfragen. **Erwartetes Ergebnis**: Reduzierung der Token-Kosten um ~40% und der Latenz um ~50% bei Follow-up-Fragen.

## Epic Description

**Existing System Context:**

- **Current Functionality:** Der `Agent` (core/domain/agent.py) implementiert eine ReAct-Loop mit TodoList-basierter Planung. Jede User-Anfrage durchläuft: Planning → TodoList-Erstellung → Step-by-Step Execution mit Tool-Calls. Tools wie `llm_generate` werden für Textverarbeitung aufgerufen, obwohl der Agent selbst LLM-Capabilities hat.
- **Technology Stack:** Python 3.11, LiteLLM (GPT-4/Azure), Clean Architecture mit Protocol-Interfaces, structlog für Logging
- **Integration Points:** 
  - `LLMProviderProtocol` für LLM-Calls
  - `TodoListManagerProtocol` für Planung
  - `ToolProtocol` für Tool-Registry
  - System Prompts in `core/prompts/`
  - `AgentFactory` für Tool-Konfiguration

**Current Inefficiencies (from Trace Analysis):**

| Problem | Trace Evidence | Impact |
|:--------|:---------------|:-------|
| **llm_generate Anti-Pattern** | Agent ruft `llm_generate` Tool auf, um Text zusammenzufassen (Trace 25) | Doppelte Token-Kosten, Kontext-Verlust |
| **Redundante API-Calls** | `wiki_get_page_tree` wird in Trace 12 & 18 identisch aufgerufen | Unnötige Latenz, API-Throttling |
| **Planner-Overhead bei Follow-ups** | Einfache Frage "Was steht da drinnen?" triggert vollen Planning-Cycle (Trace 20/21) | ~100% Latenz-Overhead |
| **Token-Bloat im Prompt** | Tool-Definitionen als Raw-JSON im System-Prompt (2118 → 4501 Tokens) | Hohe Kosten pro Call |

**Enhancement Details:**

- **What's being added/changed:**
  1. Optimierter System-Prompt mit expliziten "Memory First" und "No llm_generate" Regeln
  2. Konditionale Tool-Registry (dynamisches Ausblenden irrelevanter Tools pro Agent-Profile)
  3. Fast-Path Router vor dem Planning-Agent für direkte Follow-ups
  
- **Integration Approach:** 
  - System-Prompt-Änderungen in `core/prompts/`
  - Router-Logik als Pre-Processing in `Agent.execute()` oder neue `Router`-Komponente
  - Tool-Filterung in `AgentFactory` basierend auf Agent-Profile
  
- **Success Criteria:** 
  - Keine `llm_generate` Tool-Calls mehr bei reinen Analyse-/Synthese-Aufgaben
  - Follow-up-Fragen umgehen den Planner (messbare Latenz-Reduktion)
  - Token-Count pro Conversation-Turn reduziert um mindestens 30%

## Stories

1. **Story 4.1: System-Prompt Optimization & `llm_generate` Elimination**
   - Refaktoriere den Execution-Agent System-Prompt mit expliziten Performance-Regeln
   - Entferne `llm_generate` aus der Standard-Tool-Registry
   - Dokumentiere das optimierte Prompt-Design

2. **Story 4.2: Context-Aware Memory Pattern (Redundancy Check)**
   - Implementiere "Memory First" Pattern im System-Prompt
   - Enriche `_build_thought_context()` um vollständige Conversation-History
   - Optional: In-Memory Cache für häufig abgefragte Tool-Ergebnisse

3. **Story 4.3: Fast-Path Router for Simple Follow-ups**
   - Implementiere Router-Komponente zur Klassifikation von Anfragen
   - Überspringe Planner für direkte Follow-up-Fragen
   - Fallback auf vollen Planning-Cycle für neue Missions

## Compatibility Requirements

- [x] Existing APIs remain unchanged (`Agent.execute()` Signatur unverändert)
- [x] Database schema changes are backward compatible (N/A)
- [x] UI changes follow existing patterns (N/A)
- [x] Performance impact is minimal (Performance-Verbesserung ist das Ziel)

## Risk Mitigation

- **Primary Risk:** Agent-Verhalten verändert sich subtil → Regressions in bestehenden Workflows
- **Mitigation:** 
  - Bestehende Unit-Tests erweitern um Prompt-basierte Assertions
  - A/B Testing mit altem vs. neuem Prompt auf Trace-Daten
  - Feature-Flag für "optimized_prompt" in Agent-Profile
- **Rollback Plan:** System-Prompt wird über YAML-Config geladen → einfaches Zurückswitchen auf alten Prompt ohne Code-Deploy

## Definition of Done

- [ ] All stories completed with acceptance criteria met
- [ ] Existing functionality verified through testing (`uv run pytest tests/unit tests/integration`)
- [ ] Integration points working correctly (LLM calls, Tool execution)
- [ ] Documentation updated appropriately (System-Prompt-Referenz in README)
- [ ] No regression in existing features (bestehende Agent-Workflows funktionieren)
- [ ] Trace-Analyse zeigt Effizienz-Verbesserungen (Token-Reduktion messbar)

## Metrics & Success Measurement

| Metric | Baseline | Target | Measurement Method |
|:-------|:---------|:-------|:-------------------|
| Token-Count pro Turn | ~4500 | <3000 | Trace-Analyse (llm_traces.jsonl) |
| Latenz Follow-up Frage | ~4s | <2s | API Response Time |
| Redundante Tool-Calls | Häufig | 0 | Trace-Analyse |
| `llm_generate` Calls | Vorhanden | 0 | Tool-Call Counter |


