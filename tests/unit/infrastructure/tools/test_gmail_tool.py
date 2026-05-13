"""Per-scope routing for the Gmail tool's seen-IDs file (#213).

The standalone default lives under ``.taskforce/google_workspace/gmail_seen.json``
(Phase 3 / #246; pre-Phase-3 it was ``.taskforce/butler/gmail_seen.json``).
Enterprise plugins route the directory per-(tenant, user) via the
``set_butler_state_dir_override`` framework hook — the name predates the
package move and is kept stable for deployed enterprise installations.

These tests pin both halves: the standalone default and the
override-driven per-scope path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from taskforce_google_workspace.gmail import (
    _DEFAULT_STATE_DIR,
    _SEEN_FILE_NAME,
    _load_seen_ids,
    _resolve_seen_path,
    _save_seen_ids,
)

from taskforce.application import infrastructure_overrides


@pytest.fixture(autouse=True)
def _reset_overrides():
    """Drop any installed state-dir override between tests so the
    standalone-default assertions stay deterministic."""
    infrastructure_overrides.set_butler_state_dir_override(None)
    yield
    infrastructure_overrides.set_butler_state_dir_override(None)


def test_default_path_lives_under_google_workspace_dir(tmp_path: Path, monkeypatch):
    """Standalone default: ``.taskforce/google_workspace/gmail_seen.json``.

    Pre-Phase-3 the default was ``.taskforce/butler/gmail_seen.json``.
    """
    # cd into tmp_path so the relative ``.taskforce`` resolution is
    # hermetic — otherwise an existing project-local file would alter
    # the fallback path.
    monkeypatch.chdir(tmp_path)
    path = _resolve_seen_path()
    assert path == _DEFAULT_STATE_DIR / _SEEN_FILE_NAME
    assert path.name == "gmail_seen.json"
    assert path.parent.name == "google_workspace"


def test_default_path_honours_legacy_butler_dir(tmp_path: Path, monkeypatch):
    """When only the legacy ``.taskforce/butler/gmail_seen.json`` exists,
    the resolver keeps using it so an upgrade doesn't lose seen-ids."""
    monkeypatch.chdir(tmp_path)
    legacy_dir = tmp_path / ".taskforce" / "butler"
    legacy_dir.mkdir(parents=True)
    legacy_file = legacy_dir / "gmail_seen.json"
    legacy_file.write_text('{"seen_ids": ["legacy-1"]}', encoding="utf-8")

    path = _resolve_seen_path()
    assert path == Path(".taskforce") / "butler" / "gmail_seen.json"


def test_override_routes_seen_path_into_provided_dir(tmp_path: Path):
    """The override callable returns a directory; the seen file lands
    directly inside it. Mirrors the per-(tenant, user) routing the
    enterprise plugin installs."""
    user_root = tmp_path / "tenants" / "acme" / "users" / "alice" / "google_workspace"

    infrastructure_overrides.set_butler_state_dir_override(lambda: user_root)

    path = _resolve_seen_path()
    assert path == user_root / "gmail_seen.json"


def test_override_swallows_provider_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A misbehaving override (e.g. tenant context not bound) must
    not crash the email check — we fall back to the default and the
    next list call continues working. After #222 the failure is
    logged at ERROR (not warning) so a rename regression doesn't
    hide silently. structlog goes through its own renderer so we
    spy on the module logger directly instead of using caplog.
    """
    monkeypatch.chdir(tmp_path)
    from taskforce_google_workspace import gmail as gmail_mod

    def _broken():
        raise RuntimeError("no tenant scope")

    error_calls: list[str] = []
    monkeypatch.setattr(
        gmail_mod.logger,
        "error",
        lambda event, **_: error_calls.append(event),
    )
    infrastructure_overrides.set_butler_state_dir_override(_broken)

    path = _resolve_seen_path()
    # Fell back to the default rather than propagating the exception.
    assert path == _DEFAULT_STATE_DIR / _SEEN_FILE_NAME
    # And the failure was logged at ERROR (was WARNING before #222).
    assert "google_workspace.gmail.seen_path_override_failed" in error_calls


def test_load_and_save_round_trip_through_override(tmp_path: Path):
    """End-to-end: load_seen / save_seen consult the override and
    round-trip the persisted set correctly."""
    user_root = tmp_path / "tenants" / "acme" / "users" / "alice" / "google_workspace"
    infrastructure_overrides.set_butler_state_dir_override(lambda: user_root)

    # No data yet → empty set.
    assert _load_seen_ids() == set()

    _save_seen_ids({"msg-1", "msg-2", "msg-3"})

    persisted = user_root / "gmail_seen.json"
    assert persisted.is_file()
    body = json.loads(persisted.read_text(encoding="utf-8"))
    assert sorted(body["seen_ids"]) == ["msg-1", "msg-2", "msg-3"]

    # Re-load picks it up.
    assert _load_seen_ids() == {"msg-1", "msg-2", "msg-3"}


def test_two_scopes_keep_disjoint_seen_files(tmp_path: Path):
    """Pin the regression for #213: two users in the same tenant get
    distinct ``gmail_seen.json`` files. Switching the override mid-
    run is what a per-request scope binding does."""
    alice_dir = tmp_path / "tenants" / "acme" / "users" / "alice" / "google_workspace"
    bob_dir = tmp_path / "tenants" / "acme" / "users" / "bob" / "google_workspace"

    infrastructure_overrides.set_butler_state_dir_override(lambda: alice_dir)
    _save_seen_ids({"alice-1", "alice-2"})

    infrastructure_overrides.set_butler_state_dir_override(lambda: bob_dir)
    _save_seen_ids({"bob-1"})

    # Each user's file holds only their own ids.
    alice_body = json.loads((alice_dir / "gmail_seen.json").read_text(encoding="utf-8"))
    bob_body = json.loads((bob_dir / "gmail_seen.json").read_text(encoding="utf-8"))

    assert sorted(alice_body["seen_ids"]) == ["alice-1", "alice-2"]
    assert bob_body["seen_ids"] == ["bob-1"]
