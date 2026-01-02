"""Get document metadata tool for Azure AI Search."""

import time
from typing import Any, Dict, Optional
import structlog

from taskforce.core.interfaces.tools import ToolProtocol, ApprovalRiskLevel
from taskforce.infrastructure.tools.rag.azure_search_base import AzureSearchBase


class GetDocumentTool:
    """
    Retrieve detailed metadata for a specific document from content-blocks index.

    This tool fetches all chunks for a document and aggregates metadata
    including page count, content types, and chunk information.
    Implements ToolProtocol for dependency injection.
    """

    def __init__(self, user_context: Optional[Dict[str, Any]] = None):
        """
        Initialize the get document tool.

        Args:
            user_context: Optional user context for security filtering
                         (user_id, org_id, scope)
        """
        self.azure_base = AzureSearchBase()
        self.user_context = user_context or {}
        self.logger = structlog.get_logger().bind(tool="rag_get_document")

    @property
    def name(self) -> str:
        """Tool name used by the agent."""
        return "rag_get_document"

    @property
    def description(self) -> str:
        """Tool description for the agent."""
        return (
            "Retrieve detailed metadata and content for a specific document using its ID. "
            "Returns complete document information including title, type, chunk count, "
            "and optionally the full content text. "
            "CRITICAL: You MUST use the 'document_id' (UUID) returned by rag_list_documents, "
            "NOT the filename, because filenames are not unique."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """
        JSON schema for tool parameters.

        Used by the agent to understand what parameters this tool accepts.
        """
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": (
                        "The unique document UUID (preferred) or document title/filename. "
                        "Example: '30603b8a-9f41-47f4-9fe0-f329104faed5'"
                    )
                },
                "include_chunk_content": {
                    "type": "boolean",
                    "description": (
                        "If true, includes full chunk content (text, "
                        "images, metadata) for all chunks. Useful for "
                        "document summarization. Default: false (returns "
                        "only chunk IDs)"
                    ),
                    "default": False
                },
                "user_context": {
                    "type": "object",
                    "description": (
                        "User context for security filtering "
                        "(org_id, user_id, scope)"
                    ),
                    "default": {}
                }
            },
            "required": ["document_id"]
        }

    @property
    def requires_approval(self) -> bool:
        """RAG get document is read-only, no approval needed."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Low risk - read-only operation."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate approval preview (not used for read-only tool)."""
        document_id = kwargs.get("document_id", "")
        return f"Tool: {self.name}\nOperation: Get document\nDocument: {document_id}"

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "document_id" not in kwargs:
            return False, "Missing required parameter: document_id"
        
        if not isinstance(kwargs["document_id"], str):
            return False, "Parameter 'document_id' must be a string"
        
        return True, None

    async def execute(
        self,
        document_id: str,
        include_chunk_content: bool = False,
        user_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute document metadata retrieval from content-blocks index.

        Args:
            document_id: The document UUID or title/filename
            include_chunk_content: If True, returns full chunk content.
                                  If False (default), returns only chunk IDs
            user_context: Optional user context override for security
                         filtering
            **kwargs: Additional arguments (ignored)

        Returns:
            Dict with structure:
            {
                "success": True,
                "document": { ... }
            }
        """
        start_time = time.time()

        self.logger.info(
            "get_document_started",
            document_id=document_id,
            include_chunk_content=include_chunk_content
        )

        try:
            # Use provided user_context or fall back to instance context
            context = user_context or self.user_context

            # Build security filter from user context
            security_filter = self.azure_base.build_security_filter(context)

            # Build document filter - Allow search by ID (primary) OR Title (fallback)
            sanitized_val = self.azure_base._sanitize_filter_value(document_id)
            
            # Updated Logic: Check both document_id and document_title fields
            document_filter = f"(document_id eq '{sanitized_val}' or document_title eq '{sanitized_val}')"

            self.logger.info(
                "searching_document",
                search_term=document_id
            )

            # Combine with security filter
            combined_filter = document_filter
            if security_filter:
                combined_filter = f"({security_filter}) and {document_filter}"

            # Get search client for content-blocks index
            client = self.azure_base.get_search_client(
                self.azure_base.content_index
            )

            # Execute search to get all chunks for this document
            async with client:
                search_results = await client.search(
                    search_text="*",  # Match all chunks
                    filter=combined_filter,
                    select=[
                        "content_id",
                        "document_id",
                        "document_title",
                        "document_type",
                        "content_text",
                        "content_path",
                        "locationMetadata",
                        "org_id",
                        "user_id",
                        "scope"
                    ],
                    top=1000  # Get all chunks
                )

                # Aggregate chunk data
                chunks = []
                chunk_ids = []
                document_metadata = None
                max_page = 0
                has_text = False
                has_images = False

                async for chunk in search_results:
                    chunk_data = dict(chunk)
                    
                    # Remove polygons from locationMetadata
                    location_metadata = chunk_data.get("locationMetadata")
                    if location_metadata and isinstance(location_metadata, dict):
                        # Create a copy without polygon data
                        cleaned_metadata = {
                            k: v for k, v in location_metadata.items()
                            if k not in ["polygon", "polygons", "boundingRegions"]
                        }
                        chunk_data["locationMetadata"] = cleaned_metadata
                    
                    chunks.append(chunk_data)
                    chunk_ids.append(chunk_data.get("content_id"))

                    # Capture document metadata from first chunk
                    if document_metadata is None:
                        document_metadata = {
                            "document_id": chunk_data.get("document_id"),
                            "document_title": chunk_data.get("document_title"),
                            "document_type": chunk_data.get("document_type"),
                            "org_id": chunk_data.get("org_id"),
                            "user_id": chunk_data.get("user_id"),
                            "scope": chunk_data.get("scope")
                        }

                    # Check content types
                    if chunk_data.get("content_text"):
                        has_text = True
                    if chunk_data.get("content_path"):
                        has_images = True

                    # Extract max page number from locationMetadata
                    if (location_metadata and
                            isinstance(location_metadata, dict)):
                        page_num = location_metadata.get("pageNumber")
                        if page_num and isinstance(page_num, (int, float)):
                            max_page = max(max_page, int(page_num))

                # Check if document was found
                if not chunks:
                    latency_ms = int((time.time() - start_time) * 1000)
                    self.logger.warning(
                        "get_document_not_found",
                        document_id=document_id,
                        search_latency_ms=latency_ms
                    )
                    return {
                        "success": False,
                        "error": f"Document not found with ID or Title: {document_id}",
                        "type": "NotFoundError"
                    }

                # Build final document object
                document = {
                    **document_metadata,
                    "chunk_count": len(chunks),
                    "page_count": max_page if max_page > 0 else None,
                    "has_images": has_images,
                    "has_text": has_text,
                    "chunks": chunks if include_chunk_content else chunk_ids
                }

            # Calculate latency
            latency_ms = int((time.time() - start_time) * 1000)

            self.logger.info(
                "get_document_completed",
                azure_operation="get_document",
                index_name=self.azure_base.content_index,
                document_id=document_id,
                chunk_count=len(chunks),
                include_chunk_content=include_chunk_content,
                search_latency_ms=latency_ms
            )

            # Format result string for agent consumption
            result_text = (
                f"Document: {document['document_title']}\n"
                f"ID: {document['document_id']}\n"
                f"Type: {document['document_type']}\n"
                f"Chunks: {document['chunk_count']}\n"
                f"Content Types: {'Text' if has_text else ''} {'Images' if has_images else ''}"
            )
            
            if include_chunk_content and chunks:
                result_text += "\n\nContent Preview:\n"
                # Add preview of first few chunks (or sort by page number first if needed)
                # Simple sort by content_id usually keeps order mostly intact for basic preview
                for i, chunk in enumerate(chunks[:5]): # Show up to 5 chunks preview
                    content = chunk.get('content_text', '')
                    page = "Unknown"
                    lm = chunk.get('locationMetadata')
                    if lm and isinstance(lm, dict):
                        page = lm.get('pageNumber', 'Unknown')
                        
                    if content:
                        result_text += f"--- Page {page} ---\n{content[:500]}...\n\n"

            return {
                "success": True,
                "document": document,
                "result": result_text  # Human-readable summary for agent
            }

        except Exception as e:
            return self._handle_error(e, document_id, time.time() - start_time)

    def _handle_error(
        self,
        exception: Exception,
        document_id: str,
        elapsed_time: float
    ) -> Dict[str, Any]:
        # (Fehlerbehandlung bleibt gleich wie in deiner Originaldatei, 
        # da sie hier nicht das Problem war)
        from azure.core.exceptions import (
            HttpResponseError,
            ServiceRequestError
        )
        import traceback

        latency_ms = int(elapsed_time * 1000)

        # Determine error type and hints
        error_type = type(exception).__name__
        error_message = str(exception)
        hints = []

        if isinstance(exception, HttpResponseError):
            if exception.status_code == 401:
                error_type = "AuthenticationError"
                hints.append(
                    "Check AZURE_SEARCH_API_KEY environment variable"
                )
            elif exception.status_code == 404:
                error_type = "IndexNotFoundError"
                hints.append(
                    f"Verify index '{self.azure_base.content_index}' exists"
                )
            elif exception.status_code == 400:
                error_type = "InvalidQueryError"
                hints.append("Check document_id format")
            elif exception.status_code == 403:
                error_type = "AccessDeniedError"
                hints.append("User does not have access to this document")

            error_message = (
                f"Azure Search HTTP {exception.status_code}: "
                f"{exception.message}"
            )

        elif isinstance(exception, ServiceRequestError):
            error_type = "NetworkError"
            hints.append(
                "Check network connectivity to Azure Search endpoint"
            )
            hints.append(f"Endpoint: {self.azure_base.endpoint}")

        elif isinstance(exception, TimeoutError):
            error_type = "TimeoutError"
            hints.append("Request took too long")

        else:
            error_type = "AzureSearchError"
            hints.append("Check application logs for detailed traceback")

        self.logger.error(
            "get_document_failed",
            azure_operation="get_document",
            index_name=self.azure_base.content_index,
            error_type=error_type,
            error=error_message,
            document_id=document_id,
            search_latency_ms=latency_ms,
            traceback=traceback.format_exc()
        )

        return {
            "success": False,
            "error": error_message,
            "type": error_type,
            "hints": hints
        }
