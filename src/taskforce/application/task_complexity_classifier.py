"""
Task complexity classifier for dynamic model selection.

Classifies incoming missions as ``simple`` or ``complex`` using a fast,
cheap LLM call (e.g. Haiku). The result drives the LLM Router's
``complexity_override``, which downgrades the model for simple tasks.

Simple = single-step lookup, read, format, translate, basic Q&A.
Complex = multi-step reasoning, research, analysis, code generation, planning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from taskforce.core.interfaces.llm import LLMProviderProtocol

logger = structlog.get_logger(__name__)

_CLASSIFICATION_SYSTEM_PROMPT = (
    "Classify the user's task as 'simple' or 'complex'.\n"
    "Simple: single-step lookup, read email, read file, format text, "
    "translate, basic factual Q&A, calendar lookup, set reminder.\n"
    "Complex: multi-step reasoning, research and comparison, analysis, "
    "code generation, document processing (PDF, invoice, receipt, Rechnung, Beleg), "
    "planning, multi-tool workflows, tasks with attachments or files to process, "
    "delegation to specialist agents, bookkeeping (einpflegen, buchen, Buchung), "
    "data extraction from documents, Excel data entry from prior context.\n"
    'Reply ONLY with JSON: {"level": "simple" or "complex", '
    '"confidence": 0.0-1.0, "reason": "brief explanation"}'
)


@dataclass(frozen=True)
class ComplexityClassification:
    """Result of a task complexity classification."""

    level: str  # "simple" | "complex"
    confidence: float  # 0.0–1.0
    reason: str  # Brief explanation

    @property
    def is_simple(self) -> bool:
        """Whether the task was classified as simple."""
        return self.level == "simple"


_COMPLEX_FALLBACK = ComplexityClassification(
    level="complex", confidence=0.0, reason="fallback (classification failed)"
)


class TaskComplexityClassifier:
    """Classify mission complexity using a fast LLM call.

    Uses ``complete_json`` with the configured classification model
    (typically Haiku) to determine whether a mission is simple or complex.
    On any failure, defaults to ``complex`` to avoid accidentally
    downgrading a hard task.

    Args:
        llm_provider: LLM provider (usually the LLMRouter, which will
            resolve the classification model alias).
        classification_model: Model alias to use for the classification
            call itself (default: ``"fast"``).
        max_mission_chars: Maximum characters of mission text to send
            to the classifier (default: 500).
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

    async def classify(self, mission: str) -> ComplexityClassification:
        """Classify a mission as simple or complex.

        Args:
            mission: The user's mission text.

        Returns:
            A ``ComplexityClassification`` with level, confidence, and reason.
            On any error, returns a ``complex`` fallback.
        """
        if not mission or not mission.strip():
            return _COMPLEX_FALLBACK

        truncated = mission[: self._max_chars]

        try:
            result = await self._call_llm(truncated)
            return self._parse_result(result)
        except Exception as exc:
            logger.warning(
                "task_complexity.classification_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return _COMPLEX_FALLBACK

    async def _call_llm(self, mission_text: str) -> dict[str, Any]:
        """Make the classification LLM call."""
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

        # Fallback: use complete() and parse JSON manually
        result = await self._llm.complete(
            messages=messages,
            model=self._model,
            max_tokens=100,
        )
        content = result.get("content", "{}")
        try:
            parsed = json.loads(content)
            return {"success": True, "data": parsed}
        except json.JSONDecodeError:
            return {"success": False, "error": f"Invalid JSON: {content}"}

    def _parse_result(self, result: dict[str, Any]) -> ComplexityClassification:
        """Parse the LLM response into a ComplexityClassification."""
        if not result.get("success"):
            logger.warning(
                "task_complexity.llm_error",
                error=result.get("error", "unknown"),
            )
            return _COMPLEX_FALLBACK

        data = result.get("data", {})
        level = str(data.get("level", "complex")).lower().strip()
        if level not in ("simple", "complex"):
            level = "complex"

        try:
            confidence = float(data.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.0

        reason = str(data.get("reason", ""))[:200]

        return ComplexityClassification(
            level=level,
            confidence=confidence,
            reason=reason,
        )
