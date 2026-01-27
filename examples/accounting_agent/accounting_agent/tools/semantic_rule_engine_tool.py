"""
Semantic Rule Engine Tool

Extends rule-based account assignment with semantic similarity matching
using embeddings. Implements the hybrid workflow from the PRD:

1. Vendor-Only Rules (exact match) - Priority 1
2. Vendor + Item-Semantics (embedding comparison) - Priority 2
3. Ambiguity detection for multiple matches

This tool is deterministic and does NOT use LLMs for decisions.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
import structlog

from accounting_agent.domain.models import (
    AccountingRule,
    RuleType,
    RuleSource,
    RuleMatch,
    MatchType,
)
from accounting_agent.tools.tool_base import ApprovalRiskLevel

logger = structlog.get_logger(__name__)


class SemanticRuleEngineTool:
    """
    Semantic rule engine for account assignment (Kontierung).

    Combines deterministic rule matching with semantic similarity:
    - Vendor-Only rules: Direct vendor → account mapping
    - Vendor + Item rules: Vendor match + item embedding similarity

    No LLM involvement - embeddings are used for similarity only.
    """

    def __init__(
        self,
        rules_path: str = "configs/accounting/rules/",
        embedding_service: Optional[Any] = None,
    ):
        """
        Initialize SemanticRuleEngineTool.

        Args:
            rules_path: Path to directory containing rule YAML files
            embedding_service: EmbeddingProviderProtocol implementation
        """
        self._rules_path = Path(rules_path)
        self._embedding_service = embedding_service
        self._rules: list[AccountingRule] = []
        self._item_pattern_embeddings: dict[str, list[float]] = {}
        self._rules_loaded = False
        self._raw_rules: dict[str, Any] = {}

    async def _load_rules(self) -> None:
        """Load rules from YAML files and precompute embeddings."""
        if self._rules_loaded:
            return

        self._rules = []
        self._raw_rules = {}

        if not self._rules_path.exists():
            logger.warning(
                "semantic_rule_engine.rules_path_not_found",
                path=str(self._rules_path),
            )
            return

        # Load all YAML rule files
        for yaml_file in self._rules_path.glob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                    if content:
                        self._raw_rules[yaml_file.stem] = content
            except yaml.YAMLError as e:
                logger.error(
                    "semantic_rule_engine.yaml_error",
                    file=str(yaml_file),
                    error=str(e),
                )
                continue

        # Parse vendor_rules (Regeltyp A - Vendor-Only)
        kontierung_rules = self._raw_rules.get("kontierung_rules", {})
        for vendor_rule in kontierung_rules.get("vendor_rules", []):
            source = self._parse_rule_source(vendor_rule.get("source", "manual"))
            rule = AccountingRule(
                rule_id=vendor_rule.get("rule_id", f"VR-{len(self._rules)}"),
                rule_type=RuleType.VENDOR_ONLY,
                vendor_pattern=vendor_rule.get("vendor_pattern", ""),
                target_account=vendor_rule.get("target_account", ""),
                target_account_name=vendor_rule.get("target_account_name"),
                priority=vendor_rule.get("priority", 100),
                source=source,
                legal_basis=vendor_rule.get("legal_basis"),
                is_active=vendor_rule.get("is_active", True),
            )
            if rule.is_active:
                self._rules.append(rule)

        # Parse semantic_rules (Regeltyp B - Vendor + Item-Semantik)
        for semantic_rule in kontierung_rules.get("semantic_rules", []):
            source = self._parse_rule_source(semantic_rule.get("source", "manual"))
            rule = AccountingRule(
                rule_id=semantic_rule.get("rule_id", f"SR-{len(self._rules)}"),
                rule_type=RuleType.VENDOR_ITEM,
                vendor_pattern=semantic_rule.get("vendor_pattern", ""),
                item_patterns=semantic_rule.get("item_patterns", []),
                target_account=semantic_rule.get("target_account", ""),
                target_account_name=semantic_rule.get("target_account_name"),
                priority=semantic_rule.get("priority", 50),
                similarity_threshold=semantic_rule.get("similarity_threshold", 0.8),
                source=source,
                legal_basis=semantic_rule.get("legal_basis"),
                is_active=semantic_rule.get("is_active", True),
            )
            if rule.is_active:
                self._rules.append(rule)

        # Also parse legacy expense_categories format for backward compatibility
        expense_categories = kontierung_rules.get("expense_categories", {})
        for category_name, category_config in expense_categories.items():
            # Convert to semantic rule format
            keywords = category_config.get("keywords", [])
            if not keywords:
                continue

            # Check for conditional rules (GWG thresholds etc.)
            conditions = category_config.get("conditions", [])
            if conditions:
                # Create conditional rules (handled separately during matching)
                for i, condition in enumerate(conditions):
                    rule = AccountingRule(
                        rule_id=f"LEGACY-{category_name}-{i}",
                        rule_type=RuleType.VENDOR_ITEM,
                        vendor_pattern=".*",  # Match any vendor
                        item_patterns=keywords,
                        target_account=condition.get("debit_account", ""),
                        target_account_name=condition.get("debit_name", category_name),
                        priority=10,  # Lower priority than explicit rules
                        similarity_threshold=0.75,
                        source=RuleSource.MANUAL,
                        legal_basis=condition.get("legal_basis"),
                        is_active=True,
                    )
                    # Store condition info in a custom attribute via version field
                    rule.version = i + 1  # Use version to track condition index
                    self._rules.append(rule)
            else:
                # Simple rule without conditions
                rule = AccountingRule(
                    rule_id=f"LEGACY-{category_name}",
                    rule_type=RuleType.VENDOR_ITEM,
                    vendor_pattern=".*",  # Match any vendor
                    item_patterns=keywords,
                    target_account=category_config.get("debit_account", ""),
                    target_account_name=category_config.get("debit_name", category_name),
                    priority=10,
                    similarity_threshold=0.75,
                    source=RuleSource.MANUAL,
                    legal_basis=category_config.get("legal_basis"),
                    is_active=True,
                )
                self._rules.append(rule)

        # Sort rules by priority (highest first)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

        # Precompute embeddings for item patterns if embedding service available
        if self._embedding_service:
            await self._precompute_embeddings()

        self._rules_loaded = True
        logger.info(
            "semantic_rule_engine.rules_loaded",
            total_rules=len(self._rules),
            vendor_only=len([r for r in self._rules if r.rule_type == RuleType.VENDOR_ONLY]),
            vendor_item=len([r for r in self._rules if r.rule_type == RuleType.VENDOR_ITEM]),
        )

    async def _precompute_embeddings(self) -> None:
        """Precompute embeddings for all item patterns."""
        if not self._embedding_service:
            return

        all_patterns = set()
        for rule in self._rules:
            if rule.rule_type == RuleType.VENDOR_ITEM:
                all_patterns.update(rule.item_patterns)

        if not all_patterns:
            return

        pattern_list = list(all_patterns)
        try:
            embeddings = await self._embedding_service.embed_batch(pattern_list)
            for pattern, embedding in zip(pattern_list, embeddings):
                self._item_pattern_embeddings[pattern] = embedding

            logger.info(
                "semantic_rule_engine.embeddings_computed",
                pattern_count=len(pattern_list),
            )
        except Exception as e:
            logger.error(
                "semantic_rule_engine.embedding_error",
                error=str(e),
            )

    @property
    def name(self) -> str:
        """Return tool name."""
        return "semantic_rule_engine"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Apply semantic accounting rules to invoice data. "
            "Uses embedding-based similarity matching for intelligent account assignment. "
            "Deterministic rules first (vendor-only), then semantic matching (vendor + item). "
            "Returns RuleMatch with similarity score and confidence signals. "
            "No LLM involved - purely rule and embedding based."
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
                        "Structured invoice data with supplier_name and line_items array. "
                        "Each line_item should have: description, net_amount, vat_rate"
                    ),
                },
                "chart_of_accounts": {
                    "type": "string",
                    "description": "Account chart to use (default: SKR03)",
                    "enum": ["SKR03", "SKR04"],
                    "default": "SKR03",
                },
            },
            "required": ["invoice_data"],
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
        supplier = invoice_data.get("supplier_name", "Unknown")
        line_count = len(invoice_data.get("line_items", []))
        return (
            f"Tool: {self.name}\n"
            f"Operation: Semantic rule matching\n"
            f"Supplier: {supplier}\n"
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
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Apply semantic rules and return booking proposals with match details.

        Args:
            invoice_data: Invoice data with supplier_name and line_items
            chart_of_accounts: SKR03 or SKR04

        Returns:
            Dictionary with:
            - success: bool
            - rule_matches: List of RuleMatch results
            - booking_proposals: List of booking proposals
            - unmatched_items: Items without rule match
            - ambiguous_items: Items with ambiguous matches
        """
        try:
            # Ensure rules are loaded
            await self._load_rules()

            supplier_name = invoice_data.get("supplier_name", "")
            line_items = invoice_data.get("line_items", [])

            # If no line items, try to create one from invoice totals
            if not line_items and invoice_data.get("total_net"):
                line_items = [
                    {
                        "description": invoice_data.get("description", "Rechnung"),
                        "net_amount": invoice_data.get("total_net"),
                        "vat_rate": invoice_data.get("vat_rate", 0.19),
                        "vat_amount": invoice_data.get("total_vat", 0),
                    }
                ]

            rule_matches: list[dict[str, Any]] = []
            booking_proposals: list[dict[str, Any]] = []
            unmatched_items: list[dict[str, Any]] = []
            ambiguous_items: list[dict[str, Any]] = []

            for idx, line_item in enumerate(line_items):
                match_result = await self._match_item(
                    supplier_name=supplier_name,
                    line_item=line_item,
                    chart=chart_of_accounts,
                )

                if match_result is None:
                    unmatched_items.append(
                        {
                            "index": idx,
                            "description": line_item.get("description", ""),
                            "reason": "No matching rule found",
                        }
                    )
                elif match_result.is_ambiguous:
                    ambiguous_items.append(
                        {
                            "index": idx,
                            "description": line_item.get("description", ""),
                            "matches": [
                                {
                                    "rule_id": match_result.rule.rule_id,
                                    "account": match_result.rule.target_account,
                                    "similarity": match_result.similarity_score,
                                }
                            ]
                            + [
                                {
                                    "rule_id": alt.rule.rule_id,
                                    "account": alt.rule.target_account,
                                    "similarity": alt.similarity_score,
                                }
                                for alt in match_result.alternative_matches
                            ],
                        }
                    )
                else:
                    # Create booking proposal from match
                    proposal = self._create_proposal(
                        match_result=match_result,
                        line_item=line_item,
                        chart=chart_of_accounts,
                        idx=idx,
                    )
                    rule_matches.append(
                        {
                            "line_item_index": idx,
                            "rule_id": match_result.rule.rule_id,
                            "rule_type": match_result.rule.rule_type.value,
                            "match_type": match_result.match_type.value,
                            "similarity_score": match_result.similarity_score,
                            "matched_pattern": match_result.matched_item_pattern,
                        }
                    )
                    booking_proposals.append(proposal)

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
                    "legal_basis": "§266 Abs. 3 C.4 HGB",
                }
                booking_proposals.append(credit_proposal)

            return {
                "success": True,
                "rule_matches": rule_matches,
                "booking_proposals": booking_proposals,
                "chart_of_accounts": chart_of_accounts,
                "rules_applied": len(rule_matches),
                "unmatched_items": unmatched_items,
                "ambiguous_items": ambiguous_items,
                "total_rules_loaded": len(self._rules),
            }

        except Exception as e:
            logger.error(
                "semantic_rule_engine.execution_error",
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def _match_item(
        self,
        supplier_name: str,
        line_item: dict[str, Any],
        chart: str,
    ) -> Optional[RuleMatch]:
        """
        Match a single line item against all rules.

        Evaluation order:
        1. Vendor-Only rules (exact match) - sorted by priority
        2. Vendor + Item-Semantics rules - sorted by priority

        Args:
            supplier_name: Invoice supplier name
            line_item: Line item data
            chart: Chart of accounts

        Returns:
            RuleMatch or None if no match
        """
        description = str(line_item.get("description", ""))
        description_lower = description.lower()

        matches: list[RuleMatch] = []

        # Pre-compute description embedding once (optimization)
        desc_embedding: Optional[list[float]] = None
        if self._embedding_service and self._item_pattern_embeddings:
            try:
                desc_embedding = await self._embedding_service.embed_text(description)
            except Exception as e:
                logger.warning(
                    "semantic_rule_engine.desc_embedding_error",
                    error=str(e),
                    description=description[:50],
                )

        # Phase 1: Check Vendor-Only rules
        for rule in self._rules:
            if rule.rule_type != RuleType.VENDOR_ONLY:
                continue

            if self._matches_vendor_pattern(supplier_name, rule.vendor_pattern):
                match = RuleMatch(
                    rule=rule,
                    match_type=MatchType.EXACT,
                    similarity_score=1.0,
                )
                matches.append(match)
                logger.debug(
                    "semantic_rule_engine.vendor_match",
                    rule_id=rule.rule_id,
                    vendor=supplier_name,
                )

        # Phase 2: Check Vendor + Item-Semantics rules
        for rule in self._rules:
            if rule.rule_type != RuleType.VENDOR_ITEM:
                continue

            # Check vendor pattern (can be regex or exact)
            if not self._matches_vendor_pattern(supplier_name, rule.vendor_pattern):
                continue

            # Check item patterns
            best_pattern = None
            best_similarity = 0.0
            match_type = MatchType.EXACT

            for pattern in rule.item_patterns:
                # First try exact/keyword match
                if pattern.lower() in description_lower:
                    if 1.0 > best_similarity:
                        best_similarity = 1.0
                        best_pattern = pattern
                        match_type = MatchType.EXACT
                    continue

                # Try semantic matching if embedding available
                if desc_embedding and pattern in self._item_pattern_embeddings:
                    pattern_embedding = self._item_pattern_embeddings[pattern]
                    similarity = self._embedding_service.cosine_similarity(
                        desc_embedding, pattern_embedding
                    )

                    if similarity >= rule.similarity_threshold and similarity > best_similarity:
                        best_similarity = similarity
                        best_pattern = pattern
                        match_type = MatchType.SEMANTIC

            if best_pattern and best_similarity >= rule.similarity_threshold:
                match = RuleMatch(
                    rule=rule,
                    match_type=match_type,
                    similarity_score=best_similarity,
                    matched_item_pattern=best_pattern,
                )
                matches.append(match)
                logger.debug(
                    "semantic_rule_engine.item_match",
                    rule_id=rule.rule_id,
                    pattern=best_pattern,
                    similarity=best_similarity,
                    match_type=match_type.value,
                )

        if not matches:
            return None

        # Sort matches by: priority (desc), then similarity (desc)
        matches.sort(
            key=lambda m: (m.rule.priority, m.similarity_score),
            reverse=True,
        )

        # Check for ambiguity (multiple high-scoring matches)
        best_match = matches[0]
        if len(matches) > 1:
            # Consider ambiguous if second-best is within 0.05 similarity
            # and targets a different account
            second_match = matches[1]
            similarity_diff = best_match.similarity_score - second_match.similarity_score
            different_account = best_match.rule.target_account != second_match.rule.target_account

            if similarity_diff < 0.05 and different_account:
                best_match.is_ambiguous = True
                best_match.alternative_matches = matches[1:3]  # Include top alternatives
                logger.info(
                    "semantic_rule_engine.ambiguous_match",
                    best_rule=best_match.rule.rule_id,
                    alternatives=[m.rule.rule_id for m in matches[1:3]],
                )

        return best_match

    def _matches_vendor_pattern(self, vendor_name: str, pattern: str) -> bool:
        """Check if vendor name matches pattern (regex or exact)."""
        if not pattern or not vendor_name:
            return False

        # Treat as regex if contains regex metacharacters
        if any(c in pattern for c in ".*+?[](){}|^$\\"):
            try:
                return bool(re.search(pattern, vendor_name, re.IGNORECASE))
            except re.error:
                return False
        else:
            # Exact match (case-insensitive)
            return pattern.lower() in vendor_name.lower()

    def _parse_rule_source(self, source_str: str) -> RuleSource:
        """Parse rule source string with fallback to MANUAL."""
        try:
            return RuleSource(source_str)
        except ValueError:
            logger.warning(
                "semantic_rule_engine.invalid_source",
                source=source_str,
                fallback="manual",
            )
            return RuleSource.MANUAL

    def _get_skr04_account(self, skr03_account: str) -> str:
        """Convert SKR03 account to SKR04 using mapping."""
        kontierung_rules = self._raw_rules.get("kontierung_rules", {})
        mapping = kontierung_rules.get("skr04_mapping", {})
        return mapping.get(skr03_account, skr03_account)

    def _create_proposal(
        self,
        match_result: RuleMatch,
        line_item: dict[str, Any],
        chart: str,
        idx: int,
    ) -> dict[str, Any]:
        """Create booking proposal from rule match."""
        rule = match_result.rule
        net_amount = float(line_item.get("net_amount", 0))
        vat_rate = float(line_item.get("vat_rate", 0.19))
        vat_amount = float(line_item.get("vat_amount", net_amount * vat_rate))

        # Get VAT account from raw rules
        kontierung_rules = self._raw_rules.get("kontierung_rules", {})
        vat_rules = kontierung_rules.get("vat_rules", {})
        standard_vat = vat_rules.get("standard_rate", {})
        vat_account = standard_vat.get("input_tax_account", "1576")

        # Get debit account (apply SKR04 mapping if needed)
        debit_account = rule.target_account
        if chart == "SKR04":
            debit_account = self._get_skr04_account(debit_account)
            vat_account = self._get_skr04_account(vat_account)

        return {
            "type": "debit",
            "line_item_index": idx,
            "debit_account": debit_account,
            "debit_account_name": rule.target_account_name or debit_account,
            "amount": net_amount,
            "vat_account": vat_account,
            "vat_amount": vat_amount,
            "description": line_item.get("description", ""),
            "legal_basis": rule.legal_basis or "",
            "explanation": f"Matched rule: {rule.rule_id} ({match_result.match_type.value})",
            "rule_id": rule.rule_id,
            "match_type": match_result.match_type.value,
            "similarity_score": match_result.similarity_score,
            "confidence": match_result.similarity_score,  # Use similarity as initial confidence
        }

    def set_embedding_service(self, embedding_service: Any) -> None:
        """
        Set or update the embedding service.

        Call this after initialization to enable semantic matching.

        Args:
            embedding_service: EmbeddingProviderProtocol implementation
        """
        self._embedding_service = embedding_service
        self._rules_loaded = False  # Force reload to compute embeddings
        self._item_pattern_embeddings.clear()
