"""
Semantic Rule Engine Tool

Extends rule-based account assignment with semantic similarity matching
using embeddings. Implements the hybrid workflow from the PRD:

1. Vendor-Only Rules (exact match) - Priority 1
2. Vendor + Item-Semantics (embedding comparison) - Priority 2
3. Ambiguity detection for multiple matches

This tool is deterministic and does NOT use LLMs for decisions.
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiofiles
import yaml
import structlog

from accounting_agent.domain.models import (
    AccountingRule,
    RuleType,
    RuleSource,
    RuleMatch,
    MatchType,
    VendorAccountProfile,
)
from accounting_agent.domain.invoice_utils import (
    extract_supplier_name,
    extract_line_items,
    extract_description,
    extract_net_amount,
    extract_vat_rate,
    extract_vat_amount,
)
from accounting_agent.tools.tool_base import ApprovalRiskLevel

logger = structlog.get_logger(__name__)


class SemanticRuleEngineTool:
    """
    Semantic rule engine for account assignment (Kontierung).

    Combines deterministic rule matching with semantic similarity:
    - Vendor-Only rules: Direct vendor → account mapping
    - Vendor + Item rules: Vendor match + item embedding similarity
    - Vendor Generalization: Infer account from vendor's dominant booking pattern

    No LLM involvement - embeddings are used for similarity only.
    """

    # Vendor generalization configuration
    MIN_RULES_FOR_GENERALIZATION = 3
    MIN_DOMINANCE_RATIO = 0.6
    VENDOR_GENERALIZATION_BASE_SCORE = 0.85
    VENDOR_GENERALIZATION_PRIORITY = 60

    def __init__(
        self,
        rules_path: Optional[str] = None,
        embedding_service: Optional[Any] = None,
    ):
        """
        Initialize SemanticRuleEngineTool.

        Args:
            rules_path: Path to directory containing rule YAML files.
                        If None, auto-detects based on module location.
            embedding_service: EmbeddingProviderProtocol implementation
        """
        # Auto-detect rules path relative to this module if not provided
        if rules_path is None:
            module_dir = Path(__file__).parent.parent.parent  # accounting_agent dir
            rules_path = str(module_dir / "configs" / "accounting" / "rules")

        self._rules_path = Path(rules_path)
        self._embedding_service = embedding_service
        self._rules: list[AccountingRule] = []
        self._item_pattern_embeddings: dict[str, list[float]] = {}
        self._rules_loaded = False
        self._raw_rules: dict[str, Any] = {}
        self._learned_rules_mtime: float = 0.0  # Track file modification time
        self._vendor_profiles: dict[str, VendorAccountProfile] = {}

    async def _load_rules(self) -> None:
        """Load rules from YAML files and precompute embeddings."""
        # Always reload learned rules (they change dynamically)
        # But cache static kontierung_rules (they don't change)
        await self._reload_learned_rules_if_changed()

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

        # Load all YAML rule files from rules directory (static rules)
        for yaml_file in self._rules_path.glob("*.yaml"):
            await self._load_single_yaml_file(yaml_file)

        # Also load learned_rules.yaml from persistence directory (auto-generated rules)
        await self._load_learned_rules()

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

        # Parse learned_rules (auto-generated from high-confidence bookings and HITL)
        learned_rules = self._raw_rules.get("learned_rules", {})
        for vendor_rule in learned_rules.get("vendor_rules", []):
            if not vendor_rule.get("is_active", True):
                continue
            source = self._parse_rule_source(vendor_rule.get("source", "auto_high_confidence"))
            rule = AccountingRule(
                rule_id=vendor_rule.get("rule_id", f"LEARNED-VR-{len(self._rules)}"),
                rule_type=RuleType.VENDOR_ONLY,
                vendor_pattern=vendor_rule.get("vendor_pattern", ""),
                target_account=vendor_rule.get("target_account", ""),
                target_account_name=vendor_rule.get("target_account_name"),
                priority=vendor_rule.get("priority", 75),  # Between manual (100) and legacy (10)
                source=source,
                legal_basis=vendor_rule.get("legal_basis"),
                is_active=True,
            )
            self._rules.append(rule)

        for semantic_rule in learned_rules.get("semantic_rules", []):
            if not semantic_rule.get("is_active", True):
                continue
            source = self._parse_rule_source(semantic_rule.get("source", "auto_high_confidence"))
            rule = AccountingRule(
                rule_id=semantic_rule.get("rule_id", f"LEARNED-SR-{len(self._rules)}"),
                rule_type=RuleType.VENDOR_ITEM,
                vendor_pattern=semantic_rule.get("vendor_pattern", ""),
                item_patterns=semantic_rule.get("item_patterns", []),
                target_account=semantic_rule.get("target_account", ""),
                target_account_name=semantic_rule.get("target_account_name"),
                priority=semantic_rule.get("priority", 75),
                similarity_threshold=semantic_rule.get("similarity_threshold", 0.8),
                source=source,
                legal_basis=semantic_rule.get("legal_basis"),
                is_active=True,
            )
            self._rules.append(rule)

        logger.info(
            "semantic_rule_engine.learned_rules_parsed",
            vendor_rules=len(learned_rules.get("vendor_rules", [])),
            semantic_rules=len(learned_rules.get("semantic_rules", [])),
        )

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

        # Build vendor account profiles for generalization
        self._build_vendor_account_profiles()

        self._rules_loaded = True
        logger.info(
            "semantic_rule_engine.rules_loaded",
            total_rules=len(self._rules),
            vendor_only=len([r for r in self._rules if r.rule_type == RuleType.VENDOR_ONLY]),
            vendor_item=len([r for r in self._rules if r.rule_type == RuleType.VENDOR_ITEM]),
        )

    async def _load_single_yaml_file(self, yaml_file: Path) -> None:
        """Load a single YAML file asynchronously."""
        try:
            async with aiofiles.open(yaml_file, encoding="utf-8") as f:
                content_str = await f.read()
                content = yaml.safe_load(content_str)
                if content:
                    self._raw_rules[yaml_file.stem] = content
        except yaml.YAMLError as e:
            logger.error(
                "semantic_rule_engine.yaml_error",
                file=str(yaml_file),
                error=str(e),
            )
        except OSError as e:
            logger.error(
                "semantic_rule_engine.file_read_error",
                file=str(yaml_file),
                error=str(e),
            )

    def _get_learned_rules_paths(self) -> list[Path]:
        """Get list of possible paths for learned_rules.yaml."""
        cwd = Path(os.getcwd())
        paths = [
            self._rules_path / "learned_rules.yaml",  # In rules dir
            Path(".taskforce_accounting/learned_rules.yaml"),  # Relative work dir
            cwd / ".taskforce_accounting" / "learned_rules.yaml",  # Absolute from cwd
        ]
        # Remove duplicates while preserving order
        seen = set()
        unique_paths = []
        for p in paths:
            resolved = str(p.resolve())
            if resolved not in seen:
                seen.add(resolved)
                unique_paths.append(p)
        return unique_paths

    async def _reload_learned_rules_if_changed(self) -> None:
        """Check if learned_rules.yaml changed and force reload if needed."""
        learned_rules_paths = self._get_learned_rules_paths()

        for learned_path in learned_rules_paths:
            if learned_path.exists():
                try:
                    current_mtime = learned_path.stat().st_mtime
                    if current_mtime > self._learned_rules_mtime:
                        logger.info(
                            "semantic_rule_engine.learned_rules_changed",
                            path=str(learned_path),
                            old_mtime=self._learned_rules_mtime,
                            new_mtime=current_mtime,
                        )
                        # Force full reload
                        self._rules_loaded = False
                        self._learned_rules_mtime = current_mtime
                        return
                except OSError:
                    pass

        # Log if no learned rules found
        logger.debug(
            "semantic_rule_engine.no_learned_rules_file",
            checked_paths=[str(p) for p in learned_rules_paths],
        )
        return

    async def _load_learned_rules(self) -> None:
        """Load learned rules from persistence directory asynchronously."""
        learned_rules_paths = self._get_learned_rules_paths()

        logger.info(
            "semantic_rule_engine.searching_learned_rules",
            paths=[str(p) for p in learned_rules_paths],
        )

        for learned_path in learned_rules_paths:
            exists = learned_path.exists()
            logger.debug(
                "semantic_rule_engine.checking_path",
                path=str(learned_path),
                exists=exists,
            )
            if exists:
                try:
                    # Track modification time
                    self._learned_rules_mtime = learned_path.stat().st_mtime

                    async with aiofiles.open(learned_path, encoding="utf-8") as f:
                        content_str = await f.read()
                        content = yaml.safe_load(content_str)
                        if content:
                            self._raw_rules["learned_rules"] = content
                            semantic_rules = content.get("semantic_rules", [])
                            logger.info(
                                "semantic_rule_engine.learned_rules_loaded",
                                path=str(learned_path),
                                rules_count=len(semantic_rules),
                                rule_ids=[r.get("rule_id", "?") for r in semantic_rules[:5]],
                            )
                            return  # Use first found
                except yaml.YAMLError as e:
                    logger.warning(
                        "semantic_rule_engine.learned_rules_error",
                        path=str(learned_path),
                        error=str(e),
                    )
                except OSError as e:
                    logger.warning(
                        "semantic_rule_engine.learned_rules_file_error",
                        path=str(learned_path),
                        error=str(e),
                    )

        logger.warning(
            "semantic_rule_engine.no_learned_rules_found",
            checked_paths=[str(p) for p in learned_rules_paths],
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
            # Log incoming invoice_data for debugging
            logger.info(
                "semantic_rule_engine.execute_start",
                invoice_data_keys=list(invoice_data.keys()) if invoice_data else [],
                has_nested_invoice_data="invoice_data" in invoice_data if invoice_data else False,
                has_line_items=bool(invoice_data.get("line_items")),
                chart=chart_of_accounts,
            )

            # Ensure rules are loaded
            await self._load_rules()

            # Log learned rules for debugging
            learned_rules_info = [
                (r.rule_id, r.vendor_pattern[:20], r.item_patterns[:2] if r.item_patterns else [])
                for r in self._rules if "HITL" in r.rule_id or "AUTO" in r.rule_id
            ]
            logger.debug(
                "semantic_rule_engine.rules_summary",
                total_rules=len(self._rules),
                learned_rules_mtime=self._learned_rules_mtime,
                learned_rules=learned_rules_info,
            )

            # Use helper functions for field extraction (eliminates code duplication)
            supplier_name = extract_supplier_name(invoice_data)
            line_items = extract_line_items(invoice_data)

            # Log extraction results
            line_item_descs = [item.get("description", "")[:50] for item in line_items[:5]] if line_items else []
            logger.debug(
                "semantic_rule_engine.extraction",
                supplier=supplier_name[:50] if supplier_name else "EMPTY",
                line_items_count=len(line_items),
                line_item_descs=line_item_descs,
            )

            # If no line items from helper, try to create one from invoice totals
            if not line_items:
                net_amount = extract_net_amount(invoice_data)
                if net_amount:
                    description = extract_description(invoice_data) or "Rechnung"
                    line_items = [
                        {
                            "description": description,
                            "net_amount": net_amount,
                            "vat_rate": extract_vat_rate(invoice_data),
                            "vat_amount": extract_vat_amount(invoice_data) or 0,
                        }
                    ]
                    logger.debug(
                        "semantic_rule_engine.fallback_line_item_created",
                        description=description[:50] if description else "",
                        net_amount=net_amount,
                    )

            rule_matches: list[dict[str, Any]] = []
            booking_proposals: list[dict[str, Any]] = []
            unmatched_items: list[dict[str, Any]] = []
            ambiguous_items: list[dict[str, Any]] = []

            # Log processing info with learned rules detail
            learned_rule_count = len([r for r in self._rules if "HITL" in r.rule_id or "LEARNED" in r.rule_id or "AUTO" in r.rule_id])
            logger.info(
                "semantic_rule_engine.processing",
                supplier=supplier_name[:30] if supplier_name else "N/A",
                line_items_count=len(line_items),
                total_rules=len(self._rules),
                learned_rules=learned_rule_count,
                rule_ids=[r.rule_id for r in self._rules if "HITL" in r.rule_id or "AUTO" in r.rule_id],
                rule_vendors=[r.vendor_pattern[:30] for r in self._rules if "HITL" in r.rule_id or "AUTO" in r.rule_id],
                line_item_descriptions=[
                    str(item.get("description", ""))[:40] for item in line_items[:3]
                ],
            )

            # Debug: Check if supplier matches any learned rule
            if supplier_name:
                for rule in self._rules:
                    if "HITL" in rule.rule_id or "AUTO" in rule.rule_id:
                        match_result = self._matches_vendor_pattern(supplier_name, rule.vendor_pattern)
                        logger.info(
                            "semantic_rule_engine.vendor_match_check",
                            rule_id=rule.rule_id,
                            vendor_pattern=rule.vendor_pattern[:30],
                            supplier=supplier_name[:30],
                            matched=match_result,
                        )

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
                            "rule_source": match_result.rule.source.value,
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

            # Log final result for debugging
            logger.info(
                "semantic_rule_engine.result",
                rules_applied=len(rule_matches),
                unmatched_count=len(unmatched_items),
                booking_accounts=[p.get("debit_account") for p in booking_proposals if p.get("type") == "debit"],
            )

            # Log final results
            logger.debug(
                "semantic_rule_engine.final_result",
                rules_applied=len(rule_matches),
                booking_proposals_count=len(booking_proposals),
                unmatched_count=len(unmatched_items),
                rule_ids=[rm.get("rule_id") for rm in rule_matches],
            )

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
            vendor_matches = self._matches_vendor_pattern(supplier_name, rule.vendor_pattern)

            # Log learned rule checks
            if "HITL" in rule.rule_id or "AUTO" in rule.rule_id:
                logger.debug(
                    "semantic_rule_engine.checking_learned_rule",
                    rule_id=rule.rule_id,
                    vendor_pattern=rule.vendor_pattern,
                    item_patterns=rule.item_patterns,
                    vendor_matches=vendor_matches,
                )

            if not vendor_matches:
                continue

            # Check item patterns
            best_pattern = None
            best_similarity = 0.0
            match_type = MatchType.EXACT

            for pattern in rule.item_patterns:
                # Normalize quotes for comparison (handle typographic quotes)
                pattern_normalized = self._normalize_quotes(pattern.lower())
                description_normalized = self._normalize_quotes(description_lower)

                # Also create a "stripped" version without any quotes for fallback matching
                pattern_stripped = pattern_normalized.replace('"', '').replace("'", '')
                description_stripped = description_normalized.replace('"', '').replace("'", '')

                # Log pattern matching details for learned rules
                if "HITL" in rule.rule_id or "AUTO" in rule.rule_id:
                    logger.debug(
                        "semantic_rule_engine.pattern_matching",
                        rule_id=rule.rule_id,
                        pattern_raw=pattern[:40],
                        pattern_normalized=pattern_normalized[:40],
                        description_raw=description[:40],
                        description_normalized=description_normalized[:40],
                        match_normalized=pattern_normalized in description_normalized,
                        match_stripped=pattern_stripped in description_stripped,
                    )

                # Log detailed matching attempt
                logger.info(
                    "semantic_rule_engine.item_pattern_match_attempt",
                    rule_id=rule.rule_id,
                    pattern=pattern[:40],
                    pattern_normalized=pattern_normalized[:40],
                    description=description_lower[:40],
                    description_normalized=description_normalized[:40],
                    is_substring=pattern_normalized in description_normalized,
                )

                # First try exact/keyword match (with normalized quotes)
                # For short patterns (< 4 chars like "DB", "PC"), require word
                # boundary matching to avoid false positives (e.g. "DB" in "Goldbräu")
                if len(pattern_stripped) < 4:
                    is_match = bool(
                        re.search(
                            r"\b" + re.escape(pattern_normalized) + r"\b",
                            description_normalized,
                        )
                    )
                    if not is_match:
                        is_match = bool(
                            re.search(
                                r"\b" + re.escape(pattern_stripped) + r"\b",
                                description_stripped,
                            )
                        )
                else:
                    is_match = pattern_normalized in description_normalized
                    # Fallback: try stripped version (without quotes)
                    if not is_match:
                        is_match = pattern_stripped in description_stripped

                if is_match:
                    if 1.0 > best_similarity:
                        best_similarity = 1.0
                        best_pattern = pattern
                        match_type = MatchType.EXACT
                        logger.debug(
                            "semantic_rule_engine.pattern_matched",
                            rule_id=rule.rule_id,
                            pattern=pattern[:40],
                            description=description[:40],
                        )
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
            # Phase 2.5: Try vendor generalization
            generalized = self._try_vendor_generalization(supplier_name, description)
            if generalized:
                return generalized
            return None

        # Sort matches by: priority (desc), then similarity (desc)
        matches.sort(
            key=lambda m: (m.rule.priority, m.similarity_score),
            reverse=True,
        )

        # Check for ambiguity (multiple high-scoring matches)
        best_match = matches[0]
        if len(matches) > 1:
            second_match = matches[1]
            similarity_diff = best_match.similarity_score - second_match.similarity_score
            different_account = best_match.rule.target_account != second_match.rule.target_account
            priority_diff = best_match.rule.priority - second_match.rule.priority

            # Only consider ambiguous if:
            # 1. Similarity scores are very close (within 0.05)
            # 2. Accounts are different
            # 3. Priorities are similar (within 10 points)
            # If best match has significantly higher priority, trust it!
            is_ambiguous = (
                similarity_diff < 0.05
                and different_account
                and priority_diff < 10  # If priority diff >= 10, trust the higher priority rule
            )

            if is_ambiguous:
                best_match.is_ambiguous = True
                best_match.alternative_matches = matches[1:3]  # Include top alternatives
                logger.info(
                    "semantic_rule_engine.ambiguous_match",
                    best_rule=best_match.rule.rule_id,
                    alternatives=[m.rule.rule_id for m in matches[1:3]],
                )
            else:
                # Not ambiguous - higher priority rule wins
                logger.debug(
                    "semantic_rule_engine.priority_selection",
                    selected_rule=best_match.rule.rule_id,
                    selected_priority=best_match.rule.priority,
                    runner_up_rule=second_match.rule.rule_id,
                    runner_up_priority=second_match.rule.priority,
                )

        return best_match

    def _normalize_quotes(self, text: str) -> str:
        """Normalize various quote characters to standard ASCII quotes."""
        # Map typographic quotes to ASCII - comprehensive list
        quote_map = {
            # Double quotes (various Unicode variants)
            '\u201c': '"',  # " Left double quotation mark
            '\u201d': '"',  # " Right double quotation mark
            '\u201e': '"',  # „ German low double quote
            '\u201f': '"',  # ‟ Double high-reversed-9 quotation mark
            '\u00ab': '"',  # « Left-pointing double angle quotation mark
            '\u00bb': '"',  # » Right-pointing double angle quotation mark
            '\u2033': '"',  # ″ Double prime
            '\u301d': '"',  # 〝 Reversed double prime quotation mark
            '\u301e': '"',  # 〞 Double prime quotation mark
            # Single quotes (various Unicode variants)
            '\u2018': "'",  # ' Left single quotation mark
            '\u2019': "'",  # ' Right single quotation mark
            '\u201a': "'",  # ‚ German low single quote
            '\u201b': "'",  # ‛ Single high-reversed-9 quotation mark
            '\u2039': "'",  # ‹ Single left-pointing angle quotation mark
            '\u203a': "'",  # › Single right-pointing angle quotation mark
            '\u2032': "'",  # ′ Prime
        }
        for char, replacement in quote_map.items():
            text = text.replace(char, replacement)
        return text

    def _matches_vendor_pattern(self, vendor_name: str, pattern: str) -> bool:
        """Check if vendor name matches pattern (regex or exact)."""
        if not pattern or not vendor_name:
            return False

        # First, try simple substring match (most common case)
        # Remove backslash escapes from pattern for simple matching
        pattern_simple = pattern.replace("\\", "")
        if pattern_simple.lower() in vendor_name.lower():
            logger.info(
                "semantic_rule_engine.vendor_pattern_match_attempt",
                pattern=pattern[:30],
                pattern_simple=pattern_simple[:30],
                vendor=vendor_name[:30],
                match_type="simple",
                matched=True,
            )
            return True

        # Treat as regex if contains regex metacharacters
        if any(c in pattern for c in ".*+?[](){}|^$\\"):
            try:
                matched = bool(re.search(pattern, vendor_name, re.IGNORECASE))
                logger.info(
                    "semantic_rule_engine.vendor_pattern_match_attempt",
                    pattern=pattern[:30],
                    vendor=vendor_name[:30],
                    match_type="regex",
                    matched=matched,
                )
                return matched
            except re.error as e:
                logger.warning(
                    "semantic_rule_engine.regex_error",
                    pattern=pattern[:30],
                    error=str(e),
                )
                return False
        else:
            # Exact match (case-insensitive)
            matched = pattern.lower() in vendor_name.lower()
            logger.info(
                "semantic_rule_engine.vendor_pattern_match_attempt",
                pattern=pattern[:30],
                vendor=vendor_name[:30],
                match_type="exact",
                matched=matched,
            )
            return matched

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

        proposal = {
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

        # Add generalization info for vendor_generalized matches
        if match_result.match_type == MatchType.VENDOR_GENERALIZED:
            vendor_pattern = rule.vendor_pattern
            profile = self._vendor_profiles.get(vendor_pattern.lower())
            if profile:
                proposal["generalization_info"] = {
                    "vendor_pattern": profile.vendor_pattern,
                    "dominance_ratio": profile.dominance_ratio,
                    "known_items_count": len(profile.all_item_patterns),
                    "total_rules": profile.total_rules,
                    "reason": (
                        f"Vendor '{profile.vendor_pattern}' hat {profile.total_rules} "
                        f"gelernte Regeln, {profile.rules_for_dominant} davon "
                        f"({profile.dominance_ratio:.0%}) auf Konto {profile.dominant_account}"
                    ),
                }

        return proposal

    def _build_vendor_account_profiles(self) -> None:
        """Build vendor account profiles from learned VENDOR_ITEM rules.

        Analyzes rules from auto_high_confidence and hitl_correction sources,
        groups them by vendor pattern, and creates a VendorAccountProfile when
        a vendor has enough rules with a dominant target account.
        """
        self._vendor_profiles.clear()

        # Group learned VENDOR_ITEM rules by vendor pattern
        vendor_rules: dict[str, list[AccountingRule]] = {}
        for rule in self._rules:
            if rule.rule_type != RuleType.VENDOR_ITEM:
                continue
            if rule.source not in (RuleSource.AUTO_HIGH_CONFIDENCE, RuleSource.HITL_CORRECTION):
                continue
            vendor_key = rule.vendor_pattern.lower()
            vendor_rules.setdefault(vendor_key, []).append(rule)

        for vendor_key, rules in vendor_rules.items():
            if len(rules) < self.MIN_RULES_FOR_GENERALIZATION:
                continue

            # Count target accounts
            account_counts: dict[str, int] = {}
            account_names: dict[str, Optional[str]] = {}
            all_patterns: list[str] = []
            for rule in rules:
                account_counts[rule.target_account] = (
                    account_counts.get(rule.target_account, 0) + 1
                )
                if rule.target_account_name:
                    account_names[rule.target_account] = rule.target_account_name
                for p in rule.item_patterns:
                    if p not in all_patterns:
                        all_patterns.append(p)

            # Find dominant account
            dominant_account = max(account_counts, key=account_counts.get)  # type: ignore[arg-type]
            rules_for_dominant = account_counts[dominant_account]
            dominance_ratio = rules_for_dominant / len(rules)

            if dominance_ratio < self.MIN_DOMINANCE_RATIO:
                continue

            # Use original casing from first rule
            vendor_pattern = rules[0].vendor_pattern

            profile = VendorAccountProfile(
                vendor_pattern=vendor_pattern,
                dominant_account=dominant_account,
                dominant_account_name=account_names.get(dominant_account),
                total_rules=len(rules),
                rules_for_dominant=rules_for_dominant,
                dominance_ratio=dominance_ratio,
                all_item_patterns=all_patterns,
            )
            self._vendor_profiles[vendor_pattern.lower()] = profile

            logger.info(
                "semantic_rule_engine.vendor_profile_created",
                vendor=vendor_pattern,
                dominant_account=dominant_account,
                total_rules=len(rules),
                dominance_ratio=f"{dominance_ratio:.0%}",
            )

        logger.info(
            "semantic_rule_engine.vendor_profiles_built",
            profile_count=len(self._vendor_profiles),
            vendors=list(self._vendor_profiles.keys()),
        )

    def _try_vendor_generalization(
        self, supplier_name: str, description: str
    ) -> Optional[RuleMatch]:
        """Try to match via vendor-level generalization.

        When an item has no exact or semantic match, check if the vendor has
        a dominant account profile. If so, return a generalized match.

        Args:
            supplier_name: Invoice supplier name
            description: Line item description

        Returns:
            RuleMatch with VENDOR_GENERALIZED type, or None
        """
        if not self._vendor_profiles:
            return None

        for vendor_key, profile in self._vendor_profiles.items():
            if not self._matches_vendor_pattern(supplier_name, profile.vendor_pattern):
                continue

            # Create synthetic rule for the generalized match
            synthetic_rule = AccountingRule(
                rule_id=f"VENDOR-GEN-{profile.vendor_pattern}",
                rule_type=RuleType.VENDOR_ITEM,
                vendor_pattern=profile.vendor_pattern,
                item_patterns=profile.all_item_patterns,
                target_account=profile.dominant_account,
                target_account_name=profile.dominant_account_name,
                priority=self.VENDOR_GENERALIZATION_PRIORITY,
                source=RuleSource.AUTO_HIGH_CONFIDENCE,
                is_active=True,
            )

            similarity = self.VENDOR_GENERALIZATION_BASE_SCORE * profile.dominance_ratio

            logger.info(
                "semantic_rule_engine.vendor_generalization_match",
                supplier=supplier_name,
                description=description[:50],
                vendor_pattern=profile.vendor_pattern,
                dominant_account=profile.dominant_account,
                dominance_ratio=f"{profile.dominance_ratio:.0%}",
                similarity=f"{similarity:.2f}",
            )

            return RuleMatch(
                rule=synthetic_rule,
                match_type=MatchType.VENDOR_GENERALIZED,
                similarity_score=similarity,
                matched_item_pattern=None,
            )

        return None

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
