"""Post-mission learning service.

After a mission completes successfully, this service asks a fast LLM to
extract any *reusable* knowledge (working data sources, recurring
entities, workflow rules) and writes it as wiki pages. Transient facts
(today's weather, the next train time) are deliberately ignored — the
prompt is shaped to capture only what would still be useful next week.

The service is side-effect-only with respect to the wiki. It never
raises; on error it logs and returns a LearningResult with
``skipped_reason``. Callers can therefore await it on the hot path
without try/except wrapping.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from taskforce.core.domain.wiki_page import WikiPage
from taskforce.core.interfaces.learning import LearningResult
from taskforce.core.interfaces.wiki_store import WikiStoreProtocol

logger = structlog.get_logger(__name__)


_EXTRACTION_PROMPT = """\
You are a knowledge-extraction assistant for a long-running personal AI \
butler. Your job is to look at one finished mission and decide whether it \
produced any *reusable* fact that should go into the butler's long-term \
wiki.

Reusable means: still useful in a week or a month, for similar future \
questions. This wiki is long-term memory, not a scratchpad. NOT reusable: \
the specific answer to a one-off question, temporary working state, tool \
errors, concrete email drafts, case logs, fall-log artifacts, "I read file X", \
or anything that only matters for this single run.

Concrete reusable categories you should harvest:
- working data source for a recurring topic (URL/API/site that delivered \
  the answer reliably) → kind: concepts
- a recurring entity the user uses (a route, a counterparty, a tool) → \
  kind: entities or preferences
- a workflow rule the user expressed or that emerged from the mission \
  → kind: concepts or preferences
- a specific number/ID that looks reusable (account, customer-id, \
  recurring date) → kind: entities

Output strict JSON with the schema:
{{
  "facts": [
    {{
      "kind": "concepts" | "entities" | "preferences",
      "slug": "lowercase-hyphenated-slug-no-umlauts",
      "title": "Human Title",
      "body": "Markdown body, terse, with a ## Quelle section if a URL \
applies",
      "tags": ["tag1", "tag2"],
      "future_relevance": "One sentence explaining why this will matter later"
    }}
  ]
}}

Rules:
- Output an empty ``facts`` array if nothing reusable was learned.
- At most 3 facts per mission. Quality over quantity.
- Slug: lowercase, hyphens, ASCII only (ae/oe/ue/ss for umlauts).
- Body must be markdown, ≤ 600 characters.
- Do not invent facts. Only extract what the mission's tool results \
  actually demonstrate.
- Only write facts with explicit future relevance. If the candidate is \
  merely ephemeral run state, leave ``facts`` empty.

Mission text:
{mission}

Mission transcript (truncated):
{transcript}
"""


class LlmExtractingLearningService:
    """LearningStrategyProtocol implementation backed by an LLM.

    Args:
        wiki_store: Where to write extracted pages.
        llm_service: LiteLLMService-like object exposing
            ``complete_json(prompt, system_prompt, model)``.
        model_alias: LLM alias used for extraction (default ``fast``).
        max_transcript_chars: Cap on the transcript blob fed to the LLM.
    """

    def __init__(
        self,
        wiki_store: WikiStoreProtocol,
        llm_service: Any,
        model_alias: str = "fast",
        max_transcript_chars: int = 8000,
    ) -> None:
        self._wiki = wiki_store
        self._llm = llm_service
        self._model = model_alias
        self._max_chars = max_transcript_chars

    async def learn_from_mission(
        self,
        mission: str,
        messages: list[dict[str, Any]],
        session_id: str,
    ) -> LearningResult:
        try:
            transcript = self._render_transcript(messages)
            if not transcript.strip():
                return LearningResult(0, [], "empty transcript")

            prompt = _EXTRACTION_PROMPT.format(
                mission=mission, transcript=transcript
            )
            response = await self._llm.complete_json(
                prompt=prompt,
                model=self._model,
                temperature=0.0,
            )
            if not response.get("success"):
                logger.warning(
                    "learning.llm_failed",
                    session_id=session_id,
                    error=response.get("error"),
                )
                return LearningResult(0, [], "llm call failed")

            facts = (response.get("data") or {}).get("facts") or []
            if not isinstance(facts, list):
                return LearningResult(0, [], "invalid llm output shape")

            written: list[str] = []
            for fact in facts[:3]:
                if not self._is_future_relevant_fact(fact):
                    logger.info(
                        "learning.fact_rejected",
                        session_id=session_id,
                        reason="not_future_relevant",
                        title=str(fact.get("title", ""))[:80]
                        if isinstance(fact, dict)
                        else "",
                    )
                    continue
                page_name = await self._persist_fact(fact, session_id)
                if page_name:
                    written.append(page_name)

            if written:
                await self._wiki.append_log(
                    f"learning: extracted {len(written)} fact(s) "
                    f"from session {session_id[:8]} → {', '.join(written)}"
                )
                logger.info(
                    "learning.completed",
                    session_id=session_id,
                    pages_written=written,
                )

            return LearningResult(
                extracted_count=len(facts),
                pages_written=written,
            )
        except Exception as e:
            logger.warning(
                "learning.skipped",
                session_id=session_id,
                error=repr(e),
            )
            return LearningResult(0, [], f"exception: {e!r}")

    def _is_future_relevant_fact(self, fact: dict[str, Any]) -> bool:
        """Reject obvious scratchpad/case-specific candidates before wiki writes."""
        if not isinstance(fact, dict):
            return False
        text = " ".join(
            str(fact.get(key, ""))
            for key in ("kind", "slug", "title", "body", "future_relevance")
        ).lower()
        if not text.strip():
            return False
        ephemeral_patterns = (
            r"\bemail draft\b",
            r"\bmail draft\b",
            r"\bconcrete draft\b",
            r"\bcase log\b",
            r"\bfall-log\b",
            r"\btool error\b",
            r"\btool failure\b",
            r"\btemporary\b",
            r"\bscratchpad\b",
            r"\bthis session\b",
            r"\bthis run\b",
            r"\bi read file\b",
            r"\bfile_read\b",
            r"\bzwischenstand\b",
            r"\bfallakte\b",
        )
        if any(re.search(pattern, text) for pattern in ephemeral_patterns):
            return False
        future_relevance = str(fact.get("future_relevance", "")).strip()
        if not future_relevance:
            return False
        return len(future_relevance) >= 12

    async def _persist_fact(
        self, fact: dict[str, Any], session_id: str
    ) -> str | None:
        kind = str(fact.get("kind", "")).strip().lower()
        slug = str(fact.get("slug", "")).strip()
        title = str(fact.get("title", "")).strip()
        body = str(fact.get("body", "")).strip()
        tags = fact.get("tags") or []

        if kind not in {"concepts", "entities", "preferences"}:
            return None
        if not slug or not title or not body:
            return None

        name = f"{kind}/{slug}"
        existing = await self._wiki.get_page(name)
        if existing is not None:
            await self._wiki.update_section(
                name=name,
                section="Aktualisierung",
                content=f"- {body}",
                mode="append",
            )
            return name

        page = WikiPage(
            name=name,
            title=title,
            body=body,
            tags=[str(t) for t in tags if isinstance(t, str)][:8],
        )
        await self._wiki.write_page(page)
        return name

    def _render_transcript(self, messages: list[dict[str, Any]]) -> str:
        """Compact the message list into a plain-text transcript.

        We keep role + content for user/assistant/tool messages and
        stringify the tool args/results so the LLM can see what
        sources were tried and which actually worked. The output is
        truncated to ``max_transcript_chars``.
        """
        lines: list[str] = []
        for msg in messages:
            role = str(msg.get("role", "")).lower()
            if role == "system":
                continue
            content = msg.get("content")
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False)[:800]
            elif content is None:
                content = ""
            else:
                content = str(content)[:800]

            tool_calls = msg.get("tool_calls") or []
            if tool_calls:
                lines.append(f"[{role}] tool_calls={json.dumps(tool_calls)[:400]}")
            if content:
                lines.append(f"[{role}] {content}")

        transcript = "\n".join(lines)
        if len(transcript) > self._max_chars:
            head = transcript[: self._max_chars // 2]
            tail = transcript[-self._max_chars // 2 :]
            transcript = head + "\n…[truncated]…\n" + tail
        return transcript
