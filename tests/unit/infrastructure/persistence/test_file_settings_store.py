"""Tests for ``FileSettingsStore``.

The store keeps an entire JSON document Fernet-encrypted on disk.
These tests cover the contract (round-trip, missing section, list,
delete) plus the master-key resolution paths and the failure modes
that matter (wrong key → readable error; corrupt blob → readable
error).
"""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

from taskforce.infrastructure.persistence.file_settings_store import (
    SECRETS_KEY_ENV,
    FileSettingsStore,
    SettingsStoreError,
)


def test_put_and_get_round_trip(tmp_path) -> None:
    store = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    store.put("llm_providers", {"openai": {"api_key": "sk-test"}})
    assert store.get("llm_providers") == {"openai": {"api_key": "sk-test"}}


def test_get_missing_section_returns_none(tmp_path) -> None:
    store = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    assert store.get("nonexistent") is None


def test_list_sections_returns_sorted(tmp_path) -> None:
    store = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    store.put("zebra", {})
    store.put("alpha", {})
    assert store.list_sections() == ["alpha", "zebra"]


def test_delete_removes_section(tmp_path) -> None:
    store = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    store.put("ephemeral", {"x": 1})
    store.delete("ephemeral")
    assert store.get("ephemeral") is None
    assert "ephemeral" not in store.list_sections()


def test_delete_missing_section_is_noop(tmp_path) -> None:
    store = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    store.delete("nope")  # must not raise


def test_put_replaces_section_completely(tmp_path) -> None:
    store = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    store.put("channels", {"telegram": "old", "teams": "kept-out"})
    store.put("channels", {"telegram": "new"})
    assert store.get("channels") == {"telegram": "new"}


def test_put_rejects_non_dict_value(tmp_path) -> None:
    store = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    with pytest.raises(TypeError):
        store.put("bad", ["list", "not", "dict"])  # type: ignore[arg-type]


def test_blob_is_actually_encrypted(tmp_path) -> None:
    """The on-disk file must not contain the plaintext payload."""
    store = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    store.put("llm_providers", {"openai": {"api_key": "sk-supersecret"}})
    blob = (tmp_path / "settings.json.enc").read_bytes()
    assert b"sk-supersecret" not in blob
    assert b"openai" not in blob


def test_wrong_key_raises_settings_store_error(tmp_path) -> None:
    """Reading with a fresh key must surface a clean error, not Fernet internals."""
    key_a = Fernet.generate_key()
    store_a = FileSettingsStore(work_dir=tmp_path, key=key_a)
    store_a.put("anything", {"x": 1})

    store_b = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    with pytest.raises(SettingsStoreError):
        store_b.get("anything")


def test_master_key_from_env(tmp_path, monkeypatch) -> None:
    key = Fernet.generate_key()
    monkeypatch.setenv(SECRETS_KEY_ENV, key.decode("utf-8"))
    store = FileSettingsStore(work_dir=tmp_path)
    store.put("env_test", {"hello": "world"})
    assert store.get("env_test") == {"hello": "world"}
    # The env-keyed store must NOT have written a key file to disk.
    assert not (tmp_path / ".secrets.key").exists()


def test_master_key_auto_generates_when_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(SECRETS_KEY_ENV, raising=False)
    store = FileSettingsStore(work_dir=tmp_path)
    store.put("auto", {"v": 1})
    key_path = tmp_path / ".secrets.key"
    assert key_path.exists()
    # A second store at the same work_dir must read the same key off disk
    # and decrypt the blob written by the first store.
    store2 = FileSettingsStore(work_dir=tmp_path)
    assert store2.get("auto") == {"v": 1}


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only chmod assertion")
def test_auto_generated_key_has_restrictive_permissions(tmp_path, monkeypatch) -> None:
    import stat as stat_mod

    monkeypatch.delenv(SECRETS_KEY_ENV, raising=False)
    FileSettingsStore(work_dir=tmp_path)  # triggers key generation
    key_path = tmp_path / ".secrets.key"
    mode = key_path.stat().st_mode & 0o777
    assert mode == (stat_mod.S_IRUSR | stat_mod.S_IWUSR)


def test_atomic_write_leaves_no_temp_files(tmp_path) -> None:
    """A successful write must not leave ``.tmp`` siblings around."""
    store = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    store.put("a", {"x": 1})
    leftovers = list(tmp_path.glob(".settings-*.tmp"))
    assert leftovers == []


def test_corrupt_blob_raises_settings_store_error(tmp_path) -> None:
    """A garbled file body must surface as ``SettingsStoreError``."""
    key = Fernet.generate_key()
    store = FileSettingsStore(work_dir=tmp_path, key=key)
    store.put("a", {"x": 1})
    # Truncate the ciphertext so Fernet refuses it.
    (tmp_path / "settings.json.enc").write_bytes(b"not-a-valid-fernet-token")
    with pytest.raises(SettingsStoreError):
        store.get("a")
