"""Per-user routing for the butler Gmail tool's seen-IDs file (#213).

The legacy default kept a single ``.taskforce/gmail_seen.json`` at
the top level — shared by every user in every tenant. After #213
the default lives under ``.taskforce/butler/gmail_seen.json`` and
enterprise plugins route it per-(tenant, user) via the
``set_butler_state_dir_override`` framework hook.

These tests pin both halves: the standalone default and the
override-driven per-scope path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from taskforce_butler.infrastructure.tools.email_tool import (
    _DEFAULT_BUTLER_DIR,
    _SEEN_FILE_NAME,
    _load_seen_ids,
    _resolve_seen_path,
    _save_seen_ids,
)

from taskforce.application import infrastructure_overrides


@pytest.fixture(autouse=True)
def _reset_overrides():
    """Drop any installed butler-state-dir override between tests so
    the standalone-default assertions stay deterministic."""
    infrastructure_overrides.set_butler_state_dir_override(None)
    yield
    infrastructure_overrides.set_butler_state_dir_override(None)


def test_default_path_lives_under_butler_dir():
    """Standalone default: ``.taskforce/butler/gmail_seen.json``.

    Pre-#213 was ``.taskforce/gmail_seen.json`` at the top level.
    """
    path = _resolve_seen_path()
    assert path == _DEFAULT_BUTLER_DIR / _SEEN_FILE_NAME
    assert path.name == "gmail_seen.json"
    assert path.parent.name == "butler"


def test_override_routes_seen_path_into_provided_dir(tmp_path: Path):
    """The override callable returns a directory; the seen file lands
    directly inside it. Mirrors the per-(tenant, user) routing the
    enterprise plugin installs."""
    user_root = tmp_path / "tenants" / "acme" / "users" / "alice" / "butler"

    infrastructure_overrides.set_butler_state_dir_override(lambda: user_root)

    path = _resolve_seen_path()
    assert path == user_root / "gmail_seen.json"


def test_override_swallows_provider_exception(tmp_path: Path):
    """A misbehaving override (e.g. tenant context not bound) must
    not crash the email check — we fall back to the default and the
    next list call continues working."""
    def _broken():
        raise RuntimeError("no tenant scope")

    infrastructure_overrides.set_butler_state_dir_override(_broken)

    path = _resolve_seen_path()
    # Fell back to the default rather than propagating the exception.
    assert path == _DEFAULT_BUTLER_DIR / _SEEN_FILE_NAME


def test_load_and_save_round_trip_through_override(tmp_path: Path):
    """End-to-end: load_seen / save_seen consult the override and
    round-trip the persisted set correctly."""
    user_root = tmp_path / "tenants" / "acme" / "users" / "alice" / "butler"
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
    alice_dir = tmp_path / "tenants" / "acme" / "users" / "alice" / "butler"
    bob_dir = tmp_path / "tenants" / "acme" / "users" / "bob" / "butler"

    infrastructure_overrides.set_butler_state_dir_override(lambda: alice_dir)
    _save_seen_ids({"alice-1", "alice-2"})

    infrastructure_overrides.set_butler_state_dir_override(lambda: bob_dir)
    _save_seen_ids({"bob-1"})

    # Each user's file holds only their own ids.
    alice_body = json.loads((alice_dir / "gmail_seen.json").read_text(encoding="utf-8"))
    bob_body = json.loads((bob_dir / "gmail_seen.json").read_text(encoding="utf-8"))

    assert sorted(alice_body["seen_ids"]) == ["alice-1", "alice-2"]
    assert bob_body["seen_ids"] == ["bob-1"]
