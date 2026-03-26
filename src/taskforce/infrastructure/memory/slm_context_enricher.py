"""SLM-based context enricher.

Generates associative, generative context from long-term memories via a
small language model (SLM) before the agent's ReAct loop starts.  The
enricher produces a concise "intuition" block covering three categories:

- **Factual associations** — relevant facts from past interactions.
- **Behavioural patterns** — recognised user preferences and habits.
- **Dreamed optimisations** — insights produced during dream cycles.

The output is injected into the system prompt so the main LLM can
leverage it without an explicit tool call.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from taskforce.core.domain.context_enricher import EnricherConfig, EnrichmentCategory
from taskforce.core.domain.memory import MemoryRecord
from taskforce.core.interfaces.llm import LLMProviderProtocol

logger = structlog.get_logger(__name__)

_ENRICHMENT_PROMPT = """\
You are an internal memory assistant.  Given the user's current mission \
and a set of long-term memories, produce a SHORT intuition block that \
the main agent can use.

Respond ONLY with the categories requested below.  Be concise — at most \
3 bullet points per category.  If a category has nothing relevant, omit it.

### Requested categories
{categories}

### Current mission
{mission}

### Relevant memories
{memories}

### Output format
Return a plain-text block using this structure (omit empty sections):

[Factual]
- ...

[Behavioral]
- ...

[Dreamed]
- ...
"""

_CATEGORY_DESCRIPTIONS: dict[EnrichmentCategory, str] = {
    EnrichmentCategory.FACTUAL: (
        "Factual: past facts, decisions, or events relevant to the mission."
    ),
    EnrichmentCategory.BEHAVIORAL: (
        "Behavioral: recognised user preferences, habits, or communication style."
    ),
    EnrichmentCategory.DREAMED: (
        "Dreamed: optimisations or creative insights generated during dream/sleep cycles."
    ),
}


def _format_memories(memories: list[MemoryRecord], limit: int = 15) -> str:
    """Format memory records into a compact text block.

    Args:
        memories: Records to format.
        limit: Maximum number of records to include.

    Returns:
        Newline-separated memory summaries.
    """
    if not memories:
        return "(no memories available)"

    lines: list[str] = []
    for mem in memories[:limit]:
        tags = ", ".join(mem.tags) if mem.tags else ""
        tag_suffix = f" [{tags}]" if tags else ""
        lines.append(f"- ({mem.kind.value}) {mem.content}{tag_suffix}")
    return "\n".join(lines)


def _build_category_text(categories: list[EnrichmentCategory]) -> str:
    """Build the category instruction text for the prompt."""
    return "\n".join(
        f"- {_CATEGORY_DESCRIPTIONS[cat]}" for cat in categories if cat in _CATEGORY_DESCRIPTIONS
    )


class SLMContextEnricher:
    """Context enricher using a small language model.

    Satisfies :class:`~taskforce.core.interfaces.context_enricher.ContextEnricherProtocol`.
    """

    def __init__(
        self,
        llm_provider: LLMProviderProtocol,
        config: EnricherConfig,
    ) -> None:
        self._llm = llm_provider
        self._config = config

    async def enrich(
        self,
        mission: str,
        memories: list[MemoryRecord],
        session_context: dict[str, Any] | None = None,
    ) -> str | None:
        """Generate associative context for the current mission.

        Returns a formatted prompt section or ``None`` on failure/timeout.
        """
        if not self._config.enabled:
            return None

        if not memories:
            logger.debug("context_enricher.skipped", reason="no_memories")
            return None

        prompt = _ENRICHMENT_PROMPT.format(
            categories=_build_category_text(self._config.categories),
            mission=mission,
            memories=_format_memories(memories),
        )

        try:
            result = await asyncio.wait_for(
                self._call_slm(prompt),
                timeout=self._config.timeout_seconds,
            )
        except TimeoutError:
            logger.warning(
                "context_enricher.timeout",
                timeout_seconds=self._config.timeout_seconds,
            )
            return None
        except Exception as exc:
            logger.warning("context_enricher.failed", error=str(exc))
            return None

        if not result:
            return None

        logger.info(
            "context_enricher.completed",
            output_length=len(result),
        )
        return f"\n\n## Internal Intuition\n{result}"

    async def _call_slm(self, prompt: str) -> str | None:
        """Call the SLM and return the raw text response.

        Args:
            prompt: The enrichment prompt.

        Returns:
            Raw text content or ``None`` on empty response.
        """
        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            model=self._config.model_alias,
        )
        content: str = response.get("content", "").strip()
        return content or None
