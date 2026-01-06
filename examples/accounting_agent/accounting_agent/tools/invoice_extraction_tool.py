"""
LLM-based invoice data extraction tool for DACH region invoices.

This tool uses LLM to extract structured invoice fields from markdown
content (typically output from DoclingTool). Supports German, Austrian,
and Swiss invoice formats.
"""

from __future__ import annotations

import json
from typing import Any

from accounting_agent.prompts.invoice_extraction_prompt import INVOICE_EXTRACTION_PROMPT
from accounting_agent.tools.tool_base import ApprovalRiskLevel


class InvoiceExtractionTool:
    """
    Extract structured invoice data from markdown using LLM.

    Takes markdown content (from DoclingTool output) and extracts
    all invoice-relevant fields using an LLM call. Supports DACH
    region formats:
    - German: USt-IdNr DE123456789, Steuernummer format
    - Austrian: UID ATU12345678
    - Swiss: CHE-123.456.789 MWST/TVA/IVA

    Output is compatible with ComplianceCheckerTool input format.
    """

    def __init__(self, llm_provider: Any, model_alias: str = "main") -> None:
        """
        Initialize InvoiceExtractionTool.

        Args:
            llm_provider: LLM provider implementing LLMProviderProtocol
            model_alias: Model alias to use for extraction (default: "main")
        """
        self._llm_provider = llm_provider
        self._model_alias = model_alias

    @property
    def name(self) -> str:
        """Return tool name."""
        return "invoice_extract"

    @property
    def description(self) -> str:
        """Return tool description for LLM function calling."""
        return (
            "Extract structured invoice data from markdown content using LLM. "
            "Input: markdown text from docling_extract tool. "
            "Output: structured dict with supplier info, amounts, line items, VAT details. "
            "Supports DACH formats (DE/AT/CH). "
            "Use this AFTER docling_extract and BEFORE check_compliance."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "markdown_content": {
                    "type": "string",
                    "description": "Markdown content from docling_extract output",
                },
                "expected_currency": {
                    "type": "string",
                    "description": "Expected currency code (default: EUR)",
                    "default": "EUR",
                    "enum": ["EUR", "CHF"],
                },
            },
            "required": ["markdown_content"],
        }

    @property
    def requires_approval(self) -> bool:
        """Whether tool requires human approval before execution."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Risk level for approval workflow."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of what the tool will do."""
        content = kwargs.get("markdown_content", "")
        preview = content[:100] + "..." if len(content) > 100 else content
        return (
            f"Tool: {self.name}\n"
            f"Operation: Extract invoice data from markdown using LLM\n"
            f"Content preview: {preview}"
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "markdown_content" not in kwargs:
            return False, "Missing required parameter: markdown_content"

        content = kwargs["markdown_content"]
        if not isinstance(content, str):
            return False, "markdown_content must be a string"

        if not content.strip():
            return False, "markdown_content cannot be empty"

        # Validate currency if provided
        currency = kwargs.get("expected_currency", "EUR")
        if currency not in ("EUR", "CHF"):
            return False, f"Invalid currency: {currency}. Must be EUR or CHF."

        return True, None

    async def execute(
        self,
        markdown_content: str,
        expected_currency: str = "EUR",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Extract invoice data from markdown content.

        Args:
            markdown_content: Markdown text from DoclingTool
            expected_currency: Expected currency code (EUR or CHF)

        Returns:
            Dictionary with:
            - success: bool
            - invoice_data: Extracted structured data (on success)
            - confidence_score: Extraction confidence 0.0-1.0
            - warnings: List of extraction warnings
            - error: Error message (on failure)
        """
        try:
            # Build the extraction prompt
            prompt = INVOICE_EXTRACTION_PROMPT.format(
                markdown_content=markdown_content,
                expected_currency=expected_currency,
            )

            # Call LLM for extraction with low temperature for consistency
            result = await self._llm_provider.generate(
                prompt=prompt,
                model=self._model_alias,
                max_tokens=2500,
                temperature=0.1,
            )

            if not result.get("success"):
                return {
                    "success": False,
                    "error": f"LLM extraction failed: {result.get('error', 'Unknown error')}",
                    "error_type": result.get("error_type", "LLMError"),
                }

            # Parse the LLM response as JSON
            generated_text = result.get("generated_text") or result.get("content", "")
            invoice_data = self._parse_extraction_response(generated_text)

            # write the generated text to a file
            with open("generated_text.txt", "w") as f:
                f.write(generated_text)

            if invoice_data is None:
                return {
                    "success": False,
                    "error": "Failed to parse extraction response as JSON",
                    "raw_response": generated_text[:500] if generated_text else "",
                }

            # Ensure currency is set
            if "currency" not in invoice_data:
                invoice_data["currency"] = expected_currency

            # Extract confidence and warnings
            confidence_score = invoice_data.pop("confidence_score", 0.8)
            extraction_warnings = invoice_data.pop("extraction_warnings", [])

            return {
                "success": True,
                "invoice_data": invoice_data,
                "confidence_score": confidence_score,
                "warnings": extraction_warnings,
                "tokens_used": result.get("tokens_used", 0),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    def _parse_extraction_response(self, response: str) -> dict[str, Any] | None:
        """
        Parse LLM response, extracting JSON from markdown code blocks.

        Args:
            response: Raw LLM response text

        Returns:
            Parsed dictionary or None if parsing fails
        """
        if not response:
            return None

        # Try to find JSON in ```json code block
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end > start:
                json_str = response[start:end].strip()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

        # Try to find JSON in generic ``` code block
        if "```" in response:
            start = response.find("```") + 3
            # Skip optional language identifier on same line
            newline = response.find("\n", start)
            if newline > start and newline - start < 20:
                start = newline + 1
            end = response.find("```", start)
            if end > start:
                json_str = response[start:end].strip()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

        # Try to find JSON object directly (starts with { ends with })
        response = response.strip()
        if response.startswith("{"):
            # Find the matching closing brace
            brace_count = 0
            for i, char in enumerate(response):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = response[: i + 1]
                        try:
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            break

        # Last resort: try parsing entire response as JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return None
