from __future__ import annotations

from taskforce.core.domain.context_builder import ContextBuilder
from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.domain.planning.evidence_cache import (
    cached_file_read_result,
    invalidate_file_read_evidence,
    record_file_read_evidence,
)


def test_file_read_records_compact_evidence() -> None:
    state: dict = {}

    entry = record_file_read_evidence(
        state,
        {"path": "notes/input.txt"},
        {
            "success": True,
            "path": "D:\\work\\notes\\input.txt",
            "content": "important facts\nmore facts",
            "size": 26,
        },
        step=3,
    )

    assert entry is not None
    assert entry["normalized_path"] == "d:/work/notes/input.txt"
    assert entry["step"] == 3
    assert entry["preview"].startswith("important facts")
    assert entry["normalized_path"] in state["evidence_cache"]
    assert state["file_read_metrics"] == {"repeat_count": 0, "unique_paths": 1}


def test_context_pack_includes_already_read_sources() -> None:
    state: dict = {}
    record_file_read_evidence(
        state,
        {"path": "mail.eml"},
        {
            "success": True,
            "path": "D:\\cases\\mail.eml",
            "content": "Mueller Bau asks for pallet clarification.",
            "size": 43,
        },
        step=1,
    )

    builder = ContextBuilder(ContextPolicy(max_items=5, max_chars_per_item=500))
    context = builder.build_context_pack(
        mission="Write local draft",
        state=state,
        messages=[],
    )

    assert "Already read this run" in context
    assert "D:\\cases\\mail.eml" in context
    assert "Mueller Bau asks" in context


def test_cached_file_read_result_reuses_cached_content() -> None:
    state: dict = {}
    record_file_read_evidence(
        state,
        {"path": "D:\\cases\\mail.eml"},
        {
            "success": True,
            "path": "D:\\cases\\mail.eml",
            "content": "full mail content",
            "size": 17,
        },
        step=1,
    )

    result = cached_file_read_result(state, {"path": "d:/cases/mail.eml"})

    assert result == {
        "success": True,
        "cached": True,
        "path": "D:\\cases\\mail.eml",
        "content": "full mail content",
        "size": 17,
    }


def test_invalidate_file_read_evidence_removes_cached_path() -> None:
    state: dict = {}
    record_file_read_evidence(
        state,
        {"path": "D:\\cases\\draft.md"},
        {
            "success": True,
            "path": "D:\\cases\\draft.md",
            "content": "old draft",
            "size": 9,
        },
        step=1,
    )

    invalidate_file_read_evidence(state, "d:/cases/draft.md")

    cached = cached_file_read_result(state, {"path": "D:\\cases\\draft.md"})
    assert cached is None
