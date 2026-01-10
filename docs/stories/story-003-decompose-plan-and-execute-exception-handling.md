# Story 3: Decompose PlanAndExecuteStrategy.execute_stream and Fix Exception Handling

**Story ID:** STORY-003  
**Epic:** EPIC-2024-001 - Planning Strategy Clean Architecture Compliance  
**Priority:** P1 (Strategic)  
**Story Points:** 8  
**Status:** Ready for Development  
**Sprint:** TBD  
**Blocked by:** STORY-001 (Logging Protocol Extraction), STORY-002 (NativeReActStrategy Decomposition)

## User Story

**As a** developer maintaining plan-based execution, **I want** the 248-line function decomposed and exception handling improved, **so that** the code follows Clean Architecture standards and provides better error diagnostics.

## Acceptance Criteria

### Function Decomposition Requirements
- [x] `_execute_plan_step()` extracted (single step execution)
- [x] `_process_step_tool_calls()` extracted (tool call handling per step)
- [x] `_check_step_completion()` extracted (step completion logic)
- [x] `_generate_final_response()` extracted (final response generation)
- [x] `_initialize_plan()` extracted (plan setup logic)
- [x] Generic `except Exception` in `_parse_plan_steps()` replaced with specific handlers
- [x] All extracted functions ≤ 30 lines each
- [x] Exception handlers provide actionable error messages
- [x] Unit tests for all extracted functions

### Technical Implementation Details

#### Current Function Analysis
The `PlanAndExecuteStrategy.execute_stream` function (~248 lines) handles:
- Plan generation using LLM
- Sequential step execution with iteration limits
- Tool call processing per step
- Plan status updates and completion tracking
- Final response generation
- Error handling for plan execution

#### Proposed Function Extraction

**1. Plan Initialization:**
```python
async def _initialize_plan(
    self,
    agent: "Agent",
    mission: str,
    logger: LoggerProtocol
) -> list[str]:
    """Generate plan steps using LLM or fallback to default steps."""
    # Extract lines 774-781 logic
    # Generate plan via LLM or use defaults
    # Return plan_steps list
```

**2. Single Step Execution:**
```python
async def _execute_plan_step(
    self,
    agent: "Agent",
    step_index: int,
    step_description: str,
    messages: list[dict[str, Any]],
    session_id: str,
    max_iterations: int
) -> tuple[bool, str, list[dict[str, Any]]]:
    """Execute a single plan step with iteration limits."""
    # Extract lines 806-959 logic
    # Return (step_complete, final_content, updated_messages)
```

**3. Step Tool Call Processing:**
```python
async def _process_step_tool_calls(
    self,
    tool_calls: list[dict[str, Any]],
    agent: "Agent",
    session_id: str,
    step_index: int,
    messages: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], bool]:
    """Process tool calls for a plan step."""
    # Extract lines 858-927 logic
    # Return (updated_messages, step_progress_made)
```

**4. Step Completion Checking:**
```python
def _check_step_completion(
    self,
    content: str,
    agent: "Agent",
    step_index: int
) -> bool:
    """Determine if a plan step is complete based on content."""
    # Extract completion logic from lines 929-948
    # Return True if step complete
```

**5. Final Response Generation:**
```python
async def _generate_final_response(
    self,
    agent: "Agent",
    messages: list[dict[str, Any]],
    session_id: str
) -> str:
    """Generate final response after all plan steps complete."""
    # Extract lines 960-978 logic
    # Return final response content
```

#### Exception Handling Improvements

**Replace generic exception handling in `_parse_plan_steps()`:**
```python
def _parse_plan_steps(content: str, logger: LoggerProtocol) -> list[str]:
    """Parse plan steps from LLM response with specific error handling."""
    text = content.strip()
    
    # Try JSON parsing first
    if "```" in text:
        try:
            parts = text.split("```")
            if len(parts) >= 2:
                json_text = parts[1].strip()
                data = json.loads(json_text)
                if isinstance(data, list):
                    steps = [str(item).strip() for item in data if str(item).strip()]
                    return steps
        except json.JSONDecodeError as e:
            logger.debug("json_parse_failed", error=str(e), content_preview=text[:100])
        except (TypeError, ValueError) as e:
            logger.debug("plan_steps_parse_error", error=str(e))
    
    # Fallback to line-based parsing
    steps: list[str] = []
    for line in text.splitlines():
        candidate = line.strip().lstrip("-").strip()
        if not candidate:
            continue
        if candidate[0].isdigit() and "." in candidate:
            candidate = candidate.split(".", 1)[1].strip()
        if candidate:
            steps.append(candidate)
    
    return steps
```

## Technical Notes

### Implementation Approach
- **Behavior Preservation:** Maintain plan step execution order and timing
- **State Management:** Preserve plan status update mechanisms
- **Error Handling:** Keep graceful error handling with fallback parsing
- **Iteration Limits:** Respect `max_step_iterations` and `max_plan_steps` limits
- **Event Emission:** Maintain plan update events for UI integration

### Code Quality Requirements
- Each function must have single, clear responsibility
- Function names must indicate specific behavior and context
- Docstrings must document all parameters and return values
- Type hints must be comprehensive
- No function should exceed 30 lines (excluding docstrings)

### Testing Strategy
- Unit tests for each extracted function
- Integration tests for complete plan execution flow
- Edge case testing for iteration limits and error conditions
- Regression tests for behavior preservation
- Exception handling validation with various error types

## Definition of Done

- [ ] All 5 functions extracted with ≤ 30 lines each
- [ ] Original `execute_stream` function delegates to extracted functions
- [ ] Specific exception handling replaces generic `except Exception`
- [ ] All existing tests pass without modification
- [ ] New unit tests for each extracted function
- [ ] Exception handling tests for various error scenarios
- [ ] Plan execution behavior preserved
- [ ] Error messages are actionable and informative
- [ ] Code coverage maintained or improved
- [ ] Documentation updated for all new functions

## Risk Mitigation

**Risk:** Plan execution logic may be subtly changed
**Mitigation:**
- Extract functions incrementally with testing
- Verify plan step order and timing
- Test with various plan complexities
- Validate planner integration points

**Risk:** Exception handling changes may break error recovery
**Mitigation:**
- Test fallback parsing with malformed LLM responses
- Verify graceful degradation for parsing failures
- Validate error message clarity and actionability
- Test edge cases in JSON and line-based parsing

**Risk:** Function decomposition may affect iteration control
**Mitigation:**
- Test iteration limit enforcement
- Verify step completion detection
- Validate early termination conditions
- Test nested loop logic preservation

## Dependencies

**Prerequisites:**
- STORY-001 (Logging Protocol) - for logger parameter updates
- STORY-002 (NativeReActStrategy) - for function extraction patterns
- Understanding of plan-based execution patterns
- Knowledge of LLM response parsing

**Blocking:**
- This story completes the epic
- Must verify all architectural compliance requirements

## Story Validation

**How to verify completion:**
1. Run `python -m pytest tests/core/domain/test_planning_strategy.py` - all tests pass
2. Check function sizes: no function > 30 lines in planning_strategy.py
3. Test plan execution: Run agent with `plan_and_execute` strategy
4. Verify exception handling: Test with malformed LLM responses
5. Validate error messages: Check parsing error diagnostics
6. Test iteration limits: Verify step and plan limits enforced

**Acceptance test scenarios:**
- Plan generation creates valid step list from LLM response
- Plan steps execute sequentially with proper limits
- Tool calls work correctly within plan steps
- Plan status updates visible in events
- Final response generated after plan completion
- Error handling provides clear diagnostics
- Malformed responses handled gracefully with fallback

**Performance validation:**
- Plan execution time remains acceptable
- No significant overhead from function calls
- Memory usage patterns unchanged
- Async execution flows preserved

## Dev Agent Record

### Tasks / Subtasks Checkboxes
- [x] Fix `_parse_plan_steps()` exception handling
- [x] Extract `_initialize_plan()` function
- [x] Extract `_execute_plan_step()` function
- [x] Extract `_process_step_tool_calls()` function
- [x] Extract `_check_step_completion()` function
- [x] Extract `_generate_final_response()` function
- [x] Refactor `execute_stream` to use extracted functions
- [x] Write unit tests for extracted functions
- [x] Run existing tests to verify no regressions

### File List
- `src/taskforce/core/domain/planning_strategy.py` - Modified: Extracted 5 main functions and 5 helper functions, fixed exception handling, improved JSON parsing
- `tests/core/domain/test_plan_and_execute_strategy.py` - Created: Comprehensive unit tests for all extracted functions (21 tests)

### Change Log
- **2025-01-XX**: Extracted `_initialize_plan()`, `_execute_plan_step()`, `_process_step_tool_calls()`, `_check_step_completion()`, and `_generate_final_response()` from `PlanAndExecuteStrategy.execute_stream()`
- **2025-01-XX**: Added helper functions: `_emit_tool_result_events()`, `_build_tool_requests()`, `_prepare_step_iteration()`, `_handle_step_llm_result()`, `_handle_llm_error()`, `_handle_step_content()`
- **2025-01-XX**: Fixed `_parse_plan_steps()` to use specific exception handlers (`json.JSONDecodeError`, `TypeError`, `ValueError`) instead of generic `except Exception`
- **2025-01-XX**: All extracted functions are ≤ 30 lines (excluding docstrings)
- **2025-01-XX**: Refactored `execute_stream()` to delegate to extracted functions
- **2026-01-10**: Added comprehensive unit tests (21 tests) covering all extracted functions and exception scenarios
- **2026-01-10**: Improved `_parse_plan_steps()` to handle JSON without code blocks and skip code block markers in line parsing

### Completion Notes
- All 5 main functions successfully extracted
- Exception handling improved with specific error types
- All functions meet the ≤ 30 lines requirement
- Existing tests pass, confirming no regressions
- Code follows Clean Architecture principles with clear separation of concerns
- Unit tests added: 21 tests covering all extracted functions and exception handling scenarios

## QA Results

### Review Date: 2026-01-10

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

**Overall Assessment**: The implementation demonstrates excellent code quality with proper decomposition, clear separation of concerns, and adherence to Clean Architecture principles. The refactoring successfully breaks down a 248-line monolithic function into focused, testable components. Exception handling has been improved with specific error types and actionable logging.

**Strengths**:
- ✅ All 5 main functions successfully extracted with clear responsibilities
- ✅ All functions meet the ≤ 30 lines requirement (verified: 15-29 lines each)
- ✅ Exception handling uses specific types (`json.JSONDecodeError`, `TypeError`, `ValueError`) with debug logging
- ✅ Code follows Clean Architecture with proper dependency direction
- ✅ Existing tests pass, confirming no behavioral regressions
- ✅ Helper functions appropriately extracted to maintain conciseness
- ✅ Type hints are comprehensive throughout
- ✅ Docstrings document parameters and return values

**Areas for Improvement**:
- ⚠️ Unit tests for extracted functions are missing (AC requirement)
- ⚠️ Exception handling tests for various error scenarios not present
- ⚠️ Integration tests for complete plan execution flow could be enhanced

### Refactoring Performed

No refactoring performed during QA review. Code quality is already excellent.

### Compliance Check

- **Coding Standards**: ✓ Compliant - Follows PEP 8, proper naming conventions, comprehensive type hints
- **Project Structure**: ✓ Compliant - Files in correct locations, follows Clean Architecture layers
- **Testing Strategy**: ⚠️ Partial - Unit tests missing for extracted functions (AC requirement)
- **All ACs Met**: ⚠️ Partial - 8/9 ACs met, unit tests missing

### Requirements Traceability

**AC1**: `_execute_plan_step()` extracted ✓
- **Test Coverage**: Missing unit tests
- **Given-When-Then**: Given a plan step, when executing with iteration limits, then it should yield events and track completion

**AC2**: `_process_step_tool_calls()` extracted ✓
- **Test Coverage**: Missing unit tests
- **Given-When-Then**: Given tool calls, when processing for a step, then it should execute tools and emit events

**AC3**: `_check_step_completion()` extracted ✓
- **Test Coverage**: Missing unit tests
- **Given-When-Then**: Given step content, when checking completion, then it should return completion status and plan event

**AC4**: `_generate_final_response()` extracted ✓
- **Test Coverage**: Missing unit tests
- **Given-When-Then**: Given completed plan steps, when generating final response, then it should return LLM-generated summary

**AC5**: `_initialize_plan()` extracted ✓
- **Test Coverage**: Missing unit tests
- **Given-When-Then**: Given a mission, when initializing plan, then it should return plan steps or fallback defaults

**AC6**: Exception handling improved ✓
- **Test Coverage**: Missing exception scenario tests
- **Given-When-Then**: Given malformed LLM responses, when parsing plan steps, then it should handle errors gracefully with fallback

**AC7**: Functions ≤ 30 lines ✓
- **Verification**: All functions verified (15-29 lines each)

**AC8**: Exception handlers provide actionable messages ✓
- **Verification**: Debug logging includes error context and content previews

**AC9**: Unit tests for extracted functions ✗
- **Status**: Not implemented (AC requirement)

### Improvements Checklist

- [x] Code quality verified - excellent decomposition and architecture
- [x] Exception handling verified - specific types with actionable logging
- [x] Function size verified - all ≤ 30 lines
- [x] Existing tests verified - no regressions
- [ ] **Add unit tests for `_initialize_plan()`** - Test LLM generation and fallback logic
- [ ] **Add unit tests for `_execute_plan_step()`** - Test iteration limits and step completion
- [ ] **Add unit tests for `_process_step_tool_calls()`** - Test tool execution and event emission
- [ ] **Add unit tests for `_check_step_completion()`** - Test completion detection and planner integration
- [ ] **Add unit tests for `_generate_final_response()`** - Test final response generation
- [ ] **Add exception handling tests** - Test `_parse_plan_steps()` with malformed JSON, invalid types, empty content
- [ ] **Add integration tests** - Test complete plan execution flow with various scenarios

### Security Review

**Status**: ✓ PASS
- No security concerns identified
- No authentication/authorization changes
- No data exposure risks
- Exception handling prevents information leakage

### Performance Considerations

**Status**: ✓ PASS
- Function decomposition adds minimal overhead (function call overhead negligible)
- Async execution flows preserved
- No performance regressions expected
- Code structure supports future optimization

### Testability Evaluation

**Controllability**: ✓ Excellent
- All functions accept clear inputs
- Dependencies can be mocked (Agent, LoggerProtocol)
- State can be controlled via parameters

**Observability**: ✓ Excellent
- Functions return clear outputs (events, status, messages)
- Logging provides debug context
- StreamEvent emission enables real-time monitoring

**Debuggability**: ✓ Good
- Clear function names indicate purpose
- Error messages include context
- Could be improved with unit tests for easier debugging

### Technical Debt Identification

**Current Debt**:
- Missing unit tests for extracted functions (AC requirement)
- Missing exception scenario tests
- Integration test coverage could be enhanced

**Recommendation**: Add unit tests before marking story complete. This is a non-blocking concern but should be addressed to meet AC requirements.

### Files Modified During Review

No files modified during QA review.

### Gate Status

**Gate**: CONCERNS → `docs/qa/gates/EPIC-2024-001.STORY-003-decompose-plan-and-execute-exception-handling.yml`

**Risk Profile**: Not generated (low-medium risk refactoring)

**NFR Assessment**: Not generated (NFRs not applicable for this refactoring story)

### Recommended Status

**✗ Changes Required** - Unit tests for extracted functions must be added to meet AC9 requirement. Code quality is excellent, but test coverage gap prevents completion.

**Rationale**: While the implementation is high quality and all functional requirements are met, the acceptance criteria explicitly requires unit tests for all extracted functions. This is a medium-severity concern that should be addressed before marking the story complete.