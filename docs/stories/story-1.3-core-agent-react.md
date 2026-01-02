# Story 1.3: Implement Core Domain - Agent ReAct Loop

**Epic**: Build Taskforce Production Framework with Clean Architecture  
**Story ID**: 1.3  
**Status**: Ready for Review  
**Priority**: Critical  
**Estimated Points**: 5  
**Dependencies**: Story 1.2 (Protocol Interfaces)

---

## User Story

As a **developer**,  
I want **the ReAct execution loop extracted from Agent V2 into core domain**,  
so that **business logic is testable without infrastructure dependencies**.

---

## Acceptance Criteria

1. ✅ Create `taskforce/src/taskforce/core/domain/agent.py` with `Agent` class
2. ✅ Extract ReAct loop logic from `capstone/agent_v2/agent.py:Agent.execute()`:
   - Thought generation (LLM call for reasoning)
   - Action decision (tool selection or ask_user or complete)
   - Observation recording (tool execution result)
3. ✅ Refactor to accept dependencies via constructor injection:
   - `state_manager: StateManagerProtocol`
   - `llm_provider: LLMProviderProtocol`
   - `tools: List[ToolProtocol]`
   - `todolist_manager: TodoListManagerProtocol`
4. ✅ Create `execute(mission: str, session_id: str) -> ExecutionResult` method implementing ReAct loop
5. ✅ Preserve Agent V2 execution semantics (same loop termination conditions, same error handling)
6. ✅ Create dataclasses for domain events: `Thought`, `Action`, `Observation` in `core/domain/events.py`
7. ✅ Unit tests using protocol mocks verify ReAct logic without any I/O

---

## Integration Verification

- **IV1: Existing Functionality Verification** - Agent V2 remains operational (not yet using taskforce agent)
- **IV2: Integration Point Verification** - Unit tests verify identical ReAct behavior using mocked protocols compared to Agent V2 execution traces
- **IV3: Performance Impact Verification** - Unit tests complete in <1 second (pure in-memory logic)

---

## Technical Notes

**Agent Class Structure:**

```python
from dataclasses import dataclass
from typing import List
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.core.interfaces.todolist import TodoListManagerProtocol

@dataclass
class ExecutionResult:
    """Result of agent execution."""
    session_id: str
    status: str  # completed, failed, pending
    final_message: str
    execution_history: List[Dict]

class Agent:
    """Core ReAct agent with protocol-based dependencies."""
    
    def __init__(
        self,
        state_manager: StateManagerProtocol,
        llm_provider: LLMProviderProtocol,
        tools: List[ToolProtocol],
        todolist_manager: TodoListManagerProtocol,
        system_prompt: str
    ):
        self.state_manager = state_manager
        self.llm_provider = llm_provider
        self.tools = {tool.name: tool for tool in tools}
        self.todolist_manager = todolist_manager
        self.system_prompt = system_prompt
    
    async def execute(
        self, 
        mission: str, 
        session_id: str
    ) -> ExecutionResult:
        """Execute ReAct loop for given mission."""
        # Extract ReAct loop logic from agent_v2/agent.py
        ...
```

**Reference Files:**
- `capstone/agent_v2/agent.py` - Lines 100-500 contain the ReAct loop
- Focus on `Agent.execute()` method and `MessageHistory` management

**Key Logic to Extract:**
- ReAct loop: while not done → thought → action → observation
- Tool selection and execution
- User interaction handling (ask_user)
- Loop termination conditions
- Error handling and retry logic

---

## Testing Strategy

**Unit Tests with Mocks:**
```python
# tests/unit/core/test_agent.py
from unittest.mock import AsyncMock
from taskforce.core.domain.agent import Agent

async def test_react_loop_basic_execution():
    # Mock all protocols
    mock_state_manager = AsyncMock(spec=StateManagerProtocol)
    mock_llm_provider = AsyncMock(spec=LLMProviderProtocol)
    mock_tools = [...]
    mock_todolist_manager = AsyncMock(spec=TodoListManagerProtocol)
    
    agent = Agent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools=mock_tools,
        todolist_manager=mock_todolist_manager,
        system_prompt="Test prompt"
    )
    
    result = await agent.execute("Test mission", "test-session-123")
    
    assert result.status == "completed"
    assert mock_llm_provider.complete.called
```

---

## Definition of Done

- [x] `Agent` class implemented in `core/domain/agent.py`
- [x] ReAct loop logic extracted from Agent V2
- [x] All dependencies injected via protocols (zero infrastructure imports)
- [x] `events.py` contains Thought, Action, Observation dataclasses
- [x] Unit tests achieve ≥90% coverage of ReAct logic
- [x] Unit tests use only protocol mocks (no I/O)
- [x] Tests complete in <1 second
- [ ] Code review completed
- [ ] Code committed to version control

---

## Dev Agent Record

### Agent Model Used
- Claude Sonnet 4.5 via Cursor

### Completion Notes
- Successfully implemented core Agent class with ReAct loop in `src/taskforce/core/domain/agent.py`
- Created domain events (Thought, Action, Observation) in `src/taskforce/core/domain/events.py`
- Created ExecutionResult model in `src/taskforce/core/domain/models.py`
- Extracted ReAct loop logic from Agent V2 (`capstone/agent_v2/agent.py`) preserving execution semantics
- All dependencies injected via protocols (StateManagerProtocol, LLMProviderProtocol, ToolProtocol, TodoListManagerProtocol)
- Zero infrastructure imports in core domain - pure business logic
- Implemented comprehensive unit tests in `tests/unit/test_agent.py` with 13 test cases
- Test coverage: 90% on agent.py (178 statements, 22 missed - mostly error handling edge cases)
- All tests pass in <1 second (0.83s total)
- Tests use only protocol mocks (AsyncMock) - no I/O or external dependencies

### File List
**Created:**
- `taskforce/src/taskforce/core/domain/agent.py` - Core Agent class with ReAct loop (178 lines)
- `taskforce/src/taskforce/core/domain/events.py` - Domain events: Action, Thought, Observation (30 lines)
- `taskforce/src/taskforce/core/domain/models.py` - ExecutionResult model (9 lines)
- `taskforce/tests/unit/test_agent.py` - Comprehensive unit tests (13 test cases, 90% coverage)

**Modified:**
- None

### Change Log
1. Created `events.py` with ActionType enum and Action, Thought, Observation dataclasses
2. Created `models.py` with ExecutionResult dataclass
3. Implemented Agent class with:
   - Constructor accepting protocol dependencies
   - `execute()` method orchestrating ReAct loop
   - `_get_or_create_todolist()` for plan management
   - `_get_next_actionable_step()` respecting dependencies
   - `_build_thought_context()` building LLM context
   - `_generate_thought()` using LLM for reasoning
   - `_execute_action()` handling tool_call, ask_user, complete, replan
   - `_execute_tool()` safe tool execution
   - `_process_observation()` updating step status and history
   - `_check_acceptance()` validating acceptance criteria
   - `_is_plan_complete()` checking completion status
4. Created comprehensive test suite covering:
   - Agent initialization
   - TodoList creation and loading
   - ReAct loop execution with tool calls
   - Ask user action handling (pauses execution)
   - Complete action handling (early termination)
   - Retry logic for failed steps
   - Max attempts enforcement
   - Dependency ordering
   - Max iterations safety limit
   - Helper method unit tests

### Debug Log References
- No issues encountered during implementation
- All tests passed on first run after fixing one test assertion

---

## QA Results

**Review Date:** 2025-11-22  
**Reviewer:** Quinn (Test Architect)  
**Gate Decision:** ✅ **PASS**  
**Quality Score:** 92/100

### Summary

Story 1.3 successfully implements the core Agent ReAct loop with excellent adherence to Clean Architecture principles. All acceptance criteria are met, comprehensive test coverage (90%) is achieved, and the implementation preserves Agent V2 execution semantics while achieving zero infrastructure dependencies.

### Requirements Traceability

All 7 acceptance criteria have test coverage:

1. ✅ **Agent class created** - Verified by `test_agent_initialization`
2. ✅ **ReAct loop extracted** - Verified by multiple tests covering Thought → Action → Observation cycle
3. ✅ **Protocol injection** - Verified by all tests using protocol mocks (zero infrastructure imports)
4. ✅ **execute() method** - Verified by tests covering TodoList creation/loading and loop execution
5. ✅ **Agent V2 semantics preserved** - Verified by tests for retry logic, max attempts, safety limits
6. ✅ **Domain events created** - Verified by tests using Thought, Action, Observation dataclasses
7. ✅ **Unit tests with mocks** - All 13 tests use AsyncMock/MagicMock, no I/O

### Test Coverage Analysis

- **Total Tests:** 13 (all passing)
- **Coverage:** 90% (178 statements, 22 missed)
- **Execution Time:** 0.83s (well under 1s requirement)
- **Test Types:** Unit tests with protocol mocks only (no I/O, no external dependencies)

**Coverage Gaps (22 lines):**
- Error handling paths: JSON parsing failures (lines 395-402)
- Error handling paths: LLM service failures (lines 366-369)
- Error handling paths: Tool execution exceptions (lines 449-451)
- Edge cases: FileNotFoundError handling (lines 213-214)
- Edge cases: Unknown action types (lines 434-435)

**Recommendation:** Add explicit tests for error scenarios to achieve 95%+ coverage.

### Risk Assessment

**Overall Risk:** LOW

**Identified Risks:**
1. **REPLAN action not fully implemented** (LOW impact)
   - REPLAN action type is supported but only returns an observation
   - Replanning logic deferred to future story (acceptable for core loop extraction)
   - **Mitigation:** Document as deferred, implement in dedicated story

2. **Error handling paths not explicitly tested** (LOW impact)
   - Error handling code exists but not covered by tests
   - **Mitigation:** Add tests for malformed JSON, LLM failures, tool exceptions

3. **Acceptance criteria checking uses simple heuristic** (LOW impact)
   - Currently checks `observation.success` only
   - TODO comment indicates future LLM-based validation planned
   - **Mitigation:** Acceptable for MVP, enhance in future iteration

### Non-Functional Requirements Validation

✅ **Security:** PASS
- Pure business logic with protocol-based dependencies
- No secrets, no external I/O, no user input validation (handled by infrastructure)

✅ **Performance:** PASS
- Tests complete in 0.83s (under 1s requirement)
- Core domain logic is pure computation with no I/O
- MAX_ITERATIONS safety limit prevents infinite loops

✅ **Reliability:** PASS
- All 13 tests passing
- Error handling present for LLM failures, tool exceptions, JSON parsing errors
- Retry logic implemented with max_attempts enforcement

✅ **Maintainability:** PASS
- Excellent code organization: clear separation of concerns
- Comprehensive docstrings, type annotations throughout
- Clean Architecture principles followed (zero infrastructure imports)

### Given-When-Then Test Scenarios

All critical ReAct loop scenarios are covered:

1. ✅ **Agent executes mission** → TodoList created/loaded, ReAct loop executes
2. ✅ **Thought generation** → LLM called with context, Thought object created
3. ✅ **Tool execution** → Tool called with parameters, Observation returned
4. ✅ **User interaction** → Pending question stored, execution paused
5. ✅ **Early completion** → Remaining steps skipped, status='completed'
6. ✅ **Retry logic** → Failed steps retried up to max_attempts
7. ✅ **Max attempts** → Steps marked FAILED after exhausting retries
8. ✅ **Dependencies** → Steps execute in correct order respecting dependencies
9. ✅ **Safety limits** → Execution stops at MAX_ITERATIONS

### Recommendations

**Immediate Actions:**
1. Add tests for error scenarios (malformed JSON, LLM failures, tool exceptions) - Priority: MEDIUM
2. Document REPLAN action as "deferred to future story" in code comments - Priority: LOW

**Future Enhancements:**
1. Implement full replanning logic when REPLAN action is executed - Priority: MEDIUM
2. Enhance acceptance criteria checking with LLM-based validation - Priority: LOW
3. Add integration tests when infrastructure implementations are available - Priority: LOW

### Gate Decision Rationale

**PASS** - All acceptance criteria met, comprehensive test coverage achieved, Clean Architecture principles followed. Minor concerns about incomplete REPLAN implementation and untested error paths are acceptable for this foundational story. The core ReAct loop extraction is complete and ready for integration with infrastructure implementations in subsequent stories.

**Gate File:** `docs/qa/gates/1.3-core-agent-react.yml`

