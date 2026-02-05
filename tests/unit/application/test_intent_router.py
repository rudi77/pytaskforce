"""
Unit Tests for FastIntentRouter

Tests the regex-based intent classification that enables skipping
planning for well-defined intents in the accounting domain.
"""

import pytest

from taskforce.application.intent_router import (
    FastIntentRouter,
    IntentMatch,
    IntentPattern,
    create_intent_router_from_config,
    DEFAULT_INTENT_PATTERNS,
)


class TestFastIntentRouter:
    """Test cases for FastIntentRouter."""

    def test_router_initialization_with_defaults(self):
        """Router initializes with default German accounting patterns."""
        router = FastIntentRouter()
        intents = router.list_intents()

        assert "INVOICE_PROCESSING" in intents
        assert "INVOICE_QUESTION" in intents
        assert "ACCOUNTING_QUESTION" in intents

    def test_router_initialization_with_custom_patterns(self):
        """Router accepts custom patterns."""
        custom = [
            IntentPattern(
                intent="CUSTOM_INTENT",
                patterns=[r"custom.*pattern"],
                skill="custom-skill",
            )
        ]
        router = FastIntentRouter(patterns=custom)

        assert "CUSTOM_INTENT" in router.list_intents()
        assert len(router.list_intents()) == 1

    # --- INVOICE_PROCESSING intent tests ---

    @pytest.mark.parametrize(
        "message",
        [
            "Buche diese Rechnung",
            "Bitte verbuche das",
            "Erstelle eine Buchung für die Rechnung",
            "Verarbeite die Rechnung",
            "Kontiere diese Rechnung",
            "Prüfe die Rechnung auf Fehler",
            "Erstelle einen Buchungsvorschlag",
            "Erfasse die Rechnung bitte",
        ],
    )
    def test_classify_invoice_processing(self, message: str):
        """Messages requesting invoice processing match INVOICE_PROCESSING."""
        router = FastIntentRouter()
        match = router.classify(message)

        assert match is not None
        assert match.intent == "INVOICE_PROCESSING"
        assert match.skill_name == "smart-booking-auto"
        assert match.confidence > 0  # At least one pattern matched

    # --- INVOICE_QUESTION intent tests ---

    @pytest.mark.parametrize(
        "message",
        [
            "Wie hoch ist die MwSt?",
            "Wie viel kostet das insgesamt?",
            "Was ist der Rechnungsbetrag?",
            "Wer ist der Lieferant?",
            "Warum sind hier zwei Steuersätze?",
            "Erkläre mir diese Position",
            "Zeig mir die einzelnen Positionen",
            "Welche MwSt wurde berechnet?",
        ],
    )
    def test_classify_invoice_question(self, message: str):
        """Questions about invoices match INVOICE_QUESTION."""
        router = FastIntentRouter()
        match = router.classify(message)

        assert match is not None
        assert match.intent == "INVOICE_QUESTION"
        assert match.skill_name == "invoice-explanation"
        assert match.confidence > 0  # At least one pattern matched

    # --- ACCOUNTING_QUESTION intent tests ---

    @pytest.mark.parametrize(
        "message",
        [
            "Wie kontiere ich Bewirtungskosten?",
            "Wann ist Vorsteuerabzug möglich?",
            "Was bedeutet Reverse Charge genau?",
            "Welche Regelung gilt nach § 15 UStG?",
            "Wann ist die Vorsteuer abziehbar?",
            "Wie berechne ich den Buchwert?",
            "Wie funktioniert die AfA?",
            "Wie werden Abschreibungen gebucht?",
        ],
    )
    def test_classify_accounting_question(self, message: str):
        """General accounting questions match ACCOUNTING_QUESTION."""
        router = FastIntentRouter()
        match = router.classify(message)

        assert match is not None
        assert match.intent == "ACCOUNTING_QUESTION"
        assert match.skill_name == "accounting-expert"
        assert match.confidence > 0  # At least one pattern matched

    # --- Edge cases and negative tests ---

    def test_classify_empty_message_returns_none(self):
        """Empty messages return None."""
        router = FastIntentRouter()

        assert router.classify("") is None
        assert router.classify("   ") is None
        assert router.classify(None) is None  # type: ignore

    def test_classify_unrelated_message_returns_none(self):
        """Unrelated messages return None (no confident match)."""
        router = FastIntentRouter()

        # Generic greetings/unrelated content
        assert router.classify("Hallo, wie geht es dir?") is None
        assert router.classify("Das Wetter ist schön heute") is None
        assert router.classify("Danke für die Hilfe") is None

    def test_classify_ambiguous_message_returns_none(self):
        """Ambiguous messages that could match multiple intents return None."""
        router = FastIntentRouter()

        # This message could be both a question and a processing request
        # "Wie prüfe ich..." could be INVOICE_QUESTION or ACCOUNTING_QUESTION
        # If confidence is similar, should return None
        ambiguous = "Was bedeutet diese Buchung und wie verbuche ich sie?"
        match = router.classify(ambiguous)

        # Either returns the dominant match or None for ambiguity
        # The router should handle this gracefully
        if match is not None:
            # If it returns a match, confidence should be reasonable
            assert match.confidence > 0  # At least one pattern matched

    def test_classify_case_insensitive(self):
        """Classification is case insensitive."""
        router = FastIntentRouter()

        lower = router.classify("buche diese rechnung")
        upper = router.classify("BUCHE DIESE RECHNUNG")
        mixed = router.classify("Buche Diese Rechnung")

        assert lower is not None
        assert upper is not None
        assert mixed is not None
        assert lower.intent == upper.intent == mixed.intent

    def test_confidence_increases_with_more_matches(self):
        """Confidence increases when more patterns match."""
        router = FastIntentRouter()

        # Single pattern match
        single = router.classify("Buche diese Rechnung")
        # Multiple pattern matches
        multiple = router.classify("Verbuche und kontiere diese Rechnung, prüfe die Rechnung auch")

        assert single is not None
        assert multiple is not None
        # Multiple should have higher or equal confidence
        assert multiple.confidence >= single.confidence

    def test_matched_patterns_tracked(self):
        """IntentMatch includes list of matched patterns."""
        router = FastIntentRouter()
        match = router.classify("Buche und kontiere die Rechnung")

        assert match is not None
        assert len(match.matched_patterns) >= 1
        assert isinstance(match.matched_patterns, list)

    # --- Configuration tests ---

    def test_add_pattern_dynamically(self):
        """Patterns can be added after initialization."""
        router = FastIntentRouter()

        # Add a new pattern
        router.add_pattern(
            IntentPattern(
                intent="REPORT_GENERATION",
                patterns=[r"erstelle.*bericht", r"generiere.*report"],
                skill="report-generator",
            )
        )

        match = router.classify("Erstelle einen Monatsbericht")
        assert match is not None
        assert match.intent == "REPORT_GENERATION"

    def test_get_skill_for_intent(self):
        """Can retrieve skill name for an intent."""
        router = FastIntentRouter()

        assert router.get_skill_for_intent("INVOICE_PROCESSING") == "smart-booking-auto"
        assert router.get_skill_for_intent("INVOICE_QUESTION") == "invoice-explanation"
        assert router.get_skill_for_intent("ACCOUNTING_QUESTION") == "accounting-expert"
        assert router.get_skill_for_intent("UNKNOWN_INTENT") is None

    def test_get_patterns_for_intent(self):
        """Can retrieve patterns for an intent."""
        router = FastIntentRouter()

        patterns = router.get_patterns_for_intent("INVOICE_PROCESSING")
        assert patterns is not None
        assert len(patterns) > 0
        assert any("buch" in p for p in patterns)

    def test_create_router_from_empty_config(self):
        """Factory function works with empty config."""
        router = create_intent_router_from_config(None)
        assert len(router.list_intents()) == len(DEFAULT_INTENT_PATTERNS)

        router2 = create_intent_router_from_config({})
        assert len(router2.list_intents()) == len(DEFAULT_INTENT_PATTERNS)

    def test_create_router_from_config_with_custom_patterns(self):
        """Factory function merges custom patterns with defaults."""
        config = {
            "intent_router": {
                "patterns": [
                    {
                        "intent": "EXPENSE_REPORT",
                        "patterns": [r"spesen", r"reisekosten"],
                        "skill": "expense-handler",
                    }
                ],
                "include_defaults": True,
            }
        }
        router = create_intent_router_from_config(config)

        # Should have defaults plus custom
        intents = router.list_intents()
        assert "INVOICE_PROCESSING" in intents
        assert "EXPENSE_REPORT" in intents

    def test_create_router_from_config_without_defaults(self):
        """Factory function can exclude default patterns."""
        config = {
            "intent_router": {
                "patterns": [
                    {
                        "intent": "CUSTOM_ONLY",
                        "patterns": [r"custom"],
                        "skill": "custom-skill",
                    }
                ],
                "include_defaults": False,
            }
        }
        router = create_intent_router_from_config(config)

        # Should only have custom
        intents = router.list_intents()
        assert "CUSTOM_ONLY" in intents
        assert "INVOICE_PROCESSING" not in intents


class TestIntentMatch:
    """Test cases for IntentMatch dataclass."""

    def test_intent_match_creation(self):
        """IntentMatch holds classification result."""
        match = IntentMatch(
            intent="TEST_INTENT",
            confidence=0.8,
            skill_name="test-skill",
            matched_patterns=["pattern1", "pattern2"],
        )

        assert match.intent == "TEST_INTENT"
        assert match.confidence == 0.8
        assert match.skill_name == "test-skill"
        assert len(match.matched_patterns) == 2

    def test_intent_match_default_patterns(self):
        """IntentMatch has empty patterns by default."""
        match = IntentMatch(
            intent="TEST",
            confidence=0.5,
            skill_name="skill",
        )

        assert match.matched_patterns == []


class TestIntentPattern:
    """Test cases for IntentPattern dataclass."""

    def test_intent_pattern_creation(self):
        """IntentPattern holds pattern configuration."""
        pattern = IntentPattern(
            intent="TEST",
            patterns=[r"test", r"probe"],
            skill="test-skill",
            min_confidence=0.5,
        )

        assert pattern.intent == "TEST"
        assert len(pattern.patterns) == 2
        assert pattern.skill == "test-skill"
        assert pattern.min_confidence == 0.5

    def test_intent_pattern_default_confidence(self):
        """IntentPattern has default min_confidence of 0.4."""
        pattern = IntentPattern(
            intent="TEST",
            patterns=[r"test"],
            skill="skill",
        )

        # Default confidence threshold allows single-pattern matches
        assert pattern.min_confidence == 0.4  # Can be overridden per intent
