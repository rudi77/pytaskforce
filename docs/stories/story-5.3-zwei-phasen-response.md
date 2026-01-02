# Story 5.3: Zwei-Phasen-Response für User-Antworten - Brownfield Addition

<!-- Powered by BMAD™ Core -->
<!-- Epic: epic-5-minimal-json-architecture.md -->
<!-- Priority: OPTIONAL - Kann nach Story 5.1 + 5.2 implementiert werden -->
<!-- Status: Ready for Review -->

## User Story

**Als** User des TaskForce-Agents,  
**möchte ich** dass finale Antworten immer als sauberes Markdown formatiert sind,  
**damit** ich keine JSON-Artefakte oder Formatierungsprobleme in den Antworten sehe.

---

## Story Context

### Existing System Integration

- **Integrates with:** 
  - `core/domain/agent.py` – `_execute_action()`, `_extract_final_message()`
  - Neuer `ActionType.RESPOND` aus Story 5.2
- **Technology:** OpenAI API, separater LLM-Call ohne `response_format`
- **Follows pattern:** Bestehender LLM-Call-Pattern via `llm_provider.complete()`
- **Touch points:** Agent-Execution-Flow nach `RESPOND` Action

### Problem Statement

**Aktuell:** Das LLM muss im Thought-JSON auch die `summary` als Markdown liefern. Das führt zu:
1. JSON-Escaping-Problemen bei Markdown (Backticks, Newlines)
2. Token-Verschwendung (Markdown in JSON verpackt)
3. Häufigen Parse-Fehlern bei langen Antworten

**Ziel:** Trennung von **Steuerkanal** (JSON) und **User-Kanal** (Markdown)

```
Phase 1: JSON-Call → { "action": "respond" }
Phase 2: Markdown-Call → "Hier ist deine Antwort:\n\n- Item 1\n- Item 2"
```

---

## Acceptance Criteria

### Functional Requirements

1. **Zwei-Phasen-Flow:** Bei `action: "respond"` wird ein zweiter LLM-Call ohne JSON-Zwang ausgeführt
2. **Reiner Markdown-Output:** Die finale User-Antwort enthält keine JSON-Artefakte
3. **Context-Übergabe:** Der zweite Call erhält relevante `PREVIOUS_RESULTS` als Kontext

### Integration Requirements

4. `_execute_action()` erkennt `ActionType.RESPOND` und triggert Phase 2
5. Neuer LLM-Call nutzt `response_format=None` (kein JSON-Mode)
6. Bestehende `_extract_final_message()` Logik wird angepasst

### Quality Requirements

7. Performance-Impact < 500ms pro Antwort (akzeptabler Trade-off)
8. Streaming-kompatibel (falls später benötigt)
9. Unit-Tests für Zwei-Phasen-Flow

---

## Technical Implementation

### 1. Neuer Response-Generator

```python
# In agent.py

async def _generate_markdown_response(
    self, 
    context: dict[str, Any],
    previous_results: list[dict]
) -> str:
    """
    Generate final markdown response without JSON constraints.
    
    Called after ActionType.RESPOND to produce clean user output.
    """
    # Kontext für finale Antwort aufbereiten
    results_summary = self._summarize_results(previous_results)
    
    prompt = f"""Formuliere eine klare, gut strukturierte Antwort für den User.

## Kontext
{context.get('mission', 'Keine Mission angegeben')}

## Ergebnisse aus vorherigen Schritten
{results_summary}

## Anweisungen
- Antworte in Markdown
- Nutze Bullet-Points für Listen
- Fasse die wichtigsten Erkenntnisse zusammen
- KEIN JSON, keine Code-Blöcke außer wenn inhaltlich nötig
"""
    
    result = await self.llm_provider.complete(
        messages=[
            {"role": "system", "content": "Du bist ein hilfreicher Assistent."},
            {"role": "user", "content": prompt},
        ],
        model=self.model_alias,
        response_format=None,  # KEIN JSON-Mode!
        temperature=0.3,
    )
    
    if not result.get("success"):
        return "Entschuldigung, ich konnte keine Antwort generieren."
    
    return result["content"]
```

### 2. Integration in `_execute_action()`

```python
async def _execute_action(
    self, action: Action, step: TodoItem, state: dict[str, Any], session_id: str
) -> Observation:
    """Execute action and return observation."""
    
    if action.type == ActionType.TOOL_CALL:
        return await self._execute_tool(action, step)
    
    elif action.type == ActionType.ASK_USER:
        # ... bestehende Logik ...
    
    elif action.type == ActionType.RESPOND:
        # NEU: Zwei-Phasen-Response
        context = await self._build_response_context(state, session_id)
        previous_results = state.get("previous_results", [])
        
        markdown_response = await self._generate_markdown_response(
            context, previous_results
        )
        
        return Observation(
            success=True, 
            data={"summary": markdown_response}
        )
    
    # Legacy-Support
    elif action.type in (ActionType.FINISH_STEP, ActionType.COMPLETE):
        # Fallback auf alte Logik mit summary aus Action
        return Observation(success=True, data={"summary": action.summary})
```

### 3. Response-Context Builder

```python
async def _build_response_context(
    self, state: dict[str, Any], session_id: str
) -> dict[str, Any]:
    """Build context for markdown response generation."""
    return {
        "mission": state.get("mission", ""),
        "conversation_history": state.get("conversation_history", [])[-5:],  # Letzte 5
        "user_answers": state.get("answers", {}),
    }

def _summarize_results(self, previous_results: list[dict]) -> str:
    """Summarize previous tool results for response context."""
    if not previous_results:
        return "Keine vorherigen Ergebnisse."
    
    summaries = []
    for i, result in enumerate(previous_results[-5:], 1):  # Letzte 5
        tool = result.get("tool", "unknown")
        success = "✓" if result.get("success") else "✗"
        data_preview = str(result.get("data", ""))[:200]
        summaries.append(f"{i}. [{success}] {tool}: {data_preview}")
    
    return "\n".join(summaries)
```

---

## Technical Notes

- **Integration Approach:** Neuer Code-Pfad für `RESPOND`, Legacy bleibt intakt
- **Existing Pattern Reference:** LLM-Calls wie in `PlanGenerator.generate_plan()`
- **Key Constraints:** 
  - Zweiter LLM-Call erhöht Latenz (~300-500ms)
  - Context muss schlank bleiben (Token-Limit)
  - Streaming später nachrüstbar

---

## Definition of Done

- [x] `_generate_markdown_response()` implementiert
- [x] `_execute_action()` für `RESPOND` erweitert
- [x] Context-Builder und Result-Summarizer implementiert
- [x] Unit-Tests für Zwei-Phasen-Flow
- [ ] Performance-Test: < 500ms zusätzliche Latenz (to be validated in production)
- [x] Bestehende Tests passieren

---

## Dev Agent Record

### Status: Ready for Review

### Agent Model Used: Claude Opus 4.5

### File List

| File | Change Type |
|------|-------------|
| `src/taskforce/core/domain/agent.py` | Modified - Added _generate_markdown_response(), _build_response_context_for_respond(), _summarize_results_for_response(), modified _execute_action() for two-phase RESPOND |
| `tests/unit/test_agent.py` | Modified - Added 7 new tests for Zwei-Phasen-Flow, updated existing tests to include markdown mock |

### Change Log

- Implemented `_generate_markdown_response()` method that generates clean markdown without JSON mode
- Implemented `_build_response_context_for_respond()` to prepare context for response generation
- Implemented `_summarize_results_for_response()` to format previous tool results for LLM context
- Modified `_execute_action()` to trigger two-phase flow when `ActionType.RESPOND` is detected
- Updated `_execute_action()` signature to accept optional `todolist` parameter for extracting previous results
- `ActionType.COMPLETE` retains legacy behavior (uses summary directly, no two-phase)
- Added 7 new unit tests: `test_respond_action_triggers_two_phase_flow`, `test_two_phase_response_includes_previous_results`, `test_two_phase_response_handles_llm_failure_gracefully`, `test_complete_action_skips_two_phase`, `test_summarize_results_for_response_empty_list`, `test_summarize_results_for_response_with_results`, `test_build_response_context_for_respond`
- Updated 6 existing tests to include markdown generation mock for two-phase flow
- All 39 agent tests pass, no regressions in core functionality

### Debug Log References

None - implementation was straightforward.

### Completion Notes

- Two-phase flow only triggers for `RESPOND` action type (new minimal schema action)
- `COMPLETE` action retains legacy single-phase behavior for early exit scenarios
- The second LLM call uses `response_format=None` to allow free-form markdown
- Graceful fallback message if markdown generation fails
- Previous results are extracted from todolist and formatted with success/failure indicators

---

## Risk and Compatibility Check

### Minimal Risk Assessment

- **Primary Risk:** Zusätzliche Latenz durch zweiten LLM-Call
- **Mitigation:** Schlanker Context, schnelles Modell (gpt-4o-mini), Caching optional
- **Rollback:** `RESPOND` intern auf `FINISH_STEP` mappen → alte Logik

### Compatibility Verification

- [x] Keine Breaking Changes (Legacy-Pfad bleibt)
- [x] Keine Datenbankänderungen
- [x] Keine UI-Änderungen (bessere Markdown-Qualität)
- [x] Performance-Impact: +300-500ms (akzeptabel für bessere UX)

---

## Validation Checklist

### Scope Validation

- [x] Story kann in einer Development-Session abgeschlossen werden (~3-4h)
- [x] Integration-Ansatz ist klar (neuer Code-Pfad)
- [x] Folgt bestehenden LLM-Call-Patterns
- [x] Kein Architektur-Redesign erforderlich

### Clarity Check

- [x] Zwei-Phasen-Flow ist klar definiert
- [x] Performance-Erwartung ist spezifiziert
- [x] Success Criteria sind testbar
- [x] Rollback-Strategie ist klar

---

## Files to Modify

| File | Änderung |
|------|----------|
| `core/domain/agent.py` | `_generate_markdown_response()`, `_execute_action()` erweitern |
| `tests/test_agent.py` | Tests für Zwei-Phasen-Flow |

---

## Sequence Diagram

```
User Request
     │
     ▼
┌─────────────────┐
│ _generate_thought │  ──► JSON: { "action": "respond" }
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ _execute_action()   │  ──► Erkennt RESPOND
└────────┬────────────┘
         │
         ▼
┌──────────────────────────┐
│ _generate_markdown_response │  ──► LLM-Call OHNE JSON-Mode
└────────┬─────────────────┘
         │
         ▼
    Markdown Output
    an User
```

---

## Dependencies

- **Requires:** Story 5.2 (Minimales Action-Schema mit `RESPOND` Type)
- **Optional after:** Story 5.1 (Fallback wird mit Zwei-Phasen weniger relevant)

---

*Story erstellt: 03.12.2025 | Epic: 5 - Minimal-JSON Architecture | Priority: Optional*

