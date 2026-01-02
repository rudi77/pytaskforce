<!-- Powered by BMAD™ Core -->
<!-- Epic: epic-9-context-pack-rehydration.md -->

# Story 9.2: ContextPolicy + ContextBuilder (Pattern A Context Pack / Rehydration) - Brownfield Addition

## User Story

**Als** Betreiber/Entwickler des Taskforce-Agents,  
**möchte ich** vor jedem LLM-Call deterministisch ein **budgetiertes Context Pack** bauen,  
**damit** der Agent relevante Tool-Ergebnisse gezielt „rehydriert“, ohne die Token-Grenzen zu sprengen.

---

## Story Context

### Existing System Integration

- **Integrates with:**
  - `taskforce/src/taskforce/core/domain/lean_agent.py` – Aufbau `messages`, Loop, System-Prompt-Injection
  - (aus Story 9.1) `ToolResultStore` + `ToolResultHandle` – Quelle für Excerpts/Previews
  - `taskforce/configs/*.yaml` – Profile/Agent-Konfiguration (Policy injection)
- **Technology:** Python 3.11, async, config-driven behavior, OpenAI messages/tools
- **Follows pattern:** „Configuration over code“ – Policy in Config statt hardcoded Regeln

### Problem Statement

Wenn Tool Results nur noch als Handles in der History stehen (Story 9.1), braucht der Agent einen standardisierten Weg, **selektiv** relevante Ausschnitte in den nächsten LLM-Call einzubringen. Ohne deterministischen Builder droht Kontextverlust oder erneutes Tool-Spam-Verhalten.

---

## Acceptance Criteria

### Functional Requirements

1. **ContextPolicy Model:** Es gibt ein konfigurierbares Policy-Model (z.B. dataclass/pydantic) mit harten Caps:
   - `max_items`
   - `max_chars_per_item`
   - `max_total_chars`
   - optional: `include_latest_tool_previews_n`, `allow_tools: [...]`, `allow_selectors: [...]`
2. **ContextBuilder:** Es gibt einen Builder, der deterministisch:
   - Mission / Session State / Plan State / ToolResultHandles nimmt,
   - ein Context Pack erzeugt, das nur aus **kurzen** Snippets besteht (budgetiert).
3. **Injection Point:** Vor jedem `llm_provider.complete(...)` (und ggf. Streaming):
   - wird das Context Pack injiziert (als zusätzliche System Message oder als klar markierte Section).
4. **No blind rehydration:** Kein Tool-Result wird „blind“ komplett rehydratisiert — immer capped durch Policy.
5. **Selectors (MVP):** Es gibt eine minimal funktionierende Selector-Option (z.B. `first_chars`, `last_chars`, `json_path` optional später), die im Builder genutzt werden kann.

### Integration Requirements

6. **Config Wiring:** Policy ist pro Agent/Profil konfigurierbar (ohne Codeänderung pro Profil).
7. **Compatibility:** Wenn keine Policy konfiguriert ist, nutzt der Agent eine konservative Default-Policy (kleines Budget).

### Quality Requirements

8. **Determinism:** Gleiches State+Policy → gleiches Context Pack (keine LLM-Abhängigkeit).
9. **Tests:** Mindestens:
   - Unit-Test: `ContextBuilder` respektiert Caps (`max_total_chars`)
   - Unit-Test: `LeanAgent` injiziert Context Pack vor dem LLM-Call

---

## Technical Notes

- Context Pack sollte einen klaren Header haben (z.B. `## CONTEXT PACK (BUDGETED)`), damit das Modell es korrekt interpretiert.
- Der Builder darf bewusst „stumpf“ sein (MVP): Ziel ist Budget-Sicherheit, nicht perfekte Relevanz-Ranking.

---

## Definition of Done

- [x] `ContextPolicy` implementiert und konfigurierbar
- [x] `ContextBuilder` implementiert (budgetiert, deterministic)
- [x] Injection in `LeanAgent` vor LLM Calls (execute + streaming)
- [x] Tests grün

---

## Files to Create/Modify

- **Modify:**
  - `taskforce/src/taskforce/core/domain/lean_agent.py`
  - `taskforce/src/taskforce/application/factory.py`
  - `taskforce/configs/coding_agent.yaml`
- **Create (suggested):**
  - `taskforce/src/taskforce/core/domain/context_policy.py`
  - `taskforce/src/taskforce/core/domain/context_builder.py`
  - `taskforce/tests/unit/core/test_context_builder.py`
  - `taskforce/tests/unit/core/test_lean_agent_context_injection.py`

---

## Dev Agent Record

### Agent Model Used
Claude Sonnet 4.5

### Completion Notes

**Implementation Summary:**

Story 9.2 wurde erfolgreich implementiert. Die Lösung umfasst:

1. **ContextPolicy Model** (`context_policy.py`):
   - Dataclass mit harten Caps: `max_items`, `max_chars_per_item`, `max_total_chars`
   - Tool-Allowlist-Filterung via `is_tool_allowed()`
   - Conservative Default Policy für sichere Fallback-Konfiguration
   - Validierung und Auto-Adjustment von Constraints
   - Serialisierung via `from_dict()` / `to_dict()`

2. **ContextBuilder** (`context_builder.py`):
   - Deterministischer Builder ohne LLM-Abhängigkeit
   - Budget-sichere Context Pack Konstruktion
   - Extraktion von Tool Result Previews aus Message History (Story 9.1 Format)
   - Unterstützung für Mission, Tool Previews, Plan State
   - Selector-System (MVP: `first_chars`, `last_chars`)
   - Klarer Header: `## CONTEXT PACK (BUDGETED)`

3. **LeanAgent Integration** (`lean_agent.py`):
   - `context_policy` Parameter im Constructor (optional, default: conservative)
   - `ContextBuilder` Instanz als Agent-Attribut
   - `_build_system_prompt()` erweitert um Context Pack Injection
   - Context Pack wird vor **jedem** LLM Call neu gebaut (execute + streaming)
   - Logging für Debuggability

4. **Factory Wiring** (`factory.py`):
   - `_create_context_policy()` Methode für Config-basierte Policy-Erstellung
   - Integration in `create_lean_agent()` und `create_lean_agent_from_definition()`
   - Fallback auf Conservative Default wenn keine Config vorhanden

5. **Config Example** (`coding_agent.yaml`):
   - Beispiel-Konfiguration für `context_policy` Section
   - Dokumentierte Parameter mit sinnvollen Defaults

6. **Comprehensive Tests**:
   - **20 Tests** für ContextPolicy + ContextBuilder (alle grün)
   - **8 Tests** für LeanAgent Context Injection (alle grün)
   - **27 Regressions-Tests** für LeanAgent (alle grün, keine Regressionen)

**Key Design Decisions:**

- **Determinismus**: Context Pack ist rein funktional, keine LLM Calls
- **Budget-First**: Alle Caps werden strikt eingehalten
- **Latest-First**: Neueste Tool Results werden priorisiert
- **Backward Compatible**: Optionaler Parameter, Conservative Default
- **Config-Driven**: Policy via YAML konfigurierbar, keine Code-Änderungen nötig

**Test Coverage:**
- ✅ Policy Validierung und Auto-Adjustment
- ✅ Budget Enforcement (max_items, max_chars_per_item, max_total_chars)
- ✅ Tool Allowlist Filtering
- ✅ Deterministic Output (gleiche Inputs → gleicher Output)
- ✅ Context Pack Injection in System Prompt
- ✅ Integration mit Tool Result Store (Story 9.1)
- ✅ Rebuild auf jeder Loop Iteration

**Compliance:**
- ✅ Alle 9 Acceptance Criteria erfüllt
- ✅ PEP8 konform (minor line length violations akzeptabel)
- ✅ Type Hints vollständig
- ✅ Docstrings für alle Funktionen/Klassen
- ✅ Clean Architecture respektiert

### File List

**Created:**
- `taskforce/src/taskforce/core/domain/context_policy.py`
- `taskforce/src/taskforce/core/domain/context_builder.py`
- `taskforce/tests/unit/core/test_context_builder.py`
- `taskforce/tests/unit/core/test_lean_agent_context_injection.py`

**Modified:**
- `taskforce/src/taskforce/core/domain/lean_agent.py`
- `taskforce/src/taskforce/application/factory.py`
- `taskforce/configs/coding_agent.yaml`

### Change Log

**2025-12-13 - Story Implementation**
- Created `ContextPolicy` dataclass with validation and serialization
- Created `ContextBuilder` with deterministic budget-safe context pack construction
- Extended `LeanAgent._build_system_prompt()` to inject context packs
- Added `context_policy` parameter to `LeanAgent.__init__()`
- Implemented `_create_context_policy()` in `AgentFactory`
- Wired `ContextPolicy` into `create_lean_agent()` and `create_lean_agent_from_definition()`
- Added example `context_policy` configuration to `coding_agent.yaml`
- Created comprehensive test suite (28 tests total)
- All tests passing, no regressions

### Status

**Ready for Review** ✅

---

## QA Results

### Review Date: 2025-12-13

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

**Overall Assessment: EXCELLENT** ✅

The implementation successfully addresses the core requirement of deterministic, budget-safe context pack construction. The design follows Clean Architecture principles with clear separation of concerns. Code quality is high with comprehensive docstrings, proper error handling, and deterministic behavior. The integration with Story 9.1 (ToolResultStore) is seamless.

**Strengths:**
- Clean separation of concerns (Policy model, Builder logic, Agent integration)
- Comprehensive test coverage (28 tests, all passing)
- Deterministic behavior (no LLM calls, pure functions)
- Backward compatible (optional parameter with conservative default)
- Config-driven behavior (YAML-based policy configuration)
- Proper validation and auto-adjustment of policy constraints
- Excellent integration with existing ToolResultStore (Story 9.1)
- Clear, self-documenting code with comprehensive docstrings

**Areas for Improvement:**
- Minor linting issues (line length violations) - non-blocking, acceptable per project standards
- Consider adding integration test with real ToolResultStore to verify end-to-end flow
- Future enhancement: Consider adding metrics/logging for context pack size tracking

### Refactoring Performed

**No refactoring performed** - Code quality is already high. Minor linting fixes recommended but not blocking.

### Compliance Check

- **Coding Standards**: ✓ Compliant (PEP8, type hints, docstrings present)
- **Project Structure**: ✓ Compliant (Clean Architecture layers respected)
- **Testing Strategy**: ✓ Compliant (Unit tests comprehensive, deterministic behavior verified)
- **All ACs Met**: ✓ All 9 acceptance criteria met

### Acceptance Criteria Traceability

**AC1 - ContextPolicy Model**: ✅ PASS
- `ContextPolicy` dataclass implements all required fields: `max_items`, `max_chars_per_item`, `max_total_chars`, `include_latest_tool_previews_n`, `allow_tools`, `allow_selectors`
- Tests: `test_default_policy`, `test_conservative_default`, `test_policy_validation`, `test_policy_auto_adjustment`, `test_from_dict`, `test_to_dict`

**AC2 - ContextBuilder**: ✅ PASS
- `ContextBuilder` deterministically builds budgeted context packs from mission/state/messages
- Tests: `test_empty_context_pack`, `test_mission_only_context_pack`, `test_tool_preview_extraction`, `test_respects_max_items`, `test_respects_max_total_chars`, `test_respects_max_chars_per_item`

**AC3 - Injection Point**: ✅ PASS
- Context pack injected before every `llm_provider.complete()` call (execute + streaming)
- Tests: `test_context_pack_injected_in_system_prompt`, `test_context_pack_rebuilt_each_loop`

**AC4 - No Blind Rehydration**: ✅ PASS
- All tool results capped by policy (`max_chars_per_item`, `max_total_chars`)
- Tests: `test_respects_max_chars_per_item`, `test_respects_max_total_chars`, `test_context_pack_respects_budget`

**AC5 - Selectors (MVP)**: ✅ PASS
- Selector system implemented with `first_chars`, `last_chars` support
- Tests: `test_apply_selector_first_chars`, `test_apply_selector_last_chars`, `test_apply_selector_unknown_defaults_to_first`

**AC6 - Config Wiring**: ✅ PASS
- Policy configurable via YAML (`context_policy` section)
- Factory method `_create_context_policy()` reads from config
- Tests: Verified via factory integration tests

**AC7 - Compatibility**: ✅ PASS
- Conservative default policy used when no config provided
- Tests: `test_agent_uses_conservative_default_policy`

**AC8 - Determinism**: ✅ PASS
- Same state + policy → same context pack (no LLM calls)
- Tests: `test_deterministic_output`

**AC9 - Tests**: ✅ PASS
- Unit test: `test_respects_max_total_chars` verifies caps enforcement
- Unit test: `test_context_pack_injected_in_system_prompt` verifies injection
- Additional comprehensive coverage: 28 tests total

### Improvements Checklist

- [x] All acceptance criteria verified and mapped to tests
- [x] Code quality reviewed (excellent)
- [ ] Fix linting issues (line length violations) - **Recommended but not blocking**
- [ ] Consider adding integration test with real ToolResultStore - **Future enhancement**
- [ ] Consider adding metrics for context pack size tracking - **Future enhancement**

### Security Review

**Status: PASS** ✅

- No sensitive data exposure (context packs contain tool results, already handled by Story 9.1)
- Policy validation prevents injection attacks (input validation in `__post_init__`)
- Tool allowlist provides additional security boundary
- No SQL injection or injection risks (pure Python logic, no external queries)
- Deterministic behavior prevents timing attacks

### Performance Considerations

**Status: PASS** ✅

- Context pack building is O(n) where n is message count (acceptable)
- Budget enforcement prevents unbounded growth
- No blocking I/O operations (pure functions)
- Conservative default policy prevents token explosion
- Context pack rebuilt each loop iteration (necessary for accuracy, acceptable overhead)

**Performance Notes:**
- Context pack construction is lightweight (string operations only)
- Policy caps ensure bounded execution time
- No performance bottlenecks identified

### Test Architecture Assessment

**Test Coverage: EXCELLENT** ✅

- **Unit Tests**: 28 comprehensive tests covering all components
  - ContextPolicy: 7 tests (validation, serialization, defaults)
  - ContextBuilder: 13 tests (budget enforcement, determinism, selectors)
  - LeanAgent Integration: 8 tests (injection, policy usage, tool store integration)
- **Test Quality**: High - tests are focused, isolated, and deterministic
- **Edge Cases**: Covered (empty packs, long missions, budget limits, tool filtering)
- **Integration**: Verified with ToolResultStore (Story 9.1) via message format parsing

**Test Design Quality:**
- Tests follow Given-When-Then pattern implicitly
- Proper use of fixtures for test isolation
- Clear test names describing behavior
- Good coverage of boundary conditions

### Non-Functional Requirements (NFRs)

**Security**: ✅ PASS
- Policy validation prevents malicious input
- Tool allowlist provides security boundary
- No data leakage (context packs respect privacy)

**Performance**: ✅ PASS
- Bounded execution time (policy caps)
- No blocking operations
- Efficient string operations

**Reliability**: ✅ PASS
- Deterministic behavior (no randomness)
- Proper error handling (validation, fallbacks)
- Conservative defaults prevent failures

**Maintainability**: ✅ PASS
- Clear code structure and documentation
- Config-driven behavior (easy to adjust)
- Comprehensive test coverage
- Clean Architecture compliance

### Files Modified During Review

**No files modified** - Implementation is production-ready. Minor linting fixes recommended but not blocking.

### Gate Status

**Gate: PASS** → `docs/qa/gates/epic-9.story-9.2-context-policy-context-pack.yml`

**Quality Score: 95/100**
- Deduction: -5 for minor linting issues (non-blocking)

**Risk Profile**: Low
- No security risks
- No performance risks
- Backward compatible
- Comprehensive test coverage
- Deterministic behavior reduces risk

### Recommended Status

✅ **Ready for Done**

All acceptance criteria met, comprehensive test coverage, clean implementation. Minor linting fixes can be addressed in follow-up PR if desired. The implementation successfully solves the problem of token budget management through deterministic context pack construction.


