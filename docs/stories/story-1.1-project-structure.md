# Story 1.1: Establish Taskforce Project Structure and Dependencies

**Epic**: Build Taskforce Production Framework with Clean Architecture  
**Story ID**: 1.1  
**Status**: Ready for Review  
**Priority**: Critical  
**Estimated Points**: 2  
**Dependencies**: None (Foundation story)

---

## User Story

As a **developer**,  
I want **the Taskforce project structure created with proper Python packaging**,  
so that **I have a clean foundation for implementing Clean Architecture layers**.

---

## Acceptance Criteria

1. ✅ Create `taskforce/` directory at repository root (sibling to `capstone/`)
2. ✅ Create `taskforce/pyproject.toml` with project metadata, dependencies (LiteLLM, Typer, FastAPI, structlog, SQLAlchemy, Alembic, pytest), and CLI entry points
3. ✅ Create `taskforce/src/taskforce/` with subdirectories: `core/`, `infrastructure/`, `application/`, `api/`
4. ✅ Create subdirectory structure:
   - `core/domain/`, `core/interfaces/`, `core/prompts/`
   - `infrastructure/persistence/`, `infrastructure/llm/`, `infrastructure/tools/`, `infrastructure/memory/`
   - `application/` (factory, executor, profiles modules)
   - `api/routes/`, `api/cli/`
5. ✅ Create `taskforce/tests/` with `unit/`, `integration/`, `fixtures/` subdirectories
6. ✅ Create placeholder `__init__.py` files in all packages
7. ✅ Verify `uv sync` successfully installs all dependencies
8. ✅ Create `taskforce/README.md` with project overview and setup instructions

---

## Integration Verification

- **IV1: Existing Functionality Verification** - Agent V2 in `capstone/agent_v2` continues to function independently (no import conflicts)
- **IV2: Integration Point Verification** - `uv sync` in `taskforce/` completes successfully with all dependencies resolved
- **IV3: Performance Impact Verification** - N/A (project setup only)

---

## Technical Notes

**Directory Structure to Create:**
```
taskforce/
├── pyproject.toml
├── README.md
├── src/
│   └── taskforce/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── domain/
│       │   │   └── __init__.py
│       │   ├── interfaces/
│       │   │   └── __init__.py
│       │   └── prompts/
│       │       └── __init__.py
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   ├── persistence/
│       │   │   └── __init__.py
│       │   ├── llm/
│       │   │   └── __init__.py
│       │   ├── tools/
│       │   │   ├── __init__.py
│       │   │   ├── native/
│       │   │   │   └── __init__.py
│       │   │   ├── rag/
│       │   │   │   └── __init__.py
│       │   │   └── mcp/
│       │   │       └── __init__.py
│       │   └── memory/
│       │       └── __init__.py
│       ├── application/
│       │   └── __init__.py
│       └── api/
│           ├── __init__.py
│           ├── routes/
│           │   └── __init__.py
│           └── cli/
│               └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   └── __init__.py
│   ├── integration/
│   │   └── __init__.py
│   └── fixtures/
│       └── __init__.py
└── docs/
    └── stories/
```

**Key Dependencies (pyproject.toml):**
- Python = "^3.11"
- litellm = "^1.7.7"
- typer = "^0.9.0"
- fastapi = "^0.116.1"
- structlog = "^24.2.0"
- sqlalchemy = "^2.0"
- alembic = "^1.13"
- pytest = "^8.4.2"
- pytest-asyncio = "^0.23"
- rich = "^13.0.0"
- pydantic = "^2.0"
- pydantic-settings = "^2.0"
- aiofiles = "^23.2.1"

---

## Definition of Done

- [x] All directories and `__init__.py` files created
- [x] `pyproject.toml` contains all required dependencies
- [x] `uv sync` completes without errors
- [x] `README.md` provides clear setup instructions
- [x] Agent V2 (`capstone/agent_v2`) still works independently
- [ ] Code committed to version control

---

## Dev Agent Record

### Agent Model Used
Claude Sonnet 4.5

### Debug Log References
None

### Completion Notes
- Created complete project structure with all required directories following Clean Architecture layers
- Generated `pyproject.toml` with all specified dependencies (LiteLLM, Typer, FastAPI, structlog, SQLAlchemy, Alembic, pytest, etc.)
- Created comprehensive `README.md` with setup instructions, usage examples, and architecture overview
- Created all `__init__.py` files with descriptive docstrings for each package
- Successfully ran `uv sync` - installed 82 packages without errors
- Created and ran package structure tests - all 5 tests passed with 100% coverage on imports
- Verified no import conflicts between taskforce and Agent V2 (separate virtual environments)
- Created placeholder CLI entry point (`taskforce.api.cli.main`) to satisfy pyproject.toml entry point

### File List
**Created:**
- `taskforce/pyproject.toml` - Project configuration with dependencies and build settings
- `taskforce/README.md` - Comprehensive project documentation
- `taskforce/src/taskforce/__init__.py` - Root package init
- `taskforce/src/taskforce/core/__init__.py` - Core layer init
- `taskforce/src/taskforce/core/domain/__init__.py` - Domain models init
- `taskforce/src/taskforce/core/interfaces/__init__.py` - Protocol interfaces init
- `taskforce/src/taskforce/core/prompts/__init__.py` - Prompts init
- `taskforce/src/taskforce/infrastructure/__init__.py` - Infrastructure layer init
- `taskforce/src/taskforce/infrastructure/persistence/__init__.py` - Persistence init
- `taskforce/src/taskforce/infrastructure/llm/__init__.py` - LLM service init
- `taskforce/src/taskforce/infrastructure/tools/__init__.py` - Tools init
- `taskforce/src/taskforce/infrastructure/tools/native/__init__.py` - Native tools init
- `taskforce/src/taskforce/infrastructure/tools/rag/__init__.py` - RAG tools init
- `taskforce/src/taskforce/infrastructure/tools/mcp/__init__.py` - MCP tools init
- `taskforce/src/taskforce/infrastructure/memory/__init__.py` - Memory init
- `taskforce/src/taskforce/application/__init__.py` - Application layer init
- `taskforce/src/taskforce/api/__init__.py` - API layer init
- `taskforce/src/taskforce/api/routes/__init__.py` - FastAPI routes init
- `taskforce/src/taskforce/api/cli/__init__.py` - CLI init
- `taskforce/src/taskforce/api/cli/main.py` - CLI entry point with version command
- `taskforce/tests/__init__.py` - Tests root init
- `taskforce/tests/unit/__init__.py` - Unit tests init
- `taskforce/tests/integration/__init__.py` - Integration tests init
- `taskforce/tests/fixtures/__init__.py` - Test fixtures init
- `taskforce/tests/unit/test_package_structure.py` - Package structure validation tests
- `taskforce/uv.lock` - Locked dependency versions (auto-generated by uv)

**Modified:**
- None (all new files)

**Deleted:**
- None

### Change Log
1. Created `pyproject.toml` with all required dependencies and CLI entry point configuration
2. Created comprehensive `README.md` with setup, usage, and architecture documentation
3. Created complete directory structure using PowerShell `New-Item` command
4. Created all 21 `__init__.py` files with descriptive docstrings
5. Created placeholder CLI main.py to satisfy entry point requirement
6. Ran `uv sync` successfully - installed 82 packages including litellm, typer, fastapi, structlog, sqlalchemy, alembic, pytest
7. Created package structure test suite with 5 tests covering all layer imports
8. Verified all tests pass (5/5 passed in 0.25s)
9. Verified no import conflicts with Agent V2 (separate virtual environments maintain isolation)

---

## QA Results

### Review Date: 2025-11-22

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

**Overall Assessment**: Excellent foundation work. The project structure is well-organized, follows Clean Architecture principles, and all acceptance criteria are met. The implementation demonstrates good understanding of Python packaging, dependency management, and testing practices.

**Strengths**:
- Complete directory structure matching Clean Architecture layers
- Comprehensive `pyproject.toml` with all required dependencies
- Well-structured test suite with proper organization
- Excellent documentation in README.md
- All tests passing (5/5)
- No linting or type checking errors
- Proper isolation from Agent V2 (separate virtual environments)

**Risk Level**: Low - Foundation story with minimal risk, but critical for project success.

### Refactoring Performed

- **File**: `taskforce/pyproject.toml`
  - **Change**: Updated Ruff configuration to use `[tool.ruff.lint]` section instead of deprecated top-level settings
  - **Why**: Ruff 0.1.0+ deprecates top-level `select`, `ignore`, and `per-file-ignores` in favor of `[tool.ruff.lint]` section
  - **How**: Moved `select`, `ignore`, and `per-file-ignores` under `[tool.ruff.lint]` to eliminate deprecation warnings

### Compliance Check

- **Coding Standards**: ✓ Compliant
  - PEP 8 compliant structure
  - Proper package organization
  - All `__init__.py` files present with docstrings
  - No code duplication
  - Clean separation of concerns

- **Project Structure**: ✓ Compliant
  - Matches Clean Architecture layers exactly as specified
  - Proper `src/` layout for Python packages
  - Tests organized in `tests/` with unit/integration/fixtures subdirectories
  - Documentation in `docs/` directory

- **Testing Strategy**: ✓ Compliant
  - Test suite created with proper structure
  - Tests validate package imports and structure
  - pytest configuration properly set up
  - Coverage reporting configured

- **All ACs Met**: ✓ All 8 acceptance criteria fully met
  1. ✓ `taskforce/` directory created at repository root
  2. ✓ `pyproject.toml` with all required dependencies and CLI entry points
  3. ✓ `src/taskforce/` with all required subdirectories
  4. ✓ Complete subdirectory structure (core, infrastructure, application, api)
  5. ✓ `tests/` with unit/integration/fixtures subdirectories
  6. ✓ All `__init__.py` files created
  7. ✓ `uv sync` completes successfully (82 packages installed)
  8. ✓ `README.md` with comprehensive documentation

### Requirements Traceability

**Given-When-Then Test Mapping**:

- **AC1**: Given `taskforce/` directory exists → When importing taskforce → Then no import errors
  - **Test**: `test_taskforce_imports()` validates root package import

- **AC2**: Given `pyproject.toml` exists → When running `uv sync` → Then all dependencies install successfully
  - **Test**: Manual verification - `uv sync` completed with 82 packages

- **AC3-4**: Given package structure exists → When importing layers → Then all modules import correctly
  - **Tests**: `test_core_layer_imports()`, `test_infrastructure_layer_imports()`, `test_application_layer_imports()`, `test_api_layer_imports()`

- **AC5**: Given `tests/` directory structure exists → When running pytest → Then tests discover correctly
  - **Test**: pytest configuration validates test discovery

- **AC6**: Given `__init__.py` files exist → When importing packages → Then no import errors
  - **Tests**: All import tests validate package structure

- **AC7**: Given dependencies are specified → When running `uv sync` → Then installation succeeds
  - **Test**: Manual verification - installation successful

- **AC8**: Given `README.md` exists → When reading documentation → Then setup instructions are clear
  - **Test**: Manual review - comprehensive documentation present

**Coverage Gaps**: None identified. All acceptance criteria have corresponding validation.

### Improvements Checklist

- [x] Fixed Ruff configuration deprecation warning (pyproject.toml)
- [ ] Consider adding `.env.example` file referenced in README (low priority)
- [ ] Consider adding pre-commit hooks configuration (future enhancement)
- [ ] Consider adding CI/CD workflow configuration (future enhancement)

### Security Review

**Findings**: No security concerns identified.

- No secrets hardcoded in configuration
- Dependencies use version constraints (not `latest`)
- Proper package isolation (separate virtual environments)
- No sensitive data in code or documentation

### Performance Considerations

**Findings**: N/A for foundation story.

- Project setup only - no runtime performance implications
- Dependency installation verified (82 packages in ~2.79s)
- Test execution time acceptable (0.22s for 5 tests)

### Test Architecture Assessment

**Test Coverage**:
- Package structure tests: 5/5 passing
- Import validation: 100% coverage of all layers
- Test organization: Proper separation (unit/integration/fixtures)

**Test Design Quality**:
- Tests are focused and maintainable
- Proper use of pytest conventions
- Clear test names describing what is being validated

**Testability**:
- **Controllability**: ✓ High - Can control package structure and imports
- **Observability**: ✓ High - Import success/failure clearly observable
- **Debuggability**: ✓ High - Clear test output and error messages

### Technical Debt Identification

**Minor Items** (non-blocking):
1. Ruff config deprecation warning (FIXED during review)
2. CLI main.py has 0% coverage (acceptable for placeholder)
3. No `.env.example` file (documented in README but not created)

**No Critical Technical Debt**: Foundation is solid and ready for next stories.

### Files Modified During Review

- `taskforce/pyproject.toml` - Fixed Ruff configuration deprecation warning
  - Dev: Please verify this change doesn't break your workflow

### Gate Status

**Gate**: PASS → `docs/qa/gates/1.1-project-structure.yml`

**Quality Score**: 100/100

**Rationale**: All acceptance criteria met, all tests passing, no blocking issues, minor improvements addressed during review. Foundation is solid and ready for next development stories.

### Recommended Status

✓ **Ready for Done** - Story is complete and meets all quality gates. No blocking issues identified.

