"""
RAG Tools for Azure AI Search Integration

This module provides tools for semantic search, document listing, and document retrieval
using Azure AI Search. All tools implement ToolProtocol for dependency injection.
"""

from taskforce_rag_agent.tools.azure_search_base import AzureSearchBase
from taskforce_rag_agent.tools.citations import (
    CitationFormatter,
    CitationResult,
    CitationStyle,
    RAGCitation,
    RAGCitationExtractor,
    create_citation_formatter,
)
from taskforce_rag_agent.tools.get_document_tool import GetDocumentTool
from taskforce_rag_agent.tools.list_documents_tool import ListDocumentsTool
from taskforce_rag_agent.tools.semantic_search_tool import SemanticSearchTool

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
