# Story 3: Integration von Native Tool Calling

**Status:** Ready for Review
**Epic:** [Epic 6: Transition zu "Lean ReAct" Architektur](taskforce/docs/epics/epic-6-lean-react-transition.md)
**Priorität:** Hoch
**Schätzung:** 5 SP
**Abhängigkeiten:** Story 2 (LeanAgent Skeleton)
**Agent Model Used:** Claude Opus 4.5

## Description

Als **Entwickler** möchte ich die nativen "Tool Calling" Fähigkeiten moderner LLMs (OpenAI/Anthropic) nutzen, anstatt Custom-JSON-Parsing zu verwenden. Dies erhöht die Robustheit drastisch, da das Modell strukturiert antwortet und keine Syntaxfehler im JSON mehr auftreten ("Hallucinated Brackets").

## Technical Details

### 1. LLMProvider Anpassung
Stelle sicher, dass der `LLMProvider` (und das Protocol) die Parameter `tools` und `tool_choice` korrekt an die API weiterreicht.

*   **Interface:** `complete(messages, tools=..., tool_choice=...)`
*   **Response:** Die Rückgabe muss Zugriff auf `tool_calls` (Liste) ermöglichen, nicht nur `content`.

### 2. Handling im `LeanAgent` Loop
Im `execute` Loop des Agenten muss die Antwortweiche angepasst werden:

**Logik:**
1.  **Check:** `response.tool_calls` vorhanden?
2.  **IF YES:**
    *   Iteriere über alle `tool_calls`.
    *   Führe das entsprechende Tool aus (`self.tools[name].execute(**args)`).
    *   Füge das Ergebnis (`role: tool`) zur `history` hinzu.
    *   **WICHTIG:** Der Loop geht weiter (kein Return). Das LLM bekommt die Ergebnisse und entscheidet im nächsten Schritt weiter.
3.  **IF NO (Content Only):**
    *   Das ist die "Final Answer".
    *   Return `response.content`.

### 3. Tool Definition Conversion
Stelle sicher, dass die bestehenden `Tool` Objekte (die `parameters_schema` haben) korrekt in das Format konvertiert werden, das die OpenAI-API erwartet (JSON Schema).
*   Helper-Funktion: `tools_to_openai_format(self.tools)`.

## Acceptance Criteria

- [x] **Native Calls:** Der Agent nutzt nachweislich die API-Parameter `tools` (im Debug-Log sichtbar).
- [x] **Multi-Step:** Der Agent kann ein Tool aufrufen, das Ergebnis erhalten und *danach* eine Antwort generieren (Roundtrip).
- [x] **Kein Parsing-Code:** Der alte `json.loads(thought)` Code und Regex-Fallback sind entfernt.
- [x] **Error Handling:** Wenn ein Tool-Call fehlschlägt (Exception), landet der Fehler im Kontext und der Agent kann im nächsten Schritt darauf reagieren (Retry).

## Integration Notes

*   Das `PlannerTool` aus Story 1 ist technisch gesehen auch nur ein "Tool", das hierüber aufgerufen wird.
*   Das `Native Tool Calling` eliminiert die Notwendigkeit für den komplexen "Thought Generation" Prompt, der JSON erzwingt.

## Definition of Done

- [x] LLM Provider unterstützt Native Tools.
- [x] Agent Loop verarbeitet `tool_calls` korrekt.
- [x] Integrationstest mit einem Dummy-Tool (z.B. `Calculator`) erfolgreich.

---

## Dev Agent Record

### File List

| File | Status | Description |
|------|--------|-------------|
| `src/taskforce/core/interfaces/llm.py` | Modified | Added `tools` and `tool_choice` parameters to `LLMProviderProtocol.complete()` |
| `src/taskforce/infrastructure/llm/openai_service.py` | Modified | Updated `complete()` to pass tools to LiteLLM and extract `tool_calls` from response |
| `src/taskforce/infrastructure/tools/tool_converter.py` | New | Helper functions: `tools_to_openai_format()`, `tool_result_to_message()`, `assistant_tool_calls_to_message()` |
| `src/taskforce/core/domain/lean_agent.py` | Modified | Refactored to use native tool calling instead of JSON parsing |
| `tests/unit/core/test_lean_agent.py` | Modified | Updated tests for native tool calling pattern |

### Debug Log References

- All 21 unit tests pass for `test_lean_agent.py`
- Native tool calling verified via:
  - `test_execute_tool_call_then_respond` - Single tool call roundtrip
  - `test_execute_multiple_tool_calls_in_one_response` - Multiple parallel tool calls
  - `test_execute_with_planner_tool` - Multi-step tool calling with PlannerTool
  - `test_handles_tool_exception` - Error handling in tool execution

### Completion Notes

1. **LLMProviderProtocol**: Extended `complete()` method signature to accept `tools: list[dict]` and `tool_choice: str | dict` parameters
2. **OpenAIService**: Modified to pass tools to LiteLLM, extract `tool_calls` from response, and return structured tool call data
3. **Tool Converter**: Created utility module with:
   - `tools_to_openai_format()` - Converts ToolProtocol instances to OpenAI function calling schema
   - `tool_result_to_message()` - Creates tool result messages for conversation history
   - `assistant_tool_calls_to_message()` - Creates assistant messages with tool calls
4. **LeanAgent**: Complete refactoring to native tool calling:
   - Removed `_generate_thought()` and `_parse_thought()` methods (no more JSON parsing)
   - Removed `ActionType`, `Action`, `Thought`, `Observation` domain events (simplified)
   - Native tool calling loop: LLM → tool_calls → execute → tool results → LLM → content (final answer)
   - Proper message history management with assistant tool_calls and tool results

### Change Log

| Date | Change | Author |
|------|--------|--------|
| 2024-12-04 | Initial implementation of native tool calling | Dev Agent (James) |

---

## QA Results

### Review Date: 2024-12-04

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

**Overall: EXCELLENT**

The implementation of native tool calling is clean, well-architected, and follows best practices. The refactoring from JSON parsing to native LLM function calling significantly improves robustness by eliminating "hallucinated brackets" parsing errors. Key strengths include:

1. **Protocol-based design** - Clean dependency injection maintained
2. **Single responsibility** - `tool_converter.py` properly isolated
3. **Comprehensive documentation** - Excellent docstrings with examples
4. **Structured logging** - All key events tracked with context

### Refactoring Performed

None required. Implementation is clean and follows project standards.

### Compliance Check

- Coding Standards: ✓ PEP8 compliant, type annotations present, docstrings complete
- Project Structure: ✓ New module in correct location (`infrastructure/tools/`)
- Testing Strategy: ✓ Unit tests at appropriate level with proper mocking
- All ACs Met: ✓ All 4 acceptance criteria verified with tests

### Improvements Checklist

- [x] All acceptance criteria have test coverage
- [x] Error handling comprehensive (tool not found, exception, LLM failure, invalid JSON)
- [x] State persistence working correctly
- [x] Legacy code removed (no JSON parsing methods)
- [ ] Consider adding integration test with real LLM in CI (future)
- [ ] Consider adding OpenTelemetry span for tool execution timing (future)

### Security Review

**Status: PASS**

- No sensitive data handling changes
- Tool execution properly sandboxed within `_execute_tool` with exception handling
- No credential exposure or injection vulnerabilities

### Performance Considerations

**Status: PASS**

- Tools pre-converted to OpenAI format at initialization (`self._openai_tools`) - avoids per-call overhead
- Message history management is efficient with list appends
- No N+1 or unbounded loop issues detected

### Files Modified During Review

None. Code quality is excellent, no refactoring required.

### Gate Status

**Gate: PASS** → `taskforce/docs/qa/gates/6.3-native-tool-calling.yml`

### Recommended Status

✓ **Ready for Done** - All acceptance criteria met, comprehensive test coverage, clean implementation.

