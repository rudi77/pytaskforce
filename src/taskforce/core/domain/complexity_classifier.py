"""LLM-based mission-complexity classifier for adaptive planning.

Used by AdaptivePlanningStrategy (see core/domain/planning_strategy.py) to
route incoming missions to a cheap single-pass strategy (native_react) or
a multi-step planning strategy (plan_and_react, spar, plan_and_execute)
based on a small LLM classification call.

The pattern mirrors taskforce_coding_agent.task_complexity_classifier which
predates this; consolidating them is a future refactor. The classifier here
lives in core so the framework can route without depending on an agent
package (CLAUDE.md layer rules).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from taskforce.core.interfaces.llm import LLMProviderProtocol

logger = structlog.get_logger(__name__)

_CLASSIFICATION_SYSTEM_PROMPT = (
    "Classify the user's request as 'simple' or 'complex' for planning-strategy "
    "routing.\n\n"
    "SIMPLE: one-step request that can be answered with a single tool call or "
    "from knowledge alone. Examples: 'set a reminder for 8pm', 'how late is it', "
    "'17 times 23', 'what's the weather in Salzburg', 'save this contact', "
    "'read this file', 'send a short email'.\n\n"
    "COMPLEX: multi-step, requires planning, comparison, multi-source synthesis, "
    "iterative refinement, or coordinated tool use. Examples: 'compare the top 3 "
    "X under Y', 'plan my trip to Berlin', 'find unread emails about X and "
    "summarize each', 'first do A then B then check C', 'analyse this folder of "
    "PDFs'.\n\n"
    'Reply ONLY with JSON: {"level": "simple" or "complex", '
    '"confidence": 0.0-1.0, "reason": "brief one-line explanation"}'
)


@dataclass(frozen=True)
class ComplexityVerdict:
    """Outcome of a mission-complexity classification."""

    level: str  # "simple" | "complex"
    confidence: float  # 0.0-1.0, 0.0 means fallback was used
    reason: str

    @property
    def is_simple(self) -> bool:
        return self.level == "simple"


_COMPLEX_FALLBACK = ComplexityVerdict(
    level="complex", confidence=0.0, reason="fallback (classification failed)"
)


class MissionComplexityClassifier:
    """LLM-based simple/complex classifier for AdaptivePlanningStrategy.

    Uses a fast model alias (default ``fast``) so the routing overhead is
    minimal. On any failure (LLM error, malformed JSON, empty mission),
    falls back to ``complex`` so a hard task is never accidentally routed
    to a single-pass strategy.

    Args:
        llm_provider: LLM provider (LLMRouter or LiteLLMService).
        classification_model: Model alias for the classification call
            itself. Default ``fast``.
        max_mission_chars: Truncation cap before sending to the LLM.
    """

    def __init__(
        self,
        llm_provider: LLMProviderProtocol,
        *,
        classification_model: str = "fast",
        max_mission_chars: int = 500,
    ) -> None:
        self._llm = llm_provider
        self._model = classification_model
        self._max_chars = max_mission_chars

    async def classify(self, mission: str) -> ComplexityVerdict:
        """Classify the mission. Never raises - returns COMPLEX fallback on error."""
        if not mission or not mission.strip():
            return _COMPLEX_FALLBACK

        truncated = mission[: self._max_chars]
        try:
            result = await self._call_llm(truncated)
            return self._parse_result(result)
        except Exception as exc:
            logger.warning(
                "mission_complexity.classification_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return _COMPLEX_FALLBACK

    async def _call_llm(self, mission_text: str) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": _CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": mission_text},
        ]

        if hasattr(self._llm, "complete_json"):
            return await self._llm.complete_json(
                messages=messages,
                model=self._model,
                max_tokens=100,
            )

        # Fallback path for providers without complete_json.
        result = await self._llm.complete(
            messages=messages,
            model=self._model,
            max_tokens=100,
        )
        content = result.get("content", "{}") if isinstance(result, dict) else str(result)
        try:
            return {"success": True, "data": json.loads(content)}
        except json.JSONDecodeError:
            return {"success": False, "error": f"Invalid JSON: {content[:200]}"}

    def _parse_result(self, result: dict[str, Any]) -> ComplexityVerdict:
        if not result.get("success"):
            logger.warning(
                "mission_complexity.llm_error",
                error=str(result.get("error", "unknown"))[:200],
            )
            return _COMPLEX_FALLBACK

        data = result.get("data") or {}
        level = str(data.get("level", "complex")).lower().strip()
        if level not in ("simple", "complex"):
            level = "complex"

        try:
            confidence = float(data.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.0

        reason = str(data.get("reason", ""))[:200]
        return ComplexityVerdict(level=level, confidence=confidence, reason=reason)
