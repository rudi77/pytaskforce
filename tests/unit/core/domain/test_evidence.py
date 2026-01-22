"""Unit tests for evidence domain models."""

import pytest
from datetime import datetime, timezone

from taskforce.core.domain.evidence import (
    EvidenceItem,
    EvidenceChain,
    EvidenceCollector,
    Citation,
    EvidenceSourceType,
    ConfidenceLevel,
)


class TestEvidenceSourceType:
    """Tests for EvidenceSourceType enum."""

    def test_all_types_exist(self):
        """Test that all expected source types exist."""
        assert EvidenceSourceType.TOOL_RESULT
        assert EvidenceSourceType.RAG_DOCUMENT
        assert EvidenceSourceType.LLM_REASONING
        assert EvidenceSourceType.USER_INPUT
        assert EvidenceSourceType.EXTERNAL_API
        assert EvidenceSourceType.MEMORY
        assert EvidenceSourceType.SYSTEM


class TestConfidenceLevel:
    """Tests for ConfidenceLevel enum."""

    def test_all_levels_exist(self):
        """Test that all confidence levels exist."""
        assert ConfidenceLevel.HIGH
        assert ConfidenceLevel.MEDIUM
        assert ConfidenceLevel.LOW
        assert ConfidenceLevel.UNKNOWN


class TestEvidenceItem:
    """Tests for EvidenceItem dataclass."""

    def test_create_evidence_item(self):
        """Test creating a basic evidence item."""
        evidence = EvidenceItem(
            evidence_id="ev-123",
            source_type=EvidenceSourceType.TOOL_RESULT,
            source_id="file_read:handle-456",
            snippet="File contents here...",
        )
        assert evidence.evidence_id == "ev-123"
        assert evidence.source_type == EvidenceSourceType.TOOL_RESULT
        assert evidence.confidence == ConfidenceLevel.MEDIUM
        assert evidence.used_in_answer is False

    def test_evidence_item_to_dict(self):
        """Test converting evidence item to dictionary."""
        evidence = EvidenceItem(
            evidence_id="ev-123",
            source_type=EvidenceSourceType.RAG_DOCUMENT,
            source_id="doc-456:chunk-1",
            snippet="Relevant text...",
            confidence=ConfidenceLevel.HIGH,
            relevance_score=0.95,
        )
        data = evidence.to_dict()

        assert data["evidence_id"] == "ev-123"
        assert data["source_type"] == "rag_document"
        assert data["confidence"] == "high"
        assert data["relevance_score"] == 0.95

    def test_evidence_item_from_dict(self):
        """Test creating evidence item from dictionary."""
        data = {
            "evidence_id": "ev-123",
            "source_type": "tool_result",
            "source_id": "search:handle-1",
            "snippet": "Search results...",
            "confidence": "high",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {"query": "test"},
            "relevance_score": 0.8,
            "used_in_answer": True,
        }
        evidence = EvidenceItem.from_dict(data)

        assert evidence.evidence_id == "ev-123"
        assert evidence.source_type == EvidenceSourceType.TOOL_RESULT
        assert evidence.confidence == ConfidenceLevel.HIGH
        assert evidence.used_in_answer is True

    def test_from_tool_result(self):
        """Test creating evidence from tool result."""
        evidence = EvidenceItem.from_tool_result(
            tool_name="file_read",
            result_handle="handle-123",
            snippet="File content...",
            metadata={"path": "/data/file.txt"},
        )

        assert evidence.source_type == EvidenceSourceType.TOOL_RESULT
        assert evidence.source_id == "file_read:handle-123"
        assert evidence.confidence == ConfidenceLevel.HIGH
        assert evidence.metadata["tool_name"] == "file_read"
        assert evidence.metadata["path"] == "/data/file.txt"

    def test_from_rag_document_high_score(self):
        """Test creating evidence from RAG document with high score."""
        evidence = EvidenceItem.from_rag_document(
            document_id="doc-123",
            chunk_id="chunk-5",
            snippet="Relevant passage...",
            score=0.92,
            title="Important Document",
        )

        assert evidence.source_type == EvidenceSourceType.RAG_DOCUMENT
        assert evidence.source_id == "doc-123:chunk-5"
        assert evidence.confidence == ConfidenceLevel.HIGH
        assert evidence.relevance_score == 0.92
        assert evidence.metadata["title"] == "Important Document"

    def test_from_rag_document_medium_score(self):
        """Test creating evidence from RAG document with medium score."""
        evidence = EvidenceItem.from_rag_document(
            document_id="doc-123",
            chunk_id=None,
            snippet="Some passage...",
            score=0.65,
        )

        assert evidence.source_id == "doc-123"
        assert evidence.confidence == ConfidenceLevel.MEDIUM

    def test_from_rag_document_low_score(self):
        """Test creating evidence from RAG document with low score."""
        evidence = EvidenceItem.from_rag_document(
            document_id="doc-123",
            chunk_id="chunk-1",
            snippet="Weak match...",
            score=0.3,
        )

        assert evidence.confidence == ConfidenceLevel.LOW


class TestCitation:
    """Tests for Citation dataclass."""

    def test_create_citation(self):
        """Test creating a citation."""
        citation = Citation(
            citation_id=1,
            evidence_id="ev-123",
            text="Source Document",
            inline_marker="[1]",
            full_reference="[1] Source Document (ID: doc-123)",
        )

        assert citation.citation_id == 1
        assert citation.inline_marker == "[1]"

    def test_citation_to_dict(self):
        """Test converting citation to dictionary."""
        citation = Citation(
            citation_id=2,
            evidence_id="ev-456",
            text="API Result",
            inline_marker="[2]",
            full_reference="[2] API Result from external service",
        )
        data = citation.to_dict()

        assert data["citation_id"] == 2
        assert data["evidence_id"] == "ev-456"


class TestEvidenceChain:
    """Tests for EvidenceChain dataclass."""

    def test_create_evidence_chain(self):
        """Test creating an evidence chain."""
        chain = EvidenceChain(
            chain_id="chain-123",
            session_id="session-456",
            mission="Analyze the data",
        )

        assert chain.chain_id == "chain-123"
        assert chain.session_id == "session-456"
        assert chain.evidence == []
        assert chain.final_answer is None

    def test_add_evidence(self):
        """Test adding evidence to chain."""
        chain = EvidenceChain(
            chain_id="chain-123",
            session_id="session-456",
            mission="Test mission",
        )

        evidence = EvidenceItem(
            evidence_id="ev-1",
            source_type=EvidenceSourceType.TOOL_RESULT,
            source_id="tool:handle",
            snippet="Result data",
        )
        chain.add_evidence(evidence)

        assert len(chain.evidence) == 1
        assert chain.evidence[0].evidence_id == "ev-1"

    def test_mark_used_in_answer(self):
        """Test marking evidence as used in answer."""
        chain = EvidenceChain(
            chain_id="chain-123",
            session_id="session-456",
            mission="Test",
        )

        # Add multiple evidence items
        for i in range(3):
            chain.add_evidence(
                EvidenceItem(
                    evidence_id=f"ev-{i}",
                    source_type=EvidenceSourceType.TOOL_RESULT,
                    source_id=f"tool:{i}",
                    snippet=f"Data {i}",
                )
            )

        # Mark only first and third as used
        chain.mark_used_in_answer(["ev-0", "ev-2"])

        assert chain.evidence[0].used_in_answer is True
        assert chain.evidence[1].used_in_answer is False
        assert chain.evidence[2].used_in_answer is True

    def test_get_used_evidence(self):
        """Test getting evidence used in answer."""
        chain = EvidenceChain(
            chain_id="chain-123",
            session_id="session-456",
            mission="Test",
        )

        chain.add_evidence(
            EvidenceItem(
                evidence_id="ev-1",
                source_type=EvidenceSourceType.TOOL_RESULT,
                source_id="tool:1",
                snippet="Used",
                used_in_answer=True,
            )
        )
        chain.add_evidence(
            EvidenceItem(
                evidence_id="ev-2",
                source_type=EvidenceSourceType.RAG_DOCUMENT,
                source_id="doc:1",
                snippet="Not used",
                used_in_answer=False,
            )
        )

        used = chain.get_used_evidence()
        assert len(used) == 1
        assert used[0].evidence_id == "ev-1"

    def test_get_evidence_by_type(self):
        """Test filtering evidence by type."""
        chain = EvidenceChain(
            chain_id="chain-123",
            session_id="session-456",
            mission="Test",
        )

        chain.add_evidence(
            EvidenceItem(
                evidence_id="ev-1",
                source_type=EvidenceSourceType.TOOL_RESULT,
                source_id="tool:1",
                snippet="Tool result",
            )
        )
        chain.add_evidence(
            EvidenceItem(
                evidence_id="ev-2",
                source_type=EvidenceSourceType.RAG_DOCUMENT,
                source_id="doc:1",
                snippet="Document",
            )
        )
        chain.add_evidence(
            EvidenceItem(
                evidence_id="ev-3",
                source_type=EvidenceSourceType.TOOL_RESULT,
                source_id="tool:2",
                snippet="Another tool",
            )
        )

        tool_evidence = chain.get_evidence_by_type(EvidenceSourceType.TOOL_RESULT)
        assert len(tool_evidence) == 2

        rag_evidence = chain.get_evidence_by_type(EvidenceSourceType.RAG_DOCUMENT)
        assert len(rag_evidence) == 1

    def test_generate_citations(self):
        """Test generating citations from evidence."""
        chain = EvidenceChain(
            chain_id="chain-123",
            session_id="session-456",
            mission="Test",
        )

        chain.add_evidence(
            EvidenceItem(
                evidence_id="ev-1",
                source_type=EvidenceSourceType.RAG_DOCUMENT,
                source_id="doc:1",
                snippet="Important text",
                used_in_answer=True,
                metadata={"title": "Research Paper", "document_id": "doc-123"},
            )
        )

        citations = chain.generate_citations()

        assert len(citations) == 1
        assert citations[0].inline_marker == "[1]"
        assert "Research Paper" in citations[0].full_reference

    def test_chain_serialization(self):
        """Test evidence chain serialization."""
        chain = EvidenceChain(
            chain_id="chain-123",
            session_id="session-456",
            mission="Test mission",
            final_answer="The answer is 42",
        )

        chain.add_evidence(
            EvidenceItem(
                evidence_id="ev-1",
                source_type=EvidenceSourceType.TOOL_RESULT,
                source_id="tool:1",
                snippet="Data",
            )
        )

        data = chain.to_dict()
        restored = EvidenceChain.from_dict(data)

        assert restored.chain_id == chain.chain_id
        assert restored.mission == chain.mission
        assert restored.final_answer == chain.final_answer
        assert len(restored.evidence) == 1


class TestEvidenceCollector:
    """Tests for EvidenceCollector utility class."""

    def test_create_collector(self):
        """Test creating an evidence collector."""
        collector = EvidenceCollector(
            session_id="session-123",
            mission="Analyze data",
        )

        assert collector.chain.session_id == "session-123"
        assert collector.chain.mission == "Analyze data"

    def test_add_tool_evidence(self):
        """Test adding tool evidence."""
        collector = EvidenceCollector(
            session_id="session-123",
            mission="Test",
        )

        evidence = collector.add_tool_evidence(
            tool_name="file_read",
            result_handle="handle-1",
            snippet="File contents...",
        )

        assert evidence.source_type == EvidenceSourceType.TOOL_RESULT
        assert len(collector.chain.evidence) == 1

    def test_add_rag_evidence(self):
        """Test adding RAG evidence."""
        collector = EvidenceCollector(
            session_id="session-123",
            mission="Test",
        )

        evidence = collector.add_rag_evidence(
            document_id="doc-456",
            chunk_id="chunk-2",
            snippet="Relevant passage...",
            score=0.85,
            title="Important Document",
        )

        assert evidence.source_type == EvidenceSourceType.RAG_DOCUMENT
        assert evidence.relevance_score == 0.85

    def test_add_custom_evidence(self):
        """Test adding custom evidence."""
        collector = EvidenceCollector(
            session_id="session-123",
            mission="Test",
        )

        evidence = collector.add_custom_evidence(
            source_type=EvidenceSourceType.EXTERNAL_API,
            source_id="weather-api:forecast",
            snippet="Temperature: 72°F",
            confidence=ConfidenceLevel.HIGH,
        )

        assert evidence.source_type == EvidenceSourceType.EXTERNAL_API

    def test_finalize_chain(self):
        """Test finalizing the evidence chain."""
        collector = EvidenceCollector(
            session_id="session-123",
            mission="What's the weather?",
        )

        ev1 = collector.add_tool_evidence(
            tool_name="weather_api",
            result_handle="h1",
            snippet="Sunny, 72°F",
        )
        ev2 = collector.add_custom_evidence(
            source_type=EvidenceSourceType.MEMORY,
            source_id="memory:location",
            snippet="User is in New York",
        )

        chain = collector.finalize(
            final_answer="The weather is sunny and 72°F",
            used_evidence_ids=[ev1.evidence_id],
        )

        assert chain.final_answer == "The weather is sunny and 72°F"
        assert chain.evidence[0].used_in_answer is True
        assert chain.evidence[1].used_in_answer is False
        assert len(chain.citations) == 1

    def test_finalize_marks_all_if_not_specified(self):
        """Test that finalize marks all evidence if IDs not specified."""
        collector = EvidenceCollector(
            session_id="session-123",
            mission="Test",
        )

        collector.add_tool_evidence("tool1", "h1", "Data 1")
        collector.add_tool_evidence("tool2", "h2", "Data 2")

        chain = collector.finalize(final_answer="Combined result")

        assert all(e.used_in_answer for e in chain.evidence)
