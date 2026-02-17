"""Task complexity classifier for auto-epic orchestration.

Classifies mission complexity via a lightweight LLM call to decide whether
a mission should run as a single-agent task (SIMPLE) or be escalated to
multi-agent epic orchestration (EPIC).
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from taskforce.core.domain.epic import TaskComplexity, TaskComplexityResult
from taskforce.core.interfaces.llm import LLMProviderProtocol

logger = structlog.get_logger(__name__)

CLASSIFICATION_SYSTEM_PROMPT = """\
You are a task complexity analyzer. Classify the given task as either \
"simple" (single agent) or "epic" (multi-agent planner/worker/judge pipeline).

Criteria for EPIC (multi-agent):
- The task consists of multiple independent sub-tasks
- Different files or modules must be modified in parallel
- The task requires diverse skills (e.g. research + implementation + testing)
- The task describes a project or feature with multiple components
- The estimated number of sub-tasks exceeds 3

Criteria for SIMPLE (single agent):
- The task is clearly defined and focused
- It concerns a single file, function, or concept
- Simple research, explanation, or small change
- The task can be completed in a few steps
- Answering questions, explaining code, fixing a single bug

Respond ONLY with a JSON object (no markdown fences):
{
    "complexity": "simple" or "epic",
    "reasoning": "Brief justification (one sentence)",
    "confidence": 0.0 to 1.0,
    "suggested_worker_count": 1 to 5,
    "suggested_scopes": [],
    "estimated_task_count": N
}"""

_SIMPLE_FALLBACK = TaskComplexityResult(
    complexity=TaskComplexity.SIMPLE,
    reasoning="Fallback to simple mode",
    confidence=0.0,
    suggested_worker_count=1,
    suggested_scopes=[],
    estimated_task_count=1,
)


class TaskComplexityClassifier:
    """Classifies mission complexity using a lightweight LLM call.

    On any error (LLM failure, parse error, timeout) the classifier
    falls back to SIMPLE to avoid unnecessary epic overhead.
    """

    def __init__(
        self,
        llm_provider: LLMProviderProtocol,
        model: str | None = None,
    ) -> None:
        """Initialize the classifier.

        Args:
            llm_provider: LLM provider for the classification call.
            model: Optional model alias override (e.g. "fast").
        """
        self._llm = llm_provider
        self._model = model

    async def classify(
        self,
        mission: str,
    ) -> TaskComplexityResult:
        """Classify the complexity of a mission.

        Args:
            mission: The mission description to analyze.

        Returns:
            TaskComplexityResult with classification and reasoning.
            Falls back to SIMPLE on any error.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": mission},
        ]

        try:
            result = await self._llm.complete(
                messages=messages,
                model=self._model,
                temperature=0.0,
                max_tokens=300,
            )
        except Exception:
            logger.warning("task_complexity.llm_error", mission=mission[:100])
            return _SIMPLE_FALLBACK

        if not result.get("success"):
            logger.warning(
                "task_complexity.llm_failed",
                error=result.get("error", "unknown"),
            )
            return _SIMPLE_FALLBACK

        return self._parse_response(result.get("content", ""))

    def _parse_response(self, content: str) -> TaskComplexityResult:
        """Parse the LLM JSON response into a TaskComplexityResult.

        Args:
            content: Raw LLM response text (expected JSON).

        Returns:
            Parsed TaskComplexityResult or SIMPLE fallback on parse error.
        """
        try:
            # Strip potential markdown code fences
            text = content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("task_complexity.parse_error", content=content[:200])
            return _SIMPLE_FALLBACK

        try:
            complexity = TaskComplexity(data.get("complexity", "simple"))
        except ValueError:
            complexity = TaskComplexity.SIMPLE

        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        return TaskComplexityResult(
            complexity=complexity,
            reasoning=str(data.get("reasoning", "")),
            confidence=confidence,
            suggested_worker_count=max(1, min(10, int(data.get("suggested_worker_count", 1)))),
            suggested_scopes=[str(s) for s in data.get("suggested_scopes", [])],
            estimated_task_count=max(1, int(data.get("estimated_task_count", 1))),
        )
