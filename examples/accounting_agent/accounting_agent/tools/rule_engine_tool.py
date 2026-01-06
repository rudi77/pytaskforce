"""
YAML-based rule engine for deterministic Kontierung.

This tool applies accounting rules from YAML configuration files
to determine account assignments (Kontierung) for invoice line items.
"""

from pathlib import Path
from typing import Any

import yaml

from accounting_agent.tools.tool_base import ApprovalRiskLevel


class RuleEngineTool:
    """
    Apply accounting rules for account assignment (Kontierung).

    Uses YAML-based rule definitions for deterministic account assignments
    based on invoice characteristics. No LLM required - purely rule-driven.

    Rule matching is based on:
    - Keywords in item descriptions
    - Amount thresholds (GWG vs. Anlage)
    - VAT conditions
    - Supplier characteristics
    """

    def __init__(self, rules_path: str = "configs/accounting/rules/"):
        """
        Initialize RuleEngineTool with rules directory.

        Args:
            rules_path: Path to directory containing rule YAML files
        """
        self._rules_path = Path(rules_path)
        self._rules: dict[str, Any] = {}
        self._load_rules()

    def _load_rules(self) -> None:
        """Load all YAML rule files from rules directory."""
        if not self._rules_path.exists():
            return

        for yaml_file in self._rules_path.glob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                    if content:
                        self._rules[yaml_file.stem] = content
            except yaml.YAMLError:
                # Skip malformed YAML files
                continue

    @property
    def name(self) -> str:
        """Return tool name."""
        return "apply_kontierung_rules"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Apply deterministic Kontierung rules to invoice data. "
            "Returns booking proposal with debit/credit accounts based on "
            "SKR03 or SKR04 chart of accounts. Rule-based, no LLM involved. "
            "Use this tool BEFORE asking the LLM for account suggestions."
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
                        "Structured invoice data with line_items array. "
                        "Each line_item should have: description, net_amount, vat_rate"
                    )
                },
                "chart_of_accounts": {
                    "type": "string",
                    "description": "Account chart to use (default: SKR03)",
                    "enum": ["SKR03", "SKR04"],
                    "default": "SKR03"
                }
            },
            "required": ["invoice_data"]
        }

    @property
    def requires_approval(self) -> bool:
        """Read-only, returns proposals only."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Low risk - only generates proposals."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        chart = kwargs.get("chart_of_accounts", "SKR03")
        invoice_data = kwargs.get("invoice_data", {})
        line_count = len(invoice_data.get("line_items", []))
        return (
            f"Tool: {self.name}\n"
            f"Operation: Apply Kontierung rules\n"
            f"Chart of Accounts: {chart}\n"
            f"Line Items to process: {line_count}"
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "invoice_data" not in kwargs:
            return False, "Missing required parameter: invoice_data"
        if not isinstance(kwargs["invoice_data"], dict):
            return False, "invoice_data must be a dictionary"

        chart = kwargs.get("chart_of_accounts", "SKR03")
        if chart not in ["SKR03", "SKR04"]:
            return False, f"Invalid chart_of_accounts: {chart}. Must be SKR03 or SKR04"

        return True, None

    async def execute(
        self,
        invoice_data: dict[str, Any],
        chart_of_accounts: str = "SKR03",
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Apply rules and return booking proposals.

        Args:
            invoice_data: Invoice data with line_items
            chart_of_accounts: SKR03 or SKR04

        Returns:
            Dictionary with:
            - success: bool
            - booking_proposals: List of booking proposals
            - chart_of_accounts: Used chart
            - rules_applied: Number of rules matched
            - unmatched_items: Items without rule match
        """
        try:
            booking_proposals = []
            unmatched_items = []
            rules_applied = 0

            line_items = invoice_data.get("line_items", [])

            # If no line items, try to create one from invoice totals
            if not line_items and invoice_data.get("total_net"):
                line_items = [{
                    "description": invoice_data.get("description", "Rechnung"),
                    "net_amount": invoice_data.get("total_net"),
                    "vat_rate": invoice_data.get("vat_rate", 0.19),
                    "vat_amount": invoice_data.get("total_vat", 0)
                }]

            for idx, line_item in enumerate(line_items):
                proposal = self._match_rules(line_item, chart_of_accounts)
                if proposal:
                    proposal["line_item_index"] = idx
                    booking_proposals.append(proposal)
                    rules_applied += 1
                else:
                    unmatched_items.append({
                        "index": idx,
                        "description": line_item.get("description", ""),
                        "reason": "No matching rule found"
                    })

            # Add credit account (Verbindlichkeiten)
            total_gross = sum(
                float(p.get("amount", 0)) + float(p.get("vat_amount", 0))
                for p in booking_proposals
            )

            if booking_proposals:
                credit_proposal = {
                    "type": "credit",
                    "credit_account": "1600" if chart_of_accounts == "SKR03" else "3300",
                    "credit_account_name": "Verbindlichkeiten aus Lieferungen und Leistungen",
                    "amount": total_gross,
                    "legal_basis": "§266 Abs. 3 C.4 HGB"
                }
                booking_proposals.append(credit_proposal)

            return {
                "success": True,
                "booking_proposals": booking_proposals,
                "chart_of_accounts": chart_of_accounts,
                "rules_applied": rules_applied,
                "unmatched_items": unmatched_items,
                "rules_loaded": list(self._rules.keys())
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }

    def _match_rules(
        self,
        line_item: dict[str, Any],
        chart: str
    ) -> dict[str, Any] | None:
        """
        Match line item against loaded rules.

        Args:
            line_item: Single line item data
            chart: Chart of accounts (SKR03/SKR04)

        Returns:
            Booking proposal dict or None if no match
        """
        description = str(line_item.get("description", "")).lower()
        net_amount = float(line_item.get("net_amount", 0))
        vat_rate = float(line_item.get("vat_rate", 0.19))

        # Load kontierung rules
        kontierung_rules = self._rules.get("kontierung_rules", {})
        expense_categories = kontierung_rules.get("expense_categories", {})

        # Try to match against expense categories
        for category_name, category_config in expense_categories.items():
            keywords = category_config.get("keywords", [])

            # Check if any keyword matches
            for keyword in keywords:
                if keyword.lower() in description:
                    # Found a match - determine account based on conditions
                    conditions = category_config.get("conditions", [])

                    if conditions:
                        # Check amount-based conditions
                        for condition in conditions:
                            if "if_amount_below" in condition:
                                if net_amount < condition["if_amount_below"]:
                                    return self._create_proposal(
                                        condition, category_name, line_item, chart, vat_rate
                                    )
                            elif "if_amount_above" in condition:
                                if net_amount >= condition["if_amount_above"]:
                                    return self._create_proposal(
                                        condition, category_name, line_item, chart, vat_rate
                                    )
                    else:
                        # No conditions - use default account
                        return self._create_proposal(
                            category_config, category_name, line_item, chart, vat_rate
                        )

        # No rule matched - return None (will be added to unmatched_items)
        return None

    def _create_proposal(
        self,
        rule_config: dict[str, Any],
        category_name: str,
        line_item: dict[str, Any],
        chart: str,
        vat_rate: float
    ) -> dict[str, Any]:
        """Create a booking proposal from matched rule."""
        net_amount = float(line_item.get("net_amount", 0))
        vat_amount = float(line_item.get("vat_amount", net_amount * vat_rate))

        # Get VAT account from rules
        kontierung_rules = self._rules.get("kontierung_rules", {})
        vat_rules = kontierung_rules.get("vat_rules", {})
        standard_vat = vat_rules.get("standard_rate", {})
        vat_account = standard_vat.get("input_tax_account", "1576")

        return {
            "type": "debit",
            "debit_account": rule_config.get("debit_account"),
            "debit_account_name": rule_config.get("debit_name", category_name),
            "amount": net_amount,
            "vat_account": vat_account,
            "vat_amount": vat_amount,
            "description": line_item.get("description", ""),
            "legal_basis": rule_config.get("legal_basis", ""),
            "explanation": f"Matched category: {category_name}",
            "afa_years": rule_config.get("afa_years")
        }
