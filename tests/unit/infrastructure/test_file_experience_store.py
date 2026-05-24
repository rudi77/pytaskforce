"""Tests for FileExperienceStore."""

import asyncio
from datetime import UTC, datetime

import pytest

from taskforce.core.domain.experience import ConsolidationResult, SessionExperience
from taskforce.infrastructure.memory.file_experience_store import FileExperienceStore


@pytest.fixture
def store(tmp_path):
    return FileExperienceStore(tmp_path / "experiences")


def _make_experience(session_id: str = "sess-1", **kwargs) -> SessionExperience:
    return SessionExperience(
        session_id=session_id,
        profile=kwargs.get("profile", "dev"),
        mission=kwargs.get("mission", "Test mission"),
        started_at=datetime.now(UTC),
        **{k: v for k, v in kwargs.items() if k not in ("profile", "mission")},
    )


class TestFileExperienceStore:
    async def test_save_and_load(self, store):
        exp = _make_experience("sess-1")
        await store.save_experience(exp)
        loaded = await store.load_experience("sess-1")
        assert loaded is not None
        assert loaded.session_id == "sess-1"
        assert loaded.mission == "Test mission"

    async def test_load_nonexistent_returns_none(self, store):
        result = await store.load_experience("nonexistent")
        assert result is None

    async def test_list_experiences(self, store):
        await store.save_experience(_make_experience("sess-1"))
        await store.save_experience(_make_experience("sess-2"))
        results = await store.list_experiences(limit=10)
        assert len(results) == 2

    async def test_list_experiences_limit(self, store):
        for i in range(5):
            await store.save_experience(_make_experience(f"sess-{i}"))
        results = await store.list_experiences(limit=3)
        assert len(results) == 3

    async def test_list_unprocessed_only(self, store):
        exp1 = _make_experience("sess-1")
        exp2 = _make_experience("sess-2")
        exp2.processed_by = ["consol-1"]
        await store.save_experience(exp1)
        await store.save_experience(exp2)

        results = await store.list_experiences(unprocessed_only=True)
        assert len(results) == 1
        assert results[0].session_id == "sess-1"

    async def test_mark_processed(self, store):
        await store.save_experience(_make_experience("sess-1"))
        await store.mark_processed(["sess-1"], "consol-abc")

        loaded = await store.load_experience("sess-1")
        assert "consol-abc" in loaded.processed_by

    async def test_mark_processed_idempotent(self, store):
        await store.save_experience(_make_experience("sess-1"))
        await store.mark_processed(["sess-1"], "consol-abc")
        await store.mark_processed(["sess-1"], "consol-abc")

        loaded = await store.load_experience("sess-1")
        assert loaded.processed_by.count("consol-abc") == 1

    async def test_delete_experience(self, store):
        await store.save_experience(_make_experience("sess-1"))
        deleted = await store.delete_experience("sess-1")
        assert deleted is True

        loaded = await store.load_experience("sess-1")
        assert loaded is None

    async def test_delete_nonexistent_returns_false(self, store):
        deleted = await store.delete_experience("nonexistent")
        assert deleted is False

    async def test_save_and_list_consolidations(self, store):
        result = ConsolidationResult(
            consolidation_id="consol-1",
            strategy="batch",
            sessions_processed=3,
            memories_created=5,
        )
        await store.save_consolidation(result)
        results = await store.list_consolidations(limit=10)
        assert len(results) == 1
        assert results[0].consolidation_id == "consol-1"

    async def test_session_id_sanitized(self, store):
        """Prevent path traversal in session IDs."""
        exp = _make_experience("../../../etc/passwd")
        await store.save_experience(exp)
        loaded = await store.load_experience("../../../etc/passwd")
        assert loaded is not None

    async def test_concurrent_mark_processed_no_lost_updates(self, store):
        """Concurrent mark_processed on the same session must not lose updates."""
        await store.save_experience(_make_experience("sess-1"))
        consol_ids = [f"consol-{i}" for i in range(20)]
        await asyncio.gather(*(store.mark_processed(["sess-1"], cid) for cid in consol_ids))
        loaded = await store.load_experience("sess-1")
        assert loaded is not None
        assert sorted(loaded.processed_by) == sorted(consol_ids)

    async def test_concurrent_save_experience_does_not_corrupt_file(self, store):
        """Concurrent save_experience on the same session yields a valid JSON file."""
        await asyncio.gather(
            *(
                store.save_experience(_make_experience("sess-1", mission=f"mission {i}"))
                for i in range(20)
            )
        )
        # File must be a valid SessionExperience after the storm — content
        # is "one of the saves", but never half-written / corrupt.
        loaded = await store.load_experience("sess-1")
        assert loaded is not None
        assert loaded.session_id == "sess-1"
        assert loaded.mission.startswith("mission ")

    async def test_delete_experience_releases_lock(self, store):
        """delete_experience must drop the per-session lock to bound memory.

        Regression test for the lock-dict leak: long-running daemons that
        churn through unique session ids would otherwise accumulate one
        asyncio.Lock per session forever.
        """
        for i in range(50):
            await store.save_experience(_make_experience(f"sess-{i}"))
            await store.delete_experience(f"sess-{i}")
        assert store._locks == {}

        # Deleting a never-seen session must not leak either.
        await store.delete_experience("never-existed")
        assert store._locks == {}

    async def test_lock_key_sanitized_serializes_aliased_ids(self, store):
        """Session ids that sanitize to the same file must share a lock.

        Without sanitizing the lock key, ``"a/b"`` and ``"a_b"`` would
        map to the same file but to two different asyncio.Locks, so
        concurrent writes could interleave atomic_write_text calls and
        leave a torn temp-file scenario behind.
        """
        await asyncio.gather(
            store.save_experience(_make_experience("a/b", mission="slash")),
            store.save_experience(_make_experience("a_b", mission="underscore")),
        )
        loaded = await store.load_experience("a/b")
        assert loaded is not None
        assert loaded.mission in {"slash", "underscore"}
        # Only one lock entry for the aliased pair.
        assert "a_b" in store._locks
        assert "a/b" not in store._locks
