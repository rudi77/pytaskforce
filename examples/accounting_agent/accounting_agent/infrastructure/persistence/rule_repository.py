"""
Rule Repository Persistence

Versioned storage for accounting rules with YAML + history support.
Implements RuleRepositoryProtocol.

Storage:
- Main rules: YAML file (kontierung_rules.yaml)
- History: JSONL file for audit trail of changes
- Learned rules: Separate YAML file for auto-generated rules
"""

import json
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
)

logger = structlog.get_logger(__name__)


class RuleRepository:
    """
    Accounting rule storage with versioning and history.

    Implements RuleRepositoryProtocol.

    Rules are stored in two locations:
    - Manual rules: kontierung_rules.yaml (vendor_rules, semantic_rules)
    - Learned rules: learned_rules.yaml (auto-generated from HITL)
    - History: rules_history.jsonl (append-only audit trail)
    """

    def __init__(
        self,
        rules_dir: Optional[str] = None,
        learned_rules_file: str = "learned_rules.yaml",
        history_file: str = ".taskforce_accounting/rules_history.jsonl",
        work_dir: str = ".taskforce_accounting",
    ):
        """
        Initialize rule repository.

        Args:
            rules_dir: Directory containing rule YAML files.
                       If None, auto-detects based on module location.
            learned_rules_file: Name of file for learned rules
            history_file: Path to JSONL history file
        """
        # Auto-detect rules_dir relative to module if not provided
        if rules_dir is None:
            module_dir = Path(__file__).parent.parent.parent  # accounting_agent dir
            rules_dir = str(module_dir / "configs" / "accounting" / "rules")

        self._rules_dir = Path(rules_dir)
        self._work_dir = Path(work_dir)
        # Save learned rules to work_dir (persistent across sessions)
        self._learned_rules_path = self._work_dir / learned_rules_file
        self._history_path = Path(history_file)

        # In-memory cache
        self._rules: dict[str, AccountingRule] = {}
        self._loaded = False

        # Ensure directories exist
        self._rules_dir.mkdir(parents=True, exist_ok=True)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._history_path.parent.mkdir(parents=True, exist_ok=True)

    async def _ensure_loaded(self) -> None:
        """Load rules from storage if not already loaded."""
        if self._loaded:
            return

        self._rules = {}

        # Load main kontierung rules
        main_rules_path = self._rules_dir / "kontierung_rules.yaml"
        if main_rules_path.exists():
            await self._load_yaml_rules(main_rules_path)

        # Load learned rules
        if self._learned_rules_path.exists():
            await self._load_yaml_rules(self._learned_rules_path, source="auto")

        self._loaded = True
        logger.info(
            "rule_repository.loaded",
            total_rules=len(self._rules),
        )

    async def _load_yaml_rules(
        self, path: Path, source: str = "manual"
    ) -> None:
        """Load rules from a YAML file asynchronously."""
        try:
            async with aiofiles.open(path, encoding="utf-8") as f:
                content_str = await f.read()
                content = yaml.safe_load(content_str) or {}

            # Parse vendor_rules
            for rule_data in content.get("vendor_rules", []):
                rule = self._parse_rule(rule_data, RuleType.VENDOR_ONLY, source)
                if rule:
                    self._rules[rule.rule_id] = rule

            # Parse semantic_rules
            for rule_data in content.get("semantic_rules", []):
                rule = self._parse_rule(rule_data, RuleType.VENDOR_ITEM, source)
                if rule:
                    self._rules[rule.rule_id] = rule

        except yaml.YAMLError as e:
            logger.error(
                "rule_repository.yaml_parse_error",
                path=str(path),
                error=str(e),
            )
        except OSError as e:
            logger.error(
                "rule_repository.file_read_error",
                path=str(path),
                error=str(e),
            )

    def _parse_rule(
        self,
        data: dict[str, Any],
        rule_type: RuleType,
        default_source: str,
    ) -> Optional[AccountingRule]:
        """Parse rule data into AccountingRule."""
        try:
            source_str = data.get("source", default_source)
            source = RuleSource(source_str) if source_str in [s.value for s in RuleSource] else RuleSource.MANUAL

            return AccountingRule(
                rule_id=data.get("rule_id", f"RULE-{len(self._rules)}"),
                rule_type=rule_type,
                vendor_pattern=data.get("vendor_pattern", ""),
                item_patterns=data.get("item_patterns", []),
                target_account=data.get("target_account", ""),
                target_account_name=data.get("target_account_name"),
                priority=data.get("priority", 50),
                similarity_threshold=data.get("similarity_threshold", 0.8),
                source=source,
                version=data.get("version", 1),
                is_active=data.get("is_active", True),
                legal_basis=data.get("legal_basis"),
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
            )
        except Exception as e:
            logger.warning(
                "rule_repository.parse_error",
                data=str(data)[:100],
                error=str(e),
            )
            return None

    async def get_active_rules(self) -> list[AccountingRule]:
        """
        Get all active accounting rules, sorted by priority.

        Returns:
            List of AccountingRule objects
        """
        await self._ensure_loaded()

        active = [r for r in self._rules.values() if r.is_active]
        active.sort(key=lambda r: r.priority, reverse=True)

        return active

    async def get_rule_by_id(self, rule_id: str) -> Optional[AccountingRule]:
        """
        Get a specific rule by its ID.

        Args:
            rule_id: Unique rule identifier

        Returns:
            AccountingRule or None if not found
        """
        await self._ensure_loaded()
        return self._rules.get(rule_id)

    async def save_rule(self, rule: AccountingRule) -> None:
        """
        Save or update an accounting rule.

        Creates a new version if the rule already exists.
        Writes to learned_rules.yaml for auto-generated rules.

        Args:
            rule: AccountingRule to save
        """
        await self._ensure_loaded()

        timestamp = datetime.now(timezone.utc).isoformat()

        # Check for existing rule
        existing = self._rules.get(rule.rule_id)
        if existing:
            # Increment version
            rule.version = existing.version + 1
            rule.updated_at = timestamp
        else:
            rule.version = 1
            rule.created_at = timestamp
            rule.updated_at = timestamp

        # Add to memory cache
        self._rules[rule.rule_id] = rule

        logger.debug(
            "rule_repository.rule_added_to_cache",
            rule_id=rule.rule_id,
            source=str(rule.source),
            total_rules=len(self._rules),
        )

        # Write to appropriate file - use .value for enum comparison
        source_value = rule.source.value if hasattr(rule.source, 'value') else str(rule.source)
        if source_value in {"auto_high_confidence", "hitl_correction"}:
            await self._save_learned_rules()
        else:
            # For manual rules, just log - don't overwrite main config
            logger.info(
                "rule_repository.manual_rule_saved_to_memory",
                rule_id=rule.rule_id,
            )

        # Record in history
        await self._record_history("save", rule)

        logger.info(
            "rule_repository.rule_saved",
            rule_id=rule.rule_id,
            version=rule.version,
            source=rule.source.value,
        )

    async def _save_learned_rules(self) -> None:
        """Save learned rules to YAML file."""
        # Use string comparison to handle both enum and string source values
        valid_sources = {"auto_high_confidence", "hitl_correction"}
        learned_rules = [
            r for r in self._rules.values()
            if (r.source.value if hasattr(r.source, 'value') else str(r.source)) in valid_sources
        ]

        if not learned_rules:
            logger.debug(
                "rule_repository.no_learned_rules_to_save",
                total_rules=len(self._rules),
                rule_sources=[str(r.source) for r in self._rules.values()],
            )
            return

        # Group by rule type
        vendor_rules = []
        semantic_rules = []

        for rule in learned_rules:
            rule_dict = self._rule_to_dict(rule)
            if rule.rule_type == RuleType.VENDOR_ONLY:
                vendor_rules.append(rule_dict)
            else:
                semantic_rules.append(rule_dict)

        content = {
            "version": "2.0",
            "description": "Auto-generated rules from high-confidence bookings and HITL corrections",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if vendor_rules:
            content["vendor_rules"] = vendor_rules
        if semantic_rules:
            content["semantic_rules"] = semantic_rules

        try:
            yaml_str = yaml.dump(
                content,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
            async with aiofiles.open(self._learned_rules_path, "w", encoding="utf-8") as f:
                await f.write(yaml_str)

            logger.info(
                "rule_repository.learned_rules_saved",
                path=str(self._learned_rules_path),
                count=len(learned_rules),
            )
        except OSError as e:
            logger.error(
                "rule_repository.file_write_error",
                path=str(self._learned_rules_path),
                error=str(e),
            )
            raise

    def _rule_to_dict(self, rule: AccountingRule) -> dict[str, Any]:
        """Convert rule to dictionary for YAML serialization."""
        result = {
            "rule_id": rule.rule_id,
            "vendor_pattern": rule.vendor_pattern,
            "target_account": rule.target_account,
            "priority": rule.priority,
            "source": rule.source.value,
            "version": rule.version,
            "is_active": rule.is_active,
        }

        if rule.target_account_name:
            result["target_account_name"] = rule.target_account_name
        if rule.item_patterns:
            result["item_patterns"] = rule.item_patterns
        if rule.similarity_threshold != 0.8:
            result["similarity_threshold"] = rule.similarity_threshold
        if rule.legal_basis:
            result["legal_basis"] = rule.legal_basis
        if rule.created_at:
            result["created_at"] = rule.created_at
        if rule.updated_at:
            result["updated_at"] = rule.updated_at

        return result

    async def deactivate_rule(self, rule_id: str) -> bool:
        """
        Deactivate a rule by ID.

        Args:
            rule_id: Rule to deactivate

        Returns:
            True if rule was found and deactivated
        """
        await self._ensure_loaded()

        rule = self._rules.get(rule_id)
        if not rule:
            return False

        rule.is_active = False
        rule.updated_at = datetime.now(timezone.utc).isoformat()

        # Update storage - use string comparison for robustness
        if str(rule.source) in {"auto_high_confidence", "hitl_correction"}:
            await self._save_learned_rules()

        # Record in history
        await self._record_history("deactivate", rule)

        logger.info(
            "rule_repository.rule_deactivated",
            rule_id=rule_id,
        )

        return True

    async def get_rule_history(self, rule_id: str) -> list[dict[str, Any]]:
        """
        Get version history for a rule.

        Args:
            rule_id: Rule ID

        Returns:
            List of history entries, newest first
        """
        if not self._history_path.exists():
            return []

        history = []
        try:
            async with aiofiles.open(self._history_path, "r", encoding="utf-8") as f:
                async for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("rule_id") == rule_id:
                            history.append(entry)
                    except json.JSONDecodeError:
                        continue
        except OSError as e:
            logger.error(
                "rule_repository.history_read_error",
                error=str(e),
            )

        # Reverse to get newest first
        history.reverse()
        return history

    async def _record_history(self, action: str, rule: AccountingRule) -> None:
        """Record rule change in history file asynchronously."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "rule_id": rule.rule_id,
            "version": rule.version,
            "rule_type": rule.rule_type.value,
            "source": rule.source.value,
            "target_account": rule.target_account,
            "is_active": rule.is_active,
        }

        try:
            async with aiofiles.open(self._history_path, "a", encoding="utf-8") as f:
                await f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error(
                "rule_repository.history_write_error",
                error=str(e),
            )

    async def find_conflicting_rules(
        self, rule: AccountingRule
    ) -> list[AccountingRule]:
        """
        Find rules that might conflict with a new rule.

        Args:
            rule: Rule to check for conflicts

        Returns:
            List of potentially conflicting rules
        """
        await self._ensure_loaded()

        conflicts = []
        for existing in self._rules.values():
            if existing.rule_id == rule.rule_id:
                continue
            if not existing.is_active:
                continue

            # Check for vendor pattern overlap
            if (
                existing.vendor_pattern == rule.vendor_pattern
                and existing.target_account != rule.target_account
            ):
                conflicts.append(existing)
            # Check for item pattern overlap
            elif rule.rule_type == RuleType.VENDOR_ITEM:
                overlap = set(rule.item_patterns) & set(existing.item_patterns)
                if overlap and existing.target_account != rule.target_account:
                    conflicts.append(existing)

        return conflicts

    def reload(self) -> None:
        """Force reload of rules from storage."""
        self._loaded = False
        self._rules.clear()
