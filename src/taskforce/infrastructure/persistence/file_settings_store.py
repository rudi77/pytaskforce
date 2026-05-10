"""File-based, Fernet-encrypted :class:`SettingsStoreProtocol` implementation.

The whole settings document is stored as a single Fernet-encrypted
blob at ``<work_dir>/settings.json.enc``. Each write decrypts, mutates,
and re-encrypts the document, then atomically replaces the file —
losing power mid-write cannot leave a half-written file behind.

Master-key resolution order:

1. ``TASKFORCE_SECRETS_KEY`` environment variable. Must be a valid Fernet
   key (a base64 url-encoded 32-byte secret). Recommended for any deployment
   the operator actually controls — secrets stay out of the repo and out of
   the work_dir.
2. ``<work_dir>/.secrets.key``. Auto-generated on first run if absent so
   single-user installs Just Work. The file is created with mode 0o600 on
   POSIX; Windows ACL hardening is left to the operator.

Storage layout (post-decryption JSON)::

    {
      "version": 1,
      "sections": {
        "<section_name>": {
          "data": { ... },
          "updated_at": "<iso8601>"
        }
      }
    }

The store is intentionally not multi-process-safe. Settings are
mutated only on admin paths (UI saves, startup hydration); concurrent
admin mutation is not a use case the framework needs to optimise for.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from cryptography.fernet import Fernet, InvalidToken

logger = structlog.get_logger(__name__)

#: Environment variable name for the master Fernet key.
SECRETS_KEY_ENV = "TASKFORCE_SECRETS_KEY"

#: Storage layout schema version. Bumped only when the on-disk shape
#: changes in a way that needs migration.
_SCHEMA_VERSION = 1


class SettingsStoreError(Exception):
    """Raised when the settings store is unusable (corrupt blob, bad key)."""


class FileSettingsStore:
    """File-based, Fernet-encrypted settings store.

    Implements :class:`taskforce.core.interfaces.settings.SettingsStoreProtocol`.
    """

    def __init__(
        self,
        work_dir: str | Path = ".taskforce",
        *,
        key: bytes | None = None,
        store_filename: str = "settings.json.enc",
        key_filename: str = ".secrets.key",
    ) -> None:
        """Initialize the store.

        Args:
            work_dir: Base directory for the encrypted blob and (when needed)
                the auto-generated key file.
            key: Optional explicit Fernet key. Bypasses env + key-file
                resolution; primarily useful in tests.
            store_filename: Name of the encrypted document under ``work_dir``.
            key_filename: Name of the auto-generated key file under
                ``work_dir`` (used only when neither ``key`` nor the env
                variable provide one).
        """
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._store_path = self._work_dir / store_filename
        self._key_path = self._work_dir / key_filename
        self._logger = logger.bind(component="file_settings_store")
        self._fernet = Fernet(key or self._resolve_key())

    # ------------------------------------------------------------------
    # SettingsStoreProtocol
    # ------------------------------------------------------------------

    def get(self, section: str) -> dict[str, Any] | None:
        document = self._read_document()
        record = document.get("sections", {}).get(section)
        if record is None:
            return None
        return dict(record.get("data") or {})

    def put(self, section: str, value: dict[str, Any]) -> None:
        if not isinstance(value, dict):
            raise TypeError(f"Settings section value must be a dict, got {type(value).__name__}")
        document = self._read_document()
        sections = document.setdefault("sections", {})
        sections[section] = {
            "data": value,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._write_document(document)
        self._logger.info("settings.section.written", section=section)

    def delete(self, section: str) -> None:
        document = self._read_document()
        sections = document.get("sections", {})
        if section in sections:
            del sections[section]
            self._write_document(document)
            self._logger.info("settings.section.deleted", section=section)

    def list_sections(self) -> list[str]:
        document = self._read_document()
        return sorted(document.get("sections", {}).keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_key(self) -> bytes:
        env_key = os.getenv(SECRETS_KEY_ENV)
        if env_key:
            return env_key.encode("utf-8")
        if self._key_path.exists():
            return self._key_path.read_bytes()
        return self._create_key_file()

    def _create_key_file(self) -> bytes:
        """Generate a fresh Fernet key and persist it with restrictive perms."""
        key = Fernet.generate_key()
        # Atomic write so a crash mid-creation cannot leave a partial key on disk.
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self._work_dir, prefix=".secrets-", suffix=".tmp"
        )
        try:
            with os.fdopen(temp_fd, "wb") as f:
                f.write(key)
            self._restrict_permissions(Path(temp_path))
            if self._key_path.exists():  # pragma: no cover — race
                self._key_path.unlink()
            Path(temp_path).rename(self._key_path)
        except Exception:
            if Path(temp_path).exists():
                Path(temp_path).unlink()
            raise
        self._logger.warning(
            "settings.master_key.generated",
            path=str(self._key_path),
            hint=(
                f"For production set {SECRETS_KEY_ENV} explicitly so the key "
                "lives outside work_dir."
            ),
        )
        return key

    @staticmethod
    def _restrict_permissions(path: Path) -> None:
        """Best-effort 0o600 on the secret file (POSIX). No-op elsewhere."""
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except (OSError, NotImplementedError):  # Windows has no chmod equivalent here
            pass

    def _read_document(self) -> dict[str, Any]:
        if not self._store_path.exists():
            return {"version": _SCHEMA_VERSION, "sections": {}}
        ciphertext = self._store_path.read_bytes()
        if not ciphertext:
            return {"version": _SCHEMA_VERSION, "sections": {}}
        try:
            plaintext = self._fernet.decrypt(ciphertext)
        except InvalidToken as exc:
            raise SettingsStoreError(
                "Settings file could not be decrypted — master key mismatch."
            ) from exc
        try:
            document = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SettingsStoreError(f"Corrupt settings document: {exc}") from exc
        if not isinstance(document, dict) or "sections" not in document:
            raise SettingsStoreError("Settings document has unexpected schema.")
        return document

    def _write_document(self, document: dict[str, Any]) -> None:
        document.setdefault("version", _SCHEMA_VERSION)
        plaintext = json.dumps(document, ensure_ascii=False).encode("utf-8")
        ciphertext = self._fernet.encrypt(plaintext)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self._work_dir, prefix=".settings-", suffix=".tmp"
        )
        try:
            with os.fdopen(temp_fd, "wb") as f:
                f.write(ciphertext)
            if self._store_path.exists():
                self._store_path.unlink()
            Path(temp_path).rename(self._store_path)
        except Exception:
            if Path(temp_path).exists():
                Path(temp_path).unlink()
            raise
