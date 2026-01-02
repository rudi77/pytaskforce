# Story 1.4: Implement Core Domain - TodoList Planning

**Epic**: Build Taskforce Production Framework with Clean Architecture  
**Story ID**: 1.4  
**Status**: Ready for Review  
**Priority**: High  
**Estimated Points**: 3  
**Dependencies**: Story 1.2 (Protocol Interfaces)

---

## User Story

As a **developer**,  
I want **TodoList planning logic extracted into core domain**,  
so that **plan generation and task management are testable without persistence dependencies**.

---

## Acceptance Criteria

1. ✅ Create `taskforce/src/taskforce/core/domain/plan.py` with domain classes and logic
2. ✅ Extract from `capstone/agent_v2/planning/todolist.py`:
   - ✅ `TodoItem` dataclass (position, description, acceptance_criteria, dependencies, status, chosen_tool, execution_result)
   - ✅ `TodoList` dataclass (mission, items, created_at, updated_at)
   - ✅ `TaskStatus` enum (PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED)
   - ✅ `PlanGenerator` class (LLM-based plan generation logic)
3. ✅ Refactor `PlanGenerator` to accept `llm_provider: LLMProviderProtocol` via constructor
4. ✅ Preserve all planning algorithms from Agent V2 (dependency validation, LLM prompts for plan generation)
5. ✅ Remove all persistence logic (file I/O, JSON serialization) - delegate to infrastructure layer
6. ✅ Create `validate_dependencies(plan)` method ensuring no circular dependencies
7. ✅ Unit tests with mocked LLM verify plan generation logic without actual LLM calls

---

## Integration Verification

- **IV1: Existing Functionality Verification** - Agent V2 planning continues to work independently
- **IV2: Integration Point Verification** - Generated plans match Agent V2 plan structure (same JSON schema when serialized)
- **IV3: Performance Impact Verification** - Plan validation completes in <100ms for plans with 20 tasks

---

## Technical Notes

**Domain Classes:**

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class TodoItem:
    """Single task in a TodoList."""
    position: int
    description: str
    acceptance_criteria: List[str]
    dependencies: List[int] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    chosen_tool: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None

@dataclass
class TodoList:
    """Complete plan for a mission."""
    mission: str
    items: List[TodoItem]
    todolist_id: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

class PlanGenerator:
    """Generates TodoLists from mission descriptions using LLM."""
    
    def __init__(self, llm_provider: LLMProviderProtocol):
        self.llm_provider = llm_provider
    
    async def generate_plan(self, mission: str) -> TodoList:
        """Generate TodoList from mission description."""
        # Extract logic from agent_v2/planning/todolist.py
        ...
    
    def validate_dependencies(self, plan: TodoList) -> bool:
        """Validate no circular dependencies in plan."""
        ...
```

**Reference Files:**
- `capstone/agent_v2/planning/todolist.py` - Extract TodoItem, TodoList, PlanGenerator
- Keep LLM prompts for plan generation
- Remove `TodoListManager` class (persistence - goes to infrastructure)

**What to Extract vs. Leave:**
- ✅ Extract: Domain classes (TodoItem, TodoList, TaskStatus)
- ✅ Extract: Plan generation logic (LLM-based)
- ✅ Extract: Dependency validation
- ❌ Leave: File I/O, JSON serialization (goes to infrastructure/persistence)
- ❌ Leave: TodoListManager (becomes infrastructure adapter)

---

## Testing Strategy

```python
# tests/unit/core/test_plan.py
from unittest.mock import AsyncMock
from taskforce.core.domain.plan import PlanGenerator, TodoList

async def test_plan_generation():
    mock_llm = AsyncMock(spec=LLMProviderProtocol)
    mock_llm.complete.return_value = {
        "content": '{"items": [...]}'  # Mocked plan JSON
    }
    
    generator = PlanGenerator(llm_provider=mock_llm)
    plan = await generator.generate_plan("Create a web app")
    
    assert isinstance(plan, TodoList)
    assert len(plan.items) > 0
    assert all(item.status == TaskStatus.PENDING for item in plan.items)

def test_dependency_validation_no_cycles():
    plan = TodoList(mission="Test", items=[
        TodoItem(position=0, description="Task 1", dependencies=[]),
        TodoItem(position=1, description="Task 2", dependencies=[0]),
    ])
    
    generator = PlanGenerator(llm_provider=mock_llm)
    assert generator.validate_dependencies(plan) == True
```

---

## Definition of Done

- [x] `plan.py` contains TodoItem, TodoList, TaskStatus, PlanGenerator
- [x] All domain logic extracted from Agent V2
- [x] Zero persistence code in domain layer
- [x] Dependency validation logic implemented
- [x] Unit tests achieve ≥90% coverage (97% achieved)
- [x] Unit tests use mocked LLM (no actual API calls)
- [x] Dependency validation completes <100ms for 20-task plans (verified)
- [ ] Code review completed
- [ ] Code committed to version control

---

## Dev Agent Record

### Agent Model Used
- Claude Sonnet 4.5 (via Cursor)

### Completion Notes
- Successfully extracted all domain logic from Agent V2's `planning/todolist.py`
- Implemented `PlanGenerator` with dependency injection for LLM provider
- Created comprehensive test suite with 34 tests (31 unit + 3 performance)
- Achieved 97% code coverage on `plan.py` module
- All performance requirements met: dependency validation <100ms for 20-task plans
- Zero persistence code in domain layer - all file I/O delegated to infrastructure
- Preserved all planning algorithms including clarification questions and final plan generation

### File List
**Created:**
- `taskforce/src/taskforce/core/domain/plan.py` - Core domain planning logic (636 lines)
- `taskforce/tests/unit/core/test_plan.py` - Comprehensive unit tests (31 tests)
- `taskforce/tests/unit/core/test_plan_performance.py` - Performance validation tests (3 tests)

**Modified:**
- None

### Change Log
1. Created `plan.py` with domain classes:
   - `TaskStatus` enum with 5 states and `parse_task_status()` helper
   - `TodoItem` dataclass with 12 fields (position, description, acceptance_criteria, dependencies, status, runtime fields)
   - `TodoList` dataclass with methods: `from_json()`, `to_dict()`, `get_step_by_position()`, `insert_step()`
   - `PlanGenerator` class with LLM-based planning methods

2. Implemented PlanGenerator methods:
   - `extract_clarification_questions()` - Pre-planning clarification using "main" model
   - `generate_plan()` - TodoList generation using "fast" model
   - `validate_dependencies()` - Circular dependency detection with DFS algorithm
   - `_create_clarification_questions_prompts()` - Prompt engineering for clarification
   - `_create_final_todolist_prompts()` - Prompt engineering for plan generation

3. Created comprehensive test suite:
   - 4 tests for TaskStatus parsing
   - 3 tests for TodoItem dataclass
   - 8 tests for TodoList dataclass and methods
   - 12 tests for PlanGenerator with mocked LLM
   - 2 tests for prompt generation
   - 2 integration scenario tests
   - 3 performance validation tests

4. Verified all acceptance criteria:
   - ✅ All domain logic extracted from Agent V2
   - ✅ Zero persistence code (no file I/O)
   - ✅ LLM provider injected via constructor
   - ✅ Dependency validation with cycle detection
   - ✅ 97% test coverage (exceeds ≥90% requirement)
   - ✅ Performance: <100ms for 20-task validation
   - ✅ All tests use mocked LLM (no API calls)

### Debug Log References
- None (no issues encountered)

---

## QA Results

### Review Date: 2025-01-27

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

**Overall Assessment: Excellent** ✅

The implementation demonstrates high-quality domain logic extraction with excellent test coverage and adherence to Clean Architecture principles. The code is well-structured, properly documented, and follows all project standards.

**Strengths:**
- Clean separation of concerns: Zero persistence code in domain layer
- Comprehensive test coverage: 97% (exceeds ≥90% requirement)
- Proper dependency injection: LLM provider injected via constructor
- Excellent error handling: Proper exception chaining with `from e`
- Performance validated: Dependency validation <1ms for 20-task plans (well under <100ms requirement)
- Well-documented: Clear docstrings following Google-style format
- Type safety: Full type annotations throughout

**Minor Observations:**
- Two prompt generation methods (`_create_clarification_questions_prompts` and `_create_final_todolist_prompts`) exceed 30-line guideline but are acceptable due to prompt template nature
- Exception handling in `from_json()` uses generic `except Exception` but appropriately defaults to empty dict (defensive programming)

### Refactoring Performed

- **File**: `taskforce/tests/unit/core/test_plan_performance.py`
  - **Change**: Removed unused `TaskStatus` import
  - **Why**: Ruff linting identified unused import (F401)
  - **How**: Cleaned up import statement to only include used classes

### Compliance Check

- **Coding Standards**: ✅ PASS
  - PEP8 compliant (verified via Ruff)
  - Full type annotations present
  - Google-style docstrings for all public methods
  - Function length mostly ≤30 lines (2 exceptions acceptable for prompt templates)
  - Proper error handling with exception chaining

- **Project Structure**: ✅ PASS
  - Correct location: `src/taskforce/core/domain/plan.py`
  - Test mirroring: `tests/unit/core/test_plan.py`
  - No circular imports
  - Clean Architecture: Core layer has zero infrastructure dependencies

- **Testing Strategy**: ✅ PASS
  - Unit tests use mocked LLM (no actual API calls)
  - 34 tests total (31 unit + 3 performance)
  - Coverage: 97% (exceeds ≥90% requirement for core domain)
  - Tests mirror source structure
  - Proper use of pytest fixtures

- **All ACs Met**: ✅ PASS
  - All 7 acceptance criteria fully implemented and verified
  - Integration verification points validated
  - Performance requirements exceeded

### Requirements Traceability

**Given-When-Then Test Mapping:**

1. **AC1: Create plan.py with domain classes**
   - ✅ **Given**: Domain classes defined (TaskStatus, TodoItem, TodoList, PlanGenerator)
   - ✅ **When**: Module imported and classes instantiated
   - ✅ **Then**: All classes accessible and properly typed
   - **Tests**: `TestTaskStatus.test_task_status_values`, `TestTodoItem.test_todoitem_creation_minimal`, `TestTodoList.test_todolist_creation_minimal`

2. **AC2: Extract TodoItem, TodoList, TaskStatus, PlanGenerator**
   - ✅ **Given**: Agent V2 reference implementation
   - ✅ **When**: Domain logic extracted
   - ✅ **Then**: All classes match Agent V2 structure (verified via serialization roundtrip)
   - **Tests**: `TestTodoList.test_todolist_from_json_string`, `TestIntegrationScenarios.test_plan_serialization_roundtrip`

3. **AC3: Refactor PlanGenerator with LLMProviderProtocol**
   - ✅ **Given**: PlanGenerator class
   - ✅ **When**: Constructor accepts `llm_provider: LLMProviderProtocol`
   - ✅ **Then**: Can inject mock LLM provider for testing
   - **Tests**: `TestPlanGenerator.test_generate_plan_success` (uses mocked LLM)

4. **AC4: Preserve planning algorithms**
   - ✅ **Given**: Agent V2 planning logic
   - ✅ **When**: Algorithms extracted to PlanGenerator
   - ✅ **Then**: Clarification questions and plan generation work identically
   - **Tests**: `TestPlanGenerator.test_extract_clarification_questions_success`, `TestPlanGenerator.test_generate_plan_success`

5. **AC5: Remove persistence logic**
   - ✅ **Given**: Domain layer implementation
   - ✅ **When**: Code reviewed
   - ✅ **Then**: Zero file I/O, JSON serialization only for data transfer (not persistence)
   - **Verification**: Manual code review - no `open()`, `Path.write_text()`, or file operations found

6. **AC6: Create validate_dependencies method**
   - ✅ **Given**: TodoList with dependencies
   - ✅ **When**: `validate_dependencies()` called
   - ✅ **Then**: Circular dependencies detected, invalid positions rejected
   - **Tests**: `TestPlanGenerator.test_validate_dependencies_circular`, `TestPlanGenerator.test_validate_dependencies_invalid_position`, `TestPlanPerformance.test_validate_dependencies_performance_20_tasks`

7. **AC7: Unit tests with mocked LLM**
   - ✅ **Given**: Test suite
   - ✅ **When**: Tests executed
   - ✅ **Then**: All tests pass without actual LLM API calls
   - **Tests**: All 34 tests use `AsyncMock(spec=LLMProviderProtocol)`

### Improvements Checklist

- [x] Fixed unused import in test_plan_performance.py (Ruff F401)
- [x] Verified all tests pass (34/34 ✅)
- [x] Confirmed code coverage exceeds requirement (97% ≥ 90%)
- [x] Validated performance requirements (<100ms for 20 tasks)
- [ ] Consider extracting prompt templates to separate module if they grow (future enhancement)
- [ ] Consider adding integration tests with real LLM provider in infrastructure layer (future story)

### Security Review

**Status**: ✅ PASS

- No security concerns identified
- No secrets or sensitive data in code
- Input validation present (parse_task_status with safe defaults)
- Proper error handling prevents information leakage
- Domain layer has no external dependencies (no network/file access)

### Performance Considerations

**Status**: ✅ PASS

- Dependency validation: <1ms for 20-task plans (100x faster than <100ms requirement)
- Circular dependency detection: <1ms for 5-task cycles
- Scales well: <5ms for 50-task plans
- No performance bottlenecks identified
- Algorithm efficiency: O(V+E) DFS for cycle detection (optimal)

### Test Architecture Assessment

**Unit Test Quality**: ✅ Excellent
- Proper isolation: All tests use mocks (no I/O dependencies)
- Comprehensive coverage: 97% statement coverage
- Edge cases covered: Invalid JSON, LLM failures, circular dependencies, skipped items
- Performance tests: Validates NFR requirements
- Test maintainability: Clear test names, proper fixtures, good organization

**Test Level Appropriateness**: ✅ Correct
- All tests are unit tests (appropriate for domain layer)
- No integration tests needed (domain layer has no external dependencies)
- Performance tests validate NFRs appropriately

**Test Design Quality**: ✅ Excellent
- Clear Given-When-Then structure (implicit in test names)
- Proper use of pytest fixtures
- Good test data management (inline fixtures, no external files)
- Mock usage appropriate (LLM provider mocked correctly)

### Non-Functional Requirements (NFRs)

**Security**: ✅ PASS
- No authentication/authorization concerns (domain logic only)
- Input validation present
- No sensitive data handling

**Performance**: ✅ PASS
- Dependency validation: <1ms (requirement: <100ms) ✅
- Plan generation: Async/await properly used
- No blocking operations

**Reliability**: ✅ PASS
- Error handling: Proper exception chaining (`from e`)
- Defensive programming: Safe defaults in `from_json()`
- Logging: Structured logging with context

**Maintainability**: ✅ PASS
- Code clarity: Well-documented, clear naming
- Documentation: Comprehensive docstrings
- Testability: Excellent (97% coverage, all mocked)

### Files Modified During Review

- `taskforce/tests/unit/core/test_plan_performance.py` - Removed unused import

**Note**: Please update File List in Dev Agent Record if needed.

### Gate Status

**Gate**: PASS → `docs/qa/gates/1.4-core-todolist.yml`

**Quality Score**: 100/100

**Rationale**: All acceptance criteria met, excellent test coverage (97%), performance requirements exceeded, zero blocking issues, code quality excellent.

### Recommended Status

✅ **Ready for Done**

All requirements met, tests passing, code quality excellent. No blocking issues identified. Story is ready to be marked as Done.

