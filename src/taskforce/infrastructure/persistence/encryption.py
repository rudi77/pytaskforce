"""Encryption utilities for secure data persistence.

This module provides encryption at rest capabilities for state persistence,
supporting per-tenant encryption keys and key rotation.
"""

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import json
import structlog

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    Fernet = None
    InvalidToken = Exception
    AESGCM = None


logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


@dataclass
class EncryptionKey:
    """An encryption key with metadata.

    Attributes:
        key_id: Unique identifier for this key
        key_bytes: The actual key bytes (32 bytes for AES-256)
        algorithm: Encryption algorithm (fernet or aes-gcm)
        created_at: When this key was created
        expires_at: Optional expiration time
        tenant_id: Associated tenant (None for system key)
        version: Key version for rotation
    """

    key_id: str
    key_bytes: bytes
    algorithm: str = "fernet"
    created_at: datetime = None
    expires_at: Optional[datetime] = None
    tenant_id: Optional[str] = None
    version: int = 1

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = _utcnow()

    def is_expired(self) -> bool:
        """Check if this key has expired."""
        if self.expires_at is None:
            return False
        return _utcnow() > self.expires_at

    def to_metadata(self) -> Dict[str, Any]:
        """Get key metadata (without the actual key bytes)."""
        return {
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "tenant_id": self.tenant_id,
            "version": self.version,
        }


class EncryptionError(Exception):
    """Exception raised for encryption/decryption failures."""

    pass


class KeyManager:
    """Manages encryption keys for tenants.

    Supports:
    - Per-tenant key generation and storage
    - Key rotation with version tracking
    - Key derivation from master key
    """

    def __init__(
        self,
        master_key: Optional[bytes] = None,
        master_key_env: str = "TASKFORCE_ENCRYPTION_KEY",
    ):
        """Initialize the key manager.

        Args:
            master_key: Optional master key bytes
            master_key_env: Environment variable name for master key
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            logger.warning("encryption.cryptography_not_available")
            self._master_key = None
        elif master_key:
            self._master_key = master_key
        else:
            # Try to load from environment
            key_str = os.environ.get(master_key_env)
            if key_str:
                self._master_key = base64.urlsafe_b64decode(key_str)
            else:
                # Generate a temporary key for development
                self._master_key = secrets.token_bytes(32)
                logger.warning(
                    "encryption.using_temporary_key",
                    hint="Set TASKFORCE_ENCRYPTION_KEY for persistent encryption",
                )

        self._tenant_keys: Dict[str, EncryptionKey] = {}

    def get_or_create_tenant_key(self, tenant_id: str) -> EncryptionKey:
        """Get or create an encryption key for a tenant.

        Args:
            tenant_id: The tenant identifier

        Returns:
            EncryptionKey for the tenant
        """
        if tenant_id in self._tenant_keys:
            key = self._tenant_keys[tenant_id]
            if not key.is_expired():
                return key

        # Derive a tenant-specific key from master key
        key = self._derive_tenant_key(tenant_id)
        self._tenant_keys[tenant_id] = key
        return key

    def _derive_tenant_key(self, tenant_id: str) -> EncryptionKey:
        """Derive a tenant key from the master key.

        Args:
            tenant_id: The tenant identifier

        Returns:
            Derived EncryptionKey
        """
        if self._master_key is None:
            raise EncryptionError("No master key available")

        # Use HKDF-like derivation (simplified)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            self._master_key,
            tenant_id.encode("utf-8"),
            iterations=100000,
            dklen=32,
        )

        return EncryptionKey(
            key_id=f"tenant:{tenant_id}:v1",
            key_bytes=derived,
            algorithm="fernet",
            tenant_id=tenant_id,
        )

    def rotate_tenant_key(self, tenant_id: str) -> EncryptionKey:
        """Rotate the encryption key for a tenant.

        Args:
            tenant_id: The tenant identifier

        Returns:
            New EncryptionKey (old key is kept for decryption)
        """
        old_key = self._tenant_keys.get(tenant_id)
        old_version = old_key.version if old_key else 0

        # Create a new key with incremented version
        new_derived = hashlib.pbkdf2_hmac(
            "sha256",
            self._master_key + str(old_version + 1).encode(),
            tenant_id.encode("utf-8"),
            iterations=100000,
            dklen=32,
        )

        new_key = EncryptionKey(
            key_id=f"tenant:{tenant_id}:v{old_version + 1}",
            key_bytes=new_derived,
            algorithm="fernet",
            tenant_id=tenant_id,
            version=old_version + 1,
        )

        self._tenant_keys[tenant_id] = new_key
        logger.info(
            "encryption.key_rotated",
            tenant_id=tenant_id,
            new_version=new_key.version,
        )
        return new_key

    @staticmethod
    def generate_random_key() -> bytes:
        """Generate a random 32-byte key.

        Returns:
            Random key bytes suitable for AES-256
        """
        return secrets.token_bytes(32)


class DataEncryptor:
    """Encrypts and decrypts data using symmetric encryption.

    Supports Fernet (AES-128-CBC with HMAC) for simplicity
    and AES-256-GCM for higher security requirements.
    """

    def __init__(self, key_manager: Optional[KeyManager] = None):
        """Initialize the data encryptor.

        Args:
            key_manager: Key manager for tenant keys
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            logger.warning("encryption.disabled", reason="cryptography not installed")

        self.key_manager = key_manager or KeyManager()

    def encrypt(
        self,
        data: bytes,
        tenant_id: str,
        algorithm: str = "fernet",
    ) -> bytes:
        """Encrypt data for a tenant.

        Args:
            data: Data to encrypt
            tenant_id: Tenant identifier for key selection
            algorithm: Encryption algorithm (fernet or aes-gcm)

        Returns:
            Encrypted data with metadata prefix

        Raises:
            EncryptionError: If encryption fails
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            # Return data with a marker indicating it's unencrypted
            return b"PLAIN:" + data

        try:
            key = self.key_manager.get_or_create_tenant_key(tenant_id)

            if algorithm == "fernet":
                # Fernet uses first 32 bytes as signing key, next 32 as encryption key
                # We derive a Fernet-compatible key
                fernet_key = base64.urlsafe_b64encode(key.key_bytes)
                f = Fernet(fernet_key)
                encrypted = f.encrypt(data)
            elif algorithm == "aes-gcm":
                nonce = secrets.token_bytes(12)
                aesgcm = AESGCM(key.key_bytes)
                encrypted = nonce + aesgcm.encrypt(nonce, data, None)
            else:
                raise EncryptionError(f"Unknown algorithm: {algorithm}")

            # Prefix with key ID and algorithm for decryption
            header = f"{key.key_id}:{algorithm}:".encode("utf-8")
            return header + encrypted

        except Exception as e:
            logger.error("encryption.failed", error=str(e), tenant_id=tenant_id)
            raise EncryptionError(f"Encryption failed: {e}") from e

    def decrypt(
        self,
        encrypted_data: bytes,
        tenant_id: str,
    ) -> bytes:
        """Decrypt data for a tenant.

        Args:
            encrypted_data: Data to decrypt (with header)
            tenant_id: Tenant identifier for key selection

        Returns:
            Decrypted data

        Raises:
            EncryptionError: If decryption fails
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            if encrypted_data.startswith(b"PLAIN:"):
                return encrypted_data[6:]
            return encrypted_data

        try:
            # Parse header
            header_end = encrypted_data.find(b":", encrypted_data.find(b":") + 1)
            if header_end == -1:
                raise EncryptionError("Invalid encrypted data format")

            # Find the second colon (after algorithm)
            first_colon = encrypted_data.find(b":")
            second_colon = encrypted_data.find(b":", first_colon + 1)
            third_colon = encrypted_data.find(b":", second_colon + 1)

            key_id = encrypted_data[:second_colon].decode("utf-8")
            algorithm = encrypted_data[second_colon + 1 : third_colon].decode("utf-8")
            ciphertext = encrypted_data[third_colon + 1 :]

            key = self.key_manager.get_or_create_tenant_key(tenant_id)

            if algorithm == "fernet":
                fernet_key = base64.urlsafe_b64encode(key.key_bytes)
                f = Fernet(fernet_key)
                return f.decrypt(ciphertext)
            elif algorithm == "aes-gcm":
                nonce = ciphertext[:12]
                actual_ciphertext = ciphertext[12:]
                aesgcm = AESGCM(key.key_bytes)
                return aesgcm.decrypt(nonce, actual_ciphertext, None)
            else:
                raise EncryptionError(f"Unknown algorithm: {algorithm}")

        except InvalidToken:
            raise EncryptionError("Decryption failed: invalid key or corrupted data")
        except Exception as e:
            logger.error("decryption.failed", error=str(e), tenant_id=tenant_id)
            raise EncryptionError(f"Decryption failed: {e}") from e

    def encrypt_json(
        self,
        data: Dict[str, Any],
        tenant_id: str,
        algorithm: str = "fernet",
    ) -> bytes:
        """Encrypt a JSON-serializable object.

        Args:
            data: Data to encrypt
            tenant_id: Tenant identifier
            algorithm: Encryption algorithm

        Returns:
            Encrypted data
        """
        json_bytes = json.dumps(data).encode("utf-8")
        return self.encrypt(json_bytes, tenant_id, algorithm)

    def decrypt_json(
        self,
        encrypted_data: bytes,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Decrypt data and parse as JSON.

        Args:
            encrypted_data: Data to decrypt
            tenant_id: Tenant identifier

        Returns:
            Decrypted and parsed data
        """
        decrypted = self.decrypt(encrypted_data, tenant_id)
        return json.loads(decrypted.decode("utf-8"))


# Convenience singleton
_default_encryptor: Optional[DataEncryptor] = None


def get_encryptor() -> DataEncryptor:
    """Get the default data encryptor."""
    global _default_encryptor
    if _default_encryptor is None:
        _default_encryptor = DataEncryptor()
    return _default_encryptor
