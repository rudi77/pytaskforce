"""Integration tests for RAG tools with Azure AI Search.

These tests require actual Azure AI Search credentials and a test index.
They are skipped if credentials are not available.
"""

import os
import pytest

from taskforce.infrastructure.tools.rag.semantic_search import SemanticSearchTool
from taskforce.infrastructure.tools.rag.list_documents import ListDocumentsTool
from taskforce.infrastructure.tools.rag.get_document import GetDocumentTool


# Skip all tests in this module if Azure credentials are not available
pytestmark = pytest.mark.skipif(
    not os.getenv("AZURE_SEARCH_ENDPOINT") or not os.getenv("AZURE_SEARCH_API_KEY"),
    reason="Azure Search credentials required for integration tests"
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_search_with_real_index():
    """Test semantic search with actual Azure AI Search index."""
    tool = SemanticSearchTool(user_context={
        "org_id": os.getenv("TEST_ORG_ID", "test-org"),
        "user_id": os.getenv("TEST_USER_ID", "test-user")
    })
    
    # Execute a simple search query
    result = await tool.execute(query="test", top_k=5)
    
    # Verify result structure
    assert isinstance(result, dict)
    assert "success" in result
    
    if result["success"]:
        assert "results" in result
        assert "result_count" in result
        assert isinstance(result["results"], list)
        
        # If results exist, verify structure
        if result["results"]:
            first_result = result["results"][0]
            assert "content_id" in first_result
            assert "content_type" in first_result
            assert "document_id" in first_result
            assert "score" in first_result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_documents_with_real_index():
    """Test document listing with actual Azure AI Search index."""
    tool = ListDocumentsTool(user_context={
        "org_id": os.getenv("TEST_ORG_ID", "test-org")
    })
    
    # List documents
    result = await tool.execute(limit=10)
    
    # Verify result structure
    assert isinstance(result, dict)
    assert "success" in result
    
    if result["success"]:
        assert "documents" in result
        assert "count" in result
        assert isinstance(result["documents"], list)
        
        # If documents exist, verify structure
        if result["documents"]:
            first_doc = result["documents"][0]
            assert "document_id" in first_doc
            assert "document_title" in first_doc
            assert "document_type" in first_doc
            assert "chunk_count" in first_doc


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_document_with_real_index():
    """Test document retrieval with actual Azure AI Search index."""
    # First, list documents to get a valid document ID
    list_tool = ListDocumentsTool(user_context={
        "org_id": os.getenv("TEST_ORG_ID", "test-org")
    })
    
    list_result = await list_tool.execute(limit=1)
    
    if not list_result.get("success") or not list_result.get("documents"):
        pytest.skip("No documents available in test index")
    
    # Get the first document's title
    document_title = list_result["documents"][0]["document_title"]
    
    # Now retrieve the document details
    get_tool = GetDocumentTool(user_context={
        "org_id": os.getenv("TEST_ORG_ID", "test-org")
    })
    
    result = await get_tool.execute(document_id=document_title)
    
    # Verify result structure
    assert isinstance(result, dict)
    assert "success" in result
    
    if result["success"]:
        assert "document" in result
        doc = result["document"]
        assert "document_id" in doc
        assert "document_title" in doc
        assert "chunk_count" in doc
        assert "has_text" in doc
        assert "has_images" in doc
        assert "chunks" in doc


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_performance():
    """Test that search latency is within acceptable bounds."""
    import time
    
    tool = SemanticSearchTool(user_context={
        "org_id": os.getenv("TEST_ORG_ID", "test-org")
    })
    
    start_time = time.time()
    result = await tool.execute(query="test query", top_k=10)
    elapsed_ms = (time.time() - start_time) * 1000
    
    # Search should complete within 5 seconds (generous for integration test)
    assert elapsed_ms < 5000
    
    # If successful, result should have data
    if result.get("success"):
        assert "results" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_security_filtering():
    """Test that security filtering works correctly."""
    # Search with specific user context
    tool = SemanticSearchTool(user_context={
        "org_id": "test-org",
        "user_id": "test-user"
    })
    
    result = await tool.execute(query="test", top_k=10)
    
    # Verify that results (if any) respect security context
    if result.get("success") and result.get("results"):
        for item in result["results"]:
            # All results should belong to the same org
            if "org_id" in item:
                assert item["org_id"] == "test-org"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_handling_invalid_index():
    """Test error handling with invalid index configuration."""
    # Temporarily override index name to non-existent one
    tool = SemanticSearchTool()
    original_index = tool.azure_base.content_index
    tool.azure_base.content_index = "nonexistent-index-12345"
    
    try:
        result = await tool.execute(query="test")
        
        # Should return error, not raise exception
        assert result["success"] is False
        assert "error" in result
        assert "type" in result
    finally:
        # Restore original index
        tool.azure_base.content_index = original_index


@pytest.mark.integration
@pytest.mark.asyncio
async def test_comparison_with_agent_v2():
    """Test that Taskforce RAG tools produce similar results to Agent V2.
    
    This test verifies Integration Verification requirement IV2:
    Taskforce RAG tools produce identical search results for identical queries.
    """
    # This is a placeholder for actual comparison test
    # In a real scenario, you would:
    # 1. Execute same query with Agent V2 tools
    # 2. Execute same query with Taskforce tools
    # 3. Compare results (document IDs, scores, content)
    
    tool = SemanticSearchTool(user_context={
        "org_id": os.getenv("TEST_ORG_ID", "test-org")
    })
    
    result = await tool.execute(query="test query", top_k=5)
    
    # For now, just verify the tool works
    assert isinstance(result, dict)
    assert "success" in result
    
    # TODO: Implement actual comparison with Agent V2 results
    # when both systems are available in test environment

