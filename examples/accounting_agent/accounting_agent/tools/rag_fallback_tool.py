"""
RAG Fallback Tool

Provides LLM-based account suggestions when no semantic rules match.
Uses booking history for context-aware suggestions.

PRD Reference:
- Activated ONLY when no rule matches
- LLM generates suggestions, NOT final decisions
- Returns confidence score for evaluation
"""

from typing import Any, Optional

import structlog

from accounting_agent.tools.tool_base import ApprovalRiskLevel

logger = structlog.get_logger(__name__)

# System prompt for RAG-based account suggestion
RAG_SYSTEM_PROMPT = """Du bist ein Buchhaltungs-Assistent für deutsches Steuerrecht.

Deine Aufgabe: Schlage ein passendes Sachkonto (SKR03) für den Buchungsvorschlag vor.

WICHTIG:
- Du gibst NUR einen Vorschlag, KEINE finale Entscheidung
- Begründe deinen Vorschlag mit der Rechtsgrundlage
- Gib eine ehrliche Einschätzung deiner Konfidenz (0.0-1.0)
- Bei Unsicherheit: niedrigere Konfidenz angeben

Antworte im JSON-Format:
{
    "suggested_account": "Kontonummer",
    "account_name": "Kontoname",
    "confidence": 0.0-1.0,
    "reasoning": "Begründung",
    "legal_basis": "Rechtsgrundlage (z.B. §4 Abs. 4 EStG)",
    "alternative_accounts": [
        {"account": "...", "name": "...", "reason": "..."}
    ]
}
"""


class RAGFallbackTool:
    """
    RAG-based account suggestion tool.

    Uses booking history for context and LLM for generating
    suggestions when no semantic rules match.

    This tool does NOT make final decisions - it returns suggestions
    with confidence scores for the confidence evaluator.
    """

    def __init__(
        self,
        booking_history: Optional[Any] = None,
        llm_provider: Optional[Any] = None,
    ):
        """
        Initialize RAG fallback tool.

        Args:
            booking_history: BookingHistoryProtocol for similar bookings
            llm_provider: LLMProviderProtocol for generating suggestions
        """
        self._booking_history = booking_history
        self._llm_provider = llm_provider

    @property
    def name(self) -> str:
        """Return tool name."""
        return "rag_fallback"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Generate account suggestion when no semantic rules match. "
            "Uses historical bookings for context and LLM for suggestion. "
            "Returns a suggestion with confidence score - NOT a final decision. "
            "Use only when semantic_rule_engine returns no matches."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "invoice_data": {
                    "type": "object",
                    "description": (
                        "Invoice data with supplier_name, line_items, "
                        "total_net, total_gross"
                    ),
                },
                "unmatched_item": {
                    "type": "object",
                    "description": (
                        "The specific line item that needs account suggestion. "
                        "Contains: description, net_amount, vat_rate"
                    ),
                },
                "chart_of_accounts": {
                    "type": "string",
                    "description": "Account chart (SKR03 or SKR04)",
                    "enum": ["SKR03", "SKR04"],
                    "default": "SKR03",
                },
            },
            "required": ["invoice_data", "unmatched_item"],
        }

    @property
    def requires_approval(self) -> bool:
        """Read-only suggestions."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Low risk - only generates suggestions."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        invoice_data = kwargs.get("invoice_data", {})
        unmatched_item = kwargs.get("unmatched_item", {})
        supplier = invoice_data.get("supplier_name", "Unknown")
        description = unmatched_item.get("description", "Unknown")[:50]
        return (
            f"Tool: {self.name}\n"
            f"Operation: Generate account suggestion (RAG fallback)\n"
            f"Supplier: {supplier}\n"
            f"Item: {description}"
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "invoice_data" not in kwargs:
            return False, "Missing required parameter: invoice_data"
        if "unmatched_item" not in kwargs:
            return False, "Missing required parameter: unmatched_item"
        return True, None

    async def execute(
        self,
        invoice_data: dict[str, Any],
        unmatched_item: dict[str, Any],
        chart_of_accounts: str = "SKR03",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Generate account suggestion for unmatched item.

        Args:
            invoice_data: Invoice context
            unmatched_item: Line item needing suggestion
            chart_of_accounts: SKR03 or SKR04

        Returns:
            Dictionary with:
            - success: bool
            - suggestion: Account suggestion with confidence
            - similar_bookings: Historical context used
            - is_rag_suggestion: True (for confidence evaluator)
        """
        try:
            supplier_name = invoice_data.get("supplier_name", "")
            item_description = unmatched_item.get("description", "")
            net_amount = unmatched_item.get("net_amount", 0)

            # Get similar historical bookings for context
            similar_bookings = []
            if self._booking_history:
                similar_bookings = await self._booking_history.search_similar(
                    query=item_description,
                    vendor_name=supplier_name,
                    limit=5,
                )

            # If no LLM available, return based on history only
            if not self._llm_provider:
                return self._fallback_from_history(
                    similar_bookings=similar_bookings,
                    item_description=item_description,
                    net_amount=net_amount,
                )

            # Build context prompt
            context_prompt = self._build_context_prompt(
                invoice_data=invoice_data,
                unmatched_item=unmatched_item,
                similar_bookings=similar_bookings,
                chart=chart_of_accounts,
            )

            # Get LLM suggestion
            try:
                response = await self._llm_provider.complete_json(
                    prompt=context_prompt,
                    system_prompt=RAG_SYSTEM_PROMPT,
                    temperature=0.3,  # Low temperature for consistency
                )

                suggestion = {
                    "debit_account": response.get("suggested_account", ""),
                    "debit_account_name": response.get("account_name", ""),
                    "confidence": float(response.get("confidence", 0.5)),
                    "reasoning": response.get("reasoning", ""),
                    "legal_basis": response.get("legal_basis", ""),
                    "alternative_accounts": response.get("alternative_accounts", []),
                }

            except Exception as e:
                logger.warning(
                    "rag_fallback.llm_error",
                    error=str(e),
                )
                return self._fallback_from_history(
                    similar_bookings=similar_bookings,
                    item_description=item_description,
                    net_amount=net_amount,
                )

            logger.info(
                "rag_fallback.suggestion_generated",
                account=suggestion["debit_account"],
                confidence=suggestion["confidence"],
            )

            return {
                "success": True,
                "suggestion": suggestion,
                "similar_bookings": [
                    {
                        "supplier": b.get("invoice_data", {}).get("supplier_name", ""),
                        "description": b.get("booking_proposal", {}).get("description", ""),
                        "account": b.get("booking_proposal", {}).get("debit_account", ""),
                        "similarity": b.get("similarity_score", 0),
                    }
                    for b in similar_bookings[:3]
                ],
                "is_rag_suggestion": True,
                "rag_confidence": suggestion["confidence"],
            }

        except Exception as e:
            logger.error(
                "rag_fallback.error",
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    def _build_context_prompt(
        self,
        invoice_data: dict[str, Any],
        unmatched_item: dict[str, Any],
        similar_bookings: list[dict[str, Any]],
        chart: str,
    ) -> str:
        """Build the prompt with context for LLM."""
        supplier = invoice_data.get("supplier_name", "Unbekannt")
        description = unmatched_item.get("description", "")
        net_amount = unmatched_item.get("net_amount", 0)
        vat_rate = unmatched_item.get("vat_rate", 0.19)

        prompt = f"""Rechnungsposition zur Kontierung:

Lieferant: {supplier}
Beschreibung: {description}
Nettobetrag: {net_amount} EUR
MwSt-Satz: {vat_rate * 100}%
Kontenrahmen: {chart}
"""

        if similar_bookings:
            prompt += "\nÄhnliche historische Buchungen:\n"
            for i, booking in enumerate(similar_bookings[:3], 1):
                hist_supplier = booking.get("invoice_data", {}).get("supplier_name", "")
                hist_desc = booking.get("booking_proposal", {}).get("description", "")
                hist_account = booking.get("booking_proposal", {}).get("debit_account", "")
                hist_name = booking.get("booking_proposal", {}).get("debit_account_name", "")
                similarity = booking.get("similarity_score", 0)

                prompt += f"""
{i}. Lieferant: {hist_supplier}
   Beschreibung: {hist_desc}
   Konto: {hist_account} ({hist_name})
   Ähnlichkeit: {similarity:.0%}
"""

        prompt += "\nBitte schlage ein passendes Sachkonto vor."

        return prompt

    def _fallback_from_history(
        self,
        similar_bookings: list[dict[str, Any]],
        item_description: str,
        net_amount: float,
    ) -> dict[str, Any]:
        """Generate suggestion from history only (no LLM)."""
        if not similar_bookings:
            # No history, return generic suggestion
            return {
                "success": True,
                "suggestion": {
                    "debit_account": "4900",
                    "debit_account_name": "Sonstige betriebliche Aufwendungen",
                    "confidence": 0.3,
                    "reasoning": "Keine ähnlichen Buchungen gefunden, generisches Konto vorgeschlagen",
                    "legal_basis": "§4 Abs. 4 EStG",
                    "alternative_accounts": [],
                },
                "similar_bookings": [],
                "is_rag_suggestion": True,
                "rag_confidence": 0.3,
            }

        # Use most similar booking
        best = similar_bookings[0]
        proposal = best.get("booking_proposal", {})
        similarity = best.get("similarity_score", 0.5)

        suggestion = {
            "debit_account": proposal.get("debit_account", "4900"),
            "debit_account_name": proposal.get("debit_account_name", ""),
            "confidence": min(0.7, similarity),  # Cap at 0.7 without LLM
            "reasoning": f"Basierend auf ähnlicher Buchung ({similarity:.0%} Ähnlichkeit)",
            "legal_basis": proposal.get("legal_basis", ""),
            "alternative_accounts": [],
        }

        return {
            "success": True,
            "suggestion": suggestion,
            "similar_bookings": [
                {
                    "supplier": b.get("invoice_data", {}).get("supplier_name", ""),
                    "description": b.get("booking_proposal", {}).get("description", ""),
                    "account": b.get("booking_proposal", {}).get("debit_account", ""),
                    "similarity": b.get("similarity_score", 0),
                }
                for b in similar_bookings[:3]
            ],
            "is_rag_suggestion": True,
            "rag_confidence": suggestion["confidence"],
        }

    def set_booking_history(self, booking_history: Any) -> None:
        """Set or update the booking history service."""
        self._booking_history = booking_history

    def set_llm_provider(self, llm_provider: Any) -> None:
        """Set or update the LLM provider."""
        self._llm_provider = llm_provider
