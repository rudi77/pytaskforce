"""Tests for the per-user store override hooks added in issue #196.

Five stores that used to be hard-wired to flat ``<work_dir>/...`` paths
now go through ``InfrastructureBuilder`` and consult a matching
override hook in ``application.infrastructure_overrides``. Without an
override installed the default flat-file behaviour is preserved
bit-for-bit (single-tenant). With one installed, the override wins
and the framework hands the construction off to the plugin — that's
how the enterprise plugin will route writes per-(tenant, user).
"""

from __future__ import annotations

import pytest

from taskforce.application.infrastructure_builder import InfrastructureBuilder
from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    set_experience_store_override,
    set_pending_channel_question_store_override,
    set_runtime_checkpoint_store_override,
    set_standing_goal_store_override,
    set_tool_result_store_override,
)


@pytest.fixture(autouse=True)
def _reset_overrides():
    clear_infrastructure_overrides()
    yield
    clear_infrastructure_overrides()


class _Sentinel:
    """Identity tag for assertions — easier than comparing builder objects."""

    def __init__(self, work_dir: str) -> None:
        self.work_dir = work_dir


def test_experience_store_default_path(tmp_path) -> None:
    store = InfrastructureBuilder().build_experience_store(work_dir=str(tmp_path))
    # Default is FileExperienceStore at <work_dir>/experiences.
    assert store is not None
    assert hasattr(store, "list_experiences") or hasattr(store, "save")


def test_experience_store_override_wins(tmp_path) -> None:
    captured: dict[str, str] = {}

    def _override(work_dir: str) -> _Sentinel:
        captured["work_dir"] = work_dir
        return _Sentinel(work_dir)

    set_experience_store_override(_override)
    result = InfrastructureBuilder().build_experience_store(work_dir=str(tmp_path))
    assert isinstance(result, _Sentinel)
    assert captured["work_dir"] == str(tmp_path)


def test_standing_goal_store_default_path(tmp_path) -> None:
    store = InfrastructureBuilder().build_standing_goal_store(work_dir=str(tmp_path))
    assert store is not None


def test_standing_goal_store_override_wins(tmp_path) -> None:
    def _override(work_dir: str) -> _Sentinel:
        return _Sentinel(work_dir)

    set_standing_goal_store_override(_override)
    result = InfrastructureBuilder().build_standing_goal_store(work_dir=str(tmp_path))
    assert isinstance(result, _Sentinel)


def test_pending_channel_question_store_default_path(tmp_path) -> None:
    store = InfrastructureBuilder().build_pending_channel_question_store(
        work_dir=str(tmp_path)
    )
    assert store is not None


def test_pending_channel_question_store_override_wins(tmp_path) -> None:
    def _override(work_dir: str) -> _Sentinel:
        return _Sentinel(work_dir)

    set_pending_channel_question_store_override(_override)
    result = InfrastructureBuilder().build_pending_channel_question_store(
        work_dir=str(tmp_path)
    )
    assert isinstance(result, _Sentinel)


def test_tool_result_store_default_path(tmp_path) -> None:
    store = InfrastructureBuilder().build_tool_result_store(work_dir=str(tmp_path))
    assert store is not None


def test_tool_result_store_override_wins(tmp_path) -> None:
    def _override(work_dir: str) -> _Sentinel:
        return _Sentinel(work_dir)

    set_tool_result_store_override(_override)
    result = InfrastructureBuilder().build_tool_result_store(work_dir=str(tmp_path))
    assert isinstance(result, _Sentinel)


def test_runtime_checkpoint_store_override_replaces_checkpoint_store(tmp_path) -> None:
    """``build_runtime_tracker`` returns an AgentRuntimeTracker whose
    ``checkpoint_store`` attribute is whatever the override returned.

    Heartbeats stay in-memory regardless — only the checkpoint side is
    per-user-routed (heartbeats are write-only and not read in
    production, see the existing comment in ``build_runtime_tracker``)."""
    captured: dict[str, str] = {}

    def _override(work_dir: str) -> _Sentinel:
        captured["work_dir"] = work_dir
        return _Sentinel(work_dir)

    set_runtime_checkpoint_store_override(_override)
    tracker = InfrastructureBuilder().build_runtime_tracker(
        config={
            "runtime": {"enabled": True, "store": "file"},
            "persistence": {"work_dir": str(tmp_path)},
        },
    )
    assert tracker is not None
    assert isinstance(tracker._checkpoint_store, _Sentinel)
    assert captured["work_dir"] == str(tmp_path)


def test_runtime_checkpoint_store_override_wins_over_memory_store_type(
    tmp_path,
) -> None:
    """The checkpoint override beats the configured ``store: memory`` too
    — the plugin already knows how to scope the store, so the YAML
    setting is informational at that point."""
    def _override(work_dir: str) -> _Sentinel:
        return _Sentinel(work_dir)

    set_runtime_checkpoint_store_override(_override)
    tracker = InfrastructureBuilder().build_runtime_tracker(
        config={
            "runtime": {"enabled": True, "store": "memory"},
            "persistence": {"work_dir": str(tmp_path)},
        },
    )
    assert isinstance(tracker._checkpoint_store, _Sentinel)


def test_clear_infrastructure_overrides_removes_per_user_store_overrides(
    tmp_path,
) -> None:
    """After ``clear_infrastructure_overrides()`` the defaults must run
    again — the fixture relies on this for test isolation."""
    set_experience_store_override(lambda _w: _Sentinel(_w))
    set_standing_goal_store_override(lambda _w: _Sentinel(_w))
    set_runtime_checkpoint_store_override(lambda _w: _Sentinel(_w))
    set_pending_channel_question_store_override(lambda _w: _Sentinel(_w))
    set_tool_result_store_override(lambda _w: _Sentinel(_w))

    clear_infrastructure_overrides()

    builder = InfrastructureBuilder()
    assert not isinstance(
        builder.build_experience_store(work_dir=str(tmp_path)), _Sentinel
    )
    assert not isinstance(
        builder.build_standing_goal_store(work_dir=str(tmp_path)), _Sentinel
    )
    assert not isinstance(
        builder.build_pending_channel_question_store(work_dir=str(tmp_path)),
        _Sentinel,
    )
    assert not isinstance(
        builder.build_tool_result_store(work_dir=str(tmp_path)), _Sentinel
    )
    tracker = builder.build_runtime_tracker(
        config={
            "runtime": {"enabled": True, "store": "memory"},
            "persistence": {"work_dir": str(tmp_path)},
        },
    )
    assert not isinstance(tracker._checkpoint_store, _Sentinel)
