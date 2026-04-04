"""
Fast Intent Router - Pre-LLM Intent Classification

This module provides fast regex-based intent classification that runs BEFORE
LLM planning to skip unnecessary planning steps for well-defined intents.

The router classifies user messages into intents and maps them to skills,
enabling direct skill activation without going through the full planning process.

Usage:
    router = FastIntentRouter()
    match = router.classify("Buche diese Rechnung")
    if match and match.confidence >= 0.4:
        skill_manager.activate_skill(match.skill_name)

Performance:
    - Classification time: <1ms (regex-based)
    - Memory footprint: minimal (compiled patterns cached)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class IntentMatch:
    """
    Result of intent classification.

    Attributes:
        intent: Classified intent name (e.g., "INVOICE_PROCESSING")
        confidence: Confidence score (0.0 - 1.0)
        skill_name: Name of the skill to activate for this intent
        matched_patterns: Patterns that matched (for debugging)
    """

    intent: str
    confidence: float
    skill_name: str
    matched_patterns: list[str] = field(default_factory=list)


@dataclass
class IntentPattern:
    """
    Configuration for an intent pattern set.

    Attributes:
        intent: Intent name
        patterns: List of regex patterns to match
        skill: Skill to activate when intent is matched
        min_confidence: Minimum confidence threshold (default 0.4)
    """

    intent: str
    patterns: list[str]
    skill: str
    min_confidence: float = 0.4


# Default patterns for German accounting domain
# min_confidence is set so that at least 1 pattern match triggers classification
DEFAULT_INTENT_PATTERNS: list[IntentPattern] = [
    IntentPattern(
        intent="INVOICE_PROCESSING",
        patterns=[
            r"buch(?:e|ung|en)\s+(?:diese|die|eine)?",  # buche diese rechnung
            r"verarbeit.*rechnung",  # verarbeite die rechnung
            r"kontier.*rechnung",  # kontiere diese rechnung (not "wie kontiere ich")
            r"(?:über)?prüf.*rechnung",  # prüfe die rechnung
            r"erstelle.*(?:buchungs)?vorschlag",  # erstelle einen buchungsvorschlag
            r"erfasse.*rechnung",  # erfasse die rechnung
            r"verbuche",  # verbuche
        ],
        skill="smart-booking-auto",
        min_confidence=0.14,  # At least 1 of 7 patterns
    ),
    IntentPattern(
        intent="INVOICE_QUESTION",
        patterns=[
            r"wie\s+(?:hoch|viel)",  # wie hoch, wie viel
            r"(?:was|wer)\s+(?:ist|sind)",  # was ist, wer ist
            r"warum.*steuer",  # warum dieser steuersatz / steuersätze
            r"erklär",  # erkläre
            r"zeig.*position",  # zeige die position
            r"welche.*mwst",  # welche mwst
        ],
        skill="invoice-explanation",
        min_confidence=0.16,  # At least 1 of 6 patterns
    ),
    IntentPattern(
        intent="ACCOUNTING_QUESTION",
        patterns=[
            r"wie\s+(?:kontier|buch).*ich",  # wie kontiere/buche ich (general question)
            r"vorsteuer",  # vorsteuerabzug, vorsteuer
            r"reverse\s*charge",  # reverse charge
            r"§\s*\d+",  # paragraph reference
            r"wann.*(?:abziehbar|möglich)",  # wann ist ... abziehbar/möglich
            r"buchwert",  # buchwert
            r"\bafa\b",  # afa (absetzung für abnutzung)
            r"abschreib",  # abschreibung
            r"bedeutet.*(?:reverse|steuer|buchung)",  # was bedeutet reverse charge
        ],
        skill="accounting-expert",
        min_confidence=0.11,  # At least 1 of 9 patterns
    ),
]


class FastIntentRouter:
    """
    Fast regex-based intent classifier.

    Classifies user messages into intents via pattern matching BEFORE
    LLM planning. This allows skipping the expensive planning phase for
    well-defined, high-confidence intents.

    The router is designed to be conservative:
    - Returns None if no strong match is found
    - Multiple intents matching triggers ambiguity detection
    - Only returns matches above the configured confidence threshold

    Attributes:
        patterns: List of intent pattern configurations
        compiled_patterns: Pre-compiled regex patterns for performance
    """

    def __init__(
        self,
        patterns: list[IntentPattern] | None = None,
        custom_patterns: list[dict[str, Any]] | None = None,
    ):
        """
        Initialize the intent router.

        Args:
            patterns: List of IntentPattern configurations.
                     Uses DEFAULT_INTENT_PATTERNS if not provided.
            custom_patterns: Additional patterns as dicts (from YAML config).
                           Will be merged with base patterns.
        """
        self._patterns = patterns or DEFAULT_INTENT_PATTERNS.copy()

        # Add custom patterns from config
        if custom_patterns:
            self._patterns.extend(self._parse_custom_patterns(custom_patterns))

        # Pre-compile regex patterns for performance
        self._compiled: dict[str, list[re.Pattern[str]]] = {}
        for pattern_config in self._patterns:
            self._compiled[pattern_config.intent] = [
                re.compile(p, re.IGNORECASE) for p in pattern_config.patterns
            ]

        logger.debug(
            "intent_router.initialized",
            pattern_count=len(self._patterns),
        )

    def _parse_custom_patterns(
        self, custom_patterns: list[dict[str, Any]]
    ) -> list[IntentPattern]:
        """Parse custom patterns from YAML config format."""
        result: list[IntentPattern] = []
        for cfg in custom_patterns:
            if "intent" in cfg and "patterns" in cfg and "skill" in cfg:
                result.append(
                    IntentPattern(
                        intent=cfg["intent"],
                        patterns=cfg["patterns"],
                        skill=cfg["skill"],
                        min_confidence=cfg.get("min_confidence", 0.4),
                    )
                )
        return result

    def classify(self, message: str) -> IntentMatch | None:
        """
        Classify a message into an intent.

        Returns the best matching intent if confidence is above threshold,
        None if ambiguous or no strong match.

        Args:
            message: User message to classify

        Returns:
            IntentMatch with intent, confidence, and skill name,
            or None if no confident match found
        """
        if not message or not message.strip():
            return None

        message_lower = message.lower()
        matches: list[IntentMatch] = []

        for pattern_config in self._patterns:
            compiled_patterns = self._compiled[pattern_config.intent]
            matched_patterns: list[str] = []

            for i, compiled_pattern in enumerate(compiled_patterns):
                if compiled_pattern.search(message_lower):
                    matched_patterns.append(pattern_config.patterns[i])

            if matched_patterns:
                confidence = len(matched_patterns) / len(compiled_patterns)
                if confidence >= pattern_config.min_confidence:
                    matches.append(
                        IntentMatch(
                            intent=pattern_config.intent,
                            confidence=confidence,
                            skill_name=pattern_config.skill,
                            matched_patterns=matched_patterns,
                        )
                    )

        if not matches:
            logger.debug("intent.no_match", message_prefix=message[:50])
            return None

        # Sort by confidence descending
        matches.sort(key=lambda m: m.confidence, reverse=True)

        # Check for ambiguity: if top two matches have similar confidence
        if len(matches) > 1:
            top_confidence = matches[0].confidence
            second_confidence = matches[1].confidence
            if abs(top_confidence - second_confidence) < 0.15:
                logger.debug(
                    "intent.ambiguous",
                    intent_a=matches[0].intent,
                    confidence_a=round(top_confidence, 2),
                    intent_b=matches[1].intent,
                    confidence_b=round(second_confidence, 2),
                )
                return None

        best_match = matches[0]
        logger.info(
            "intent.classified",
            intent=best_match.intent,
            confidence=round(best_match.confidence, 2),
            skill_name=best_match.skill_name,
        )
        return best_match

    def add_pattern(self, pattern: IntentPattern) -> None:
        """
        Add a new intent pattern configuration.

        Args:
            pattern: IntentPattern to add
        """
        self._patterns.append(pattern)
        self._compiled[pattern.intent] = [
            re.compile(p, re.IGNORECASE) for p in pattern.patterns
        ]

    def get_patterns_for_intent(self, intent: str) -> list[str] | None:
        """Get the patterns configured for a specific intent."""
        for pattern_config in self._patterns:
            if pattern_config.intent == intent:
                return pattern_config.patterns
        return None

    def list_intents(self) -> list[str]:
        """List all configured intent names."""
        return [p.intent for p in self._patterns]

    def get_skill_for_intent(self, intent: str) -> str | None:
        """Get the skill name mapped to an intent."""
        for pattern_config in self._patterns:
            if pattern_config.intent == intent:
                return pattern_config.skill
        return None


def create_intent_router_from_config(
    config: dict[str, Any] | None = None,
) -> FastIntentRouter:
    """
    Create a FastIntentRouter from plugin/agent configuration.

    Args:
        config: Configuration dict with optional 'intent_router' section

    Returns:
        Configured FastIntentRouter instance
    """
    if not config:
        return FastIntentRouter()

    router_config = config.get("intent_router", {})
    custom_patterns = router_config.get("patterns", [])

    # Check if we should use only custom patterns or merge with defaults
    use_defaults = router_config.get("include_defaults", True)

    if use_defaults:
        return FastIntentRouter(custom_patterns=custom_patterns)
    else:
        parsed_patterns = []
        for cfg in custom_patterns:
            if "intent" in cfg and "patterns" in cfg and "skill" in cfg:
                parsed_patterns.append(
                    IntentPattern(
                        intent=cfg["intent"],
                        patterns=cfg["patterns"],
                        skill=cfg["skill"],
                        min_confidence=cfg.get("min_confidence", 0.4),
                    )
                )
        return FastIntentRouter(patterns=parsed_patterns)
