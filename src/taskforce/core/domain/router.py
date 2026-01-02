"""
Fast-Path Query Router

This module implements a query classification system to determine whether
incoming queries should follow the full planning path (new missions) or
the fast path (follow-up questions).

The router uses a combination of heuristic rules and optional LLM classification
to make routing decisions. This significantly reduces latency for simple
follow-up questions by bypassing the TodoList creation overhead.

Architecture:
    User Query → QueryRouter.classify() → RouteDecision
                                           ├── NEW_MISSION → Full Planning Path
                                           └── FOLLOW_UP → Fast Path (Direct Execution)
"""

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog


class RouteDecision(Enum):
    """Classification of incoming query."""

    NEW_MISSION = "new_mission"  # Requires full planning
    FOLLOW_UP = "follow_up"  # Can be handled directly


@dataclass
class RouterContext:
    """
    Context for routing decision.

    Attributes:
        query: The user's incoming query
        has_active_todolist: Whether a todolist exists for current session
        todolist_completed: Whether the active todolist is fully completed
        previous_results: Results from previous step executions
        conversation_history: Recent conversation messages
        last_query: The previous user query (for continuity detection)
    """

    query: str
    has_active_todolist: bool
    todolist_completed: bool
    previous_results: list[dict[str, Any]]
    conversation_history: list[dict[str, str]]
    last_query: str | None = None


@dataclass
class RouterResult:
    """
    Result of query classification.

    Attributes:
        decision: The routing decision (NEW_MISSION or FOLLOW_UP)
        confidence: Confidence level of the decision (0.0-1.0)
        rationale: Explanation of why this decision was made
    """

    decision: RouteDecision
    confidence: float
    rationale: str


class QueryRouter:
    """
    Classifies incoming queries to determine optimal execution path.

    Uses a combination of heuristic rules and optional LLM classification
    to decide whether a query is a follow-up (fast path) or new mission
    (full planning).

    The router prioritizes:
    1. Context availability (no context = new mission)
    2. New mission patterns (explicit creation/analysis requests)
    3. Follow-up patterns (question words, pronouns, short queries)
    4. Query length (long queries suggest new missions)
    """

    # Heuristic patterns indicating follow-up questions
    FOLLOW_UP_PATTERNS = [
        r"^(was|wie|wo|wer|wann|warum|welche|erkläre|zeig|sag)\b",  # German question words
        r"^(what|how|where|who|when|why|which|explain|show|tell)\b",  # English question words
        r"^(und|also|dann|außerdem|noch|mehr)\b",  # Continuation words (DE)
        r"^(and|also|then|additionally|more|another)\b",  # Continuation words (EN)
        r"^(das|dies|es|sie|er)\b",  # Pronouns referencing previous context (DE)
        r"^(that|this|it|they|he|she)\b",  # Pronouns referencing previous context (EN)
        r"^\?",  # Starts with question mark (sometimes used in follow-ups)
        r"^(ja|nein|yes|no|ok|okay)\b",  # Simple responses/confirmations
    ]

    # Patterns indicating new missions (override follow-up detection)
    NEW_MISSION_PATTERNS = [
        r"(erstelle|create|build|implement|schreibe|write)\b.*\b(projekt|project|app|api|service)",
        r"(analysiere|analyze|untersuche|investigate)\b.*\b(daten|data|logs|files)",
        r"(migriere|migrate|konvertiere|convert|refaktor|refactor)",
        r"\b(step[s]?|schritt[e]?|plan|workflow)\b",
        r"(start|begin|initiate|initialize)\b.*\b(new|neues|fresh)",
    ]

    # Maximum query length for follow-up (longer queries likely new missions)
    MAX_FOLLOW_UP_LENGTH = 100

    def __init__(
        self,
        llm_provider=None,
        use_llm_classification: bool = False,
        max_follow_up_length: int = 100,
        logger=None,
    ):
        """
        Initialize QueryRouter.

        Args:
            llm_provider: Optional LLM provider for classification fallback
            use_llm_classification: Whether to use LLM for uncertain cases
            max_follow_up_length: Maximum query length for follow-up classification
            logger: Optional logger instance
        """
        self.llm_provider = llm_provider
        self.use_llm_classification = use_llm_classification
        self.MAX_FOLLOW_UP_LENGTH = max_follow_up_length
        self.logger = logger or structlog.get_logger().bind(component="router")

    async def classify(self, context: RouterContext) -> RouterResult:
        """
        Classify query as follow-up or new mission.

        Uses heuristics first, falls back to LLM if configured and uncertain.
        Now includes "bold" fast-start heuristic for simple queries without context.

        Args:
            context: RouterContext with query and session information

        Returns:
            RouterResult with decision, confidence, and rationale
        """
        # Heuristik für "Quick Start"
        # Prüfen auf typische "Single-Step"-Fragen (Wer, Was, Wie, Liste...)
        start_words = ["wer", "was", "wie", "wo", "wann", "welche", "zeig", "liste",
                       "who", "what", "how", "where", "when", "which", "show", "list"]

        query_lower = context.query.lower().strip()
        is_simple_start = any(query_lower.startswith(w) for w in start_words)
        is_short = len(context.query.split()) < 20

        # Rule 1: No active context
        if not context.has_active_todolist and not context.previous_results:
            # NEUE LOGIK: Wenn es wie eine simple Frage aussieht -> Fast Path riskieren!
            if is_simple_start and is_short:
                self.logger.debug(
                    "router_fast_start_heuristic",
                    query=context.query,
                )
                return RouterResult(
                    decision=RouteDecision.FOLLOW_UP,  # Wir nutzen FOLLOW_UP als Signal für "Direkt"
                    confidence=0.85,
                    rationale="Initial query looks simple enough for fast path",
                )

            # Sonst: Sicherer Weg über Planung
            self.logger.debug(
                "router_no_context",
                query_preview=context.query[:50],
            )
            return RouterResult(
                decision=RouteDecision.NEW_MISSION,
                confidence=1.0,
                rationale="No active context - starting new mission",
            )

        # Rule 2: Completed todolist -> check follow-up
        if context.todolist_completed:
            if self._references_previous_context(context) or (is_simple_start and is_short):
                self.logger.debug(
                    "router_references_context",
                    query_preview=context.query[:50],
                )
                return RouterResult(
                    decision=RouteDecision.FOLLOW_UP,
                    confidence=0.8,
                    rationale="Query references context or is simple follow-up",
                )

        # Rule 3: Apply heuristic patterns
        heuristic_result = self._apply_heuristics(context)
        if heuristic_result.confidence >= 0.7:
            self.logger.debug(
                "router_heuristic_match",
                decision=heuristic_result.decision.value,
                confidence=heuristic_result.confidence,
                rationale=heuristic_result.rationale[:50],
            )
            return heuristic_result

        # Rule 4: Optional LLM classification for uncertain cases
        if self.use_llm_classification and self.llm_provider:
            self.logger.debug(
                "router_llm_fallback",
                query_preview=context.query[:50],
            )
            return await self._llm_classify(context)

        # Fallback
        self.logger.debug(
            "router_default_new_mission",
            query_preview=context.query[:50],
        )
        return RouterResult(
            decision=RouteDecision.NEW_MISSION,
            confidence=0.5,
            rationale="Defaulting to full planning",
        )

    def _references_previous_context(self, context: RouterContext) -> bool:
        """
        Check if query contains references to previous results.

        Args:
            context: RouterContext with query and previous results

        Returns:
            True if query appears to reference previous context
        """
        query_lower = context.query.lower()

        # Check for pronouns and demonstratives
        reference_words = [
            "das",
            "dies",
            "es",
            "davon",
            "darüber",
            "darin",
            "that",
            "this",
            "it",
            "those",
            "these",
            "there",
        ]

        for word in reference_words:
            if re.search(rf"\b{word}\b", query_lower):
                return True

        # Check if query mentions entities from previous results
        for result in context.previous_results[-3:]:  # Last 3 results
            if isinstance(result.get("result"), dict):
                # Extract entity names from results
                result_text = str(result.get("result", "")).lower()
                # Simple overlap check
                query_words = set(query_lower.split())
                result_words = set(result_text.split())
                overlap = query_words & result_words
                if len(overlap) >= 2:  # At least 2 overlapping words
                    return True

        return False

    def _apply_heuristics(self, context: RouterContext) -> RouterResult:
        """
        Apply rule-based heuristics for classification.

        Args:
            context: RouterContext with query and session information

        Returns:
            RouterResult based on heuristic matching
        """
        query = context.query.strip()
        query_lower = query.lower()

        # Check for new mission patterns first (higher priority)
        for pattern in self.NEW_MISSION_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return RouterResult(
                    decision=RouteDecision.NEW_MISSION,
                    confidence=0.9,
                    rationale=f"Query matches new mission pattern: {pattern}",
                )

        # Short query + question pattern = likely follow-up
        if len(query) <= self.MAX_FOLLOW_UP_LENGTH:
            for pattern in self.FOLLOW_UP_PATTERNS:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    return RouterResult(
                        decision=RouteDecision.FOLLOW_UP,
                        confidence=0.8,
                        rationale=f"Short query matches follow-up pattern: {pattern}",
                    )

        # Long query = likely new mission
        if len(query) > self.MAX_FOLLOW_UP_LENGTH * 2:
            return RouterResult(
                decision=RouteDecision.NEW_MISSION,
                confidence=0.7,
                rationale="Long query suggests new mission",
            )

        # Uncertain
        return RouterResult(
            decision=RouteDecision.NEW_MISSION,
            confidence=0.5,
            rationale="No strong heuristic match",
        )

    async def _llm_classify(self, context: RouterContext) -> RouterResult:
        """
        Use LLM for query classification (fallback for uncertain cases).

        Args:
            context: RouterContext with query and session information

        Returns:
            RouterResult based on LLM classification
        """
        prompt = f"""Classify this query as either FOLLOW_UP or NEW_MISSION.

FOLLOW_UP: Simple question about previous results, clarification, or continuation.
NEW_MISSION: New task requiring planning, multi-step execution, or fresh context.

Previous context summary: {context.previous_results[-1] if context.previous_results else 'None'}
Query: "{context.query}"

Respond with JSON: {{"decision": "FOLLOW_UP" or "NEW_MISSION", "confidence": 0.0-1.0, "rationale": "..."}}
"""

        try:
            result = await self.llm_provider.complete(
                messages=[{"role": "user", "content": prompt}],
                model="fast",  # Use faster/cheaper model for classification
                response_format={"type": "json_object"},
                temperature=0.1,
            )

            if result.get("success"):
                data = json.loads(result["content"])
                return RouterResult(
                    decision=RouteDecision(data["decision"].lower()),
                    confidence=data["confidence"],
                    rationale=data["rationale"],
                )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning(
                "llm_classification_parse_error",
                error=str(e),
            )

        # Fallback on LLM failure
        return RouterResult(
            decision=RouteDecision.NEW_MISSION,
            confidence=0.5,
            rationale="LLM classification failed - defaulting to new mission",
        )

