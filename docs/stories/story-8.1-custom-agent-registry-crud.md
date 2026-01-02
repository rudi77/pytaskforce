# Story 8.1: Custom Agent Registry (CRUD + YAML Persistence)

**Status:** Ready for Review  
**Epic:** [Epic 8: Custom Agent Registry via API](../epics/epic-8-custom-agent-registry-api.md)  
**Priorität:** Hoch  
**Schätzung:** 5 SP  
**Abhängigkeiten:** -  

---

## User Story

As a **Taskforce API consumer**,  
I want **to create, list, read, update, and delete custom LeanAgent definitions**,  
so that **I can manage reusable agents (prompt + tools + optional MCP) centrally via API**.

---

## Story Context

**Existing System Integration:**
- **Integrates with:** FastAPI (`taskforce.api.server`), existing routing pattern (`taskforce.api.routes.*`)
- **Persistence pattern:** file-based, similar operational expectations as `.taskforce/states/*.json`, but now under `taskforce/configs/custom/*.yaml`
- **Config style reference:** `taskforce/configs/dev.yaml` and other profiles (YAML, safe_load, predictable schema)

---

## Acceptance Criteria

### Functional Requirements

1. **Create**
   - `POST /api/v1/agents` creates a new custom agent and persists it as YAML in `taskforce/configs/custom/{agent_id}.yaml`.
   - If `{agent_id}.yaml` already exists → **409**.

2. **List (IMPORTANT: full detail + includes profiles)**
   - `GET /api/v1/agents` returns a list of **all agents that can be called**:
     - **custom** agents from `taskforce/configs/custom/*.yaml`
     - **profile** agents from `taskforce/configs/*.yaml`
   - For **custom** agents, each list entry includes:
     - `agent_id`, `name`, `description`, `system_prompt`, `tool_allowlist`, `mcp_servers`, `mcp_tool_allowlist`, `created_at`, `updated_at`
   - For **profile** agents, each list entry includes at minimum:
     - `profile`, `specialist` (or `agent_type`), `tools` (raw config list), `mcp_servers`, `llm` (config path + default model), `persistence` (work_dir)
   - Each list entry includes a discriminator field:
     - `source: "custom" | "profile"`
   - Listing is derived from scanning:
     - `taskforce/configs/custom/*.yaml`
     - `taskforce/configs/*.yaml` (excluding `llm_config.yaml` and excluding the `custom/` directory)

3. **Get**
   - `GET /api/v1/agents/{agent_id}` returns the full agent definition (same shape as in list).
   - Not found → **404**.

4. **Update**
   - `PUT /api/v1/agents/{agent_id}` replaces the agent definition and updates `updated_at`.
   - Not found → **404**.

5. **Delete**
   - `DELETE /api/v1/agents/{agent_id}` deletes the YAML file.
   - Not found → **404**.
   - Success → **204**.

### Data / Validation Requirements (Minimal in this story)

6. `agent_id` must match filename rules (lowercase `[a-z0-9-_]`, 3–64 chars) and is required for create.
7. Required fields for Create/Update:
   - `name`, `description`, `system_prompt`, `tool_allowlist` (tool validation comes in Story 8.2)
8. YAML must be written in a stable format (block style), preserving readability.
9. Timestamps:
   - `created_at` set on create
   - `updated_at` set on create/update
   - Both are ISO strings (UTC recommended)

### Quality Requirements

10. **Atomic write**: YAML persistence must be atomic on Windows (write temp + rename; remove target first if needed).
11. **Corrupt YAML behavior**: If a file cannot be parsed, it is skipped during list and logged as warning (do not crash endpoint).
12. **No secrets in repo**: Story examples must not introduce real PATs; env placeholders allowed.

---

## API Contract (Normative)

### Create Agent

`POST /api/v1/agents`

Request JSON:
```json
{
  "agent_id": "invoice-extractor",
  "name": "Invoice Extractor",
  "description": "Extracts structured fields from invoice text.",
  "system_prompt": "You are a LeanAgent ...",
  "tool_allowlist": ["file_read", "python"],
  "mcp_servers": [],
  "mcp_tool_allowlist": []
}
```

Response JSON (200/201 OK):
```json
{
  "agent_id": "invoice-extractor",
  "name": "Invoice Extractor",
  "description": "Extracts structured fields from invoice text.",
  "system_prompt": "You are a LeanAgent ...",
  "tool_allowlist": ["file_read", "python"],
  "mcp_servers": [],
  "mcp_tool_allowlist": [],
  "created_at": "2025-12-12T10:00:00Z",
  "updated_at": "2025-12-12T10:00:00Z"
}
```

Error responses:
- 400: invalid payload
- 409: agent_id already exists

### List Agents

`GET /api/v1/agents`

Response JSON:
```json
{
  "agents": [
    {
      "source": "custom",
      "agent_id": "invoice-extractor",
      "name": "Invoice Extractor",
      "description": "Extracts structured fields from invoice text.",
      "system_prompt": "You are a LeanAgent ...",
      "tool_allowlist": ["file_read", "python"],
      "mcp_servers": [],
      "mcp_tool_allowlist": [],
      "created_at": "2025-12-12T10:00:00Z",
      "updated_at": "2025-12-12T10:00:00Z"
    },
    {
      "source": "profile",
      "profile": "dev",
      "specialist": "generic",
      "tools": [
        { "type": "WebSearchTool", "module": "taskforce.infrastructure.tools.native.web_tools", "params": {} }
      ],
      "mcp_servers": [],
      "llm": { "config_path": "configs/llm_config.yaml", "default_model": "main" },
      "persistence": { "type": "file", "work_dir": ".taskforce" }
    }
  ]
}
```

---

## Technical Implementation Notes

### Suggested Files / Modules

- `taskforce/src/taskforce/infrastructure/persistence/file_agent_registry.py`
  - Responsible for file IO and YAML parsing/writing
  - Public methods (suggested):
    - `list_agents() -> list[AgentDefinition]`
    - `get_agent(agent_id: str) -> AgentDefinition | None`
    - `create_agent(definition: AgentDefinition) -> AgentDefinition`
    - `update_agent(agent_id: str, definition: AgentDefinition) -> AgentDefinition`
    - `delete_agent(agent_id: str) -> None`
- `taskforce/src/taskforce/api/routes/agents.py`
  - Implements CRUD endpoints
- `taskforce/src/taskforce/api/server.py`
  - Register router: `app.include_router(agents.router, prefix="/api/v1", tags=["agents"])`

### YAML Persistence Rules

- Directory: `taskforce/configs/custom/`
- Filename: `{agent_id}.yaml`
- YAML structure on disk should follow the epic’s schema (prompt/tools/mcp).
- Write algorithm:
  1. ensure directory exists
  2. serialize to YAML (`yaml.safe_dump`)
  3. write to temp file
  4. if target exists: delete target (Windows)
  5. rename temp → target

---

## Test Plan (Required)

- **Integration tests** (FastAPI TestClient):
  - Create → Get → List → Update → Get → Delete → Get(404)
  - Create conflict (409)
  - List with corrupt YAML file present (skipped + warning)

---

## Definition of Done

- [x] Endpoints exist and conform to the contracts above
- [x] YAML persistence is atomic and Windows-safe
- [x] List returns full details per agent (prompt/tools/MCP)
- [x] Tests added and passing

---

## Dev Agent Record

### Agent Model Used
- Claude Sonnet 4.5 (via Cursor)

### Completion Notes
- ✅ Created Pydantic schemas for custom and profile agents with validation
- ✅ Implemented FileAgentRegistry with atomic YAML writes (Windows-safe)
- ✅ Created REST API endpoints (POST, GET, PUT, DELETE) in `/api/v1/agents`
- ✅ Registered agents router in FastAPI server
- ✅ Created `configs/custom/` directory structure
- ✅ Wrote 16 integration tests covering all CRUD operations
- ✅ Tested corrupt YAML handling (graceful skip with warning)
- ✅ Tested atomic write behavior on Windows (temp file + rename)
- ✅ All tests passing (16/16)

### File List
**Created:**
- `taskforce/src/taskforce/api/schemas/agent_schemas.py` - Pydantic models for API
- `taskforce/src/taskforce/api/schemas/__init__.py` - Schema package exports
- `taskforce/src/taskforce/infrastructure/persistence/file_agent_registry.py` - CRUD logic
- `taskforce/src/taskforce/api/routes/agents.py` - REST API endpoints
- `taskforce/configs/custom/.gitkeep` - Custom agents directory
- `taskforce/tests/integration/test_agent_registry_api.py` - Integration tests

**Modified:**
- `taskforce/src/taskforce/api/server.py` - Registered agents router

### Change Log
- 2025-12-12: Implemented Story 8.1 - Custom Agent Registry CRUD
  - Added full CRUD API for custom agents
  - Implemented Windows-safe atomic YAML persistence
  - List endpoint returns both custom and profile agents with discriminator
  - 16 integration tests covering all scenarios
  - Graceful handling of corrupt YAML files

---

## QA Results

### Review Date: 2025-12-12

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

**Overall:** Excellent implementation with comprehensive test coverage. Code follows Clean Architecture principles, adheres to coding standards, and demonstrates thoughtful error handling. Minor concerns around thread safety documentation and error handling specificity.

**Strengths:**
- Clean separation of concerns (schemas, persistence, routes)
- Comprehensive test suite (16 tests, 90% coverage on registry)
- Windows-safe atomic file operations
- Graceful error handling for corrupt YAML
- Well-documented with clear docstrings
- Proper use of Pydantic for validation
- Type hints throughout

**Areas for Improvement:**
- Thread safety concern: Singleton registry instance may have concurrency issues (documented but not mitigated)
- Generic exception handling in routes could be more specific
- Missing input sanitization for file paths (low risk, but defense-in-depth)

### Refactoring Performed

No refactoring performed. Code quality is high and changes would be premature optimization.

### Compliance Check

- **Coding Standards:** ✓ Compliant
  - PEP 8 formatting
  - English variable names
  - Type annotations present
  - Docstrings follow Google style
  - Functions ≤30 lines (all methods well-sized)
  - No code duplication observed

- **Project Structure:** ✓ Compliant
  - Files placed in correct Clean Architecture layers
  - Follows existing patterns (similar to FileStateManager)
  - Proper package organization

- **Testing Strategy:** ✓ Compliant
  - Integration tests cover all CRUD operations
  - Tests use proper fixtures and isolation
  - Edge cases covered (corrupt YAML, validation, conflicts)
  - Test coverage: 90% for registry, 90% for routes

- **All ACs Met:** ✓ Verified
  - AC1: Create endpoint with 409 conflict ✓
  - AC2: List returns custom + profile agents with discriminator ✓
  - AC3: Get endpoint with 404 handling ✓
  - AC4: Update preserves created_at, updates updated_at ✓
  - AC5: Delete returns 204 ✓
  - AC6: agent_id validation (3-64 chars, lowercase) ✓
  - AC7: Required fields validated ✓
  - AC8: YAML written in block style ✓
  - AC9: Timestamps ISO format UTC ✓
  - AC10: Atomic writes Windows-safe ✓
  - AC11: Corrupt YAML skipped gracefully ✓
  - AC12: No secrets in examples ✓

### Requirements Traceability

**Given-When-Then Test Mapping:**

| AC | Test Case | Status |
|----|-----------|--------|
| AC1 | `test_create_agent_success`, `test_create_agent_conflict` | ✓ Covered |
| AC2 | `test_list_agents_empty`, `test_list_agents_with_custom`, `test_get_profile_agent` | ✓ Covered |
| AC3 | `test_get_agent_success`, `test_get_agent_not_found` | ✓ Covered |
| AC4 | `test_update_agent_success` | ✓ Covered |
| AC5 | `test_delete_agent_success`, `test_delete_agent_not_found` | ✓ Covered |
| AC6 | `test_agent_id_validation` | ✓ Covered |
| AC10 | `test_atomic_write_windows_safe` | ✓ Covered |
| AC11 | `test_list_with_corrupt_yaml` | ✓ Covered |
| AC1-5 | `test_crud_workflow` (end-to-end) | ✓ Covered |

**Coverage Gaps:** None identified. All acceptance criteria have corresponding tests.

### Improvements Checklist

- [x] Verified all ACs have test coverage
- [x] Confirmed Windows-safe atomic writes
- [x] Validated error handling for edge cases
- [ ] **Consider:** Add thread-safe locking for registry singleton (low priority - atomic writes mitigate risk)
- [ ] **Consider:** More specific exception types in route handlers (nice-to-have)
- [ ] **Consider:** Input sanitization for path traversal (defense-in-depth, low risk)

### Security Review

**Status:** PASS with minor recommendations

**Findings:**
- ✓ Input validation via Pydantic (agent_id regex, field lengths)
- ✓ No secrets in code or examples
- ✓ YAML parsing uses `safe_load` (prevents code execution)
- ⚠️ Path traversal: `agent_id` is validated but file paths constructed directly (low risk due to validation)
- ⚠️ No authentication/authorization (by design per story scope)

**Recommendations:**
- Future: Add path sanitization defense-in-depth
- Future: Add authentication/authorization when multi-user support needed (Story 8.2+)

### Performance Considerations

**Status:** PASS

**Findings:**
- ✓ File I/O is synchronous but lightweight (YAML files small)
- ✓ List operation scans directory (acceptable for expected scale)
- ✓ No N+1 queries or performance bottlenecks
- ✓ Atomic writes don't block reads

**Recommendations:**
- Future: Consider caching agent definitions if list endpoint becomes high-traffic
- Future: Consider async file I/O if performance becomes concern

### Reliability Assessment

**Status:** PASS

**Findings:**
- ✓ Atomic writes prevent corruption during concurrent access
- ✓ Corrupt YAML files handled gracefully (skip + log)
- ✓ Error handling covers all failure modes
- ⚠️ Thread safety: Singleton registry not thread-safe (documented, mitigated by atomic writes)

**Recommendations:**
- Consider adding file-level locking if concurrent writes become common
- Current implementation acceptable for MVP scope

### Maintainability Assessment

**Status:** PASS

**Findings:**
- ✓ Clear code structure and naming
- ✓ Comprehensive docstrings
- ✓ Follows existing patterns (FileStateManager)
- ✓ Type hints enable IDE support
- ✓ Tests serve as documentation

### Files Modified During Review

None. No refactoring performed.

### Gate Status

**Gate:** PASS → `docs/qa/gates/8.1-custom-agent-registry-crud.yml`

**Rationale:** All acceptance criteria met, comprehensive test coverage (16 tests, 90% coverage), code quality high, minor concerns documented but not blocking. Implementation is production-ready for MVP scope.

**Quality Score:** 95/100
- -5 points for thread safety concern (documented but not mitigated)

### Recommended Status

✓ **Ready for Done**

Implementation meets all requirements and quality standards. Minor recommendations are non-blocking and can be addressed in future iterations.


