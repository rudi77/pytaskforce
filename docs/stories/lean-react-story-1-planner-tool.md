# Story 1: Implementierung des `PlannerTool`

**Status:** Draft
**Epic:** [Epic 6: Transition zu "Lean ReAct" Architektur](taskforce/docs/epics/epic-6-lean-react-transition.md)
**Priorität:** Hoch
**Schätzung:** 5 SP

## Description

Als **Entwickler** möchte ich ein `PlannerTool` implementieren, das dem Agenten erlaubt, seinen eigenen Plan zu erstellen und zu verwalten, damit die Planungslogik vom Python-Code in den LLM-Kontext verlagert werden kann ("Planning as a Tool").

Das Tool soll eine einfache Liste von Aufgaben verwalten und dem Agenten ermöglichen, diese als "erledigt" zu markieren oder den Plan bei Bedarf anzupassen. Der Status des Plans muss über den `state_manager` persistiert werden, damit er Sessions überdauert.

## Technical Details

### 1. Neue Klasse `PlannerTool`
Erstelle die Klasse `src/taskforce/core/tools/planner_tool.py`, die das `ToolProtocol` implementiert.

**Schema:**
Das Tool soll folgende Aktionen (Methoden) unterstützen:

1.  **`create_plan(tasks: List[str])`**
    *   **Beschreibung:** Erstellt einen neuen Plan und überschreibt jeden existierenden.
    *   **Input:** Eine Liste von Strings (die Schritte).
    *   **Verhalten:** Setzt internen Status auf eine Liste von Items (Status: PENDING).

2.  **`mark_done(step_index: int)`**
    *   **Beschreibung:** Markiert einen Schritt als erledigt.
    *   **Input:** Index des Schritts (1-basiert oder 0-basiert, konsistent entscheiden -> Empfehlung: 1-basiert für LLM-Freundlichkeit).
    *   **Verhalten:** Ändert Status von PENDING auf COMPLETED.

3.  **`read_plan()`**
    *   **Beschreibung:** Gibt den aktuellen Plan zurück.
    *   **Output:** String-Repräsentation des Plans (z.B. Markdown Checkboxen).
    *   **Beispiel Output:**
        ```markdown
        [x] 1. Recherche starten
        [ ] 2. Ergebnisse zusammenfassen
        ```

4.  **`update_plan(action: str, ...)`** (Optional für V1, aber gut für Robustheit)
    *   Ermöglicht das Hinzufügen/Löschen von Schritten.

### 2. State Persistence
Das `PlannerTool` darf nicht stateless sein. Es muss seinen State (die Liste der Tasks) speichern.
*   **Lösung:** Das Tool bekommt Zugriff auf ein Dictionary (oder den `state_manager` Kontext), das beim `execute` des Agenten geladen/gespeichert wird.
*   **Data Structure:**
    ```python
    {
      "tasks": [
        {"description": "...", "status": "DONE"},
        {"description": "...", "status": "PENDING"}
      ]
    }
    ```

## Acceptance Criteria

- [x] **Klasse Existiert:** `PlannerTool` ist implementiert und erfüllt `ToolProtocol`.
- [x] **Plan Erstellung:** `create_plan(["A", "B"])` erzeugt einen internen State mit 2 offenen Tasks.
- [x] **Plan Status:** `mark_done(1)` setzt den ersten Task auf erledigt.
- [x] **Read Output:** `read_plan()` liefert einen sauber formatierten String (Markdown-Liste), der den Status (Done/Pending) korrekt anzeigt.
- [x] **Empty State:** Wenn kein Plan existiert, liefert `read_plan()` eine entsprechende Meldung (z.B. "No active plan.").
- [x] **Unit Tests:** Tests decken alle Methoden ab (`test_planner_tool.py`).

## Integration Notes

*   Dieses Tool wird später im `LeanAgent` instanziiert.
*   Es ersetzt den kompletten `TodoListManager` und die `TodoList` Klassen der alten Architektur.

## Definition of Done

- [x] Code implementiert & reviewed.
- [x] Unit Tests grün.
- [x] Keine Linter-Fehler.

## Dev Agent Record

### File List
- `taskforce/src/taskforce/core/tools/__init__.py` (created)
- `taskforce/src/taskforce/core/tools/planner_tool.py` (created)
- `taskforce/tests/unit/core/tools/__init__.py` (created)
- `taskforce/tests/unit/core/tools/test_planner_tool.py` (created)

### Completion Notes
- Implemented `PlannerTool` class implementing `ToolProtocol`
- Supports actions: `create_plan`, `mark_done` (1-based indexing), `read_plan`, `update_plan`
- Uses "status": "PENDING"/"DONE" format as specified in story
- State serialization via `get_state()`/`set_state()` methods for persistence
- All 46 unit tests passing
- No linter errors
- 83% code coverage

### Change Log
- Created PlannerTool implementation with action-based interface
- Added comprehensive unit tests covering all acceptance criteria
- Fixed linting issues (line length compliance)

## QA Results

### Review Date: 2025-12-04

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

**Overall Assessment**: Excellent implementation quality. The `PlannerTool` is well-designed, comprehensively tested, and follows all project standards. The action-based interface is LLM-friendly with clear documentation and examples. All acceptance criteria are fully met.

**Strengths**:
- **ToolProtocol Compliance**: Perfect implementation of ToolProtocol with all required properties and methods
- **LLM-Friendly Design**: Excellent description property with clear action examples and usage patterns
- **Comprehensive Testing**: 46 tests covering all functionality, edge cases, and acceptance criteria
- **State Management**: Clean state serialization via `get_state()`/`set_state()` methods
- **Error Handling**: Proper validation and clear error messages for all failure scenarios
- **Code Organization**: Well-structured with clear separation of concerns (action handlers, formatting, validation)
- **Documentation**: Comprehensive docstrings following Google-style format

**Architecture Compliance**:
- Correctly placed in `core/tools/` layer (core domain tool)
- No dependencies on infrastructure layer (Clean Architecture compliance)
- Proper use of ToolProtocol for tool contract
- State structure matches story specification exactly

### Refactoring Performed

No refactoring performed - code quality is excellent and meets all standards.

### Compliance Check

- **Coding Standards**: ✓ PASS - PEP 8 compliant, Black formatted, Ruff linting passes, type annotations throughout, docstrings present
- **Project Structure**: ✓ PASS - Correctly placed in `core/tools/`, proper package structure, test mirroring structure
- **Testing Strategy**: ✓ PASS - Comprehensive unit tests (46 tests), proper test organization by functionality, edge cases covered, 83% code coverage
- **All ACs Met**: ✓ PASS - All 6 acceptance criteria fully implemented and validated

### Requirements Traceability

**AC 1 - Klasse Existiert**: ✓ PASS
- **Given**: PlannerTool class must exist and implement ToolProtocol
- **When**: Tool is instantiated and protocol properties/methods are accessed
- **Then**: All ToolProtocol requirements are met (name, description, parameters_schema, execute, validate_params, etc.)
- **Test Coverage**: `test_name_property`, `test_description_property`, `test_parameters_schema_structure`, `test_requires_approval_property`, `test_approval_risk_level_property`

**AC 2 - Plan Erstellung**: ✓ PASS
- **Given**: Tool is instantiated with no initial state
- **When**: `create_plan(["A", "B"])` is called
- **Then**: Internal state contains 2 tasks with status "PENDING"
- **Test Coverage**: `test_create_plan_success`, `test_acceptance_criteria_plan_creation`

**AC 3 - Plan Status**: ✓ PASS
- **Given**: Plan exists with tasks
- **When**: `mark_done(1)` is called (1-based indexing)
- **Then**: First task status changes from "PENDING" to "DONE"
- **Test Coverage**: `test_mark_done_success`, `test_mark_done_one_based_indexing`, `test_acceptance_criteria_mark_done`

**AC 4 - Read Output**: ✓ PASS
- **Given**: Plan exists with mixed done/pending tasks
- **When**: `read_plan()` is called
- **Then**: Returns properly formatted Markdown checklist with [x] for done, [ ] for pending
- **Test Coverage**: `test_read_plan_with_tasks`, `test_read_plan_mixed_status`, `test_read_plan_format_matches_story_example`, `test_acceptance_criteria_read_output_format`

**AC 5 - Empty State**: ✓ PASS
- **Given**: Tool is instantiated with no plan
- **When**: `read_plan()` is called
- **Then**: Returns "No active plan." message
- **Test Coverage**: `test_read_plan_empty`, `test_acceptance_criteria_empty_state`

**AC 6 - Unit Tests**: ✓ PASS
- **Given**: All methods and actions exist
- **When**: Test suite is executed
- **Then**: All 46 tests pass, covering create_plan, mark_done, read_plan, update_plan, state serialization, validation, metadata, edge cases
- **Test Coverage**: Complete test suite in `test_planner_tool.py`

### Improvements Checklist

- [x] All acceptance criteria validated with tests
- [x] Error handling comprehensive (invalid indices, missing parameters, empty states)
- [x] State serialization tested (roundtrip, copy semantics)
- [x] LLM-friendly description with examples
- [x] Code follows project standards (PEP 8, type hints, docstrings)
- [ ] Consider adding integration test with actual LLM tool calling (future enhancement)
- [ ] Consider performance test for large plans if needed (future enhancement)

### Security Review

**Status**: PASS - No security concerns identified.

- Tool manages internal state only, no external I/O operations
- No user input validation needed (handled by LLM via ToolProtocol)
- State serialization is safe (dict-based, no code execution)
- No secrets or sensitive data handled
- No network or file system access

### Performance Considerations

**Status**: PASS - Excellent performance characteristics.

- All operations are O(n) where n is number of tasks (linear complexity)
- No I/O operations, pure in-memory state management
- Formatting uses efficient string concatenation
- No blocking operations (async execute method properly implemented)
- State serialization is lightweight (simple dict operations)

### Testability Evaluation

**Controllability**: ✓ EXCELLENT
- All inputs controllable via action parameter and kwargs
- State can be initialized via constructor or set_state()
- Edge cases easily testable (empty state, invalid indices, missing params)

**Observability**: ✓ EXCELLENT
- All outputs clearly structured (success bool, output/error fields)
- State can be inspected via get_state()
- Formatting output is deterministic and testable

**Debuggability**: ✓ EXCELLENT
- Clear error messages with context (step_index out of bounds with range)
- Error types included in error responses
- State structure is simple and inspectable

### Files Modified During Review

No files modified during review - implementation quality is excellent.

### Gate Status

**Gate**: PASS → `docs/qa/gates/epic-6.story-1-planner-tool.yml`

**Quality Score**: 100/100

**Risk Profile**: LOW - Core tool implementation with no external dependencies, comprehensive test coverage

**NFR Assessment**: All NFRs PASS (Security, Performance, Reliability, Maintainability)

### Recommended Status

✓ **Ready for Done** - All acceptance criteria met, comprehensive test coverage, excellent code quality, no blocking issues. Implementation is production-ready and follows all project standards.

