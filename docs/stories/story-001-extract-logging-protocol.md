# Story 1: Extract Logging Protocol and Remove Core Dependencies

**Story ID:** STORY-001  
**Epic:** EPIC-2024-001 - Planning Strategy Clean Architecture Compliance  
**Priority:** P1 (Critical)  
**Story Points:** 8  
**Status:** Ready for Review  
**Sprint:** TBD  

## User Story

**As a** developer maintaining the Taskforce codebase, **I want** to extract a logging protocol from the Core domain, **so that** the Core layer has zero external dependencies and follows Clean Architecture principles.

## Acceptance Criteria

### Core Requirements
- [x] `LoggerProtocol` interface created in `src/taskforce/core/interfaces/logging.py`
- [x] Function signatures updated to accept `LoggerProtocol` instead of `FilteringBoundLogger`
- [x] `structlog` imports removed from `planning_strategy.py`
- [x] Logger instances created in `application/factory.py` and injected via DI
- [x] Tests updated to provide logger instances (required due to API change)
- [x] New unit tests for protocol interface

### Technical Implementation Details

#### 1. Create LoggerProtocol Interface
```python
# src/taskforce/core/interfaces/logging.py
from typing import Any, Protocol

class LoggerProtocol(Protocol):
    """Protocol for logging operations in Core domain."""
    
    def info(self, event: str, **kwargs: Any) -> None: ...
    def warning(self, event: str, **kwargs: Any) -> None: ...
    def error(self, event: str, **kwargs: Any) -> None: ...
    def debug(self, event: str, **kwargs: Any) -> None: ...
```

#### 2. Update Function Signatures in planning_strategy.py
- `_parse_tool_args(tool_call: dict[str, Any], logger: LoggerProtocol)`
- `_generate_plan_steps(agent: "Agent", mission: str, logger: LoggerProtocol)`
- Strategy class constructors accept `LoggerProtocol` parameter

#### 3. Remove structlog Dependencies
- Remove `import structlog` from planning_strategy.py
- Remove `from structlog.typing import FilteringBoundLogger`
- Update all logger usage to use protocol methods

#### 4. Update Factory Dependency Injection
```python
# src/taskforce/application/factory.py
import structlog
from taskforce.core.interfaces.logging import LoggerProtocol

def create_strategy(self, strategy_type: str) -> PlanningStrategy:
    logger = structlog.get_logger().bind(component=f"{strategy_type}_strategy")
    # Create adapter or use logger directly as protocol
    return strategy_class(logger=logger)
```

#### 5. Update Other Core Files
- Address 19 other occurrences of structlog in Core domain
- Apply same protocol extraction pattern consistently

## Technical Notes

### Implementation Approach
- **Backward Compatibility:** Maintain existing behavior during transition
- **Protocol Design:** Start minimal with core logging methods, extend if needed
- **Dependency Injection:** Use existing factory pattern for logger injection
- **Testing Strategy:** Verify protocol compliance and behavior preservation

### Code Changes Required
1. **New File:** `src/taskforce/core/interfaces/logging.py`
2. **Modified:** `src/taskforce/core/domain/planning_strategy.py`
3. **Modified:** `src/taskforce/application/factory.py`
4. **Modified:** Other Core domain files using structlog (19 occurrences)

### Testing Requirements
- Unit tests for `LoggerProtocol` interface compliance
- Integration tests verifying logger injection works correctly
- Regression tests ensuring all existing functionality preserved
- Mock-based tests for protocol-based logging

## Definition of Done

- [x] `LoggerProtocol` interface created and documented
- [x] All function signatures updated to use protocol
- [x] Zero `structlog` imports remain in Core layer
- [x] Logger instances properly injected via DI
- [x] Tests updated to provide logger (API change requires test updates)
- [x] New unit tests for protocol interface
- [x] Code coverage maintained or improved
- [x] Documentation updated (docstrings, type hints)
- [x] Other Core files updated for consistency

## Risk Mitigation

**Risk:** Logger protocol may not support all structlog features needed
**Mitigation:** 
- Start with minimal protocol covering current usage
- Use adapter pattern if advanced features needed
- Gradual rollout with fallback to structlog if issues

**Risk:** Breaking changes in function signatures
**Mitigation:**
- Update all call sites simultaneously
- Use type hints to catch signature mismatches
- Comprehensive testing of all integration points

## Dependencies

**Prerequisites:**
- Understanding of existing factory pattern in `application/factory.py`
- Knowledge of dependency injection patterns used in codebase
- Familiarity with Protocol-based interfaces in Python

**Blocking:**
- This story blocks Story 2 and Story 3 (function decomposition)
- Must be completed before other Core domain structlog removals

## Story Validation

**How to verify completion:**
1. Run `grep -r "import structlog" src/taskforce/core/` - should return 0 results
2. Run existing test suite - all tests should pass
3. Verify logger injection works in integration tests
4. Check that logging output format remains consistent
5. Validate protocol interface compliance with mypy

**Acceptance test scenarios:**
- ✅ Agent execution with all three strategy types works correctly
- ✅ Logging output visible and properly formatted
- ✅ No runtime errors from logger usage
- ✅ Factory creates strategies with proper logger injection

## Dev Agent Record

### File List
- **New:** `src/taskforce/core/interfaces/logging.py` - LoggerProtocol interface
- **Modified:** `src/taskforce/core/domain/planning_strategy.py` - Updated to use LoggerProtocol
- **Modified:** `src/taskforce/core/domain/lean_agent.py` - Accept logger via DI
- **Modified:** `src/taskforce/core/domain/lean_agent_components/tool_executor.py` - Use LoggerProtocol
- **Modified:** `src/taskforce/core/domain/lean_agent_components/message_history_manager.py` - Use LoggerProtocol
- **Modified:** `src/taskforce/core/domain/lean_agent_components/prompt_builder.py` - Use LoggerProtocol
- **Modified:** `src/taskforce/core/domain/lean_agent_components/state_store.py` - Use LoggerProtocol
- **Modified:** `src/taskforce/core/domain/lean_agent_components/resource_closer.py` - Use LoggerProtocol
- **Modified:** `src/taskforce/core/domain/token_budgeter.py` - Accept logger via DI
- **Modified:** `src/taskforce/application/factory.py` - Create and inject logger instances
- **New:** `tests/unit/test_logging_protocol.py` - Unit tests for LoggerProtocol
- **Modified:** `tests/unit/core/test_lean_agent.py` - Updated to provide logger instances

### Change Log
- Created LoggerProtocol interface in `src/taskforce/core/interfaces/logging.py`
- Removed all structlog imports from Core domain (9 files updated)
- Updated function signatures to use LoggerProtocol instead of FilteringBoundLogger
- Updated Agent and strategy classes to accept logger via dependency injection
- Updated factory to create and inject logger instances for all agents and strategies
- Added unit tests for LoggerProtocol interface compliance
- Updated test fixtures to provide logger instances (required due to API change)

### Completion Notes
- All structlog imports successfully removed from Core domain
- LoggerProtocol interface implemented and tested
- Dependency injection pattern implemented in factory
- Tests updated to provide logger instances (API change requires test updates)
- Zero external dependencies remain in Core layer for logging

## QA Results

### Review Date: 2025-01-26

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

**Overall Assessment: EXCELLENT**

The implementation successfully achieves all acceptance criteria and demonstrates strong adherence to Clean Architecture principles. The LoggerProtocol abstraction is well-designed, properly tested, and correctly integrated throughout the Core domain.

**Strengths:**
- Clean separation of concerns: Core domain is now completely independent of structlog
- Proper dependency injection: Factory correctly creates and injects logger instances
- Comprehensive test coverage: Protocol compliance verified with multiple test scenarios
- Type safety: Proper use of Protocol type hints enables static type checking
- Consistent implementation: All Core domain files updated uniformly
- Backward compatibility: Existing functionality preserved while removing dependencies

### Refactoring Performed

No refactoring required. Code quality is excellent and follows best practices.

### Compliance Check

- **Coding Standards**: ✓ Fully compliant with PEP 8 and project standards
- **Project Structure**: ✓ Protocol correctly placed in `core/interfaces/`
- **Testing Strategy**: ✓ Unit tests cover protocol compliance and integration
- **All ACs Met**: ✓ All 6 acceptance criteria fully implemented and verified

### Improvements Checklist

- [x] LoggerProtocol interface created and documented
- [x] All function signatures updated to use protocol
- [x] Zero structlog imports remain in Core layer (verified via grep)
- [x] Logger instances properly injected via DI
- [x] Tests updated to provide logger instances
- [x] New unit tests for protocol interface
- [x] Code coverage maintained
- [x] Documentation updated (docstrings, type hints)
- [ ] Consider adding LoggerProtocol to `__all__` export in `core/interfaces/__init__.py` (minor enhancement)
- [ ] Consider adding `@runtime_checkable` decorator if runtime type checking needed (optional)

### Security Review

**Status: PASS**

No security concerns identified. The protocol abstraction maintains existing security posture. Logger injection follows secure dependency injection patterns.

### Performance Considerations

**Status: PASS**

No performance impact. Protocol abstraction adds minimal overhead (essentially zero at runtime). Existing performance characteristics maintained.

### Files Modified During Review

No files modified during QA review. Implementation is production-ready.

### Gate Status

**Gate: PASS** → `docs/qa/gates/001.001-extract-logging-protocol.yml`

**Quality Score: 95/100**

**Risk Profile**: Low risk - All acceptance criteria met, comprehensive tests passing, zero structlog dependencies in Core domain verified.

**NFR Assessment**: All non-functional requirements validated:
- Security: PASS
- Performance: PASS  
- Reliability: PASS
- Maintainability: PASS

### Recommended Status

✓ **Ready for Done**

All acceptance criteria met. Implementation demonstrates excellent adherence to Clean Architecture principles. Minor enhancement suggestions (adding to `__all__` export) are optional and do not block completion.