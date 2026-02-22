"""Tests for memory domain models: MemoryScope, MemoryKind, MemoryRecord."""

from datetime import UTC, datetime
from time import sleep

import pytest

from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope


class TestMemoryScope:
    """Tests for MemoryScope enum."""

    def test_values(self) -> None:
        assert MemoryScope.SESSION.value == "session"
        assert MemoryScope.PROFILE.value == "profile"
        assert MemoryScope.USER.value == "user"
        assert MemoryScope.ORG.value == "org"

    def test_is_str_enum(self) -> None:
        assert isinstance(MemoryScope.SESSION, str)
        assert MemoryScope.SESSION == "session"

    def test_member_count(self) -> None:
        assert len(MemoryScope) == 4

    def test_lookup_by_value(self) -> None:
        assert MemoryScope("session") == MemoryScope.SESSION
        assert MemoryScope("org") == MemoryScope.ORG

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            MemoryScope("invalid")


class TestMemoryKind:
    """Tests for MemoryKind enum."""

    def test_values(self) -> None:
        assert MemoryKind.SHORT_TERM.value == "short_term"
        assert MemoryKind.LONG_TERM.value == "long_term"
        assert MemoryKind.TOOL_RESULT.value == "tool_result"
        assert MemoryKind.EPIC_LOG.value == "epic_log"
        assert MemoryKind.PREFERENCE.value == "preference"
        assert MemoryKind.LEARNED_FACT.value == "learned_fact"

    def test_is_str_enum(self) -> None:
        assert isinstance(MemoryKind.SHORT_TERM, str)
        assert MemoryKind.SHORT_TERM == "short_term"

    def test_member_count(self) -> None:
        assert len(MemoryKind) == 6

    def test_lookup_by_value(self) -> None:
        assert MemoryKind("preference") == MemoryKind.PREFERENCE
        assert MemoryKind("learned_fact") == MemoryKind.LEARNED_FACT


class TestMemoryRecord:
    """Tests for MemoryRecord dataclass."""

    def test_create_minimal(self) -> None:
        record = MemoryRecord(
            scope=MemoryScope.SESSION,
            kind=MemoryKind.SHORT_TERM,
            content="Remember this",
        )
        assert record.scope == MemoryScope.SESSION
        assert record.kind == MemoryKind.SHORT_TERM
        assert record.content == "Remember this"
        assert record.id  # auto-generated, non-empty
        assert record.tags == []
        assert record.metadata == {}
        assert isinstance(record.created_at, datetime)
        assert isinstance(record.updated_at, datetime)

    def test_create_full(self) -> None:
        now = datetime.now(UTC)
        record = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.PREFERENCE,
            content="Prefers dark mode",
            id="custom-id",
            tags=["ui", "preference"],
            metadata={"source": "chat"},
            created_at=now,
            updated_at=now,
        )
        assert record.id == "custom-id"
        assert record.tags == ["ui", "preference"]
        assert record.metadata["source"] == "chat"
        assert record.created_at == now
        assert record.updated_at == now

    def test_id_is_unique(self) -> None:
        r1 = MemoryRecord(scope=MemoryScope.SESSION, kind=MemoryKind.SHORT_TERM, content="a")
        r2 = MemoryRecord(scope=MemoryScope.SESSION, kind=MemoryKind.SHORT_TERM, content="b")
        assert r1.id != r2.id

    def test_id_is_hex_string(self) -> None:
        record = MemoryRecord(
            scope=MemoryScope.SESSION,
            kind=MemoryKind.SHORT_TERM,
            content="test",
        )
        # uuid4().hex produces a 32-char hex string
        assert len(record.id) == 32
        int(record.id, 16)  # Should not raise if valid hex

    def test_touch_updates_timestamp(self) -> None:
        record = MemoryRecord(
            scope=MemoryScope.SESSION,
            kind=MemoryKind.LONG_TERM,
            content="test",
        )
        original_updated = record.updated_at
        original_created = record.created_at
        # Small sleep to ensure timestamp difference
        sleep(0.01)
        record.touch()
        assert record.updated_at > original_updated
        assert record.created_at == original_created

    def test_tags_default_is_independent(self) -> None:
        """Default tags list should be independent per instance."""
        r1 = MemoryRecord(scope=MemoryScope.SESSION, kind=MemoryKind.SHORT_TERM, content="a")
        r2 = MemoryRecord(scope=MemoryScope.SESSION, kind=MemoryKind.SHORT_TERM, content="b")
        r1.tags.append("tag1")
        assert r2.tags == []

    def test_metadata_default_is_independent(self) -> None:
        """Default metadata dict should be independent per instance."""
        r1 = MemoryRecord(scope=MemoryScope.SESSION, kind=MemoryKind.SHORT_TERM, content="a")
        r2 = MemoryRecord(scope=MemoryScope.SESSION, kind=MemoryKind.SHORT_TERM, content="b")
        r1.metadata["key"] = "value"
        assert r2.metadata == {}

    def test_timestamps_are_utc(self) -> None:
        record = MemoryRecord(
            scope=MemoryScope.SESSION,
            kind=MemoryKind.SHORT_TERM,
            content="test",
        )
        assert record.created_at.tzinfo == UTC
        assert record.updated_at.tzinfo == UTC

    def test_all_scope_kind_combinations(self) -> None:
        """All scope/kind combinations should be valid."""
        for scope in MemoryScope:
            for kind in MemoryKind:
                record = MemoryRecord(scope=scope, kind=kind, content="test")
                assert record.scope == scope
                assert record.kind == kind

    def test_empty_content(self) -> None:
        record = MemoryRecord(
            scope=MemoryScope.SESSION,
            kind=MemoryKind.SHORT_TERM,
            content="",
        )
        assert record.content == ""

    def test_large_content(self) -> None:
        large = "x" * 100_000
        record = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LONG_TERM,
            content=large,
        )
        assert len(record.content) == 100_000
