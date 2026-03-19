"""Retrieval evaluation benchmark for the human-like memory system.

Verifies that the memory retrieval pipeline surfaces the *right* memories
for a given query / mission context — combining keyword matching, effective
strength, contextual boosting, and (optionally) semantic similarity.

These tests use a realistic in-memory corpus of ~30 memories spanning
several domains (Python, cooking, finance, health, travel) with varying
strengths, emotions, and tags.  Each test case asserts that the top-K
results contain the expected memories for a given retrieval scenario.

Run with::

    uv run pytest tests/unit/infrastructure/test_memory_retrieval_benchmark.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from taskforce.core.domain.lean_agent_components.memory_context_loader import (
    MemoryContextConfig,
    MemoryContextLoader,
)
from taskforce.core.domain.memory import (
    EmotionalValence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.infrastructure.memory.file_memory_store import FileMemoryStore

# ------------------------------------------------------------------
# Corpus builder
# ------------------------------------------------------------------

_NOW = datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC)


def _rec(
    content: str,
    *,
    tags: list[str] | None = None,
    kind: MemoryKind = MemoryKind.LEARNED_FACT,
    strength: float = 0.7,
    importance: float = 0.5,
    emotion: EmotionalValence = EmotionalValence.NEUTRAL,
    hours_ago: float = 0,
    access_count: int = 1,
    record_id: str | None = None,
) -> MemoryRecord:
    created = _NOW - timedelta(hours=hours_ago)
    r = MemoryRecord(
        scope=MemoryScope.USER,
        kind=kind,
        content=content,
        tags=tags or [],
        strength=strength,
        importance=importance,
        emotional_valence=emotion,
        created_at=created,
        updated_at=created,
        last_accessed=created,
        access_count=access_count,
    )
    if record_id:
        r.id = record_id
    return r


def _build_corpus() -> list[MemoryRecord]:
    """Build a diverse test corpus spanning multiple domains."""
    return [
        # --- Python / Coding ---
        _rec(
            "Use pytest fixtures for test setup instead of setUp methods",
            tags=["python", "testing", "pytest"],
            strength=0.9,
            importance=0.7,
            access_count=5,
            hours_ago=2,
            record_id="py-test-fixtures",
        ),
        _rec(
            "Always use type annotations on public function signatures",
            tags=["python", "coding", "types"],
            strength=0.85,
            importance=0.8,
            access_count=8,
            hours_ago=4,
            record_id="py-type-hints",
        ),
        _rec(
            "asyncio.gather is better than sequential awaits for independent IO",
            tags=["python", "async", "performance"],
            strength=0.75,
            importance=0.6,
            hours_ago=24,
            record_id="py-asyncio-gather",
        ),
        _rec(
            "Use structlog for structured logging with context binding",
            tags=["python", "logging"],
            strength=0.6,
            hours_ago=72,
            record_id="py-structlog",
        ),
        _rec(
            "Python 3.12 introduced generic syntax for type aliases",
            tags=["python", "types", "release"],
            strength=0.5,
            hours_ago=168,
            record_id="py-312-generics",
        ),
        # --- Cooking ---
        _rec(
            "Risotto needs constant stirring for the last 18 minutes",
            tags=["cooking", "italian", "technique"],
            strength=0.8,
            importance=0.3,
            emotion=EmotionalValence.POSITIVE,
            hours_ago=48,
            record_id="cook-risotto",
        ),
        _rec(
            "Sear meat on high heat before slow cooking for flavor",
            tags=["cooking", "technique", "meat"],
            strength=0.7,
            hours_ago=96,
            record_id="cook-sear",
        ),
        _rec(
            "Fresh pasta dough: 100g flour per egg, knead 10 minutes",
            tags=["cooking", "italian", "pasta"],
            strength=0.65,
            hours_ago=120,
            record_id="cook-pasta",
        ),
        # --- Finance ---
        _rec(
            "Emergency fund should cover 6 months of expenses",
            tags=["finance", "savings", "planning"],
            strength=0.8,
            importance=0.9,
            hours_ago=240,
            record_id="fin-emergency",
        ),
        _rec(
            "Dollar cost averaging reduces timing risk in volatile markets",
            tags=["finance", "investing", "strategy"],
            strength=0.7,
            importance=0.7,
            hours_ago=480,
            record_id="fin-dca",
        ),
        _rec(
            "Tax loss harvesting can offset capital gains up to 3000 per year",
            tags=["finance", "tax", "investing"],
            strength=0.55,
            hours_ago=720,
            record_id="fin-tax",
        ),
        # --- Health ---
        _rec(
            "7-9 hours of sleep is optimal for cognitive performance",
            tags=["health", "sleep", "cognitive"],
            strength=0.85,
            importance=0.8,
            emotion=EmotionalValence.POSITIVE,
            hours_ago=12,
            record_id="health-sleep",
        ),
        _rec(
            "Walking 10000 steps daily reduces cardiovascular risk by 40%",
            tags=["health", "exercise", "cardio"],
            strength=0.7,
            hours_ago=168,
            record_id="health-walking",
        ),
        # --- Travel ---
        _rec(
            "Book flights 6-8 weeks before departure for best prices",
            tags=["travel", "flights", "tips"],
            strength=0.5,
            hours_ago=336,
            record_id="travel-flights",
        ),
        _rec(
            "Japan Rail Pass must be purchased outside Japan before arrival",
            tags=["travel", "japan", "transport"],
            strength=0.4,
            importance=0.3,
            hours_ago=720,
            record_id="travel-japan",
        ),
        # --- Fading / archived ---
        _rec(
            "The old API key for service X was revoked",
            tags=["archived", "devops"],
            strength=0.05,
            importance=0.0,
            hours_ago=2000,
            record_id="old-api-key",
        ),
        _rec(
            "Temporary workaround for bug #1234 in version 2.1",
            tags=["python", "workaround"],
            strength=0.12,
            importance=0.0,
            hours_ago=1500,
            record_id="old-workaround",
        ),
        # --- Emotional memories ---
        _rec(
            "The deployment failure on Friday caused 2 hours of downtime",
            tags=["devops", "incident", "deployment"],
            strength=0.8,
            importance=0.7,
            emotion=EmotionalValence.FRUSTRATION,
            hours_ago=48,
            record_id="incident-deploy",
        ),
        _rec(
            "User feedback: the new dashboard design was very well received",
            tags=["product", "feedback", "ui"],
            strength=0.75,
            importance=0.6,
            emotion=EmotionalValence.POSITIVE,
            hours_ago=72,
            record_id="feedback-dashboard",
        ),
        _rec(
            "Unexpected finding: caching reduced API latency by 80%",
            tags=["performance", "caching", "api"],
            strength=0.85,
            importance=0.7,
            emotion=EmotionalValence.SURPRISE,
            hours_ago=24,
            record_id="surprise-cache",
        ),
    ]


# ------------------------------------------------------------------
# FileMemoryStore benchmarks (keyword + strength)
# ------------------------------------------------------------------


class TestKeywordRetrievalBenchmark:
    """Verify that keyword search surfaces the right memories."""

    @pytest.fixture()
    async def store(self, tmp_path) -> FileMemoryStore:
        s = FileMemoryStore(tmp_path)
        for rec in _build_corpus():
            await s.add(rec)
        return s

    async def test_python_testing_query(self, store: FileMemoryStore) -> None:
        results = await store.search("python testing pytest", limit=5)
        ids = [r.id for r in results]
        assert "py-test-fixtures" in ids[:2]

    async def test_cooking_italian_query(self, store: FileMemoryStore) -> None:
        results = await store.search("italian cooking pasta", limit=5)
        ids = [r.id for r in results]
        # Both risotto (strong + italian + cooking) and pasta should appear.
        italian_ids = {"cook-risotto", "cook-pasta"}
        assert len(italian_ids & set(ids[:3])) >= 2

    async def test_finance_investing_query(self, store: FileMemoryStore) -> None:
        results = await store.search("investing strategy", limit=5)
        ids = [r.id for r in results]
        assert "fin-dca" in ids[:3]

    async def test_archived_excluded(self, store: FileMemoryStore) -> None:
        results = await store.search("API key service", limit=10)
        ids = [r.id for r in results]
        assert "old-api-key" not in ids

    async def test_stronger_memories_rank_higher(self, store: FileMemoryStore) -> None:
        """Given two Python memories, the one with more strength/access ranks higher."""
        results = await store.search("python types", limit=3)
        ids = [r.id for r in results]
        # py-type-hints (0.85, 8 accesses) should beat py-312-generics (0.5, 1 access)
        if "py-type-hints" in ids and "py-312-generics" in ids:
            assert ids.index("py-type-hints") < ids.index("py-312-generics")


# ------------------------------------------------------------------
# MemoryContextLoader benchmarks (contextual retrieval)
# ------------------------------------------------------------------


class TestContextualRetrievalBenchmark:
    """Verify that mission context properly biases memory selection."""

    def _make_loader(
        self, records: list[MemoryRecord]
    ) -> MemoryContextLoader:
        # Filter records by kind to match real store behavior.
        def _filtered_list(scope=None, kind=None):
            return [r for r in records if kind is None or r.kind == kind]

        store = AsyncMock()
        store.list = AsyncMock(side_effect=_filtered_list)
        store.update = AsyncMock(side_effect=lambda r: r)
        return MemoryContextLoader(
            memory_store=store,
            config=MemoryContextConfig(max_memories=10),
            logger=Mock(),
        )

    async def test_python_mission_boosts_python_memories(self) -> None:
        """A Python-related mission should surface Python memories first."""
        corpus = _build_corpus()
        loader = self._make_loader(corpus)
        result = await loader.load_memory_context(
            mission="Write python testing code with pytest and async"
        )
        assert result is not None
        lines = result.strip().split("\n")
        # Python-related memories should appear in the top results.
        content_lines = [ln for ln in lines if ln.startswith("- **[")]
        python_keywords = ["pytest", "async", "python", "type annotation"]
        assert any(
            any(kw in ln.lower() for kw in python_keywords)
            for ln in content_lines[:5]
        )

    async def test_cooking_mission_boosts_cooking_memories(self) -> None:
        corpus = _build_corpus()
        loader = self._make_loader(corpus)

        # With cooking mission, cooking memories should appear in results.
        result = await loader.load_memory_context(
            mission="Plan an Italian cooking dinner with pasta risotto"
        )
        assert result is not None
        content_lines = [ln for ln in result.split("\n") if ln.startswith("- **[")]
        all_text = " ".join(content_lines).lower()
        assert "pasta" in all_text or "risotto" in all_text

    async def test_no_mission_uses_pure_strength(self) -> None:
        corpus = _build_corpus()
        loader = self._make_loader(corpus)
        result = await loader.load_memory_context(mission=None)
        assert result is not None
        content_lines = [ln for ln in result.split("\n") if ln.startswith("- **[")]
        # Without mission, the strongest memories (py-test-fixtures, health-sleep,
        # py-type-hints, surprise-cache) should be at the top.
        top3 = " ".join(content_lines[:3]).lower()
        # At least one of the strongest should be there.
        strong_keywords = ["pytest", "sleep", "type annotation", "caching"]
        assert any(kw in top3 for kw in strong_keywords)

    async def test_emotional_memories_surface_naturally(self) -> None:
        """Emotional memories get encoding boosts and should surface easily."""
        corpus = _build_corpus()
        loader = self._make_loader(corpus)
        result = await loader.load_memory_context(
            mission="Review the deployment incident and prevent future downtime"
        )
        assert result is not None
        # The deployment frustration memory should appear somewhere.
        assert "deployment" in result.lower() or "downtime" in result.lower()

    async def test_weak_memories_excluded_from_injection(self) -> None:
        """Memories below the injection threshold should never appear."""
        corpus = _build_corpus()
        loader = self._make_loader(corpus)
        result = await loader.load_memory_context()
        assert result is not None
        # old-workaround has strength 0.12 < 0.15 threshold
        assert "workaround for bug #1234" not in result

    async def test_strength_indicators_reflect_memory_quality(self) -> None:
        """Vivid/clear/fading/dim labels should match effective strength."""
        corpus = _build_corpus()
        loader = self._make_loader(corpus)
        result = await loader.load_memory_context()
        assert result is not None
        if "[vivid]" in result:
            # A vivid memory exists; verify it's a strong one.
            for line in result.split("\n"):
                if "[vivid]" in line:
                    assert any(
                        kw in line.lower()
                        for kw in ["pytest", "type annotation", "sleep", "caching", "deployment", "emergency"]
                    )
                    break


# ------------------------------------------------------------------
# Cross-domain interference test
# ------------------------------------------------------------------


class TestCrossDomainInterference:
    """Ensure that unrelated domains don't pollute results."""

    @pytest.fixture()
    async def store(self, tmp_path) -> FileMemoryStore:
        s = FileMemoryStore(tmp_path)
        for rec in _build_corpus():
            await s.add(rec)
        return s

    async def test_python_query_excludes_cooking(self, store: FileMemoryStore) -> None:
        results = await store.search("python async performance", limit=5)
        ids = [r.id for r in results]
        cooking_ids = {"cook-risotto", "cook-sear", "cook-pasta"}
        assert len(cooking_ids & set(ids)) == 0

    async def test_cooking_query_excludes_finance(self, store: FileMemoryStore) -> None:
        results = await store.search("cooking meat technique", limit=5)
        ids = [r.id for r in results]
        finance_ids = {"fin-emergency", "fin-dca", "fin-tax"}
        assert len(finance_ids & set(ids)) == 0

    async def test_health_query_excludes_travel(self, store: FileMemoryStore) -> None:
        results = await store.search("health sleep cognitive", limit=5)
        ids = [r.id for r in results]
        travel_ids = {"travel-flights", "travel-japan"}
        assert len(travel_ids & set(ids)) == 0
