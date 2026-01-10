# Epic: Planning Strategy Clean Architecture Compliance

**Epic ID:** EPIC-2024-001  
**Epic Type:** Brownfield Enhancement  
**Priority:** P1 (Strategic)  
**Target Component:** `src/taskforce/core/domain/planning_strategy.py`  
**Estimated Effort:** 3-5 days  
**Status:** Ready for Development

## Epic Goal

Refactor the Planning Strategy module to comply with Taskforce Clean Architecture standards by extracting logging protocols, decomposing oversized functions, and improving error handling. This enhancement will improve testability, maintainability, and architectural integrity while preserving all existing functionality.

## Epic Description

### Existing System Context

**Current relevant functionality:**
- The `planning_strategy.py` module contains 1,078 lines implementing three agent planning strategies: `NativeReActStrategy`, `PlanAndExecuteStrategy`, and `PlanAndReactStrategy`
- These strategies orchestrate agent execution loops, handle tool calls, manage streaming events, and coordinate with LLM providers
- The module is central to the agent execution engine and handles critical execution flows

**Technology stack:**
- Python 3.11+ with asyncio for concurrent execution
- structlog for structured logging (currently violating Clean Architecture)
- Native LLM tool calling with OpenAI-compatible APIs
- AsyncIterator for streaming event processing

**Integration points:**
- `Agent` class in `src/taskforce/core/domain/lean_agent.py` (calls strategy methods)
- `application/factory.py` (strategy instantiation and dependency injection)
- `core/domain/models.py` (ExecutionResult, StreamEvent data models)
- `core/tools/tool_converter.py` (tool call message conversion)

### Enhancement Details

**What's being added/changed:**
1. **Protocol Extraction:** Create `LoggerProtocol` in `core/interfaces/logging.py` to abstract logging operations
2. **Function Decomposition:** Break down two oversized functions (440+ and 248+ lines) into smaller, focused units
3. **Dependency Inversion:** Move structlog instantiation from Core to Infrastructure layer
4. **Exception Handling:** Replace generic `except Exception` with specific exception handlers

**How it integrates:**
- New `LoggerProtocol` will be injected via dependency injection in `application/factory.py`
- Existing strategy classes will accept `LoggerProtocol` instead of concrete `FilteringBoundLogger`
- Function extraction maintains all existing behavior while improving organization
- No changes to public APIs or external interfaces

**Success criteria:**
- [ ] Zero `structlog` imports remain in Core layer
- [ ] All functions ≤ 30 lines (or documented exceptions)
- [ ] All existing tests pass without modification
- [ ] New unit tests for extracted helper functions
- [ ] Specific exception handling throughout
- [ ] Maintained or improved code coverage

## Stories

### Story 1: Extract Logging Protocol and Remove Core Dependencies
**Priority:** P1 (Critical)  
**Estimated Effort:** 1 day  

**As a** developer maintaining the Taskforce codebase, **I want** to extract a logging protocol from the Core domain, **so that** the Core layer has zero external dependencies and follows Clean Architecture principles.

**Acceptance Criteria:**
- [ ] `LoggerProtocol` interface created in `src/taskforce/core/interfaces/logging.py`
- [ ] Function signatures updated to accept `LoggerProtocol` instead of `FilteringBoundLogger`
- [ ] `structlog` imports removed from `planning_strategy.py`
- [ ] Logger instances created in `application/factory.py` and injected via DI
- [ ] All existing tests pass without modification
- [ ] New unit tests for protocol interface

**Technical Notes:**
- Protocol should include: `info()`, `warning()`, `error()`, `debug()` methods
- Maintain backward compatibility during transition
- Update other Core domain files using structlog (19 occurrences found)

---

### Story 2: Decompose NativeReActStrategy.execute_stream Function
**Priority:** P1 (Strategic)  
**Estimated Effort:** 2 days  

**As a** developer working on agent execution logic, **I want** the 440-line `execute_stream` function decomposed into smaller, focused functions, **so that** the code is easier to understand, test, and maintain.

**Acceptance Criteria:**
- [ ] `_execute_non_streaming_loop()` extracted (handles fallback path)
- [ ] `_execute_streaming_loop()` extracted (handles streaming path)
- [ ] `_process_stream_chunk()` extracted (individual chunk processing)
- [ ] `_accumulate_tool_calls()` extracted (tool call accumulation)
- [ ] `_emit_tool_events()` extracted (event emission logic)
- [ ] `_handle_streaming_completion()` extracted (final answer handling)
- [ ] All extracted functions ≤ 30 lines each
- [ ] Comprehensive unit tests for each extracted function
- [ ] Integration tests verify behavior preservation

**Technical Notes:**
- Preserve all existing execution flows and edge cases
- Maintain streaming event emission timing
- Keep tool call parallelism logic intact
- Document function responsibilities clearly

---

### Story 3: Decompose PlanAndExecuteStrategy.execute_stream and Fix Exception Handling
**Priority:** P1 (Strategic)  
**Estimated Effort:** 1-2 days  

**As a** developer maintaining plan-based execution, **I want** the 248-line function decomposed and exception handling improved, **so that** the code follows Clean Architecture standards and provides better error diagnostics.

**Acceptance Criteria:**
- [ ] `_execute_plan_step()` extracted (single step execution)
- [ ] `_process_step_tool_calls()` extracted (tool call handling per step)
- [ ] `_check_step_completion()` extracted (step completion logic)
- [ ] `_generate_final_response()` extracted (final response generation)
- [ ] `_initialize_plan()` extracted (plan setup logic)
- [ ] Generic `except Exception` in `_parse_plan_steps()` replaced with specific handlers
- [ ] All extracted functions ≤ 30 lines each
- [ ] Exception handlers provide actionable error messages
- [ ] Unit tests for all extracted functions

**Technical Notes:**
- Maintain plan step execution order and timing
- Preserve plan status update mechanisms
- Keep error handling graceful with fallback parsing
- Document exception handling patterns for future reference

## Compatibility Requirements

- [x] **Existing APIs remain unchanged** - All public method signatures preserved
- [x] **Database schema changes are backward compatible** - No database changes required
- [x] **UI changes follow existing patterns** - No UI changes required
- [x] **Performance impact is minimal** - Function extraction may add minimal overhead, offset by improved maintainability

## Risk Mitigation

**Primary Risk:** Function refactoring may introduce subtle behavioral changes in execution flows
**Mitigation:** 
- Comprehensive unit tests for each extracted function
- Integration tests covering all execution paths
- Manual verification of streaming behavior
- Code review focusing on behavior preservation

**Secondary Risk:** Logger protocol extraction may break logging in production
**Mitigation:**
- Gradual rollout with adapter pattern support
- Extensive logging verification in staging environment
- Rollback plan using git revert if issues discovered

**Rollback Plan:**
1. All changes are in single module with clear git history
2. Revert commits if issues discovered during testing
3. Fallback to original structlog implementation if protocol issues arise
4. No external dependencies or schema changes to complicate rollback

## Definition of Done

- [ ] All three stories completed with acceptance criteria met
- [ ] Existing functionality verified through comprehensive testing
- [ ] Integration points working correctly (Agent → Strategy → LLM Provider)
- [ ] Documentation updated (function docstrings, architecture notes)
- [ ] No regression in existing features (all tests pass)
- [ ] Code coverage maintained or improved
- [ ] Clean Architecture compliance verified (zero Core dependencies)
- [ ] Function size compliance verified (≤ 30 lines per function)
- [ ] Exception handling compliance verified (specific exceptions only)

## Story Manager Handoff

Please develop detailed user stories for this brownfield epic. Key considerations:

- This is an enhancement to an existing system running Python 3.11+ with asyncio and structlog
- Integration points: Agent class, Factory DI container, LLM providers, Tool execution
- Existing patterns to follow: Protocol-based interfaces, dependency injection, async/await
- Critical compatibility requirements: Zero public API changes, behavior preservation
- Each story must include verification that existing functionality remains intact

The epic should maintain system integrity while delivering Clean Architecture compliance and improved code organization for the Planning Strategy module.