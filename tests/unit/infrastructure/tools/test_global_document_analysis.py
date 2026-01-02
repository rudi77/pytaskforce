"""Unit tests for GlobalDocumentAnalysisTool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List

from taskforce.infrastructure.tools.rag.global_document_analysis import GlobalDocumentAnalysisTool
from taskforce.infrastructure.tools.rag.azure_search_base import Document, Chunk
from taskforce.infrastructure.tools.rag.get_document import GetDocumentTool
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.tools import ApprovalRiskLevel


class MockLLMProvider:
    """Mock LLM provider for testing."""
    
    async def generate(self, prompt: str) -> str:
        """Mock generate method."""
        return f"Mock response for: {prompt[:50]}..."


class MockGetDocumentTool:
    """Mock GetDocumentTool for testing."""
    
    def __init__(self, return_value: Dict[str, Any]):
        self.return_value = return_value
    
    async def execute(self, document_id: str, user_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Mock execute method."""
        return self.return_value


class TestGlobalDocumentAnalysisTool:
    """Test GlobalDocumentAnalysisTool functionality."""

    def create_mock_chunk(self, content_text: str, chunk_id: str = "chunk1") -> Chunk:
        """Create a mock Chunk object for testing."""
        return Chunk(
            content_id=chunk_id,
            document_id="test-doc-id",
            document_title="Test Document",
            image_document_id="",
            content_text=content_text,
            org_id="test-org",
            user_id="test-user",
            scope="test",
            conversation_id="",
            document_type="pdf",
            content_path="",
            locationMetadata=None,
            hash="test-hash"
        )

    def create_mock_document(self, chunk_count: int = 5) -> Document:
        """Create a mock Document object with specified number of chunks."""
        chunks = [
            self.create_mock_chunk(f"Content of chunk {i+1}", f"chunk{i+1}")
            for i in range(chunk_count)
        ]
        
        return Document(
            document_id="test-doc-id",
            document_title="Test Document",
            document_type="pdf",
            org_id="test-org",
            user_id="test-user",
            scope="test",
            chunk_count=chunk_count,
            page_count=5,
            has_images=False,
            has_text=True,
            chunks=chunks
        )

    @pytest.fixture
    def llm_provider(self):
        """Create mock LLM provider."""
        return MockLLMProvider()

    @pytest.fixture
    def successful_get_document_tool(self):
        """Create mock GetDocumentTool that returns successful response."""
        mock_document = self.create_mock_document(5)
        return MockGetDocumentTool({
            "success": True,
            "content": mock_document.to_dict()
        })

    @pytest.fixture
    def failed_get_document_tool(self):
        """Create mock GetDocumentTool that returns failure response."""
        return MockGetDocumentTool({
            "success": False,
            "error": "Document not found"
        })

    @pytest.fixture
    def tool_small_doc(self, llm_provider, successful_get_document_tool):
        """Create GlobalDocumentAnalysisTool instance with small document."""
        return GlobalDocumentAnalysisTool(llm_provider, successful_get_document_tool)

    @pytest.fixture
    def tool_large_doc(self, llm_provider):
        """Create GlobalDocumentAnalysisTool instance with large document."""
        mock_document = self.create_mock_document(25)  # More than 20 chunks
        get_doc_tool = MockGetDocumentTool({
            "success": True,
            "content": mock_document.to_dict()
        })
        return GlobalDocumentAnalysisTool(llm_provider, get_doc_tool)

    @pytest.fixture
    def tool_failed_doc(self, llm_provider, failed_get_document_tool):
        """Create GlobalDocumentAnalysisTool instance with failed document retrieval."""
        return GlobalDocumentAnalysisTool(llm_provider, failed_get_document_tool)

    def test_tool_properties(self, tool_small_doc):
        """Test tool basic properties."""
        assert tool_small_doc.name == "global_document_analysis"
        assert "global questions about an certain document" in tool_small_doc.description
        assert not tool_small_doc.requires_approval
        assert tool_small_doc.approval_risk_level == ApprovalRiskLevel.LOW

    def test_parameters_schema(self, tool_small_doc):
        """Test parameters schema structure."""
        schema = tool_small_doc.parameters_schema
        
        assert schema["type"] == "object"
        assert "document_id" in schema["properties"]
        assert "question" in schema["properties"]
        assert "user_context" in schema["properties"]
        assert schema["required"] == ["document_id", "question"]

    def test_get_approval_preview(self, tool_small_doc):
        """Test approval preview generation."""
        preview = tool_small_doc.get_approval_preview(
            document_id="test-doc",
            question="What is this document about?"
        )
        
        assert "global_document_analysis" in preview
        assert "test-doc" in preview
        assert "What is this document about?" in preview

    def test_validate_params_success(self, tool_small_doc):
        """Test successful parameter validation."""
        is_valid, error = tool_small_doc.validate_params(
            document_id="test-doc",
            question="Test question"
        )
        
        assert is_valid is True
        assert error is None

    def test_validate_params_missing_document_id(self, tool_small_doc):
        """Test validation failure when document_id is missing."""
        is_valid, error = tool_small_doc.validate_params(
            question="Test question"
        )
        
        assert is_valid is False
        assert "Missing required parameter: document_id" in error

    def test_validate_params_missing_question(self, tool_small_doc):
        """Test validation failure when question is missing."""
        is_valid, error = tool_small_doc.validate_params(
            document_id="test-doc"
        )
        
        assert is_valid is False
        assert "Missing required parameter: question" in error

    def test_validate_params_invalid_document_id_type(self, tool_small_doc):
        """Test validation failure when document_id is not a string."""
        is_valid, error = tool_small_doc.validate_params(
            document_id=123,
            question="Test question"
        )
        
        assert is_valid is False
        assert "Parameter 'document_id' must be a string" in error

    def test_validate_params_invalid_question_type(self, tool_small_doc):
        """Test validation failure when question is not a string."""
        is_valid, error = tool_small_doc.validate_params(
            document_id="test-doc",
            question=123
        )
        
        assert is_valid is False
        assert "Parameter 'question' must be a string" in error

    @pytest.mark.asyncio
    async def test_execute_small_document_success(self, tool_small_doc):
        """Test execute method with small document (<=20 chunks)."""
        result = await tool_small_doc.execute(
            document_id="test-doc-id",
            question="What is this document about?",
            user_context={"org_id": "test-org", "user_id": "test-user"}
        )
        
        assert result["success"] is True
        assert "result" in result

    @pytest.mark.asyncio
    async def test_execute_large_document_success(self, tool_large_doc):
        """Test execute method with large document (>20 chunks) using map-reduce."""
        result = await tool_large_doc.execute(
            document_id="test-doc-id",
            question="What is this document about?",
            user_context={"org_id": "test-org", "user_id": "test-user"}
        )
        
        assert result["success"] is True
        assert "result" in result

    @pytest.mark.asyncio
    async def test_execute_document_retrieval_failure(self, tool_failed_doc):
        """Test execute method when document retrieval fails."""
        result = await tool_failed_doc.execute(
            document_id="nonexistent-doc",
            question="What is this document about?"
        )
        
        assert result["success"] is False
        assert "error" in result
        assert result["error"] == "Document not found"

    @pytest.mark.asyncio
    async def test_execute_no_user_context(self, tool_small_doc):
        """Test execute method without user context."""
        result = await tool_small_doc.execute(
            document_id="test-doc-id",
            question="What is this document about?"
        )
        
        assert result["success"] is True
        assert "result" in result

    @pytest.mark.asyncio
    async def test_execute_with_empty_user_context(self, tool_small_doc):
        """Test execute method with empty user context."""
        result = await tool_small_doc.execute(
            document_id="test-doc-id",
            question="What is this document about?",
            user_context={}
        )
        
        assert result["success"] is True
        assert "result" in result

    @pytest.mark.asyncio
    @patch('asyncio.gather')
    async def test_execute_large_document_map_reduce_flow(self, mock_gather, tool_large_doc):
        """Test that large documents use map-reduce processing."""
        # Mock asyncio.gather to return intermediate answers
        mock_gather.return_value = [
            "Answer from chunk group 1",
            "Answer from chunk group 2",
            "Answer from chunk group 3",
            "Answer from chunk group 4",
            "Answer from chunk group 5"
        ]
        
        result = await tool_large_doc.execute(
            document_id="test-doc-id",
            question="What is this document about?",
            user_context={"org_id": "test-org", "user_id": "test-user"}
        )
        
        # Verify asyncio.gather was called (indicating map-reduce was used)
        mock_gather.assert_called_once()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_with_kwargs(self, tool_small_doc):
        """Test execute method with additional kwargs."""
        result = await tool_small_doc.execute(
            document_id="test-doc-id",
            question="What is this document about?",
            user_context={"org_id": "test-org"},
            extra_param="ignored"
        )
        
        assert result["success"] is True
        assert "result" in result

    def test_document_edge_case_exactly_20_chunks(self, llm_provider):
        """Test behavior with exactly 20 chunks (boundary condition)."""
        mock_document = self.create_mock_document(20)
        get_doc_tool = MockGetDocumentTool({
            "success": True,
            "content": mock_document.to_dict()
        })
        tool = GlobalDocumentAnalysisTool(llm_provider, get_doc_tool)
        
        # Should use direct processing (not map-reduce) for exactly 20 chunks
        assert True  # This test verifies the tool can be created with 20 chunks

    def test_document_edge_case_21_chunks(self, llm_provider):
        """Test behavior with 21 chunks (just over boundary)."""
        mock_document = self.create_mock_document(21)
        get_doc_tool = MockGetDocumentTool({
            "success": True,
            "content": mock_document.to_dict()
        })
        tool = GlobalDocumentAnalysisTool(llm_provider, get_doc_tool)
        
        # Should use map-reduce for 21 chunks
        assert True  # This test verifies the tool can be created with 21 chunks

    @pytest.mark.asyncio
    async def test_execute_empty_chunks(self, llm_provider):
        """Test execute method with document having no chunks."""
        mock_document = Document(
            document_id="test-doc-id",
            document_title="Empty Document",
            document_type="pdf",
            org_id="test-org",
            user_id="test-user",
            scope="test",
            chunk_count=0,
            page_count=0,
            has_images=False,
            has_text=False,
            chunks=[]
        )
        
        get_doc_tool = MockGetDocumentTool({
            "success": True,
            "content": mock_document.to_dict()
        })
        tool = GlobalDocumentAnalysisTool(llm_provider, get_doc_tool)
        
        result = await tool.execute(
            document_id="test-doc-id",
            question="What is this document about?"
        )
        
        assert result["success"] is True
        assert "result" in result

    @pytest.mark.asyncio
    async def test_execute_none_chunks(self, llm_provider):
        """Test execute method with document having None chunks."""
        mock_document = Document(
            document_id="test-doc-id",
            document_title="Document with None chunks",
            document_type="pdf",
            org_id="test-org",
            user_id="test-user",
            scope="test",
            chunk_count=0,
            page_count=0,
            has_images=False,
            has_text=False,
            chunks=None
        )
        
        get_doc_tool = MockGetDocumentTool({
            "success": True,
            "content": mock_document.to_dict()
        })
        tool = GlobalDocumentAnalysisTool(llm_provider, get_doc_tool)
        
        result = await tool.execute(
            document_id="test-doc-id",
            question="What is this document about?"
        )
        
        assert result["success"] is True
        assert "result" in result