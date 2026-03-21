"""Encrypted file-based token store.

Persists OAuth2 tokens and credentials as Fernet-encrypted JSON files
under a configurable directory (default: ``~/.taskforce/auth/``).

The master key is derived from the ``TASKFORCE_AUTH_KEY`` environment
variable.  When that variable is absent a machine-local key is
auto-generated on first use and stored alongside the encrypted files.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import aiofiles
import structlog

from taskforce.core.interfaces.auth import TokenStoreProtocol

logger = structlog.get_logger(__name__)

_KEY_FILE_NAME = ".key"
_ENC_SUFFIX = ".enc"


class EncryptedTokenStore:
    """Fernet-encrypted, file-based token store.

    Implements :class:`TokenStoreProtocol`.

    Args:
        store_dir: Directory for encrypted token files.
            Defaults to ``~/.taskforce/auth``.
    """

    def __init__(self, store_dir: str | None = None) -> None:
        self._store_dir = Path(store_dir or (Path.home() / ".taskforce" / "auth"))
        self._locks: dict[str, asyncio.Lock] = {}
        self._fernet: Any | None = None

    # ------------------------------------------------------------------
    # TokenStoreProtocol implementation
    # ------------------------------------------------------------------

    async def save_token(self, provider: str, token_data: dict[str, Any]) -> None:
        """Encrypt and persist token data for *provider*."""
        fernet = self._get_fernet()
        payload = json.dumps(token_data, ensure_ascii=False).encode()
        encrypted = fernet.encrypt(payload)

        self._store_dir.mkdir(parents=True, exist_ok=True)
        target = self._token_path(provider)
        tmp = target.with_suffix(".tmp")

        lock = self._lock_for(provider)
        async with lock:
            async with aiofiles.open(tmp, "wb") as f:
                await f.write(encrypted)
            tmp.replace(target)

        logger.info("auth.token_saved", provider=provider, path=str(target))

    async def load_token(self, provider: str) -> dict[str, Any] | None:
        """Load and decrypt token data for *provider*."""
        target = self._token_path(provider)
        if not target.exists():
            return None

        fernet = self._get_fernet()
        lock = self._lock_for(provider)
        async with lock:
            async with aiofiles.open(target, "rb") as f:
                encrypted = await f.read()

        try:
            decrypted = fernet.decrypt(encrypted)
            return json.loads(decrypted)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("auth.token_decrypt_failed", provider=provider, error=str(exc))
            return None
        except Exception as exc:
            logger.error("auth.token_load_error", provider=provider, error=str(exc))
            raise

    async def delete_token(self, provider: str) -> None:
        """Delete stored token for *provider*."""
        target = self._token_path(provider)
        lock = self._lock_for(provider)
        async with lock:
            if target.exists():
                target.unlink()
                logger.info("auth.token_deleted", provider=provider)

    async def list_providers(self) -> list[str]:
        """List all providers that have stored tokens."""
        if not self._store_dir.exists():
            return []
        return [
            p.stem
            for p in sorted(self._store_dir.glob(f"*{_ENC_SUFFIX}"))
            if p.stem != _KEY_FILE_NAME.rstrip(_ENC_SUFFIX)
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _token_path(self, provider: str) -> Path:
        """Return the file path for a provider's encrypted token."""
        safe_name = provider.replace("/", "_").replace("\\", "_")
        return self._store_dir / f"{safe_name}{_ENC_SUFFIX}"

    def _lock_for(self, provider: str) -> asyncio.Lock:
        """Return (or create) an asyncio lock for the given provider."""
        if provider not in self._locks:
            self._locks[provider] = asyncio.Lock()
        return self._locks[provider]

    def _get_fernet(self) -> Any:
        """Lazily initialise and return the Fernet cipher."""
        if self._fernet is not None:
            return self._fernet

        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise ImportError(
                "The 'cryptography' package is required for encrypted token storage. "
                "Install with: uv add cryptography"
            ) from exc

        key = self._resolve_key()
        self._fernet = Fernet(key)
        return self._fernet

    def _resolve_key(self) -> bytes:
        """Resolve the Fernet encryption key.

        Priority:
        1. ``TASKFORCE_AUTH_KEY`` environment variable (base64 Fernet key).
        2. Auto-generated key file at ``<store_dir>/.key``.
        """
        env_key = os.environ.get("TASKFORCE_AUTH_KEY")
        if env_key:
            return env_key.encode()

        return self._load_or_create_key_file()

    def _load_or_create_key_file(self) -> bytes:
        """Load or create the machine-local key file."""
        from cryptography.fernet import Fernet

        key_path = self._store_dir / _KEY_FILE_NAME
        if key_path.exists():
            return key_path.read_bytes().strip()

        self._store_dir.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        logger.warning(
            "auth.key_auto_generated",
            path=str(key_path),
            hint="Set TASKFORCE_AUTH_KEY env variable for production use.",
        )
        return key


# Ensure the module-level protocol assertion works at import time.
_: type[TokenStoreProtocol] = EncryptedTokenStore  # type: ignore[assignment]
