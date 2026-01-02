import asyncio
import asyncio
from typing import Any, Dict, List, Optional

import structlog
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.infrastructure.tools.rag.azure_search_base import AzureSearchBase, Document
from taskforce.infrastructure.tools.rag.get_document import GetDocumentTool

class GlobalDocumentAnalysisTool(ToolProtocol):
    """
    This tool is used to handle global questions about an certain document,
    e.g. it is able to summarize the document, answer questions about the document,
    and provide a detailed analysis of the document.
    """
    def __init__(
            self,
            llm_provider: Optional[LLMProviderProtocol] = None,
            get_document_tool: Optional[GetDocumentTool] = None,
            user_context: Optional[Dict[str, Any]] = None):
        self._llm_provider = llm_provider
        self._get_document_tool = get_document_tool
        self.azure_base = AzureSearchBase()
        self.logger = structlog.get_logger().bind(tool="global_document_analysis")

    @property
    def llm_provider(self) -> LLMProviderProtocol:
        """Lazy-load LLM provider if not provided."""
        if self._llm_provider is None:
            # Use the same approach as AgentFactory._create_llm_provider
            from taskforce.infrastructure.llm.openai_service import OpenAIService
            self._llm_provider = OpenAIService(config_path="configs/llm_config.yaml")
        return self._llm_provider

    @property
    def get_document_tool(self) -> GetDocumentTool:
        """Lazy-load GetDocumentTool if not provided."""
        if self._get_document_tool is None:
            self._get_document_tool = GetDocumentTool()
        return self._get_document_tool

    @classmethod
    def create_default(cls, user_context: Optional[Dict[str, Any]] = None) -> "GlobalDocumentAnalysisTool":
        """Factory method to create tool with default dependencies."""
        return cls(user_context=user_context)

    @property
    def name(self) -> str:
        return "global_document_analysis"

    @property
    def description(self) -> str:
        return "This tool is used to handle global questions about an certain document, \
            e.g. it is able to summarize the document, answer questions about the document, \
            and provide a detailed analysis of the document."

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
                "question": {
                    "type": "string",
                    "description": "The question to answer"
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
            "required": ["document_id", "question"]
        }

    @property
    def requires_approval(self) -> bool:
        """Global document analysis is read-only, no approval needed."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Low risk - read-only operation."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate approval preview (not used for read-only tool)."""
        document_id = kwargs.get("document_id", "")
        question = kwargs.get("question", "")
        return f"Tool: {self.name}\nOperation: Global document analysis\nDocument: {document_id}\nQuestion: {question}"

    async def execute(
        self,
        document_id: str,
        question: str,
        user_context: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Execute global document analysis.

        Args:
            document_id: The unique document UUID
            question: The question to answer
            user_context: Optional user context for security filtering
            **kwargs: Additional arguments (ignored)

        Returns:
            Dict with structure:
            {
                "success": True,
                "result": "The analysis result",
                "document_id": "document_id",
                "total_chunks_processed": 25,
                "analysis_method": "map_reduce" | "direct"
            }
        """
        if user_context is None:
            user_context = {}

        try:
            result = await self.get_document_tool.execute(document_id, user_context=user_context, include_chunk_content=True)

            if not result["success"]:
                return {"success": False, "error": result["error"]}

            # Get the document data from the result
            document_data = result["document"]
            
            # Handle the case where document might already be a Document object or a dict
            if hasattr(document_data, 'chunks'):
                # Already a Document object
                document = document_data
            else:
                # Convert dict to Document object with better error handling
                try:
                    document = Document.from_dict(document_data)
                except Exception as e:
                    self.logger.error("Failed to convert document data", error=str(e), document_data=document_data)
                    return {"success": False, "error": f"Failed to process document data: {str(e)}"}

            # 1. Get the total length of the chunks in the document
            total_chunks = len(document.chunks) if document.chunks else 0
            
            if total_chunks == 0:
                return {"success": False, "error": "Document has no content chunks available for analysis"}

            # 2. If total chunks greater than 20 then use map reduce
            if total_chunks > 20:
                # split chunks into groups of 5
                chunk_groups = [
                    document.chunks[i:i + 5] 
                    for i in range(0, total_chunks, 5)
                ]

                summaries = []

                for group in chunk_groups:
                    chunk_texts = "\n\n".join([chunk.content_text for chunk in group])
                    prompt = (
                        f"Given the following document chunks:\n{chunk_texts}\n\n"
                        f"Answer the following question:\n{question}\n\n"
                        "Provide a concise answer based on the provided chunks."
                    )
                    response = await self.llm_provider.generate(prompt)
                    summaries.append(response['generated_text'])

                # async def process_chunk_group(chunk_group: List[str]) -> str:
                #     # create a prompt for the llm
                #     chunk_texts = "\n\n".join([chunk.content_text for chunk in chunk_group])
                #     prompt = (
                #         f"Given the following document chunks:\n{chunk_texts}\n\n"
                #         f"Answer the following question:\n{question}\n\n"
                #         "Provide a concise answer based on the provided chunks."
                #     )
                #     response = await self.llm_provider.generate(prompt)
                #     return response
                
                # # process chunk groups concurrently
                # intermediate_answers = await asyncio.gather(
                #     *(process_chunk_group(group) for group in chunk_groups)
                # )

                # combine intermediate answers
                combined_prompt = (
                    f"Given the following intermediate answers from document chunks:\n"
                    f"{chr(10).join(summaries)}\n\n"
                    f"Answer the following question:\n{question}\n\n"
                    "Provide a comprehensive final answer based on the intermediate answers."
                )
                analysis_method = "map_reduce"
                
            # 3. If total chunks less than 20 then process directly
            else:
                chunk_texts = "\n\n".join([chunk.content_text for chunk in document.chunks])
                combined_prompt = (
                    f"Given the following document chunks:\n{chunk_texts}\n\n"
                    f"Answer the following question:\n{question}\n\n"
                    "Provide a comprehensive answer based on the provided chunks."
                )
                analysis_method = "direct"

            final_answer = await self.llm_provider.generate(combined_prompt)

            # 4. Return the actual result to the user
            return {
                "success": True, 
                "result": final_answer,
                "document_id": document_id,
                "total_chunks_processed": total_chunks,
                "analysis_method": analysis_method
            }

        except Exception as e:
            self.logger.error("Global document analysis failed", error=str(e), document_id=document_id)
            return {
                "success": False, 
                "error": f"Global document analysis failed: {str(e)}"
            }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "document_id" not in kwargs:
            return False, "Missing required parameter: document_id"
        
        if not isinstance(kwargs["document_id"], str):
            return False, "Parameter 'document_id' must be a string"
        
        if "question" not in kwargs:
            return False, "Missing required parameter: question"
        
        if not isinstance(kwargs["question"], str):
            return False, "Parameter 'question' must be a string"
        
        return True, None
