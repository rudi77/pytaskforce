"""Tests for encrypted token store."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from taskforce.infrastructure.auth.encrypted_token_store import EncryptedTokenStore


@pytest.fixture
def store(tmp_path: Path) -> EncryptedTokenStore:
    """Create an EncryptedTokenStore with a temp directory."""
    return EncryptedTokenStore(store_dir=str(tmp_path / "auth"))


@pytest.fixture
def store_with_env_key(tmp_path: Path) -> EncryptedTokenStore:
    """Create a store with an explicit TASKFORCE_AUTH_KEY."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    with patch.dict(os.environ, {"TASKFORCE_AUTH_KEY": key}):
        store = EncryptedTokenStore(store_dir=str(tmp_path / "auth"))
        # Force Fernet initialization while env var is set.
        store._get_fernet()
    return store


class TestEncryptedTokenStore:
    async def test_save_and_load_roundtrip(self, store: EncryptedTokenStore):
        token_data = {
            "provider": "google",
            "access_token": "access123",
            "refresh_token": "refresh456",
            "scopes": ["calendar.readonly"],
        }
        await store.save_token("google", token_data)
        loaded = await store.load_token("google")
        assert loaded == token_data

    async def test_load_nonexistent_returns_none(self, store: EncryptedTokenStore):
        result = await store.load_token("nonexistent")
        assert result is None

    async def test_delete_token(self, store: EncryptedTokenStore):
        await store.save_token("google", {"access_token": "abc"})
        await store.delete_token("google")
        result = await store.load_token("google")
        assert result is None

    async def test_delete_nonexistent_no_error(self, store: EncryptedTokenStore):
        await store.delete_token("nonexistent")  # Should not raise.

    async def test_list_providers(self, store: EncryptedTokenStore):
        await store.save_token("google", {"access_token": "g"})
        await store.save_token("microsoft", {"access_token": "m"})
        providers = await store.list_providers()
        assert set(providers) == {"google", "microsoft"}

    async def test_list_providers_empty(self, store: EncryptedTokenStore):
        providers = await store.list_providers()
        assert providers == []

    async def test_overwrite_token(self, store: EncryptedTokenStore):
        await store.save_token("google", {"access_token": "old"})
        await store.save_token("google", {"access_token": "new"})
        loaded = await store.load_token("google")
        assert loaded["access_token"] == "new"

    async def test_auto_generates_key_file(self, store: EncryptedTokenStore):
        await store.save_token("test", {"access_token": "x"})
        key_path = Path(store._store_dir) / ".key"
        assert key_path.exists()

    async def test_env_key_takes_precedence(
        self, store_with_env_key: EncryptedTokenStore
    ):
        """Store using TASKFORCE_AUTH_KEY should not create a .key file."""
        await store_with_env_key.save_token("test", {"access_token": "x"})
        key_path = Path(store_with_env_key._store_dir) / ".key"
        assert not key_path.exists()

    async def test_unicode_data(self, store: EncryptedTokenStore):
        data = {"access_token": "abc", "note": "Ümlauts und Sönderzéichen"}
        await store.save_token("test", data)
        loaded = await store.load_token("test")
        assert loaded == data

    async def test_sanitizes_provider_name(self, store: EncryptedTokenStore):
        await store.save_token("my/provider", {"access_token": "x"})
        loaded = await store.load_token("my/provider")
        assert loaded is not None
