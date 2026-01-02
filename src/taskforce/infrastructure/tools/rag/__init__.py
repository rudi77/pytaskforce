"""
RAG Tools for Azure AI Search Integration

This module provides tools for semantic search, document listing, and document retrieval
using Azure AI Search. All tools implement ToolProtocol for dependency injection.
"""

from taskforce.infrastructure.tools.rag.azure_search_base import AzureSearchBase
from taskforce.infrastructure.tools.rag.semantic_search import SemanticSearchTool
from taskforce.infrastructure.tools.rag.list_documents import ListDocumentsTool
from taskforce.infrastructure.tools.rag.get_document import GetDocumentTool

__all__ = [
    "AzureSearchBase",
    "SemanticSearchTool",
    "ListDocumentsTool",
    "GetDocumentTool",
]
