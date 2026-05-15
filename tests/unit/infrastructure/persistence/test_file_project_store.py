"""Tests for ``FileProjectStore``."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.infrastructure.persistence.file_project_store import FileProjectStore


@pytest.fixture
def store(tmp_path: Path) -> FileProjectStore:
    return FileProjectStore(work_dir=str(tmp_path))


class TestCreate:
    async def test_persists_and_returns(self, store: FileProjectStore, tmp_path: Path) -> None:
        project_dir = tmp_path / "tutti"
        project_dir.mkdir()

        project = await store.create(name="TuttiPaletti", path=str(project_dir))

        assert project.name == "TuttiPaletti"
        assert project.path == str(project_dir.resolve())
        assert project.project_id
        assert project.created_at is not None

        # Should be loadable.
        loaded = await store.get(project.project_id)
        assert loaded is not None
        assert loaded.name == "TuttiPaletti"

    async def test_normalises_path(self, store: FileProjectStore, tmp_path: Path) -> None:
        sub = tmp_path / "a" / ".." / "b"
        (tmp_path / "b").mkdir()
        project = await store.create(name="P", path=str(sub))
        assert project.path == str((tmp_path / "b").resolve())

    async def test_rejects_empty_name(self, store: FileProjectStore, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="name"):
            await store.create(name="   ", path=str(tmp_path))

    async def test_rejects_empty_path(self, store: FileProjectStore) -> None:
        with pytest.raises(ValueError, match="path"):
            await store.create(name="P", path="   ")

    async def test_rejects_duplicate_path(
        self, store: FileProjectStore, tmp_path: Path
    ) -> None:
        await store.create(name="First", path=str(tmp_path))
        with pytest.raises(ValueError, match="already exists"):
            await store.create(name="Second", path=str(tmp_path))


class TestList:
    async def test_returns_newest_first(
        self, store: FileProjectStore, tmp_path: Path
    ) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()

        first = await store.create(name="A", path=str(a))
        second = await store.create(name="B", path=str(b))

        projects = await store.list()
        assert [p.project_id for p in projects] == [
            second.project_id,
            first.project_id,
        ]

    async def test_empty_when_no_file(self, store: FileProjectStore) -> None:
        assert await store.list() == []


class TestDelete:
    async def test_removes_entry(self, store: FileProjectStore, tmp_path: Path) -> None:
        project = await store.create(name="P", path=str(tmp_path))
        await store.delete(project.project_id)
        assert await store.get(project.project_id) is None

    async def test_does_not_remove_directory_on_disk(
        self, store: FileProjectStore, tmp_path: Path
    ) -> None:
        marker = tmp_path / "keep-me.txt"
        marker.write_text("hi")

        project = await store.create(name="P", path=str(tmp_path))
        await store.delete(project.project_id)

        assert marker.exists(), "delete must not touch the workspace directory"

    async def test_silent_when_missing(self, store: FileProjectStore) -> None:
        # Should be idempotent — deleting a non-existent id is a no-op.
        await store.delete("does-not-exist")


class TestPersistenceAcrossInstances:
    async def test_second_instance_sees_first_writes(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        a.mkdir()

        store_one = FileProjectStore(work_dir=str(tmp_path / "store"))
        created = await store_one.create(name="A", path=str(a))

        store_two = FileProjectStore(work_dir=str(tmp_path / "store"))
        loaded = await store_two.get(created.project_id)

        assert loaded is not None
        assert loaded.path == str(a.resolve())

    async def test_concurrent_creates_with_same_path_only_one_wins(
        self, tmp_path: Path
    ) -> None:
        """Lock must be shared across instances pointing at the same file.

        ``get_project_store()`` rebuilds the store per request, so a
        per-instance lock would let two concurrent POSTs both pass
        the duplicate-path check.
        """
        import asyncio

        target = tmp_path / "shared-target"
        target.mkdir()

        async def attempt(name: str) -> Exception | None:
            store = FileProjectStore(work_dir=str(tmp_path / "store"))
            try:
                await store.create(name=name, path=str(target))
                return None
            except ValueError as exc:
                return exc

        results = await asyncio.gather(
            attempt("A"), attempt("B"), attempt("C")
        )
        # Exactly one create wins; the other two see "already exists".
        successes = [r for r in results if r is None]
        failures = [r for r in results if isinstance(r, ValueError)]
        assert len(successes) == 1
        assert len(failures) == 2
        assert all("already exists" in str(e) for e in failures)
