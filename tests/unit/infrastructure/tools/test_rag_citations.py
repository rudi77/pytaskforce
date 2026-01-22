"""Tests for RAG citation support."""

import pytest
from taskforce.infrastructure.tools.rag.citations import (
    RAGCitation,
    RAGCitationExtractor,
    CitationFormatter,
    CitationStyle,
    CitationResult,
    create_citation_formatter,
)


class TestRAGCitation:
    """Tests for RAGCitation dataclass."""

    def test_citation_creation(self):
        """Test creating a basic citation."""
        citation = RAGCitation(
            document_id="doc-123",
            title="Test Document",
            score=0.85,
        )

        assert citation.document_id == "doc-123"
        assert citation.title == "Test Document"
        assert citation.score == 0.85
        assert citation.chunk_id is None
        assert citation.page_number is None

    def test_citation_full_fields(self):
        """Test citation with all fields populated."""
        citation = RAGCitation(
            document_id="doc-456",
            chunk_id="chunk-1",
            title="Complete Document",
            score=0.92,
            page_number=15,
            section="Introduction",
            snippet="This is a sample text...",
            metadata={"author": "Test Author"},
        )

        assert citation.chunk_id == "chunk-1"
        assert citation.page_number == 15
        assert citation.section == "Introduction"
        assert citation.metadata["author"] == "Test Author"

    def test_citation_to_dict(self):
        """Test converting citation to dictionary."""
        citation = RAGCitation(
            document_id="doc-123",
            title="Test",
            score=0.75,
            page_number=5,
        )

        result = citation.to_dict()

        assert result["document_id"] == "doc-123"
        assert result["title"] == "Test"
        assert result["score"] == 0.75
        assert result["page_number"] == 5

    def test_citation_from_dict(self):
        """Test creating citation from dictionary."""
        data = {
            "document_id": "doc-789",
            "title": "From Dict",
            "score": 0.88,
            "page_number": 10,
            "section": "Methods",
        }

        citation = RAGCitation.from_dict(data)

        assert citation.document_id == "doc-789"
        assert citation.title == "From Dict"
        assert citation.score == 0.88
        assert citation.page_number == 10
        assert citation.section == "Methods"


class TestRAGCitationExtractor:
    """Tests for RAGCitationExtractor."""

    def test_extract_from_semantic_search_success(self):
        """Test extracting citations from semantic search results."""
        result = {
            "success": True,
            "results": [
                {
                    "document_id": "doc-1",
                    "content_id": "chunk-1",
                    "document_title": "First Document",
                    "score": 0.95,
                    "page_number": 3,
                    "content": "Sample content from first document",
                    "relevance_reason": "Semantic Match",
                },
                {
                    "document_id": "doc-2",
                    "content_id": "chunk-2",
                    "document_title": "Second Document",
                    "score": 0.82,
                    "content": "Content from second document",
                },
            ],
            "result_count": 2,
        }

        citations = RAGCitationExtractor.extract_from_semantic_search(result)

        assert len(citations) == 2
        assert citations[0].document_id == "doc-1"
        assert citations[0].chunk_id == "chunk-1"
        assert citations[0].title == "First Document"
        assert citations[0].score == 0.95
        assert citations[0].page_number == 3
        assert "Sample content" in citations[0].snippet

        assert citations[1].document_id == "doc-2"
        assert citations[1].score == 0.82

    def test_extract_from_semantic_search_failure(self):
        """Test extracting from failed search returns empty list."""
        result = {
            "success": False,
            "error": "Search failed",
        }

        citations = RAGCitationExtractor.extract_from_semantic_search(result)

        assert len(citations) == 0

    def test_extract_from_semantic_search_empty(self):
        """Test extracting from empty results."""
        result = {
            "success": True,
            "results": [],
            "result_count": 0,
        }

        citations = RAGCitationExtractor.extract_from_semantic_search(result)

        assert len(citations) == 0

    def test_extract_from_get_document(self):
        """Test extracting citation from document retrieval."""
        result = {
            "success": True,
            "document": {
                "document_id": "doc-specific",
                "title": "Specific Document",
                "content": "Full document content here",
                "metadata": {"version": "1.0"},
            },
        }

        citations = RAGCitationExtractor.extract_from_get_document(result)

        assert len(citations) == 1
        assert citations[0].document_id == "doc-specific"
        assert citations[0].title == "Specific Document"
        assert citations[0].score == 1.0  # Direct retrieval

    def test_extract_from_result_routes_correctly(self):
        """Test that extract_from_result routes to correct extractor."""
        semantic_result = {
            "success": True,
            "results": [
                {
                    "document_id": "doc-1",
                    "document_title": "Doc",
                    "score": 0.9,
                    "content": "text",
                }
            ],
        }

        citations = RAGCitationExtractor.extract_from_result(
            "rag_semantic_search", semantic_result
        )

        assert len(citations) == 1
        assert citations[0].document_id == "doc-1"

    def test_extract_from_result_unknown_tool(self):
        """Test generic extraction for unknown tools."""
        result = {
            "success": True,
            "results": [
                {
                    "id": "doc-generic",
                    "title": "Generic Doc",
                    "relevance": 0.7,
                    "content": "Generic content",
                }
            ],
        }

        citations = RAGCitationExtractor.extract_from_result(
            "unknown_rag_tool", result
        )

        assert len(citations) == 1
        assert citations[0].document_id == "doc-generic"
        assert citations[0].score == 0.7

    def test_snippet_length_limited(self):
        """Test that snippets are limited in length."""
        long_content = "x" * 1000
        result = {
            "success": True,
            "results": [
                {
                    "document_id": "doc-1",
                    "document_title": "Long Doc",
                    "score": 0.8,
                    "content": long_content,
                }
            ],
        }

        citations = RAGCitationExtractor.extract_from_semantic_search(result)

        assert len(citations[0].snippet) <= 500


class TestCitationFormatter:
    """Tests for CitationFormatter."""

    @pytest.fixture
    def sample_citations(self):
        """Create sample citations for testing."""
        return [
            RAGCitation(
                document_id="doc-1",
                title="First Document",
                score=0.95,
                page_number=10,
                snippet="Content about machine learning",
            ),
            RAGCitation(
                document_id="doc-2",
                title="Second Document",
                score=0.85,
                page_number=25,
                section="Results",
                snippet="Analysis of results",
            ),
            RAGCitation(
                document_id="doc-3",
                title="Third Document",
                score=0.75,
                snippet="Additional information",
            ),
        ]

    def test_format_none_style(self, sample_citations):
        """Test that none style returns unmodified text."""
        formatter = CitationFormatter(style=CitationStyle.NONE)
        text = "This is a response about machine learning."

        result = formatter.format_citations(text, sample_citations)

        assert result.formatted_text == text
        assert result.style == CitationStyle.NONE
        assert len(result.references) == 0
        assert len(result.citations) == 3

    def test_format_appendix_style(self, sample_citations):
        """Test appendix style adds references at end."""
        formatter = CitationFormatter(style=CitationStyle.APPENDIX)
        text = "This is a response."

        result = formatter.format_citations(text, sample_citations)

        assert "**References:**" in result.formatted_text
        assert "[1]" in result.formatted_text
        assert "First Document" in result.formatted_text
        assert result.style == CitationStyle.APPENDIX

    def test_format_inline_style(self, sample_citations):
        """Test inline style adds markers to text."""
        formatter = CitationFormatter(style=CitationStyle.INLINE)
        text = "The machine learning model showed good results."

        result = formatter.format_citations(text, sample_citations)

        # Should have citation markers
        assert "[" in result.formatted_text
        assert "]" in result.formatted_text
        assert result.style == CitationStyle.INLINE

    def test_max_citations_limit(self, sample_citations):
        """Test that max_citations limits output."""
        formatter = CitationFormatter(
            style=CitationStyle.APPENDIX,
            max_citations=2,
        )
        text = "Test response."

        result = formatter.format_citations(text, sample_citations)

        assert len(result.citations) == 2
        assert len(result.references) == 2

    def test_format_reference_with_page(self, sample_citations):
        """Test reference formatting includes page number."""
        formatter = CitationFormatter(
            style=CitationStyle.APPENDIX,
            include_page=True,
        )

        ref = formatter._format_reference(sample_citations[0], 1)

        assert "p. 10" in ref
        assert "First Document" in ref

    def test_format_reference_with_score(self, sample_citations):
        """Test reference formatting includes score when enabled."""
        formatter = CitationFormatter(
            style=CitationStyle.APPENDIX,
            include_score=True,
        )

        ref = formatter._format_reference(sample_citations[0], 1)

        assert "relevance: 0.95" in ref

    def test_format_reference_with_section(self, sample_citations):
        """Test reference formatting includes section."""
        formatter = CitationFormatter(style=CitationStyle.APPENDIX)

        ref = formatter._format_reference(sample_citations[1], 2)

        assert "§Results" in ref

    def test_format_inline_marker(self):
        """Test inline marker formatting."""
        formatter = CitationFormatter()

        marker = formatter.format_inline_marker(5)

        assert marker == "[5]"

    def test_format_citation_block(self, sample_citations):
        """Test citation block formatting."""
        formatter = CitationFormatter(include_score=True)

        block = formatter.format_citation_block(sample_citations, "Sources")

        assert "**Sources:**" in block
        assert "1. First Document" in block
        assert "2. Second Document" in block
        assert "3. Third Document" in block

    def test_format_citation_block_empty(self):
        """Test citation block with empty list."""
        formatter = CitationFormatter()

        block = formatter.format_citation_block([])

        assert block == ""


class TestCreateCitationFormatter:
    """Tests for create_citation_formatter factory."""

    def test_create_with_inline_style(self):
        """Test creating formatter with inline style."""
        config = {"citation_style": "inline"}

        formatter = create_citation_formatter(config)

        assert formatter.style == CitationStyle.INLINE

    def test_create_with_appendix_style(self):
        """Test creating formatter with appendix style."""
        config = {"citation_style": "appendix"}

        formatter = create_citation_formatter(config)

        assert formatter.style == CitationStyle.APPENDIX

    def test_create_with_none_style(self):
        """Test creating formatter with none style."""
        config = {"citation_style": "none"}

        formatter = create_citation_formatter(config)

        assert formatter.style == CitationStyle.NONE

    def test_create_with_invalid_style_defaults_to_inline(self):
        """Test invalid style defaults to inline."""
        config = {"citation_style": "invalid"}

        formatter = create_citation_formatter(config)

        assert formatter.style == CitationStyle.INLINE

    def test_create_with_all_options(self):
        """Test creating formatter with all options."""
        config = {
            "citation_style": "appendix",
            "max_citations": 5,
            "include_score": True,
            "include_page": False,
        }

        formatter = create_citation_formatter(config)

        assert formatter.style == CitationStyle.APPENDIX
        assert formatter.max_citations == 5
        assert formatter.include_score is True
        assert formatter.include_page is False

    def test_create_with_empty_config(self):
        """Test creating formatter with empty config uses defaults."""
        config = {}

        formatter = create_citation_formatter(config)

        assert formatter.style == CitationStyle.INLINE
        assert formatter.max_citations == 10
        assert formatter.include_score is False
        assert formatter.include_page is True


class TestCitationIntegration:
    """Integration tests for citation workflow."""

    def test_full_citation_workflow(self):
        """Test complete workflow from extraction to formatting."""
        # Simulate semantic search result
        search_result = {
            "success": True,
            "results": [
                {
                    "document_id": "manual-001",
                    "content_id": "chunk-5",
                    "document_title": "User Manual v2.0",
                    "score": 0.93,
                    "page_number": 42,
                    "content": "To configure the system, navigate to Settings > Advanced.",
                    "relevance_reason": "Semantic Match",
                },
                {
                    "document_id": "faq-003",
                    "content_id": "chunk-12",
                    "document_title": "FAQ: Configuration",
                    "score": 0.81,
                    "content": "Common configuration questions answered here.",
                    "relevance_reason": "Keyword Match",
                },
            ],
            "result_count": 2,
        }

        # Extract citations
        citations = RAGCitationExtractor.extract_from_result(
            "rag_semantic_search", search_result
        )

        assert len(citations) == 2

        # Format with appendix style
        formatter = CitationFormatter(
            style=CitationStyle.APPENDIX,
            include_page=True,
        )

        response_text = "To configure the system, go to Settings > Advanced. For more help, see the FAQ."
        result = formatter.format_citations(response_text, citations)

        # Verify output
        assert result.formatted_text.startswith(response_text)
        assert "**References:**" in result.formatted_text
        assert "User Manual v2.0" in result.formatted_text
        assert "p. 42" in result.formatted_text
        assert "FAQ: Configuration" in result.formatted_text
        assert len(result.citations) == 2
        assert len(result.references) == 2

    def test_citation_with_evidence_integration(self):
        """Test that citations can be converted to evidence items."""
        from taskforce.core.domain.evidence import EvidenceItem

        citation = RAGCitation(
            document_id="doc-123",
            chunk_id="chunk-5",
            title="Test Document",
            score=0.88,
            snippet="Relevant text here",
        )

        # Convert citation to evidence
        evidence = EvidenceItem.from_rag_document(
            document_id=citation.document_id,
            chunk_id=citation.chunk_id,
            snippet=citation.snippet,
            score=citation.score,
            title=citation.title,
        )

        assert evidence.source_id == "doc-123:chunk-5"
        assert evidence.metadata["title"] == "Test Document"
        assert evidence.relevance_score == 0.88
