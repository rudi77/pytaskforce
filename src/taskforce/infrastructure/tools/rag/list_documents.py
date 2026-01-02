"""List documents tool for Azure AI Search document metadata retrieval."""

import time
from typing import Any, Dict, Optional
import structlog

from taskforce.core.interfaces.tools import ToolProtocol, ApprovalRiskLevel
from taskforce.infrastructure.tools.rag.azure_search_base import AzureSearchBase


class ListDocumentsTool(ToolProtocol):
    """
    List available documents from the content-blocks index.
    
    This tool retrieves unique documents by aggregating content blocks. It attempts to use 
    Azure Search facets for efficiency, but automatically falls back to manual deduplication 
    if the document_id field is not marked as facetable in the index schema.
    
    Returns document metadata including chunk counts and access control fields.
    Implements ToolProtocol for dependency injection.
    """

    def __init__(self, user_context: Optional[Dict[str, Any]] = None):
        """
        Initialize the list documents tool.

        Args:
            user_context: Optional user context for security filtering
                         (user_id, org_id, scope)
        """
        self.azure_base = AzureSearchBase()
        self.user_context = user_context or {}
        self.logger = structlog.get_logger().bind(tool="rag_list_documents")

    @property
    def name(self) -> str:
        """Tool name used by the agent."""
        return "rag_list_documents"

    @property
    def description(self) -> str:
        """Tool description for the agent."""
        return (
            "List all available documents in the knowledge base. "
            "Returns document metadata including document ID, title, type, "
            "organization, user, scope, and chunk count. "
            "Valid filter fields: document_type, org_id, user_id, scope. "
            "Use this to discover what documents are available before searching their content."
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
                "filters": {
                    "type": "object",
                    "description": "Optional filters. Valid fields: document_type, org_id, user_id, scope. Example: {'document_type': 'application/pdf', 'scope': 'shared'}",
                    "default": {}
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of documents to return (default: 20, max: 100)",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100
                },
                "user_context": {
                    "type": "object",
                    "description": "User context for security filtering (org_id, user_id, scope)",
                    "default": {}
                }
            },
            "required": []
        }

    @property
    def requires_approval(self) -> bool:
        """RAG list is read-only, no approval needed."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Low risk - read-only operation."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate approval preview (not used for read-only tool)."""
        limit = kwargs.get("limit", 20)
        return f"Tool: {self.name}\nOperation: List documents\nLimit: {limit}"

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "limit" in kwargs:
            limit = kwargs["limit"]
            if not isinstance(limit, int) or limit < 1 or limit > 100:
                return False, "Parameter 'limit' must be an integer between 1 and 100"
        
        return True, None

    async def execute(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        user_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute document listing from content-blocks index using facets.

        Args:
            filters: Optional additional filters. Valid fields: document_type, org_id, user_id, scope
            limit: Maximum number of documents to return (1-100)
            user_context: Optional user context override for security filtering
            **kwargs: Additional arguments (ignored)

        Returns:
            Dict with structure:
            {
                "success": True,
                "documents": [
                    {
                        "document_id": "...",
                        "document_title": "...",
                        "document_type": "application/pdf",
                        "org_id": "...",
                        "user_id": "...",
                        "scope": "shared",
                        "chunk_count": 15
                    },
                    ...
                ],
                "count": 10
            }

        Example:
            >>> tool = ListDocumentsTool(user_context={"org_id": "MS-corp"})
            >>> result = await tool.execute(limit=10)
            >>> print(result["count"])
            10
        """
        start_time = time.time()

        self.logger.info(
            "list_documents_started",
            has_filters=bool(filters),
            limit=limit
        )

        try:
            # Validate limit
            limit = max(1, min(limit, 100))

            # Use provided user_context or fall back to instance context
            context = user_context or self.user_context

            # Build security filter from user context
            security_filter = self.azure_base.build_security_filter(context)

            # Combine with additional filters if provided
            combined_filter = self._combine_filters(security_filter, filters)

            # Get search client for content-blocks index
            client = self.azure_base.get_search_client(
                self.azure_base.content_index
            )

            # Execute search to get unique document_ids
            async with client:
                document_ids = []
                
                # Try faceting approach first (most efficient)
                try:
                    search_results = await client.search(
                        search_text="*",  # Match all documents
                        filter=combined_filter if combined_filter else None,
                        facets=["document_id,count:1000"],  # Get up to 1000 unique doc IDs
                        top=0  # We don't need results, just facets
                    )

                    # Extract unique document IDs from facets (async call)
                    facets = await search_results.get_facets()
                    
                    if facets and "document_id" in facets:
                        # Limit to requested number of documents
                        document_ids = [
                            facet["value"] 
                            for facet in facets["document_id"][:limit]
                        ]
                    
                    self.logger.info(
                        "faceting_success",
                        unique_documents=len(document_ids),
                        method="faceting"
                    )

                except Exception as facet_error:
                    # Check if error is due to field not being facetable
                    error_msg = str(facet_error).lower()
                    if "not been marked as facetable" in error_msg or "fieldnotfacetable" in error_msg:
                        self.logger.warning(
                            "faceting_not_supported",
                            message="document_id field not facetable, using fallback approach",
                            original_error=str(facet_error)[:200]
                        )
                        
                        # Fallback: Use regular search and manually deduplicate
                        self.logger.info(
                            "fallback_search_starting",
                            filter=combined_filter,
                            limit=limit
                        )
                        
                        search_results = await client.search(
                            search_text="*",
                            filter=combined_filter if combined_filter else None,
                            select=["document_id"],
                            top=1000  # Get enough results to find unique documents
                        )
                        
                        seen_ids = set()
                        chunk_count = 0
                        async for chunk in search_results:
                            chunk_count += 1
                            doc_id = chunk.get("document_id")
                            if doc_id and doc_id not in seen_ids:
                                seen_ids.add(doc_id)
                                document_ids.append(doc_id)
                                if len(document_ids) >= limit:
                                    break
                        
                        self.logger.info(
                            "fallback_success",
                            unique_documents=len(document_ids),
                            total_chunks_processed=chunk_count,
                            method="manual_deduplication"
                        )
                    else:
                        # Re-raise if it's a different error
                        raise

                # Now fetch one representative chunk per document to get metadata
                documents = []
                for doc_id in document_ids:
                    doc_filter = f"document_id eq '{doc_id}'"
                    if combined_filter:
                        doc_filter = f"({combined_filter}) and {doc_filter}"

                    # Get all chunks for this document to count them
                    doc_results = await client.search(
                        search_text="*",
                        filter=doc_filter,
                        select=[
                            "document_id",
                            "document_title",
                            "document_type",
                            "org_id",
                            "user_id",
                            "scope"
                        ],
                        top=1000  # Get all chunks to count
                    )

                    chunks = []
                    representative = None
                    async for chunk in doc_results:
                        chunks.append(chunk)
                        if representative is None:
                            representative = chunk

                    if representative:
                        documents.append({
                            "document_id": representative.get("document_id"),
                            "document_title": representative.get("document_title"),
                            "document_type": representative.get("document_type"),
                            "org_id": representative.get("org_id"),
                            "user_id": representative.get("user_id"),
                            "scope": representative.get("scope"),
                            "chunk_count": len(chunks)
                        })

            # Calculate latency
            latency_ms = int((time.time() - start_time) * 1000)

            self.logger.info(
                "list_documents_completed",
                azure_operation="list_documents",
                index_name=self.azure_base.content_index,
                result_count=len(documents),
                unique_documents=len(documents),
                search_latency_ms=latency_ms
            )

            # Format result string for agent consumption
            if not documents:
                result_text = "No documents found in the knowledge base."
            else:
                count = len(documents)
                result_text = f"Found {count} documents:\n"
                for i, doc in enumerate(documents[:10], 1):
                    result_text += f"{i}. {doc.get('document_title', 'Unknown')} (ID: {doc.get('document_id')})\n"
                
                if count > 10:
                    result_text += f"... and {count - 10} more.\n"

            return {
                "success": True,
                "documents": documents,
                "count": len(documents),
                "result": result_text  # Human-readable summary for agent
            }

        except Exception as e:
            return self._handle_error(e, time.time() - start_time)

    # Valid filter fields that exist in the Azure Search index
    VALID_FILTER_FIELDS = {"document_type", "org_id", "user_id", "scope"}

    def _combine_filters(
        self,
        security_filter: str,
        additional_filters: Optional[Dict[str, Any]]
    ) -> str:
        """
        Combine security filter with additional user filters.

        Args:
            security_filter: OData filter from user context
            additional_filters: Additional filter dict (e.g., {"document_type": "application/pdf"})

        Returns:
            Combined OData filter string
        """
        filters = []

        if security_filter:
            filters.append(f"({security_filter})")

        if additional_filters:
            for key, value in additional_filters.items():
                # Skip invalid filter fields (e.g., 'query' is not a valid index field)
                if key not in self.VALID_FILTER_FIELDS:
                    self.logger.warning(
                        "invalid_filter_field_ignored",
                        field=key,
                        valid_fields=list(self.VALID_FILTER_FIELDS)
                    )
                    continue
                    
                # Sanitize the value
                sanitized_value = self.azure_base._sanitize_filter_value(str(value))
                if isinstance(value, str):
                    filters.append(f"{key} eq '{sanitized_value}'")
                elif isinstance(value, (int, float)):
                    filters.append(f"{key} eq {value}")

        if not filters:
            return ""

        return " and ".join(filters)

    def _handle_error(
        self,
        exception: Exception,
        elapsed_time: float
    ) -> Dict[str, Any]:
        """
        Handle errors and return structured error response.

        Args:
            exception: The exception that occurred
            elapsed_time: Time elapsed before error

        Returns:
            Structured error dict matching agent's expected format
        """
        from azure.core.exceptions import HttpResponseError, ServiceRequestError
        import traceback

        latency_ms = int(elapsed_time * 1000)

        # Determine error type and hints
        error_type = type(exception).__name__
        error_message = str(exception)
        hints = []

        if isinstance(exception, HttpResponseError):
            if exception.status_code == 401:
                error_type = "AuthenticationError"
                hints.append("Check AZURE_SEARCH_API_KEY environment variable")
            elif exception.status_code == 404:
                error_type = "IndexNotFoundError"
                hints.append(f"Verify index '{self.azure_base.content_index}' exists")
            elif exception.status_code == 400:
                error_type = "InvalidQueryError"
                hints.append("Check filter format and field names")
            elif exception.status_code == 403:
                error_type = "AccessDeniedError"
                hints.append("User does not have access to requested documents")

            error_message = f"Azure Search HTTP {exception.status_code}: {exception.message}"

        elif isinstance(exception, ServiceRequestError):
            error_type = "NetworkError"
            hints.append("Check network connectivity to Azure Search endpoint")
            hints.append(f"Endpoint: {self.azure_base.endpoint}")

        elif isinstance(exception, TimeoutError):
            error_type = "TimeoutError"
            hints.append("Request took too long - try reducing limit")

        else:
            error_type = "AzureSearchError"
            hints.append("Check application logs for detailed traceback")

        self.logger.error(
            "list_documents_failed",
            azure_operation="list_documents",
            index_name=self.azure_base.content_index,
            error_type=error_type,
            error=error_message,
            search_latency_ms=latency_ms,
            traceback=traceback.format_exc()
        )

        return {
            "success": False,
            "error": error_message,
            "type": error_type,
            "hints": hints
        }

