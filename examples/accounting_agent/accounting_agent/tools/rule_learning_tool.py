"""
Rule Learning Tool

Automatically generates accounting rules from:
- High-confidence bookings (>95% confidence)
- HITL corrections (user-provided corrections)

PRD Reference:
- Auto-Regel bei >95% Confidence
- Manuelle Regel aus HITL-Korrektur
- Versionierung und Konflikt-Check
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import re

import structlog

from accounting_agent.domain.models import (
    AccountingRule,
    RuleType,
    RuleSource,
)
from accounting_agent.domain.invoice_utils import (
    extract_supplier_name,
    extract_line_items,
    AUTO_RULE_PRIORITY,
    HITL_RULE_PRIORITY,
    MAX_ITEM_PATTERNS,
    MAX_PATTERN_LENGTH,
    MIN_PATTERN_LENGTH,
)
from accounting_agent.tools.tool_base import ApprovalRiskLevel

logger = structlog.get_logger(__name__)

# Lazy import to avoid circular dependency
_rule_repository_class = None

def _get_rule_repository_class():
    global _rule_repository_class
    if _rule_repository_class is None:
        from accounting_agent.infrastructure.persistence.rule_repository import RuleRepository
        _rule_repository_class = RuleRepository
    return _rule_repository_class


class RuleLearningTool:
    """
    Automatic rule generation from bookings and corrections.

    Creates new accounting rules based on:
    1. High-confidence automatic bookings (auto_high_confidence)
    2. HITL corrections (hitl_correction)

    Rules are versioned and checked for conflicts before saving.
    """

    def __init__(
        self,
        rule_repository: Optional[Any] = None,
        min_confidence_for_auto_rule: float = 0.95,
    ):
        """
        Initialize rule learning tool.

        Args:
            rule_repository: RuleRepositoryProtocol for rule storage.
                            If None, auto-creates a RuleRepository.
            min_confidence_for_auto_rule: Minimum confidence for auto-rule creation
        """
        # Auto-create RuleRepository if not provided
        if rule_repository is None:
            RuleRepository = _get_rule_repository_class()
            rule_repository = RuleRepository()
            logger.info("rule_learning.auto_created_repository")

        self._rule_repository = rule_repository
        self._min_confidence = min_confidence_for_auto_rule

    @property
    def name(self) -> str:
        """Return tool name."""
        return "rule_learning"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Create new accounting rules from high-confidence bookings or HITL corrections. "
            "Actions: 'create_from_booking' (auto-rule from high confidence), "
            "'create_from_hitl' (rule from user correction), "
            "'check_conflicts' (verify rule doesn't conflict). "
            "Rules are versioned and auditable."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to perform: 'create_from_booking' (auto-rule, requires confidence>=95%), 'create_from_hitl_confirmation' (user confirmed HITL, no confidence check), 'create_from_hitl' (user correction), 'check_conflicts'",
                    "enum": ["create_from_booking", "create_from_hitl_confirmation", "create_from_hitl", "check_conflicts"],
                },
                "invoice_data": {
                    "type": "object",
                    "description": "Invoice data for rule creation",
                },
                "booking_proposal": {
                    "type": "object",
                    "description": "Single booking proposal (DEPRECATED - use position_bookings for multiple positions)",
                },
                "position_bookings": {
                    "type": "array",
                    "description": "Array of position-account mappings. Each creates a separate rule. Use this for invoices with multiple positions that need different accounts.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item_description": {
                                "type": "string",
                                "description": "Description of the line item"
                            },
                            "debit_account": {
                                "type": "string",
                                "description": "Account number (SKR03)"
                            },
                            "debit_account_name": {
                                "type": "string",
                                "description": "Account name"
                            }
                        },
                        "required": ["item_description", "debit_account"]
                    }
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score (for create_from_booking)",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "correction": {
                    "type": "object",
                    "description": "User correction (for create_from_hitl)",
                },
                "rule_type": {
                    "type": "string",
                    "description": "Type of rule to create",
                    "enum": ["vendor_only", "vendor_item"],
                    "default": "vendor_item",
                },
            },
            "required": ["action", "invoice_data"],
        }

    @property
    def requires_approval(self) -> bool:
        """Rule creation should be reviewed."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Medium risk - creates persistent rules."""
        return ApprovalRiskLevel.MEDIUM

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        action = kwargs.get("action", "unknown")
        invoice_data = kwargs.get("invoice_data", {})
        supplier = invoice_data.get("supplier_name", "Unknown")
        return (
            f"Tool: {self.name}\n"
            f"Operation: {action}\n"
            f"Supplier: {supplier}"
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        action = kwargs.get("action")
        if action not in ["create_from_booking", "create_from_hitl_confirmation", "create_from_hitl", "check_conflicts"]:
            return False, "Invalid action"
        if "invoice_data" not in kwargs:
            return False, "Missing invoice_data"
        return True, None

    async def execute(
        self,
        action: str,
        invoice_data: dict[str, Any],
        booking_proposal: Optional[dict[str, Any]] = None,
        position_bookings: Optional[list[dict[str, Any]]] = None,
        confidence: Optional[float] = None,
        correction: Optional[dict[str, Any]] = None,
        rule_type: str = "vendor_item",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Create or check accounting rules.

        Args:
            action: 'create_from_booking', 'create_from_hitl', or 'check_conflicts'
            invoice_data: Invoice context
            booking_proposal: Single booking proposal (deprecated - use position_bookings)
            position_bookings: Array of position-account mappings (creates one rule per item)
            confidence: Confidence score (for auto-rules)
            correction: User correction (for HITL rules)
            rule_type: Type of rule to create

        Returns:
            Dictionary with rule creation or conflict check result
        """
        try:
            if action == "create_from_booking":
                return await self._create_from_booking(
                    invoice_data=invoice_data,
                    booking_proposal=booking_proposal or {},
                    confidence=confidence or 0.0,
                    rule_type_str=rule_type,
                )
            elif action == "create_from_hitl_confirmation":
                # User confirmed HITL - no confidence check needed
                # Support both: single booking_proposal OR multiple position_bookings
                return await self._create_from_hitl_confirmation(
                    invoice_data=invoice_data,
                    booking_proposal=booking_proposal or {},
                    position_bookings=position_bookings,
                    rule_type_str=rule_type,
                )
            elif action == "create_from_hitl":
                return await self._create_from_hitl(
                    invoice_data=invoice_data,
                    correction=correction or {},
                    rule_type_str=rule_type,
                )
            elif action == "check_conflicts":
                return await self._check_conflicts(
                    invoice_data=invoice_data,
                    target_account=correction.get("debit_account") if correction else None,
                )
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                }

        except Exception as e:
            logger.error(
                "rule_learning.error",
                action=action,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def _create_from_booking(
        self,
        invoice_data: dict[str, Any],
        booking_proposal: dict[str, Any],
        confidence: float,
        rule_type_str: str,
    ) -> dict[str, Any]:
        """Create or update auto-rule from high-confidence booking."""
        logger.info(
            "rule_learning.create_from_booking_start",
            confidence=confidence,
            min_confidence=self._min_confidence,
            has_invoice_data=bool(invoice_data),
            has_booking_proposal=bool(booking_proposal),
        )

        # Check confidence threshold
        if confidence < self._min_confidence:
            logger.info(
                "rule_learning.confidence_below_threshold",
                confidence=confidence,
                threshold=self._min_confidence,
            )
            return {
                "success": False,
                "error": f"Confidence {confidence:.1%} below threshold {self._min_confidence:.1%}",
                "rule_created": False,
            }

        # Use helper for supplier name extraction
        supplier_name = extract_supplier_name(invoice_data)
        if not supplier_name:
            return {
                "success": False,
                "error": "Missing supplier_name (tried: supplier_name, vendor_name, lieferant, supplier, vendor)",
                "rule_created": False,
            }

        # Validate target account
        target_account = booking_proposal.get("debit_account", "")
        if not target_account:
            return {
                "success": False,
                "error": "Missing debit_account in booking_proposal - cannot create rule without account",
                "rule_created": False,
                "hint": "Provide booking_proposal with debit_account field",
            }

        # Determine rule type
        rule_type = RuleType.VENDOR_ONLY if rule_type_str == "vendor_only" else RuleType.VENDOR_ITEM

        # Use helper for line item extraction
        line_items = extract_line_items(invoice_data)
        item_patterns = self._extract_item_patterns(line_items, rule_type)
        vendor_pattern = self._create_vendor_pattern(supplier_name)

        # Check for existing rule to UPDATE instead of creating duplicate
        existing_rule = None
        if self._rule_repository:
            existing_rule = await self._rule_repository.find_existing_rule(
                vendor_pattern, item_patterns
            )

        timestamp = datetime.now(timezone.utc)

        if existing_rule:
            # UPDATE existing rule
            existing_rule.target_account = target_account
            existing_rule.target_account_name = booking_proposal.get("debit_account_name")
            existing_rule.updated_at = timestamp.isoformat()
            # Keep existing rule_id, just update the account
            rule = existing_rule
            action = "updated"
            logger.info(
                "rule_learning.updating_existing_rule",
                rule_id=rule.rule_id,
                vendor=supplier_name,
                new_account=target_account,
            )
        else:
            # CREATE new rule
            rule_id = f"AUTO-{timestamp.strftime('%Y%m%d%H%M%S')}"
            rule = AccountingRule(
                rule_id=rule_id,
                rule_type=rule_type,
                vendor_pattern=vendor_pattern,
                item_patterns=item_patterns,
                target_account=target_account,
                target_account_name=booking_proposal.get("debit_account_name"),
                priority=AUTO_RULE_PRIORITY,
                similarity_threshold=0.8,
                source=RuleSource.AUTO_HIGH_CONFIDENCE,
                legal_basis=booking_proposal.get("legal_basis"),
                created_at=timestamp.isoformat(),
                is_active=True,
            )
            action = "created"

        # Check for conflicts (different target accounts for same vendor)
        if self._rule_repository:
            conflicts = await self._rule_repository.find_conflicting_rules(rule)
            if conflicts:
                logger.warning(
                    "rule_learning.conflicts_found",
                    rule_id=rule.rule_id,
                    conflicts=[c.rule_id for c in conflicts],
                )
                return {
                    "success": False,
                    "error": "Rule conflicts with existing rules with different accounts",
                    "rule_created": False,
                    "conflicts": [
                        {
                            "rule_id": c.rule_id,
                            "target_account": c.target_account,
                        }
                        for c in conflicts
                    ],
                }

            # Save rule
            await self._rule_repository.save_rule(rule)

        logger.info(
            f"rule_learning.auto_rule_{action}",
            rule_id=rule.rule_id,
            rule_type=rule_type.value,
            vendor=supplier_name,
            account=rule.target_account,
        )

        return {
            "success": True,
            "rule_created": action == "created",
            "rule_updated": action == "updated",
            "rule_id": rule.rule_id,
            "rule_type": rule_type.value,
            "source": RuleSource.AUTO_HIGH_CONFIDENCE.value,
            "vendor_pattern": rule.vendor_pattern,
            "target_account": rule.target_account,
            "item_patterns": item_patterns,
        }

    async def _create_from_hitl_confirmation(
        self,
        invoice_data: dict[str, Any],
        booking_proposal: dict[str, Any],
        position_bookings: Optional[list[dict[str, Any]]] = None,
        rule_type_str: str = "vendor_item",
    ) -> dict[str, Any]:
        """
        Create or update rules from HITL confirmation (user confirmed the booking proposal).

        Unlike create_from_booking, this does NOT check confidence threshold
        because the user has already confirmed the booking.

        Supports two modes:
        1. Single booking_proposal (legacy) - creates one rule for all items
        2. position_bookings array (preferred) - creates one rule per item-account pair
        """
        # Use helper for supplier name extraction
        supplier_name = extract_supplier_name(invoice_data)
        if not supplier_name:
            return {
                "success": False,
                "error": "Missing supplier_name (tried: supplier_name, vendor_name, lieferant, supplier, vendor)",
                "rule_created": False,
            }

        vendor_pattern = self._create_vendor_pattern(supplier_name)
        timestamp = datetime.now(timezone.utc)

        # NEW: Handle multiple position_bookings (preferred)
        if position_bookings and len(position_bookings) > 0:
            return await self._create_rules_for_positions(
                vendor_pattern=vendor_pattern,
                supplier_name=supplier_name,
                position_bookings=position_bookings,
                timestamp=timestamp,
            )

        # LEGACY: Single booking_proposal (deprecated but still supported)
        target_account = booking_proposal.get("debit_account", "")
        if not target_account:
            return {
                "success": False,
                "error": "Missing debit_account in booking_proposal - cannot create rule without account",
                "rule_created": False,
                "hint": "Use position_bookings array for multiple positions with different accounts",
            }

        # Determine rule type
        rule_type = RuleType.VENDOR_ONLY if rule_type_str == "vendor_only" else RuleType.VENDOR_ITEM

        # Use helper for line item extraction
        line_items = extract_line_items(invoice_data)
        item_patterns = self._extract_item_patterns(line_items, rule_type)

        # Check for existing rule to UPDATE instead of creating duplicate
        existing_rule = None
        if self._rule_repository:
            existing_rule = await self._rule_repository.find_existing_rule(
                vendor_pattern, item_patterns
            )

        if existing_rule:
            # UPDATE existing rule
            existing_rule.target_account = target_account
            existing_rule.target_account_name = booking_proposal.get("debit_account_name")
            existing_rule.updated_at = timestamp.isoformat()
            rule = existing_rule
            action = "updated"
            logger.info(
                "rule_learning.updating_existing_rule_from_hitl",
                rule_id=rule.rule_id,
                vendor=supplier_name,
                new_account=target_account,
            )
        else:
            # CREATE new rule
            rule_id = f"HITL-CONF-{timestamp.strftime('%Y%m%d%H%M%S')}"
            rule = AccountingRule(
                rule_id=rule_id,
                rule_type=rule_type,
                vendor_pattern=vendor_pattern,
                item_patterns=item_patterns,
                target_account=target_account,
                target_account_name=booking_proposal.get("debit_account_name"),
                priority=AUTO_RULE_PRIORITY,
                similarity_threshold=0.8,
                source=RuleSource.AUTO_HIGH_CONFIDENCE,
                legal_basis=booking_proposal.get("legal_basis"),
                created_at=timestamp.isoformat(),
                is_active=True,
            )
            action = "created"

        # Check for conflicts
        if self._rule_repository:
            conflicts = await self._rule_repository.find_conflicting_rules(rule)
            if conflicts:
                logger.warning(
                    "rule_learning.conflicts_found",
                    rule_id=rule.rule_id,
                    conflicts=[c.rule_id for c in conflicts],
                )
                return {
                    "success": False,
                    "error": "Rule conflicts with existing rules with different accounts",
                    "rule_created": False,
                    "conflicts": [
                        {
                            "rule_id": c.rule_id,
                            "target_account": c.target_account,
                        }
                        for c in conflicts
                    ],
                }

            # Save rule
            await self._rule_repository.save_rule(rule)

        logger.info(
            f"rule_learning.hitl_confirmation_rule_{action}",
            rule_id=rule.rule_id,
            rule_type=rule_type.value,
            vendor=supplier_name,
            account=rule.target_account,
        )

        return {
            "success": True,
            "rule_created": action == "created",
            "rule_updated": action == "updated",
            "rule_id": rule.rule_id,
            "rule_type": rule_type.value,
            "source": "hitl_confirmation",
            "vendor_pattern": rule.vendor_pattern,
            "target_account": rule.target_account,
            "item_patterns": item_patterns,
        }

    async def _create_rules_for_positions(
        self,
        vendor_pattern: str,
        supplier_name: str,
        position_bookings: list[dict[str, Any]],
        timestamp: datetime,
    ) -> dict[str, Any]:
        """
        Create one rule per position-account pair.

        This is the preferred method for invoices with multiple line items
        that need different account assignments.
        """
        rules_created = []
        rules_updated = []
        errors = []

        for i, position in enumerate(position_bookings):
            item_description = position.get("item_description", "")
            debit_account = position.get("debit_account", "")
            debit_account_name = position.get("debit_account_name", "")

            if not debit_account:
                errors.append(f"Position {i+1}: Missing debit_account")
                continue

            if not item_description:
                errors.append(f"Position {i+1}: Missing item_description")
                continue

            # Create single-item pattern list
            item_patterns = [item_description[:MAX_PATTERN_LENGTH]]

            # Check for existing rule for THIS specific item
            existing_rule = None
            if self._rule_repository:
                existing_rule = await self._rule_repository.find_existing_rule(
                    vendor_pattern, item_patterns
                )

            if existing_rule:
                # UPDATE existing rule
                existing_rule.target_account = debit_account
                existing_rule.target_account_name = debit_account_name
                existing_rule.updated_at = timestamp.isoformat()
                rule = existing_rule
                action = "updated"
            else:
                # CREATE new rule - unique ID per position
                rule_id = f"HITL-CONF-{timestamp.strftime('%Y%m%d%H%M%S')}-{i+1}"
                rule = AccountingRule(
                    rule_id=rule_id,
                    rule_type=RuleType.VENDOR_ITEM,
                    vendor_pattern=vendor_pattern,
                    item_patterns=item_patterns,
                    target_account=debit_account,
                    target_account_name=debit_account_name,
                    priority=AUTO_RULE_PRIORITY,
                    similarity_threshold=0.8,
                    source=RuleSource.AUTO_HIGH_CONFIDENCE,
                    created_at=timestamp.isoformat(),
                    is_active=True,
                )
                action = "created"

            # Save rule
            if self._rule_repository:
                await self._rule_repository.save_rule(rule)

            if action == "created":
                rules_created.append({
                    "rule_id": rule.rule_id,
                    "item": item_description,
                    "account": debit_account,
                    "account_name": debit_account_name,
                })
            else:
                rules_updated.append({
                    "rule_id": rule.rule_id,
                    "item": item_description,
                    "account": debit_account,
                    "account_name": debit_account_name,
                })

            logger.info(
                f"rule_learning.position_rule_{action}",
                rule_id=rule.rule_id,
                vendor=supplier_name,
                item=item_description[:50],
                account=debit_account,
            )

        return {
            "success": len(errors) == 0,
            "rules_created": len(rules_created),
            "rules_updated": len(rules_updated),
            "created_rules": rules_created,
            "updated_rules": rules_updated,
            "errors": errors if errors else None,
            "vendor_pattern": vendor_pattern,
            "total_positions": len(position_bookings),
        }

    async def _create_from_hitl(
        self,
        invoice_data: dict[str, Any],
        correction: dict[str, Any],
        rule_type_str: str,
    ) -> dict[str, Any]:
        """Create or update rule from HITL correction."""
        # Use helper for supplier name extraction
        supplier_name = extract_supplier_name(invoice_data)
        if not supplier_name:
            return {
                "success": False,
                "error": "Missing supplier_name (tried: supplier_name, vendor_name, lieferant, supplier, vendor)",
                "rule_created": False,
            }

        target_account = correction.get("debit_account")
        if not target_account:
            return {
                "success": False,
                "error": "Missing debit_account in correction",
                "rule_created": False,
            }

        # Determine rule type
        rule_type = RuleType.VENDOR_ONLY if rule_type_str == "vendor_only" else RuleType.VENDOR_ITEM

        # Use helper for line item extraction
        line_items = extract_line_items(invoice_data)
        item_patterns = self._extract_item_patterns(line_items, rule_type)
        vendor_pattern = self._create_vendor_pattern(supplier_name)

        # Check for existing rule to UPDATE instead of creating duplicate
        existing_rule = None
        if self._rule_repository:
            existing_rule = await self._rule_repository.find_existing_rule(
                vendor_pattern, item_patterns
            )

        timestamp = datetime.now(timezone.utc)

        if existing_rule:
            # UPDATE existing rule with correction
            existing_rule.target_account = target_account
            existing_rule.target_account_name = correction.get("debit_account_name")
            existing_rule.source = RuleSource.HITL_CORRECTION  # Upgrade to HITL correction
            existing_rule.priority = HITL_RULE_PRIORITY  # Higher priority for corrections
            existing_rule.updated_at = timestamp.isoformat()
            rule = existing_rule
            action = "updated"
            logger.info(
                "rule_learning.updating_existing_rule_from_hitl_correction",
                rule_id=rule.rule_id,
                vendor=supplier_name,
                new_account=target_account,
            )
        else:
            # CREATE new rule
            rule_id = f"HITL-{timestamp.strftime('%Y%m%d%H%M%S')}"
            rule = AccountingRule(
                rule_id=rule_id,
                rule_type=rule_type,
                vendor_pattern=vendor_pattern,
                item_patterns=item_patterns,
                target_account=target_account,
                target_account_name=correction.get("debit_account_name"),
                priority=HITL_RULE_PRIORITY,
                similarity_threshold=0.8,
                source=RuleSource.HITL_CORRECTION,
                legal_basis=correction.get("legal_basis"),
                created_at=timestamp.isoformat(),
                is_active=True,
            )
            action = "created"

        # Check for conflicts (different accounts)
        if self._rule_repository:
            conflicts = await self._rule_repository.find_conflicting_rules(rule)
            if conflicts:
                # For HITL corrections, we can override - deactivate conflicting rules
                for conflict in conflicts:
                    await self._rule_repository.deactivate_rule(conflict.rule_id)
                    logger.info(
                        "rule_learning.conflict_deactivated",
                        deactivated=conflict.rule_id,
                        new_rule=rule.rule_id,
                    )

            # Save rule
            await self._rule_repository.save_rule(rule)

        logger.info(
            f"rule_learning.hitl_rule_{action}",
            rule_id=rule.rule_id,
            rule_type=rule_type.value,
            vendor=supplier_name,
            account=rule.target_account,
        )

        return {
            "success": True,
            "rule_created": action == "created",
            "rule_updated": action == "updated",
            "rule_id": rule.rule_id,
            "rule_type": rule_type.value,
            "source": RuleSource.HITL_CORRECTION.value,
            "vendor_pattern": rule.vendor_pattern,
            "target_account": rule.target_account,
            "item_patterns": item_patterns,
        }

    async def _check_conflicts(
        self,
        invoice_data: dict[str, Any],
        target_account: Optional[str],
    ) -> dict[str, Any]:
        """Check if a potential rule would conflict."""
        if not self._rule_repository:
            return {
                "success": True,
                "has_conflicts": False,
                "conflicts": [],
            }

        # Use helper for supplier name extraction
        supplier_name = extract_supplier_name(invoice_data)

        # Create temporary rule for conflict check
        temp_rule = AccountingRule(
            rule_id="TEMP",
            rule_type=RuleType.VENDOR_ITEM,
            vendor_pattern=self._create_vendor_pattern(supplier_name),
            target_account=target_account or "",
        )

        conflicts = await self._rule_repository.find_conflicting_rules(temp_rule)

        return {
            "success": True,
            "has_conflicts": len(conflicts) > 0,
            "conflicts": [
                {
                    "rule_id": c.rule_id,
                    "vendor_pattern": c.vendor_pattern,
                    "target_account": c.target_account,
                    "source": c.source.value,
                }
                for c in conflicts
            ],
        }

    def _create_vendor_pattern(self, vendor_name: str) -> str:
        """Create a vendor pattern from vendor name."""
        # Use plain vendor name for simple substring matching
        # No regex escaping needed - we do case-insensitive substring match first
        return vendor_name.strip()

    def _extract_item_patterns(
        self,
        line_items: list[dict[str, Any]],
        rule_type: RuleType,
    ) -> list[str]:
        """
        Extract item patterns from invoice line items.

        Args:
            line_items: List of line item dictionaries
            rule_type: Type of rule being created

        Returns:
            List of item patterns (max MAX_ITEM_PATTERNS)
        """
        if rule_type != RuleType.VENDOR_ITEM:
            return []

        patterns = []
        for item in line_items:
            desc = item.get("description", "")
            if desc and len(desc) > MIN_PATTERN_LENGTH:
                patterns.append(desc[:MAX_PATTERN_LENGTH])

        return patterns[:MAX_ITEM_PATTERNS]

    def set_rule_repository(self, rule_repository: Any) -> None:
        """Set or update the rule repository."""
        self._rule_repository = rule_repository

    def set_min_confidence(self, min_confidence: float) -> None:
        """Set minimum confidence threshold for auto-rules."""
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0.0 and 1.0")
        self._min_confidence = min_confidence
