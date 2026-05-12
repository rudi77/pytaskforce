"""Per-scope routing for the framework's ``FileStorage`` (#212).

Pre-#212 the upload storage was a process-singleton rooted at
``.taskforce/uploads`` (or wherever ``TASKFORCE_UPLOADS_DIR`` pointed)
for every user. ``set_upload_storage_dir_override`` lets enterprise
plugins route uploads per-(tenant, user); the framework caches one
``FileStorage`` per resolved root so each scope keeps its own SQLite
index.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.application import file_storage as fs_module
from taskforce.application import infrastructure_overrides
from taskforce.application.file_storage import (
    _default_root,
    get_file_storage,
    reset_file_storage,
)


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch):
    """Drop any installed override + cached storage between tests."""
    monkeypatch.delenv("TASKFORCE_UPLOADS_DIR", raising=False)
    infrastructure_overrides.set_upload_storage_dir_override(None)
    reset_file_storage()
    yield
    infrastructure_overrides.set_upload_storage_dir_override(None)
    reset_file_storage()


def test_default_root_falls_back_to_taskforce_uploads():
    """No override, no env var → historic default."""
    assert _default_root() == Path(".taskforce") / "uploads"


def test_default_root_honours_env_var_when_no_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Env var still works for single-tenant ops who want to move the
    bucket. Only when no scope-aware override is installed."""
    monkeypatch.setenv("TASKFORCE_UPLOADS_DIR", str(tmp_path / "uploads"))
    assert _default_root() == tmp_path / "uploads"


def test_override_wins_over_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """An installed override always wins so an operator's env var
    cannot accidentally collapse per-(tenant, user) routing back to a
    single shared bucket."""
    monkeypatch.setenv("TASKFORCE_UPLOADS_DIR", str(tmp_path / "env"))
    override_dir = tmp_path / "tenants" / "acme" / "users" / "alice" / "uploads"
    infrastructure_overrides.set_upload_storage_dir_override(lambda: override_dir)

    assert _default_root() == override_dir


def test_override_swallows_provider_exception(tmp_path: Path):
    """A misbehaving provider (no tenant scope yet) falls through to
    the env var / default so uploads keep working during early-init
    paths instead of crashing the route."""
    def _broken():
        raise RuntimeError("no tenant scope")

    infrastructure_overrides.set_upload_storage_dir_override(_broken)
    # Should fall back rather than raise.
    assert _default_root() == Path(".taskforce") / "uploads"


def test_get_file_storage_caches_per_resolved_root(tmp_path: Path):
    """Different override results yield different FileStorage
    instances; the same result yields the same cached instance.
    """
    alice_dir = tmp_path / "alice"
    bob_dir = tmp_path / "bob"

    state = {"target": alice_dir}
    infrastructure_overrides.set_upload_storage_dir_override(lambda: state["target"])

    fs_alice = get_file_storage()
    state["target"] = bob_dir
    fs_bob = get_file_storage()

    assert fs_alice is not fs_bob
    assert Path(fs_alice._root).resolve() == alice_dir.resolve()
    assert Path(fs_bob._root).resolve() == bob_dir.resolve()

    # Switching back to alice returns the cached instance, not a new
    # one — important because each FileStorage opens its own SQLite
    # handle and re-creating per request would be wasteful.
    state["target"] = alice_dir
    assert get_file_storage() is fs_alice


def test_get_file_storage_singleton_when_no_override():
    """Singleton semantics preserved when no override is installed —
    bit-for-bit pre-#212 behaviour."""
    assert fs_module._storage is None
    first = get_file_storage()
    second = get_file_storage()
    assert first is second
