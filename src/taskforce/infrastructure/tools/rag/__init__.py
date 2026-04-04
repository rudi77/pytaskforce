"""
RAG Tools for Azure AI Search Integration

This module provides tools for semantic search, document listing, and document retrieval
using Azure AI Search. All tools implement ToolProtocol for dependency injection.
"""

from taskforce.infrastructure.tools.rag.azure_search_base import AzureSearchBase
from taskforce.infrastructure.tools.rag.citations import (
    CitationFormatter,
    CitationResult,
    CitationStyle,
    RAGCitation,
    RAGCitationExtractor,
    create_citation_formatter,
)
from taskforce.infrastructure.tools.rag.get_document_tool import GetDocumentTool
from taskforce.infrastructure.tools.rag.list_documents_tool import ListDocumentsTool
from taskforce.infrastructure.tools.rag.semantic_search_tool import SemanticSearchTool

__all__ = [
    "AzureSearchBase",
    "SemanticSearchTool",
    "ListDocumentsTool",
    "GetDocumentTool",
    # Citation support
    "RAGCitation",
    "RAGCitationExtractor",
    "CitationFormatter",
    "CitationStyle",
    "CitationResult",
    "create_citation_formatter",
]
