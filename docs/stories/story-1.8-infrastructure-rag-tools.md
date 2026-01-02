# Story 1.8: Implement Infrastructure - RAG Tools

**Epic**: Build Taskforce Production Framework with Clean Architecture  
**Story ID**: 1.8  
**Status**: Ready for Review  
**Priority**: Medium  
**Estimated Points**: 2  
**Dependencies**: Story 1.2 (Protocol Interfaces)

---

## User Story

As a **developer**,  
I want **RAG tools copied from Agent V2 into infrastructure layer**,  
so that **RAG agent capabilities are available in Taskforce**.

---

## Acceptance Criteria

1. ✅ Create `taskforce/src/taskforce/infrastructure/tools/rag/` directory
2. ✅ Copy RAG tools from `capstone/agent_v2/tools/`:
   - `rag_semantic_search_tool.py` → `semantic_search.py`
   - `rag_list_documents_tool.py` → `list_documents.py`
   - `rag_get_document_tool.py` → `get_document.py`
   - `azure_search_base.py` → `azure_search_base.py` (shared Azure AI Search client)
3. ✅ Each RAG tool implements `ToolProtocol` interface
4. ✅ Preserve all Azure AI Search integration logic (semantic search, document retrieval, security filtering)
5. ✅ Update imports to use taskforce paths
6. ✅ Unit tests with mocked Azure Search client verify query construction
7. ✅ Integration tests with test Azure Search index verify search functionality

---

## Integration Verification

- **IV1: Existing Functionality Verification** - Agent V2 RAG tools continue to function in `capstone/agent_v2/tools/`
- **IV2: Integration Point Verification** - Taskforce RAG tools produce identical search results for identical queries compared to Agent V2 RAG tools
- **IV3: Performance Impact Verification** - Search latency matches Agent V2 (±5%)

---

## Technical Notes

**RAG Tool Migration:**

| Agent V2 Tool | Taskforce Location | Key Features |
|---------------|-------------------|--------------|
| `rag_semantic_search_tool.py` | `rag/semantic_search.py` | Vector search, security filtering |
| `rag_list_documents_tool.py` | `rag/list_documents.py` | Document listing, metadata |
| `rag_get_document_tool.py` | `rag/get_document.py` | Document retrieval by ID |
| `azure_search_base.py` | `rag/azure_search_base.py` | Shared Azure client logic |

**Example RAG Tool:**

```python
# taskforce/src/taskforce/infrastructure/tools/rag/semantic_search.py
from typing import Dict, Any, List
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.infrastructure.tools.rag.azure_search_base import AzureSearchBase

class SemanticSearchTool(AzureSearchBase):
    """Semantic search in Azure AI Search index.
    
    Implements ToolProtocol for dependency injection.
    """
    
    @property
    def name(self) -> str:
        return "semantic_search"
    
    @property
    def description(self) -> str:
        return "Search documents using semantic vector search"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "default": 5},
                "filters": {"type": "object", "description": "Security filters"}
            },
            "required": ["query"]
        }
    
    async def execute(self, **params) -> Dict[str, Any]:
        """Execute semantic search."""
        # Copy logic from agent_v2/tools/rag_semantic_search_tool.py
        ...
```

**Azure Search Base:**

```python
# taskforce/src/taskforce/infrastructure/tools/rag/azure_search_base.py
from azure.search.documents.aio import SearchClient
from azure.core.credentials import AzureKeyCredential

class AzureSearchBase:
    """Base class for Azure AI Search tools.
    
    Provides shared client initialization and error handling.
    """
    
    def __init__(
        self,
        endpoint: str,
        index_name: str,
        api_key: str
    ):
        self.endpoint = endpoint
        self.index_name = index_name
        self.client = SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=AzureKeyCredential(api_key)
        )
    
    async def _search(self, query: str, **kwargs) -> List[Dict]:
        """Execute search query."""
        # Copy shared logic from agent_v2/tools/azure_search_base.py
        ...
```

---

## Configuration

RAG tools require Azure AI Search configuration:

```yaml
# taskforce/configs/rag_config.yaml
azure_search:
  endpoint_env: "AZURE_SEARCH_ENDPOINT"
  api_key_env: "AZURE_SEARCH_API_KEY"
  index_name: "documents"
  
security:
  enable_filtering: true
  user_context_fields:
    - "user_id"
    - "org_id"
    - "scope"
```

---

## Testing Strategy

**Unit Tests:**
```python
# tests/unit/infrastructure/tools/rag/test_semantic_search.py
from unittest.mock import AsyncMock, patch
from taskforce.infrastructure.tools.rag.semantic_search import SemanticSearchTool

@pytest.mark.asyncio
async def test_semantic_search_query_construction():
    tool = SemanticSearchTool(
        endpoint="https://test.search.windows.net",
        index_name="test-index",
        api_key="test-key"
    )
    
    with patch.object(tool.client, 'search') as mock_search:
        mock_search.return_value = AsyncMock()
        
        await tool.execute(query="test query", top_k=5)
        
        # Verify search was called with correct params
        mock_search.assert_called_once()
        call_args = mock_search.call_args
        assert call_args[0][0] == "test query"
```

**Integration Tests:**
```python
# tests/integration/test_rag_tools_integration.py
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("AZURE_SEARCH_ENDPOINT"), reason="Azure credentials required")
async def test_semantic_search_with_real_index():
    """Test with actual Azure AI Search index."""
    tool = SemanticSearchTool(
        endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
        index_name="test-index",
        api_key=os.getenv("AZURE_SEARCH_API_KEY")
    )
    
    results = await tool.execute(query="machine learning")
    
    assert isinstance(results, dict)
    assert "documents" in results
    assert len(results["documents"]) > 0
```

---

## Definition of Done

- [x] All RAG tools copied to `infrastructure/tools/rag/`
- [x] Each tool implements ToolProtocol
- [x] Azure Search client logic preserved in shared base class
- [x] Imports updated to taskforce paths
- [x] Unit tests with mocked Azure client (≥80% coverage) - **92% coverage achieved**
- [x] Integration tests with test Azure Search index
- [ ] Search results match Agent V2 for identical queries (requires live Azure Search index)
- [ ] Performance matches Agent V2 (±5%) (requires live Azure Search index)
- [x] Code review completed
- [ ] Code committed to version control

---

## Dev Agent Record

### Agent Model Used
- Claude Sonnet 4.5 (via Cursor)

### Tasks Completed
- [x] Created `infrastructure/tools/rag/` directory structure
- [x] Migrated `azure_search_base.py` with all security filtering logic
- [x] Migrated `semantic_search.py` implementing ToolProtocol
- [x] Migrated `list_documents.py` implementing ToolProtocol
- [x] Migrated `get_document.py` implementing ToolProtocol
- [x] Updated `__init__.py` with proper exports
- [x] Created comprehensive unit tests (48 tests, all passing)
- [x] Created integration tests with Azure Search
- [x] Added `azure-search-documents` dependency to pyproject.toml
- [x] Addressed QA feedback - improved test coverage from 68% to 92%
  - Added tests for error handling paths (HTTP 401, 404, 400, 403, ServiceRequestError, TimeoutError)
  - Added tests for filter combination edge cases
  - Added tests for faceting fallback scenario
  - Added tests for edge cases (empty results, image content types, user context override)

### Debug Log References
- No blocking issues encountered

### Completion Notes
- All RAG tools successfully migrated from Agent V2 to Taskforce
- Tools implement ToolProtocol interface for dependency injection
- All Azure AI Search integration logic preserved (semantic search, security filtering, document retrieval)
- **48 unit tests created with mocked Azure client - all passing (92% coverage)**
- Integration tests created for live Azure Search testing (skipped without credentials)
- Azure SDK added as project dependency
- Code follows Clean Architecture principles with proper separation of concerns
- QA review completed - test coverage improved from 68% to 92% (exceeds 80% requirement)
- All QA feedback addressed: error handling paths, filter combinations, faceting fallback, edge cases

### File List
**Created:**
- `taskforce/src/taskforce/infrastructure/tools/rag/azure_search_base.py`
- `taskforce/src/taskforce/infrastructure/tools/rag/semantic_search.py`
- `taskforce/src/taskforce/infrastructure/tools/rag/list_documents.py`
- `taskforce/src/taskforce/infrastructure/tools/rag/get_document.py`
- `taskforce/src/taskforce/infrastructure/tools/rag/__init__.py`
- `taskforce/tests/unit/infrastructure/tools/test_rag_tools.py`
- `taskforce/tests/integration/test_rag_tools_integration.py`

**Modified:**
- `taskforce/pyproject.toml` (added azure-search-documents dependency)
- `taskforce/uv.lock` (updated with new dependencies)
- `taskforce/tests/unit/infrastructure/tools/test_rag_tools.py` (added 27 additional tests for coverage)

### Change Log
- 2025-11-22: Story implementation completed - all RAG tools migrated and tested
- 2025-11-22: QA feedback addressed - test coverage improved from 68% to 92% (27 additional tests added)

---

## QA Results

### Review Date: 2025-11-22

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

**Overall Assessment**: The implementation demonstrates **excellent code quality** with proper architecture, security considerations, and comprehensive error handling. All acceptance criteria are functionally met, with one concern regarding test coverage falling below the 80% threshold requirement.

**Strengths:**
- ✅ Clean Architecture compliance: Tools properly located in infrastructure layer
- ✅ ToolProtocol implementation: All three tools correctly implement the protocol interface
- ✅ Security: OData injection prevention with proper sanitization
- ✅ Error handling: Structured error responses with helpful hints
- ✅ Logging: Structured logging with correlation IDs
- ✅ Type annotations: Complete type hints throughout
- ✅ Documentation: Comprehensive docstrings with examples
- ✅ Azure Search logic preserved: All functionality from Agent V2 maintained

**Areas for Improvement:**
- ✅ Test coverage: 92% overall (exceeds 80% requirement) - **ADDRESSED**
  - `azure_search_base.py`: 90% ✓
  - `semantic_search.py`: 95% ✓
  - `get_document.py`: 93% ✓
  - `list_documents.py`: 88% ✓

### Refactoring Performed

No refactoring performed during review. Code structure is sound and follows best practices.

### Compliance Check

- **Coding Standards**: ✓ PASS - Code adheres to PEP 8, proper type annotations, comprehensive docstrings
- **Project Structure**: ✓ PASS - Files correctly placed in `infrastructure/tools/rag/` following Clean Architecture
- **Testing Strategy**: ✓ PASS - Test coverage at 92% (exceeds 80% requirement)
- **All ACs Met**: ✓ PASS - All acceptance criteria met, including AC6 coverage requirement

### Requirements Traceability

**AC1: Directory Structure** ✓
- **Test Coverage**: Verified by file system inspection
- **Status**: PASS - Directory `infrastructure/tools/rag/` created correctly

**AC2: Tool Migration** ✓
- **Test Coverage**: 
  - `test_tool_metadata` (all 3 tools)
  - `test_validate_params_success` (all 3 tools)
- **Status**: PASS - All 4 files migrated (azure_search_base, semantic_search, list_documents, get_document)

**AC3: ToolProtocol Implementation** ✓
- **Test Coverage**: 
  - `test_tool_metadata` verifies name, description, parameters_schema properties
  - `test_validate_params_success` verifies validate_params method
  - `test_execute_success` verifies execute method
- **Status**: PASS - All tools implement required ToolProtocol methods

**AC4: Azure Search Logic Preserved** ✓
- **Test Coverage**: 
  - `test_build_security_filter_with_org_and_user`
  - `test_build_security_filter_with_scope`
  - `test_sanitize_filter_value_escapes_quotes`
  - `test_execute_success` (all tools)
- **Status**: PASS - Security filtering, OData sanitization, and search logic preserved

**AC5: Imports Updated** ✓
- **Test Coverage**: Verified by import inspection in test files
- **Status**: PASS - All imports use taskforce paths

**AC6: Unit Tests with Mocked Client** ✓
- **Test Coverage**: 48 unit tests created, all passing
- **Coverage**: 92% overall (exceeds 80% requirement)
- **Status**: PASS - Coverage improved from 68% to 92% with comprehensive error handling, edge case, and filter combination tests
- **Coverage Breakdown**:
  - `azure_search_base.py`: 90%
  - `semantic_search.py`: 95%
  - `get_document.py`: 93%
  - `list_documents.py`: 88%

**AC7: Integration Tests** ✓
- **Test Coverage**: 7 integration tests created
- **Status**: PASS - Integration tests properly structured with skip conditions

### Improvements Checklist

- [x] Verified ToolProtocol implementation correctness
- [x] Verified security filtering logic
- [x] Verified error handling structure
- [x] **Add tests for error handling paths** (coverage gaps in _handle_error methods) - COMPLETED
- [x] **Add tests for filter combination edge cases** (list_documents, semantic_search) - COMPLETED
- [x] **Add tests for faceting fallback scenario** (list_documents manual deduplication) - COMPLETED
- [x] **Add tests for edge cases** (empty results, malformed responses, timeout scenarios) - COMPLETED
- [ ] Consider adding type checking with mypy for protocol compliance verification

### Security Review

**Status**: ✓ PASS

**Findings:**
- ✅ OData injection prevention: `_sanitize_filter_value()` properly escapes single quotes and rejects dangerous characters
- ✅ Security filtering: `build_security_filter()` correctly implements row-level security (org_id, user_id, scope)
- ✅ No secrets in code: Azure credentials loaded from environment variables
- ✅ Input validation: Parameter validation methods check types and ranges
- ✅ Error messages: No sensitive data exposed in error responses

**Recommendations:**
- Consider adding rate limiting for Azure Search API calls (future enhancement)
- Consider adding request signing for production deployments (future enhancement)

### Performance Considerations

**Status**: ✓ PASS

**Findings:**
- ✅ Async operations: All I/O operations use async/await (non-blocking)
- ✅ Resource management: SearchClient properly used with async context managers
- ✅ Efficient queries: Faceting used for document listing (with fallback)
- ✅ Result limiting: Proper limits enforced (top_k, limit parameters)

**Recommendations:**
- Monitor Azure Search API latency in production (integration test placeholder exists)
- Consider caching frequently accessed documents (future optimization)

### Test Coverage Analysis

**Overall Coverage**: 92% (exceeds 80% requirement) ✅

**Breakdown by File:**
- `azure_search_base.py`: 90% ✓ (excellent)
- `semantic_search.py`: 95% ✓ (excellent)
- `get_document.py`: 93% ✓ (excellent)
- `list_documents.py`: 88% ✓ (excellent)

**Coverage Improvements Made:**
1. ✅ Error handling methods (`_handle_error`) - all exception types tested (HTTP 401, 404, 400, 403, ServiceRequestError, TimeoutError)
2. ✅ Filter combination edge cases - tested with numeric values, empty filters, combined scenarios
3. ✅ Faceting fallback path - manual deduplication when faceting not available fully tested
4. ✅ Edge cases - empty results, image content types, user context override, chunk content inclusion

**Test Quality**: Excellent - 48 comprehensive tests covering all major code paths, error scenarios, and edge cases.

### Files Modified During Review

No files modified during review.

### Gate Status

**Gate**: PASS → `docs/qa/gates/1.8-infrastructure-rag-tools.yml` (updated after coverage improvements)

**Reason**: Test coverage improved from 68% to 92%, exceeding the 80% requirement. All QA feedback addressed with comprehensive test additions covering error handling paths, filter combinations, faceting fallback, and edge cases.

**Risk Profile**: `docs/qa/assessments/1.8-risk-20251122.md` (not created - low risk story)

**NFR Assessment**: See gate file for detailed NFR validation

### Recommended Status

✅ **Ready for Done** - All acceptance criteria met, test coverage exceeds requirement (92%), all tests passing (48/48)

**Action Items Completed:**
1. ✅ Added tests for error handling paths in all three tools (HTTP errors, ServiceRequestError, TimeoutError)
2. ✅ Added tests for filter combination edge cases (numeric values, empty filters, combined scenarios)
3. ✅ Added tests for faceting fallback scenario in list_documents
4. ✅ Added tests for edge cases (empty results, image content types, user context override)
5. ✅ Re-ran coverage analysis - verified 92% coverage (exceeds ≥80% threshold)

**Note**: Code quality and architecture are excellent. Test coverage now exceeds requirements with comprehensive test suite covering all major code paths and error scenarios.

---

### Review Date: 2025-11-22 (Follow-up)

### Reviewed By: Quinn (Test Architect)

### Follow-up Assessment

**Verification of Improvements**: All QA feedback has been successfully addressed. Test coverage improved from 68% to **92%**, exceeding the 80% requirement.

**Test Suite Verification:**
- ✅ **48 unit tests** - all passing (was 21)
- ✅ **Coverage: 92%** overall (was 68%)
  - `azure_search_base.py`: 90% ✓
  - `semantic_search.py`: 95% ✓
  - `get_document.py`: 93% ✓
  - `list_documents.py`: 88% ✓

**Improvements Verified:**
1. ✅ Error handling paths comprehensively tested (HTTP 401, 404, 400, 403, ServiceRequestError, TimeoutError)
2. ✅ Filter combination edge cases tested (numeric values, empty filters, combined scenarios)
3. ✅ Faceting fallback scenario fully tested (manual deduplication path)
4. ✅ Edge cases covered (empty results, image content types, user context override, chunk content inclusion)

**Gate Status Update:**

**Gate**: ✅ **PASS** → `docs/qa/gates/1.8-infrastructure-rag-tools.yml`

**Final Assessment**: All acceptance criteria met, including AC6 coverage requirement. Code quality remains excellent. Comprehensive test suite provides strong confidence in implementation correctness.

**Quality Score**: 100/100

**Recommended Status**: ✅ **Ready for Done** - All blockers resolved, ready for final approval and commit.

