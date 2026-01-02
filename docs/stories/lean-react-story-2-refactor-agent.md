# Story 2: Refactoring der `agent.py` (The Big Cut)

**Status:** Ready for Review
**Epic:** [Epic 6: Transition zu "Lean ReAct" Architektur](taskforce/docs/epics/epic-6-lean-react-transition.md)
**Priorität:** Hoch
**Schätzung:** 8 SP
**Abhängigkeiten:** Story 1 (PlannerTool)
**Agent Model Used:** Claude Opus 4.5

## Description

Als **Maintainer** möchte ich die `agent.py` radikal vereinfachen und von der komplexen "Plan-and-Execute" State-Machine befreien, um einen wartbaren, leichten "Lean Agent" zu erhalten, der flexibel auf LLM-Entscheidungen reagiert.

Dies ist der "destruktive" Teil des Epics: Wir entfernen alten Code (`TodoListManager`, `QueryRouter`, `ReplanStrategy`) und ersetzen ihn durch einen einfachen Loop.

## Technical Details

### 1. Cleanup (Removal)
Entferne folgende Komponenten/Imports aus `agent.py` (oder markiere sie als deprecated):
*   `TodoListManagerProtocol` & Usage
*   `QueryRouter` & Usage
*   `ReplanStrategy` & Usage
*   Die Unterscheidung `_execute_fast_path` vs `_execute_full_path`.
*   `_replan()` Methode.
*   `_get_next_actionable_step()` Logik.

### 2. Neue Klasse `LeanAgent`
Implementiere (oder refactoriere `Agent` zu) `LeanAgent`:

**Konstruktor:**
*   Nimmt `PlannerTool` als festes (oder injiziertes) Werkzeug entgegen.
*   Kein `todolist_manager` mehr.

**`execute(mission)` Methode:**
*   **Single Loop Design:**
    ```python
    while steps < MAX_STEPS:
        # 1. Get Plan Context (via PlannerTool)
        # 2. Build Prompt (See Story 4 for dynamic part)
        # 3. Call LLM
        # 4. Handle Tool Calls (See Story 3)
        # 5. Update History
    ```
*   **Return Value:** Gibt am Ende den Final Content zurück (kein komplexes `ExecutionResult` mit Steps-History mehr notwendig, bzw. vereinfacht).

### 3. Vereinfachtes Prompting
*   Entferne die komplexen JSON-Schema-Vorgaben im Code (`_generate_thought`).
*   Verlasse dich auf die System-Prompts (Kernel), die in Story 4 integriert werden.

## Acceptance Criteria

- [x] **Code Size:** `agent.py` (Core Logic) ist signifikant kleiner (< 300 Zeilen). ✓ `lean_agent.py` = 298 Zeilen
- [x] **No Legacy:** Keine Referenzen mehr auf `TodoListManager`, `QueryRouter` oder `ReplanStrategy` im aktiven Code-Pfad.
- [x] **Single Loop:** Es gibt nur noch eine zentrale Ausführungsschleife.
- [x] **Tests:** Bestehende Integrationstests müssen ggf. angepasst werden (Mocking des neuen Flows). **Hinweis:** Da dies ein Refactoring ist, werden viele alte Unit-Tests brechen. Diese müssen durch neue, einfachere Tests für den `LeanAgent` ersetzt werden. ✓ 17 neue Tests in `test_lean_agent.py`

## Integration Notes

*   Dies ist der größte Eingriff.
*   Strategie: Erstelle `LeanAgent` parallel zur alten `Agent` Klasse (oder in neuer Datei `lean_agent.py`), um das System lauffähig zu halten, bis die Migration abgeschlossen ist.

## Definition of Done

- [x] `LeanAgent` implementiert.
- [x] Alter Ballast entfernt/auskommentiert. *(LeanAgent in separater Datei, alte Agent-Klasse bleibt für Migration erhalten)*
- [x] Basis-Test (`test_lean_agent.py`) läuft und führt eine einfache Mission ("Sag Hallo") durch.

---

## Dev Agent Record

### File List
| File | Action | Description |
|------|--------|-------------|
| `src/taskforce/core/domain/lean_agent.py` | Created | New LeanAgent class with single execution loop |
| `tests/unit/core/test_lean_agent.py` | Created | 17 unit tests for LeanAgent |

### Debug Log References
*None*

### Completion Notes
- LeanAgent implemented in new file `lean_agent.py` (298 lines) - under the 300 line target
- No dependencies on legacy components (TodoListManager, QueryRouter, ReplanStrategy)
- Single execution loop with PlannerTool integration for plan management
- PlannerTool state is serialized/restored via StateManager
- 17 tests pass covering initialization, execution, state persistence, parsing, and verifying no legacy dependencies
- Legacy `Agent` class preserved in `agent.py` for gradual migration

### Change Log
| Date | Change |
|------|--------|
| 2025-12-04 | Initial implementation of LeanAgent and tests |

---

## QA Results

### Review Date: 2025-12-04

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

**Overall Assessment:** Excellent implementation quality. The LeanAgent successfully achieves the goal of radical simplification, reducing complexity from ~1800 lines (legacy Agent) to 298 lines while maintaining full functionality. The code follows Clean Architecture principles with proper dependency injection, clear separation of concerns, and comprehensive error handling.

**Strengths:**
- Clean single execution loop design (no fast-path/full-path complexity)
- Proper protocol-based dependency injection (no infrastructure coupling)
- Comprehensive error handling with fallbacks
- Excellent docstrings and type annotations throughout
- No legacy dependencies (verified via tests)
- PlannerTool integration is elegant and LLM-friendly

**Minor Observations:**
- `execute()` method is 85 lines (exceeds 30-line guideline), but this is acceptable for orchestration methods per coding standards
- `_generate_thought()` is 48 lines (exceeds guideline), but complexity is justified by prompt construction
- `_get_tools_description()` method exists but is unused (dead code) - minor cleanup opportunity

### Refactoring Performed

**No refactoring performed** - Code quality is excellent and meets all standards. The minor method length violations are acceptable for orchestration methods per project guidelines.

### Compliance Check

- **Coding Standards:** ✓ All PEP 8 compliant, proper type annotations, comprehensive docstrings, structured logging
- **Project Structure:** ✓ Files in correct locations (`core/domain/` for agent, `tests/unit/core/` for tests)
- **Testing Strategy:** ✓ 17 unit tests with proper mocking, zero infrastructure dependencies, fast execution (<2s)
- **All ACs Met:** ✓ All 4 acceptance criteria fully implemented and verified

### Requirements Traceability

**AC 1: Code Size < 300 lines**
- **Status:** ✓ PASS
- **Evidence:** `lean_agent.py` = 298 lines (verified via line count)
- **Test Coverage:** Verified via file inspection

**AC 2: No Legacy Dependencies**
- **Status:** ✓ PASS
- **Evidence:** No imports or references to `TodoListManager`, `QueryRouter`, or `ReplanStrategy`
- **Test Coverage:** 
  - `test_no_todolist_manager_attribute`
  - `test_no_router_attribute`
  - `test_no_fast_path_methods`
  - `test_no_replan_method`

**AC 3: Single Loop**
- **Status:** ✓ PASS
- **Evidence:** Single `while step < MAX_STEPS` loop in `execute()` method (lines 114-165)
- **Test Coverage:** Verified via code inspection and execution tests

**AC 4: Tests**
- **Status:** ✓ PASS
- **Evidence:** 17 comprehensive unit tests in `test_lean_agent.py`
- **Test Coverage:** 
  - Initialization (2 tests)
  - Execution flows (6 tests)
  - State persistence (2 tests)
  - Thought parsing (3 tests)
  - Legacy dependency verification (4 tests)

### Improvements Checklist

- [x] Verified all acceptance criteria are met
- [x] Confirmed no legacy dependencies exist
- [x] Validated single loop implementation
- [x] Reviewed test coverage (17 tests, all passing)
- [ ] Consider extracting prompt construction from `_generate_thought()` to separate method (future improvement)
- [ ] Remove unused `_get_tools_description()` method (minor cleanup)

### Security Review

**Status:** ✓ PASS

**Findings:**
- No security concerns identified
- No user input validation needed (handled by LLM provider)
- No secrets or sensitive data in code
- State serialization is safe (dict-based, no code injection risk)
- PlannerTool state is internal-only (no external I/O)

### Performance Considerations

**Status:** ✓ PASS

**Findings:**
- Single loop design eliminates overhead of state machine transitions
- PlannerTool operations are O(n) where n = number of tasks (efficient)
- No blocking I/O operations in core loop
- MAX_STEPS limit (30) prevents infinite loops
- Execution history limited to recent 10 steps (prevents unbounded growth)

**Performance Characteristics:**
- Expected to be faster than legacy Agent (no TodoListManager overhead)
- Memory usage is bounded (MAX_STEPS limit, history truncation)

### Reliability Assessment

**Status:** ✓ PASS

**Findings:**
- Comprehensive error handling with fallbacks
- Graceful degradation on LLM failures (returns error message)
- Tool execution failures don't crash agent (continues loop)
- Invalid JSON parsing handled gracefully (fallback response)
- State persistence verified (PlannerTool state serialization tested)

**Edge Cases Covered:**
- Tool not found → Error logged, loop continues
- Invalid JSON response → Fallback response returned
- MAX_STEPS exceeded → Graceful failure with clear message
- ASK_USER action → Execution paused, state saved

### Testability Evaluation

**Status:** ✓ PASS

**Controllability:** ✓ Excellent
- All dependencies injected via protocols (easy to mock)
- No hidden state or global variables
- Clear method boundaries

**Observability:** ✓ Excellent
- Structured logging throughout (structlog)
- Execution history tracked in `execution_history`
- Clear return types (ExecutionResult, Observation)

**Debuggability:** ✓ Excellent
- Clear error messages with context
- Execution history provides full trace
- Logging at appropriate levels (info, warning, error)

### Files Modified During Review

**No files modified** - Code quality is excellent and requires no changes.

### Gate Status

**Gate:** PASS → `docs/qa/gates/epic-6.story-2-refactor-agent.yml`

**Quality Score:** 95/100

**Rationale:** All acceptance criteria met, comprehensive test coverage (17 tests), excellent code quality, no blocking issues. Minor deduction (-5) for method length violations, but these are acceptable for orchestration methods.

### Recommended Status

✓ **Ready for Done**

All acceptance criteria are met, tests are comprehensive and passing, code quality is excellent, and no blocking issues were identified. The implementation successfully achieves the goal of radical simplification while maintaining functionality.

