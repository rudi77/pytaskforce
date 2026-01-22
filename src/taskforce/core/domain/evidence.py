"""Evidence domain models for audit and traceability.

This module provides domain models for tracking evidence and source
information for agent responses, enabling compliance and trust verification.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum
import uuid


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class EvidenceSourceType(Enum):
    """Types of evidence sources."""

    TOOL_RESULT = "tool_result"
    RAG_DOCUMENT = "rag_document"
    LLM_REASONING = "llm_reasoning"
    USER_INPUT = "user_input"
    EXTERNAL_API = "external_api"
    MEMORY = "memory"
    SYSTEM = "system"


class ConfidenceLevel(Enum):
    """Confidence levels for evidence."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass
class EvidenceItem:
    """A single piece of evidence supporting an agent's response.

    Attributes:
        evidence_id: Unique identifier for this evidence
        source_type: Type of source (tool, document, etc.)
        source_id: Identifier of the source (tool name, document ID, etc.)
        snippet: Relevant excerpt from the source
        confidence: Confidence level of this evidence
        timestamp: When this evidence was collected
        metadata: Additional source metadata
        relevance_score: Optional relevance score (0.0-1.0)
        used_in_answer: Whether this evidence was used in the final answer
    """

    evidence_id: str
    source_type: EvidenceSourceType
    source_id: str
    snippet: str
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    timestamp: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    relevance_score: Optional[float] = None
    used_in_answer: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "evidence_id": self.evidence_id,
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "snippet": self.snippet,
            "confidence": self.confidence.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "relevance_score": self.relevance_score,
            "used_in_answer": self.used_in_answer,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceItem":
        """Create from dictionary."""
        return cls(
            evidence_id=data["evidence_id"],
            source_type=EvidenceSourceType(data["source_type"]),
            source_id=data["source_id"],
            snippet=data["snippet"],
            confidence=ConfidenceLevel(data.get("confidence", "medium")),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
            relevance_score=data.get("relevance_score"),
            used_in_answer=data.get("used_in_answer", False),
        )

    @classmethod
    def from_tool_result(
        cls,
        tool_name: str,
        result_handle: str,
        snippet: str,
        confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "EvidenceItem":
        """Create evidence from a tool result.

        Args:
            tool_name: Name of the tool that produced the result
            result_handle: Handle/ID of the tool result
            snippet: Relevant excerpt from the result
            confidence: Confidence level
            metadata: Additional metadata

        Returns:
            EvidenceItem for the tool result
        """
        return cls(
            evidence_id=str(uuid.uuid4()),
            source_type=EvidenceSourceType.TOOL_RESULT,
            source_id=f"{tool_name}:{result_handle}",
            snippet=snippet,
            confidence=confidence,
            metadata={"tool_name": tool_name, "result_handle": result_handle, **(metadata or {})},
        )

    @classmethod
    def from_rag_document(
        cls,
        document_id: str,
        chunk_id: Optional[str],
        snippet: str,
        score: float,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "EvidenceItem":
        """Create evidence from a RAG document.

        Args:
            document_id: ID of the source document
            chunk_id: Optional chunk ID within the document
            snippet: Relevant excerpt from the document
            score: Retrieval relevance score
            title: Optional document title
            metadata: Additional metadata

        Returns:
            EvidenceItem for the RAG document
        """
        source_id = f"{document_id}:{chunk_id}" if chunk_id else document_id

        # Map score to confidence
        if score >= 0.8:
            confidence = ConfidenceLevel.HIGH
        elif score >= 0.5:
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW

        return cls(
            evidence_id=str(uuid.uuid4()),
            source_type=EvidenceSourceType.RAG_DOCUMENT,
            source_id=source_id,
            snippet=snippet,
            confidence=confidence,
            relevance_score=score,
            metadata={
                "document_id": document_id,
                "chunk_id": chunk_id,
                "title": title,
                **(metadata or {}),
            },
        )


@dataclass
class Citation:
    """A formatted citation for use in responses.

    Attributes:
        citation_id: Unique citation identifier (e.g., [1], [2])
        evidence_id: Reference to the underlying evidence
        text: Formatted citation text
        inline_marker: Inline reference marker (e.g., "[1]")
        full_reference: Full reference for appendix/footnotes
    """

    citation_id: int
    evidence_id: str
    text: str
    inline_marker: str
    full_reference: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "citation_id": self.citation_id,
            "evidence_id": self.evidence_id,
            "text": self.text,
            "inline_marker": self.inline_marker,
            "full_reference": self.full_reference,
        }


@dataclass
class EvidenceChain:
    """A chain of evidence supporting a response or conclusion.

    This tracks all evidence items and their relationships to
    the final answer, enabling full audit trails.

    Attributes:
        chain_id: Unique identifier for this chain
        session_id: Session this chain belongs to
        mission: The original mission/question
        evidence: List of evidence items
        citations: Formatted citations derived from evidence
        final_answer: The final answer/response
        created_at: When this chain was created
        metadata: Additional chain metadata
    """

    chain_id: str
    session_id: str
    mission: str
    evidence: List[EvidenceItem] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    final_answer: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_evidence(self, item: EvidenceItem) -> None:
        """Add an evidence item to the chain.

        Args:
            item: The evidence item to add
        """
        self.evidence.append(item)

    def mark_used_in_answer(self, evidence_ids: List[str]) -> None:
        """Mark evidence items as used in the final answer.

        Args:
            evidence_ids: IDs of evidence items used in the answer
        """
        id_set = set(evidence_ids)
        for item in self.evidence:
            if item.evidence_id in id_set:
                item.used_in_answer = True

    def get_used_evidence(self) -> List[EvidenceItem]:
        """Get all evidence items marked as used in the answer.

        Returns:
            List of evidence items used in the answer
        """
        return [e for e in self.evidence if e.used_in_answer]

    def get_evidence_by_type(
        self, source_type: EvidenceSourceType
    ) -> List[EvidenceItem]:
        """Get evidence items by source type.

        Args:
            source_type: The source type to filter by

        Returns:
            List of matching evidence items
        """
        return [e for e in self.evidence if e.source_type == source_type]

    def generate_citations(self, style: str = "inline") -> List[Citation]:
        """Generate formatted citations from used evidence.

        Args:
            style: Citation style ("inline", "appendix", or "numbered")

        Returns:
            List of formatted citations
        """
        citations = []
        used_evidence = self.get_used_evidence()

        for i, evidence in enumerate(used_evidence, 1):
            citation = self._format_citation(evidence, i, style)
            citations.append(citation)

        self.citations = citations
        return citations

    def _format_citation(
        self, evidence: EvidenceItem, num: int, style: str
    ) -> Citation:
        """Format a single citation.

        Args:
            evidence: The evidence item to cite
            num: Citation number
            style: Citation style

        Returns:
            Formatted Citation
        """
        inline_marker = f"[{num}]"

        if evidence.source_type == EvidenceSourceType.RAG_DOCUMENT:
            title = evidence.metadata.get("title", "Document")
            doc_id = evidence.metadata.get("document_id", evidence.source_id)
            text = title
            full_reference = f"{inline_marker} {title} (ID: {doc_id})"
        elif evidence.source_type == EvidenceSourceType.TOOL_RESULT:
            tool_name = evidence.metadata.get("tool_name", "Tool")
            text = f"{tool_name} result"
            full_reference = f"{inline_marker} {tool_name} execution result"
        else:
            text = evidence.source_id
            full_reference = f"{inline_marker} {evidence.source_type.value}: {evidence.source_id}"

        return Citation(
            citation_id=num,
            evidence_id=evidence.evidence_id,
            text=text,
            inline_marker=inline_marker,
            full_reference=full_reference,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "chain_id": self.chain_id,
            "session_id": self.session_id,
            "mission": self.mission,
            "evidence": [e.to_dict() for e in self.evidence],
            "citations": [c.to_dict() for c in self.citations],
            "final_answer": self.final_answer,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceChain":
        """Create from dictionary."""
        chain = cls(
            chain_id=data["chain_id"],
            session_id=data["session_id"],
            mission=data["mission"],
            final_answer=data.get("final_answer"),
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
        )
        chain.evidence = [EvidenceItem.from_dict(e) for e in data.get("evidence", [])]
        return chain


class EvidenceCollector:
    """Utility class for collecting evidence during agent execution.

    This class provides methods for collecting evidence from various
    sources and building an evidence chain.
    """

    def __init__(self, session_id: str, mission: str):
        """Initialize the evidence collector.

        Args:
            session_id: The session ID for this collection
            mission: The mission being executed
        """
        self.chain = EvidenceChain(
            chain_id=str(uuid.uuid4()),
            session_id=session_id,
            mission=mission,
        )

    def add_tool_evidence(
        self,
        tool_name: str,
        result_handle: str,
        snippet: str,
        confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EvidenceItem:
        """Add evidence from a tool result.

        Args:
            tool_name: Name of the tool
            result_handle: Handle/ID of the result
            snippet: Relevant excerpt
            confidence: Confidence level
            metadata: Additional metadata

        Returns:
            The created evidence item
        """
        evidence = EvidenceItem.from_tool_result(
            tool_name=tool_name,
            result_handle=result_handle,
            snippet=snippet,
            confidence=confidence,
            metadata=metadata,
        )
        self.chain.add_evidence(evidence)
        return evidence

    def add_rag_evidence(
        self,
        document_id: str,
        chunk_id: Optional[str],
        snippet: str,
        score: float,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EvidenceItem:
        """Add evidence from a RAG document.

        Args:
            document_id: ID of the source document
            chunk_id: Optional chunk ID
            snippet: Relevant excerpt
            score: Retrieval score
            title: Optional document title
            metadata: Additional metadata

        Returns:
            The created evidence item
        """
        evidence = EvidenceItem.from_rag_document(
            document_id=document_id,
            chunk_id=chunk_id,
            snippet=snippet,
            score=score,
            title=title,
            metadata=metadata,
        )
        self.chain.add_evidence(evidence)
        return evidence

    def add_custom_evidence(
        self,
        source_type: EvidenceSourceType,
        source_id: str,
        snippet: str,
        confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EvidenceItem:
        """Add custom evidence.

        Args:
            source_type: Type of source
            source_id: Source identifier
            snippet: Relevant excerpt
            confidence: Confidence level
            metadata: Additional metadata

        Returns:
            The created evidence item
        """
        evidence = EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            source_type=source_type,
            source_id=source_id,
            snippet=snippet,
            confidence=confidence,
            metadata=metadata or {},
        )
        self.chain.add_evidence(evidence)
        return evidence

    def finalize(
        self,
        final_answer: str,
        used_evidence_ids: Optional[List[str]] = None,
        citation_style: str = "inline",
    ) -> EvidenceChain:
        """Finalize the evidence chain with the final answer.

        Args:
            final_answer: The final answer/response
            used_evidence_ids: IDs of evidence used in the answer
            citation_style: Citation formatting style

        Returns:
            The finalized evidence chain
        """
        self.chain.final_answer = final_answer

        if used_evidence_ids:
            self.chain.mark_used_in_answer(used_evidence_ids)
        else:
            # Mark all evidence as used if not specified
            for evidence in self.chain.evidence:
                evidence.used_in_answer = True

        self.chain.generate_citations(style=citation_style)
        return self.chain

    def get_chain(self) -> EvidenceChain:
        """Get the current evidence chain.

        Returns:
            The evidence chain
        """
        return self.chain
