"""LLM-based topic change detection for conversation segmentation.

Analyses incoming messages to determine whether the user has changed topic.
Uses a fast/cheap model via the LLM Router (hint: ``summarizing``) to
minimise latency (~200ms).

Usage::

    detector = TopicDetector(llm_provider)
    result = await detector.detect(
        message="Let's talk about the budget now",
        current_label="Project timeline discussion",
        recent_messages=[...],
    )
    if result is not None:
        # Topic changed — result.label is the new topic
        conversation.start_topic(result.label, message_idx)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DETECTION_PROMPT = """\
You are a topic-change detector. Given the current conversation topic, \
the last few messages, and a new message, determine whether the user \
has changed topic.

Current topic: {current_label}

Recent messages:
{recent_context}

New message: {message}

Respond with JSON only:
{{"changed": true/false, "label": "new topic label if changed", "confidence": 0.0-1.0}}

Rules:
- Only set "changed" to true if the new message clearly introduces a different subject.
- Minor follow-up questions on the same theme are NOT a topic change.
- If the user explicitly says "let's talk about X" or introduces a completely new subject, that IS a change.
- "label" should be a short (3-8 word) descriptive label for the NEW topic.
- "confidence" reflects how certain you are that a topic change occurred.
"""


@dataclass(frozen=True)
class TopicChange:
    """Result of topic change detection.

    Attributes:
        label: Short descriptive label for the new topic.
        confidence: How confident the detector is (0.0–1.0).
    """

    label: str
    confidence: float


class TopicDetector:
    """Detects topic changes in conversation messages using an LLM.

    Args:
        llm_provider: LLM provider implementing ``LLMProviderProtocol``.
        confidence_threshold: Minimum confidence to report a change (default 0.7).
        model_hint: Model hint for the LLM Router (default ``"summarizing"``
            for fast/cheap inference).
    """

    def __init__(
        self,
        llm_provider: Any,
        *,
        confidence_threshold: float = 0.7,
        model_hint: str = "summarizing",
    ) -> None:
        self._llm = llm_provider
        self._threshold = confidence_threshold
        self._model_hint = model_hint

    async def detect(
        self,
        message: str,
        current_label: str | None,
        recent_messages: list[dict[str, Any]] | None = None,
    ) -> TopicChange | None:
        """Detect whether a new message introduces a topic change.

        Args:
            message: The new user message.
            current_label: Label of the currently active topic segment.
                ``None`` means no topic is active yet — always returns a new topic.
            recent_messages: Last 3–5 messages for context (``role``/``content`` dicts).

        Returns:
            ``TopicChange`` if a change was detected above the confidence
            threshold, ``None`` otherwise.
        """
        # If there is no current topic, always start one.
        if current_label is None:
            label = await self._generate_label(message, recent_messages)
            return TopicChange(label=label, confidence=1.0)

        recent_context = self._format_recent(recent_messages)

        prompt = _DETECTION_PROMPT.format(
            current_label=current_label,
            recent_context=recent_context or "(no prior messages)",
            message=message,
        )

        try:
            result = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model_hint,
            )

            content = result.get("content", "") or ""
            parsed = self._parse_response(content)

            if parsed is None:
                return None

            changed, label, confidence = parsed

            if not changed or confidence < self._threshold:
                return None

            return TopicChange(label=label, confidence=confidence)

        except Exception:
            logger.debug("topic_detector.detection_failed", exc_info=True)
            return None

    async def generate_summary(
        self,
        messages: list[dict[str, Any]],
        label: str,
    ) -> str:
        """Generate a brief summary for a closing topic segment.

        Args:
            messages: Messages belonging to the topic segment.
            label: The topic label.

        Returns:
            A 1–2 sentence summary of the conversation segment.
        """
        content_parts = []
        for msg in messages[-10:]:  # Limit to last 10 messages
            role = msg.get("role", "?")
            text = msg.get("content", "")
            if text:
                content_parts.append(f"{role}: {text[:200]}")

        prompt = (
            f"Summarize the following conversation about '{label}' in 1-2 sentences:\n\n"
            + "\n".join(content_parts)
        )

        try:
            result = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model_hint,
            )
            return (result.get("content", "") or "").strip() or f"Discussion about {label}"
        except Exception:
            logger.debug("topic_detector.summary_failed", exc_info=True)
            return f"Discussion about {label}"

    async def _generate_label(
        self,
        message: str,
        recent_messages: list[dict[str, Any]] | None,
    ) -> str:
        """Generate a topic label for the first message."""
        prompt = (
            "Generate a short (3-8 word) topic label for this conversation message. "
            "Respond with just the label, no quotes or explanation.\n\n"
            f"Message: {message[:300]}"
        )
        try:
            result = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model_hint,
            )
            label = (result.get("content", "") or "").strip().strip('"\'')
            return label or "General conversation"
        except Exception:
            return "General conversation"

    @staticmethod
    def _format_recent(messages: list[dict[str, Any]] | None) -> str:
        """Format recent messages for the detection prompt."""
        if not messages:
            return ""
        lines = []
        for msg in messages[-3:]:
            role = msg.get("role", "?")
            content = msg.get("content", "")[:150]
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)

    @staticmethod
    def _parse_response(content: str) -> tuple[bool, str, float] | None:
        """Parse the JSON response from the LLM.

        Returns:
            ``(changed, label, confidence)`` tuple or ``None`` on parse failure.
        """
        # Try to extract JSON from the response
        content = content.strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            )

        try:
            data = json.loads(content)
            changed = bool(data.get("changed", False))
            label = str(data.get("label", ""))
            confidence = float(data.get("confidence", 0.0))
            return (changed, label, confidence)
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.debug("topic_detector.parse_failed", content=content[:100])
            return None
