"""Semantic search tool for multimodal content blocks using Azure AI Search."""

import time
import os
from typing import Any, Dict, Optional
import structlog

from azure.search.documents.models import (
    VectorizableTextQuery,
    QueryType,
    QueryCaptionType,
    QueryAnswerType
)

from taskforce.core.interfaces.tools import ToolProtocol, ApprovalRiskLevel
from taskforce.infrastructure.tools.rag.azure_search_base import AzureSearchBase


class SemanticSearchTool:
    """
    Search across multimodal content blocks using Hybrid Search + Semantic Reranking.

    This tool utilizes Azure AI Search's most powerful features:
    1. Vector Search (Semantic meaning)
    2. Keyword Search (BM25 for exact matches)
    3. Semantic Reranking (L2 ranking for relevance)
    
    It requires the index to have a vector field (e.g. 'content_embedding') and
    a semantic configuration to be set up in Azure.
    """

    def __init__(self, user_context: Optional[Dict[str, Any]] = None):
        """
        Initialize the semantic search tool.

        Args:
            user_context: Optional user context for security filtering
        """
        self.azure_base = AzureSearchBase()
        self.user_context = user_context or {}
        self.logger = structlog.get_logger().bind(tool="rag_semantic_search")
        
        # Load semantic configuration name from env or default
        self.semantic_config = os.getenv("AZURE_SEARCH_SEMANTIC_CONFIG", "default")

    @property
    def name(self) -> str:
        return "rag_semantic_search"

    @property
    def description(self) -> str:
        return (
            "Perform a deep semantic search across documents using Hybrid Search "
            "(Vector + Keyword) and Semantic Reranking. "
            "Returns highly relevant text chunks and images with relevance scores. "
            "Use this for 'How', 'Why', or 'What' questions where understanding the "
            "meaning is more important than exact keyword matching."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The natural language search query"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 10, max: 50)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50
                },
                "filters": {
                    "type": "object",
                    "description": "Optional filters (e.g., {'document_type': 'Manual'})",
                    "default": {}
                }
            },
            "required": ["query"]
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        return f"Tool: {self.name}\nOperation: Hybrid Search\nQuery: {query}"

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "query" not in kwargs or not isinstance(kwargs["query"], str):
            return False, "Missing or invalid parameter: query"
        return True, None

    async def execute(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute Hybrid Search (Vector + Text) with Semantic Reranking.
        """
        start_time = time.time()
        top_k = max(1, min(top_k, 50))

        self.logger.info("search_started", query=query[:100], top_k=top_k)

        try:
            # 1. Build Security & Custom Filters
            security_filter = self.azure_base.build_security_filter(self.user_context)
            combined_filter = self._combine_filters(security_filter, filters)

            # 2. Prepare Vector Query (Server-side embedding)
            # Assuming the index field for vectors is named 'content_embedding'
            vector_query = VectorizableTextQuery(
                text=query, 
                k_nearest_neighbors=top_k, 
                fields="content_embedding",
                exhaustive=True
            )

            # 3. Get Client
            client = self.azure_base.get_search_client(self.azure_base.content_index)

            async with client:
                # 4. Execute Search
                search_results = await client.search(
                    search_text=query,                  # Keyword Search (BM25)
                    vector_queries=[vector_query],      # Vector Search
                    filter=combined_filter if combined_filter else None,
                    top=top_k,
                    
                    # Semantic Reranking Configuration
                    query_type=QueryType.SEMANTIC,
                    semantic_configuration_name=self.semantic_config,
                    query_caption=QueryCaptionType.EXTRACTIVE,
                    query_answer=QueryAnswerType.EXTRACTIVE,
                    
                    select=[
                        "content_id",
                        "content_text",
                        "content_path",
                        "document_id",
                        "document_title",
                        "document_type",
                        "locationMetadata",
                        "org_id",
                        "scope"
                    ]
                )

                # 5. Process Results
                results = []
                async for result in search_results:
                    # Determine Scores
                    # @search.rerankerScore is the Semantic Score (0-4 usually)
                    # @search.score is the BM25/Vector score
                    reranker_score = result.get("@search.rerankerScore", 0.0)
                    base_score = result.get("@search.score", 0.0)
                    
                    # Normalize semantic score roughly to 0-1 for consistency
                    normalized_score = min(reranker_score / 4.0, 1.0) if reranker_score else base_score

                    # Get Captions (High quality snippets generated by Azure)
                    captions = []
                    if result.get("@search.captions"):
                        captions = [c.text for c in result["@search.captions"]]
                    
                    # Fallback to content text if no captions
                    content_preview = " ".join(captions) if captions else result.get("content_text", "")

                    # Extract Page Number
                    page_number = None
                    if result.get("locationMetadata"):
                        page_number = result["locationMetadata"].get("pageNumber")

                    block = {
                        "content_id": result.get("content_id"),
                        "document_title": result.get("document_title"),
                        "document_id": result.get("document_id"),
                        "page_number": page_number,
                        "score": float(normalized_score),
                        "relevance_reason": "Semantic Match" if reranker_score else "Keyword Match",
                        "content": content_preview, # Prefer caption/highlight
                        "full_content": result.get("content_text"),
                        "image_path": result.get("content_path")
                    }
                    results.append(block)

            # 6. Format Output for Agent
            latency_ms = int((time.time() - start_time) * 1000)
            
            if not results:
                return {
                    "success": True, 
                    "result_count": 0, 
                    "result": "No relevant documents found."
                }

            # Human-readable output for the LLM
            result_text = f"Found {len(results)} relevant results (Hybrid Search):\n\n"
            for i, res in enumerate(results, 1):
                res_type = "🖼️ [IMAGE]" if res.get('image_path') else "📄 [TEXT]"
                page_info = f", p. {res['page_number']}" if res['page_number'] else ""
                
                result_text += (
                    f"{i}. {res_type} {res['document_title']} {page_info}\n"
                    f"   Relevance: {res['score']:.2f} ({res['relevance_reason']})\n"
                    f"   Excerpt: {res['content'][:300]}...\n\n"
                )

            self.logger.info("search_completed", count=len(results), ms=latency_ms)

            return {
                "success": True,
                "results": results,
                "result_count": len(results),
                "result": result_text
            }

        except Exception as e:
            return self._handle_error(e, query, time.time() - start_time)

    def _combine_filters(self, security_filter: str, additional_filters: Optional[Dict[str, Any]]) -> str:
        # Same logic as before
        filters = []
        if security_filter:
            filters.append(f"({security_filter})")
        
        if additional_filters:
            for key, value in additional_filters.items():
                sanitized_value = self.azure_base._sanitize_filter_value(str(value))
                if isinstance(value, str):
                    filters.append(f"{key} eq '{sanitized_value}'")
                else:
                    filters.append(f"{key} eq {value}")
        
        return " and ".join(filters) if filters else ""

    def _handle_error(self, exception: Exception, query: str, elapsed_time: float) -> Dict[str, Any]:
        # Same error handling logic as before, just ensuring imports are there
        from azure.core.exceptions import HttpResponseError
        
        error_msg = str(exception)
        hints = []
        
        if isinstance(exception, HttpResponseError):
            if "Semantic search is not enabled" in error_msg:
                hints.append("Your Azure Search tier does not support Semantic Search or it is disabled.")
                hints.append("Fallback: Remove 'query_type=SEMANTIC' from the code.")
            elif "content_embedding" in error_msg:
                hints.append("The index is missing the 'content_embedding' vector field.")

        self.logger.error("search_failed", error=error_msg)
        
        return {
            "success": False, 
            "error": error_msg, 
            "hints": hints
        }