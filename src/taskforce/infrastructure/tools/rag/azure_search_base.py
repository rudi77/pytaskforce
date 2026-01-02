"""
Azure AI Search Base Infrastructure

Provides shared connection and security infrastructure for all RAG tools
that integrate with Azure AI Search.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient


class AzureSearchBase:
    """Base class for Azure AI Search integration providing shared connection and security logic."""

    def __init__(self):
        """Initialize Azure Search base configuration from environment variables."""
        self.endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
        self.api_key = os.getenv("AZURE_SEARCH_API_KEY")
        self.documents_index = os.getenv("AZURE_SEARCH_DOCUMENTS_INDEX", "documents-metadata")
        self.content_index = os.getenv("AZURE_SEARCH_CONTENT_INDEX", "content-blocks")

        # Validate required environment variables
        if not self.endpoint or not self.api_key:
            raise ValueError(
                "Azure Search configuration missing. Please set:\n"
                "  AZURE_SEARCH_ENDPOINT=https://your-service.search.windows.net\n"
                "  AZURE_SEARCH_API_KEY=your-api-key\n"
                "Optional:\n"
                "  AZURE_SEARCH_DOCUMENTS_INDEX=documents-metadata (default)\n"
                "  AZURE_SEARCH_CONTENT_INDEX=content-blocks (default)"
            )

    def get_search_client(self, index_name: str) -> SearchClient:
        """
        Create an AsyncSearchClient for the specified index.

        Args:
            index_name: Name of the Azure Search index

        Returns:
            AsyncSearchClient configured with credentials

        Example:
            client = self.get_search_client("content-blocks")
            async with client:
                results = await client.search(...)
        """
        return SearchClient(
            endpoint=self.endpoint,
            index_name=index_name,
            credential=AzureKeyCredential(self.api_key)
        )

    def build_security_filter(self, user_context: Optional[Dict[str, Any]] = None) -> str:
        """
        Build OData filter for row-level security based on user context.

        Implements proper access control logic:
        - Documents must belong to the organization (org_id match)
        - Documents are accessible if:
          - They belong to the user (user_id match), OR
          - They are shared/public (scope eq 'shared' or 'public')

        Args:
            user_context: Dict with user_id, org_id, scope keys

        Returns:
            OData filter string for access control

        Examples:
            >>> build_security_filter({"user_id": "ms-user", "org_id": "MS-corp"})
            "org_id eq 'MS-corp' and user_id eq 'ms-user'"

            >>> build_security_filter({"user_id": "ms-user", "org_id": "MS-corp", "scope": "shared"})
            "org_id eq 'MS-corp' and (user_id eq 'ms-user' or scope eq 'shared')"

            >>> build_security_filter({"org_id": "MS-corp"})
            "org_id eq 'MS-corp'"

            >>> build_security_filter(None)
            ""

        Raises:
            ValueError: If user context values contain invalid characters
        """
        if not user_context:
            return ""  # No filter for testing scenarios

        filters = []
        
        # Organization filter (required if provided)
        org_id = user_context.get("org_id")
        if org_id:
            sanitized_org = self._sanitize_filter_value(org_id)
            filters.append(f"org_id eq '{sanitized_org}'")
        
        # User/Scope access filter (OR logic)
        user_id = user_context.get("user_id")
        scope = user_context.get("scope")
        
        access_filters = []
        if user_id:
            sanitized_user = self._sanitize_filter_value(user_id)
            access_filters.append(f"user_id eq '{sanitized_user}'")
        if scope:
            sanitized_scope = self._sanitize_filter_value(scope)
            access_filters.append(f"scope eq '{sanitized_scope}'")
        
        # Combine access filters with OR
        if access_filters:
            if len(access_filters) == 1:
                filters.append(access_filters[0])
            else:
                filters.append(f"({' or '.join(access_filters)})")
        
        if not filters:
            return ""

        # Combine all filters with AND
        return " and ".join(filters)

    def _sanitize_filter_value(self, value: str) -> str:
        """
        Sanitize a value for use in OData filter expressions.

        Prevents OData injection by escaping single quotes and validating format.

        Args:
            value: The value to sanitize

        Returns:
            Sanitized value safe for use in OData filters

        Raises:
            ValueError: If value contains potentially malicious characters
        """
        if not isinstance(value, str):
            raise ValueError(f"Filter value must be string, got {type(value)}")

        # Check for suspicious patterns that could indicate injection attempts
        dangerous_chars = [";", "--", "/*", "*/", "\\"]
        for char in dangerous_chars:
            if char in value:
                raise ValueError(
                    f"Filter value contains potentially dangerous character sequence: {char}"
                )

        # Escape single quotes by doubling them (OData standard)
        sanitized = value.replace("'", "''")

        return sanitized

    async def __aenter__(self):
        """Support async context manager pattern."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup on context exit."""
        # No cleanup needed for SearchClient (handled per-use)
        pass


@dataclass
class LocationMetadata:
    """
    The location metadata for a chunk of content.
    """
    pageNumber: int
    boundingPolygons: Optional[str] = None

"""
        {
            "document_id": "2a7bf582-06f8-45fc-8e4f-a9ae84c4d218",
            "content_id": "64258321-4085-47f3-91b4-f8914a964610",
            "scope": "conversation",
            "document_type": null,
            "locationMetadata": {
                "pageNumber": 2,
                "boundingPolygons": null
            },
            "content_path": "/tmp/worker_2a7bf582-06f8-45fc-8e4f-a9ae84c4d218_2a7bf582-06f8-45fc-8e4f-a9ae84c4d218_resume.pdf",
            "org_id": "MS-corp",
            "content_text": "08/2007 \u2013 09/2010 HALE electronic: Software developer.\nwww.hale.at\n2005 \u2013 07/2007 project assistant in the Aeronautical Digital\nCommunications (ADC) group at the University of\nSalzburg on the Institute of Computer Science.\n2003 \u2013 2004 software developer at \u201eGassner Wiegen und Messen\u201c\nwww.gassner-waagen.com\nProjects, \u27a2 BLU DELTA \u2013 Invoice Capturing System (Blumatix GmbH):\nConferences,\n\u27a2 An invoice entry system as a cloud and on-premise solution.\nExhibitions\n\u27a2 Developed as a microservice architecture. It is based on\nServiceStack, Azure WebApps, Azure Functions, Storage Queues,\nDocker Container Services and Azure MSSQL.\n\u27a2 Creation and maintenance of various CI/CD Pipelines in Azure\nDevOps.\n\u27a2 Integration of various machine learning models.\n\u27a2 Multicheck for Spark (Tecan):\n\u27a2 Architecture, design and implementation of an OQ-Tools\n(operational qualification) for Spark instruments.\n\u27a2 SparkControl Software (Tecan):\n\u27a2 Design and implementation oft the control and analysis software\nfor the \u201eMultimode Microplate Reader Spark 10M und Spark\n20M\u201c in C#.\n\u27a2 UI implementation with WPF and MVVM frameworks.\n\u27a2 Database development with Entity Framework.\n\u27a2 Implementation of a communication component in C++ used for\nPC-to-Instrument communication via USB\n\u27a2 TT-01 Taxameter-Terminal (Hale electronic):\n\u27a2 Architecture, design and implementation of SW-components in\nC++ for an linux based embedded system\n\u27a2 Codereviews, error analysis and bug fixing\n\u27a2 UI development with GTK/GTKmm\n\u27a2 System-oriented development under Linux and the Linux Kernel.\n\u27a2 Implementation of an odometer as a Linux Kernel module.\n\u27a2 Implementation of the control software for GSM/GPS modules\n(Siemens XT75)\n\u27a2 Weighting terminal DMA03 (Gassner Wiegen und Messen GmbH):\n\u27a2 Setup and commissioning of the Linux 2.4 Kernels on an ARM-\nbased Evaluation-Board.",
            "document_title": "resume.pdf",
            "user_id": "ms-user",
            "@search.score": 1.0,
            "@search.reranker_score": null,
            "@search.highlights": null,
            "@search.captions": null
        },
"""
@dataclass
class Chunk:
    """
    A chunk of content from a document.
    
    Use Chunk.from_azure_search_result() to create instances from Azure Search API responses
    which contain @search.* fields. Use direct constructor for programmatic creation or when
    working with data that doesn't have the Azure Search specific fields.
    """
    document_id: str
    content_id: str
    scope: str
    document_type: Optional[str]
    content_path: str
    org_id: str
    content_text: str
    document_title: str
    user_id: str
    locationMetadata: Optional[LocationMetadata] = None
    # Azure Search specific fields (prefixed with @search)
    search_score: Optional[float] = None
    search_reranker_score: Optional[float] = None
    search_highlights: Optional[Dict[str, List[str]]] = None
    search_captions: Optional[Dict[str, Any]] = None
    # Additional optional fields
    hash: Optional[str] = None
    image_document_id: Optional[str] = None
    conversation_id: Optional[str] = None
    content_embedding: Optional[List[float]] = None

    @classmethod
    def from_azure_search_result(cls, search_result: Dict[str, Any]) -> 'Chunk':
        """
        Create a Chunk instance from Azure Search result JSON.
        
        Handles the @search.* prefixed fields by mapping them to search_* attributes.
        
        Args:
            search_result: Dictionary from Azure Search API response
            
        Returns:
            Chunk instance with all fields populated
        """
        # Handle location metadata
        location_meta = search_result.get("locationMetadata")
        location_metadata = None
        if location_meta:
            location_metadata = LocationMetadata(
                pageNumber=location_meta.get("pageNumber", 0),
                boundingPolygons=location_meta.get("boundingPolygons")
            )
        
        return cls(
            document_id=search_result.get("document_id", ""),
            content_id=search_result.get("content_id", ""),
            scope=search_result.get("scope", ""),
            document_type=search_result.get("document_type"),
            content_path=search_result.get("content_path", ""),
            org_id=search_result.get("org_id", ""),
            content_text=search_result.get("content_text", ""),
            document_title=search_result.get("document_title", ""),
            user_id=search_result.get("user_id", ""),
            locationMetadata=location_metadata,
            # Map @search.* fields to search_* attributes
            search_score=search_result.get("@search.score"),
            search_reranker_score=search_result.get("@search.reranker_score"),
            search_highlights=search_result.get("@search.highlights"),
            search_captions=search_result.get("@search.captions"),
            # Optional fields that might not be in search results
            hash=search_result.get("hash"),
            image_document_id=search_result.get("image_document_id"),
            conversation_id=search_result.get("conversation_id"),
            content_embedding=search_result.get("content_embedding")
        )
    
    def to_azure_search_dict(self) -> Dict[str, Any]:
        """
        Convert Chunk instance back to Azure Search JSON format.
        
        Maps search_* attributes back to @search.* keys and handles None values appropriately.
        
        Returns:
            Dictionary in Azure Search result format
        """
        result = {
            "document_id": self.document_id,
            "content_id": self.content_id,
            "scope": self.scope,
            "document_type": self.document_type,
            "content_path": self.content_path,
            "org_id": self.org_id,
            "content_text": self.content_text,
            "document_title": self.document_title,
            "user_id": self.user_id
        }
        
        # Add location metadata if present
        if self.locationMetadata:
            result["locationMetadata"] = {
                "pageNumber": self.locationMetadata.pageNumber,
                "boundingPolygons": self.locationMetadata.boundingPolygons
            }
        
        # Add Azure Search specific fields with @search prefix
        if self.search_score is not None:
            result["@search.score"] = self.search_score
        if self.search_reranker_score is not None:
            result["@search.reranker_score"] = self.search_reranker_score
        if self.search_highlights is not None:
            result["@search.highlights"] = self.search_highlights
        if self.search_captions is not None:
            result["@search.captions"] = self.search_captions
            
        # Add optional fields if present
        if self.hash is not None:
            result["hash"] = self.hash
        if self.image_document_id is not None:
            result["image_document_id"] = self.image_document_id
        if self.conversation_id is not None:
            result["conversation_id"] = self.conversation_id
        if self.content_embedding is not None:
            result["content_embedding"] = self.content_embedding
            
        return result

@dataclass
class Document:
    """
    A document from the database.
    """
    document_id: str
    document_title: str
    document_type: str
    org_id: str
    user_id: str
    scope: str
    chunk_count: int
    page_count: int
    has_images: bool
    has_text: bool
    chunks: Optional[List[Chunk]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert Document dataclass to dictionary."""
        return {
            "document_id": self.document_id,
            "document_title": self.document_title,
            "document_type": self.document_type,
            "org_id": self.org_id,
            "user_id": self.user_id,
            "scope": self.scope,
            "chunk_count": self.chunk_count,
            "page_count": self.page_count,
            "has_images": self.has_images,
            "has_text": self.has_text,
            "chunks": [chunk.__dict__ for chunk in self.chunks] if self.chunks else []
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Document':
        """Convert dictionary to Document dataclass with robust error handling."""
        try:
            chunks_data = data.get("chunks", [])
            chunks = []
            
            for chunk_item in chunks_data:
                # Use from_azure_search_result to handle @search.* fields properly
                chunks.append(Chunk.from_azure_search_result(chunk_item))
                # Handle cases where chunk might be a string or unexpected format
                                    
            return Document(
                document_id=data["document_id"],
                document_title=data["document_title"],
                document_type=data["document_type"],
                org_id=data["org_id"],
                user_id=data["user_id"],
                scope=data["scope"],            
                chunk_count=data["chunk_count"],
                page_count=data["page_count"],
                has_images=data["has_images"],
                has_text=data["has_text"],
                chunks=chunks
            )
        except KeyError as e:
            raise ValueError(f"Missing required field in document data: {e}")
        except Exception as e:
            raise ValueError(f"Failed to create Document from dict: {e}")
