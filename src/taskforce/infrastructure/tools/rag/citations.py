"""RAG citation support for evidence-based responses.

This module provides utilities for extracting citations from RAG tool results
and formatting them for use in agent responses.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Literal
from enum import Enum
import re


class CitationStyle(Enum):
    """Supported citation styles."""

    INLINE = "inline"  # [1] embedded in text
    APPENDIX = "appendix"  # References listed at end
    NONE = "none"  # No citations


@dataclass
class RAGCitation:
    """A citation extracted from RAG search results.

    Attributes:
        document_id: ID of the source document
        chunk_id: Optional chunk/content block ID
        title: Document title
        score: Relevance score (0.0-1.0)
        page_number: Optional page number
        section: Optional section name
        snippet: Text excerpt
        metadata: Additional metadata
    """

    document_id: str
    chunk_id: Optional[str] = None
    title: str = ""
    score: float = 0.0
    page_number: Optional[int] = None
    section: Optional[str] = None
    snippet: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "score": self.score,
            "page_number": self.page_number,
            "section": self.section,
            "snippet": self.snippet,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RAGCitation":
        """Create from dictionary."""
        return cls(
            document_id=data.get("document_id", ""),
            chunk_id=data.get("chunk_id"),
            title=data.get("title", ""),
            score=data.get("score", 0.0),
            page_number=data.get("page_number"),
            section=data.get("section"),
            snippet=data.get("snippet", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CitationResult:
    """Result of citation formatting.

    Attributes:
        formatted_text: The text with citations applied
        citations: List of citations used
        references: Formatted reference list (for appendix style)
        style: Citation style used
    """

    formatted_text: str
    citations: List[RAGCitation]
    references: List[str]
    style: CitationStyle


class RAGCitationExtractor:
    """Extracts citation information from RAG tool results."""

    @staticmethod
    def extract_from_semantic_search(result: Dict[str, Any]) -> List[RAGCitation]:
        """Extract citations from semantic search results.

        Args:
            result: The result dictionary from SemanticSearchTool

        Returns:
            List of extracted RAG citations
        """
        citations = []

        if not result.get("success"):
            return citations

        results = result.get("results", [])
        for item in results:
            citation = RAGCitation(
                document_id=item.get("document_id", ""),
                chunk_id=item.get("content_id"),
                title=item.get("document_title", "Untitled"),
                score=item.get("score", 0.0),
                page_number=item.get("page_number"),
                snippet=item.get("content", "")[:500],  # Limit snippet length
                metadata={
                    "relevance_reason": item.get("relevance_reason"),
                    "image_path": item.get("image_path"),
                    "full_content": item.get("full_content"),
                },
            )
            citations.append(citation)

        return citations

    @staticmethod
    def extract_from_get_document(result: Dict[str, Any]) -> List[RAGCitation]:
        """Extract citations from get document results.

        Args:
            result: The result dictionary from GetDocumentTool

        Returns:
            List of extracted RAG citations (typically one)
        """
        citations = []

        if not result.get("success"):
            return citations

        doc = result.get("document", {})
        if doc:
            citation = RAGCitation(
                document_id=doc.get("document_id", ""),
                title=doc.get("title", "Untitled"),
                score=1.0,  # Direct retrieval has full confidence
                snippet=doc.get("content", "")[:500],
                metadata=doc.get("metadata", {}),
            )
            citations.append(citation)

        return citations

    @staticmethod
    def extract_from_result(
        tool_name: str, result: Dict[str, Any]
    ) -> List[RAGCitation]:
        """Extract citations from any RAG tool result.

        Args:
            tool_name: Name of the tool that produced the result
            result: The tool result dictionary

        Returns:
            List of extracted RAG citations
        """
        if tool_name in ("rag_semantic_search", "semantic_search"):
            return RAGCitationExtractor.extract_from_semantic_search(result)
        elif tool_name in ("rag_get_document", "get_document"):
            return RAGCitationExtractor.extract_from_get_document(result)
        elif tool_name in ("rag_list_documents", "list_documents"):
            # List documents doesn't typically provide citable content
            return []
        else:
            # Try generic extraction
            return RAGCitationExtractor._extract_generic(result)

    @staticmethod
    def _extract_generic(result: Dict[str, Any]) -> List[RAGCitation]:
        """Generic extraction for unknown RAG tool formats.

        Args:
            result: The tool result dictionary

        Returns:
            List of extracted citations
        """
        citations = []

        # Look for common patterns
        results = result.get("results", result.get("documents", []))
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    citation = RAGCitation(
                        document_id=item.get("document_id", item.get("id", "")),
                        chunk_id=item.get("chunk_id", item.get("content_id")),
                        title=item.get("title", item.get("document_title", "")),
                        score=item.get("score", item.get("relevance", 0.0)),
                        page_number=item.get("page_number", item.get("page")),
                        snippet=item.get("snippet", item.get("content", ""))[:500],
                        metadata={
                            k: v
                            for k, v in item.items()
                            if k
                            not in (
                                "document_id",
                                "id",
                                "chunk_id",
                                "content_id",
                                "title",
                                "document_title",
                                "score",
                                "relevance",
                                "page_number",
                                "page",
                                "snippet",
                                "content",
                            )
                        },
                    )
                    if citation.document_id:
                        citations.append(citation)

        return citations


class CitationFormatter:
    """Formats citations for display in agent responses."""

    def __init__(
        self,
        style: CitationStyle = CitationStyle.INLINE,
        max_citations: int = 10,
        include_score: bool = False,
        include_page: bool = True,
    ):
        """Initialize the formatter.

        Args:
            style: Citation style to use
            max_citations: Maximum citations to include
            include_score: Whether to include relevance scores
            include_page: Whether to include page numbers
        """
        self.style = style
        self.max_citations = max_citations
        self.include_score = include_score
        self.include_page = include_page

    def format_citations(
        self,
        text: str,
        citations: List[RAGCitation],
    ) -> CitationResult:
        """Format citations for a response text.

        Args:
            text: The response text
            citations: Citations to include

        Returns:
            CitationResult with formatted text and references
        """
        if self.style == CitationStyle.NONE:
            return CitationResult(
                formatted_text=text,
                citations=citations[: self.max_citations],
                references=[],
                style=self.style,
            )

        # Limit citations
        used_citations = citations[: self.max_citations]

        # Build references list
        references = []
        for i, citation in enumerate(used_citations, 1):
            ref = self._format_reference(citation, i)
            references.append(ref)

        if self.style == CitationStyle.INLINE:
            # Add inline markers to text
            formatted_text = self._add_inline_markers(text, used_citations)
        else:  # APPENDIX
            # Add references section at end
            formatted_text = text
            if references:
                formatted_text += "\n\n---\n**References:**\n"
                for ref in references:
                    formatted_text += f"{ref}\n"

        return CitationResult(
            formatted_text=formatted_text,
            citations=used_citations,
            references=references,
            style=self.style,
        )

    def _format_reference(self, citation: RAGCitation, num: int) -> str:
        """Format a single reference.

        Args:
            citation: The citation to format
            num: Reference number

        Returns:
            Formatted reference string
        """
        parts = [f"[{num}]", citation.title or "Untitled"]

        if self.include_page and citation.page_number:
            parts.append(f"p. {citation.page_number}")

        if citation.section:
            parts.append(f"§{citation.section}")

        if self.include_score and citation.score > 0:
            parts.append(f"(relevance: {citation.score:.2f})")

        return " ".join(parts)

    def _add_inline_markers(
        self, text: str, citations: List[RAGCitation]
    ) -> str:
        """Add inline citation markers to text.

        This is a simple heuristic that adds markers at the end of sentences
        that contain content from the citations.

        Args:
            text: The text to annotate
            citations: Citations to reference

        Returns:
            Text with inline markers
        """
        # Build a mapping of citation keywords to numbers
        citation_map = {}
        for i, citation in enumerate(citations, 1):
            # Extract key terms from citation
            keywords = self._extract_keywords(citation)
            for keyword in keywords:
                if keyword not in citation_map:
                    citation_map[keyword] = []
                citation_map[keyword].append(i)

        # Split text into sentences
        sentences = re.split(r"(?<=[.!?])\s+", text)
        annotated_sentences = []

        for sentence in sentences:
            # Find which citations apply to this sentence
            applicable = set()
            sentence_lower = sentence.lower()
            for keyword, nums in citation_map.items():
                if keyword.lower() in sentence_lower:
                    applicable.update(nums)

            if applicable:
                # Add citation markers
                markers = ", ".join(f"[{n}]" for n in sorted(applicable))
                # Remove existing markers first
                sentence = re.sub(r"\[\d+\]", "", sentence).strip()
                sentence = f"{sentence} {markers}"

            annotated_sentences.append(sentence)

        return " ".join(annotated_sentences)

    def _extract_keywords(self, citation: RAGCitation) -> List[str]:
        """Extract keywords from a citation for matching.

        Args:
            citation: The citation to extract keywords from

        Returns:
            List of keywords
        """
        keywords = []

        # Extract from title
        if citation.title:
            # Get significant words (>3 chars)
            words = re.findall(r"\b\w{4,}\b", citation.title)
            keywords.extend(words[:3])

        # Extract from snippet
        if citation.snippet:
            # Get first few significant words
            words = re.findall(r"\b\w{5,}\b", citation.snippet)
            keywords.extend(words[:5])

        return keywords

    def format_inline_marker(self, num: int) -> str:
        """Format an inline citation marker.

        Args:
            num: Citation number

        Returns:
            Formatted marker string
        """
        return f"[{num}]"

    def format_citation_block(
        self, citations: List[RAGCitation], header: str = "Sources"
    ) -> str:
        """Format a block of citations for display.

        Args:
            citations: Citations to format
            header: Block header

        Returns:
            Formatted citation block
        """
        if not citations:
            return ""

        lines = [f"\n**{header}:**\n"]

        for i, citation in enumerate(citations[: self.max_citations], 1):
            line = f"{i}. {citation.title or 'Untitled'}"

            if self.include_page and citation.page_number:
                line += f", p. {citation.page_number}"

            if citation.section:
                line += f" (§{citation.section})"

            if self.include_score and citation.score > 0:
                line += f" [relevance: {citation.score:.2f}]"

            lines.append(line)

        return "\n".join(lines)


def create_citation_formatter(
    config: Dict[str, Any]
) -> CitationFormatter:
    """Create a citation formatter from configuration.

    Args:
        config: Configuration dictionary with keys:
            - citation_style: "inline" | "appendix" | "none"
            - max_citations: Maximum citations to include
            - include_score: Whether to show relevance scores
            - include_page: Whether to show page numbers

    Returns:
        Configured CitationFormatter instance
    """
    style_str = config.get("citation_style", "inline")
    try:
        style = CitationStyle(style_str)
    except ValueError:
        style = CitationStyle.INLINE

    return CitationFormatter(
        style=style,
        max_citations=config.get("max_citations", 10),
        include_score=config.get("include_score", False),
        include_page=config.get("include_page", True),
    )
