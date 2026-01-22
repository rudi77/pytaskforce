"""JWT-based identity provider implementation.

This module provides JWT token validation and user context extraction
for OAuth2/OIDC authentication flows.
"""

import json
import base64
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
import structlog

from taskforce.core.interfaces.identity import (
    IdentityProviderProtocol,
    TenantContext,
    UserContext,
    Permission,
    get_permissions_for_roles,
)
from taskforce.core.domain.identity import IdentityToken


logger = structlog.get_logger(__name__)


@dataclass
class JWTConfig:
    """Configuration for JWT token validation.

    Attributes:
        secret_key: Secret key for HS256 validation (for symmetric signing)
        public_key: Public key for RS256 validation (for asymmetric signing)
        algorithms: Allowed signing algorithms
        issuer: Expected token issuer (iss claim)
        audience: Expected token audience (aud claim)
        leeway_seconds: Clock skew tolerance for expiration checks
        tenant_claim: JWT claim containing tenant ID
        roles_claim: JWT claim containing user roles
        username_claim: JWT claim containing username
        email_claim: JWT claim containing email
    """

    secret_key: Optional[str] = None
    public_key: Optional[str] = None
    algorithms: List[str] = field(default_factory=lambda: ["HS256"])
    issuer: Optional[str] = None
    audience: Optional[str] = None
    leeway_seconds: int = 30
    tenant_claim: str = "tenant_id"
    roles_claim: str = "roles"
    username_claim: str = "preferred_username"
    email_claim: str = "email"


class JWTIdentityProvider:
    """JWT-based identity provider implementing IdentityProviderProtocol.

    This provider validates JWT tokens and extracts user/tenant context.
    It supports both symmetric (HS256) and asymmetric (RS256) signing.

    Note: For production use, consider using PyJWT library for full JWT support.
    This implementation provides basic validation for demonstration purposes.
    """

    def __init__(
        self,
        config: JWTConfig,
        tenant_store: Optional[Dict[str, TenantContext]] = None,
    ):
        """Initialize the JWT identity provider.

        Args:
            config: JWT configuration
            tenant_store: Optional in-memory tenant store for development
        """
        self.config = config
        self._tenant_store = tenant_store or {}
        self._user_store: Dict[str, Dict[str, UserContext]] = {}

    async def validate_token(self, token: str) -> Optional[UserContext]:
        """Validate a JWT token and return user context.

        Args:
            token: The JWT token string

        Returns:
            UserContext if valid, None otherwise
        """
        try:
            # Parse and validate the JWT
            identity_token = self._decode_and_validate(token)
            if identity_token is None:
                return None

            # Extract user context from claims
            return self._extract_user_context(identity_token)

        except Exception as e:
            logger.warning("jwt.validation.failed", error=str(e))
            return None

    async def validate_api_key(self, api_key: str) -> Optional[UserContext]:
        """Validate an API key - not supported by JWT provider.

        This method always returns None. Use APIKeyProvider for API key auth.

        Args:
            api_key: The API key to validate

        Returns:
            None (not supported)
        """
        return None

    async def get_tenant(self, tenant_id: str) -> Optional[TenantContext]:
        """Retrieve tenant context by ID.

        Args:
            tenant_id: The tenant identifier

        Returns:
            TenantContext if found, None otherwise
        """
        return self._tenant_store.get(tenant_id)

    async def get_user(self, user_id: str, tenant_id: str) -> Optional[UserContext]:
        """Retrieve user context by ID within a tenant.

        Args:
            user_id: The user identifier
            tenant_id: The tenant identifier

        Returns:
            UserContext if found, None otherwise
        """
        tenant_users = self._user_store.get(tenant_id, {})
        return tenant_users.get(user_id)

    def register_tenant(self, tenant: TenantContext) -> None:
        """Register a tenant in the in-memory store.

        Args:
            tenant: The tenant context to register
        """
        self._tenant_store[tenant.tenant_id] = tenant
        logger.info("tenant.registered", tenant_id=tenant.tenant_id)

    def register_user(self, user: UserContext) -> None:
        """Register a user in the in-memory store.

        Args:
            user: The user context to register
        """
        if user.tenant_id not in self._user_store:
            self._user_store[user.tenant_id] = {}
        self._user_store[user.tenant_id][user.user_id] = user
        logger.info(
            "user.registered",
            user_id=user.user_id,
            tenant_id=user.tenant_id,
        )

    def _decode_and_validate(self, token: str) -> Optional[IdentityToken]:
        """Decode and validate a JWT token.

        Args:
            token: The JWT token string

        Returns:
            IdentityToken if valid, None otherwise
        """
        try:
            # Split JWT into parts
            parts = token.split(".")
            if len(parts) != 3:
                logger.warning("jwt.invalid.structure")
                return None

            header_b64, payload_b64, signature_b64 = parts

            # Decode header and payload
            header = self._base64_decode_json(header_b64)
            payload = self._base64_decode_json(payload_b64)

            if header is None or payload is None:
                return None

            # Validate algorithm
            alg = header.get("alg")
            if alg not in self.config.algorithms:
                logger.warning("jwt.invalid.algorithm", algorithm=alg)
                return None

            # Validate signature (HS256 only for now)
            if alg == "HS256" and self.config.secret_key:
                if not self._validate_hs256_signature(
                    f"{header_b64}.{payload_b64}",
                    signature_b64,
                    self.config.secret_key,
                ):
                    logger.warning("jwt.invalid.signature")
                    return None

            # Validate standard claims
            now = datetime.now(timezone.utc).timestamp()

            # Check expiration
            exp = payload.get("exp")
            if exp and now > exp + self.config.leeway_seconds:
                logger.warning("jwt.expired")
                return None

            # Check not-before
            nbf = payload.get("nbf")
            if nbf and now < nbf - self.config.leeway_seconds:
                logger.warning("jwt.not.yet.valid")
                return None

            # Check issuer
            if self.config.issuer and payload.get("iss") != self.config.issuer:
                logger.warning(
                    "jwt.invalid.issuer",
                    expected=self.config.issuer,
                    actual=payload.get("iss"),
                )
                return None

            # Check audience
            if self.config.audience:
                aud = payload.get("aud")
                if isinstance(aud, list):
                    if self.config.audience not in aud:
                        logger.warning("jwt.invalid.audience")
                        return None
                elif aud != self.config.audience:
                    logger.warning("jwt.invalid.audience")
                    return None

            # Build identity token
            return IdentityToken(
                token_id=payload.get("jti", ""),
                token_type="jwt",
                subject=payload.get("sub", ""),
                tenant_id=payload.get(self.config.tenant_claim, "default"),
                issued_at=datetime.fromtimestamp(
                    payload.get("iat", now), tz=timezone.utc
                ),
                expires_at=datetime.fromtimestamp(
                    payload.get("exp", now + 3600), tz=timezone.utc
                ),
                claims=payload,
                raw_token=token,
            )

        except Exception as e:
            logger.warning("jwt.decode.failed", error=str(e))
            return None

    def _extract_user_context(self, token: IdentityToken) -> UserContext:
        """Extract user context from a validated token.

        Args:
            token: The validated identity token

        Returns:
            UserContext extracted from token claims
        """
        claims = token.claims

        # Extract roles
        roles_claim = claims.get(self.config.roles_claim, [])
        if isinstance(roles_claim, str):
            roles = {roles_claim}
        else:
            roles = set(roles_claim)

        # Get permissions for roles
        permissions = get_permissions_for_roles(roles)

        return UserContext(
            user_id=token.subject,
            tenant_id=token.tenant_id,
            username=claims.get(self.config.username_claim, token.subject),
            email=claims.get(self.config.email_claim),
            roles=roles,
            permissions=permissions,
            attributes={
                k: v
                for k, v in claims.items()
                if k
                not in {
                    "sub",
                    "iss",
                    "aud",
                    "exp",
                    "iat",
                    "nbf",
                    "jti",
                    self.config.tenant_claim,
                    self.config.roles_claim,
                    self.config.username_claim,
                    self.config.email_claim,
                }
            },
            authenticated_at=token.issued_at,
            token_expires_at=token.expires_at,
        )

    def _base64_decode_json(self, b64_string: str) -> Optional[Dict[str, Any]]:
        """Decode a base64url-encoded JSON string.

        Args:
            b64_string: Base64url-encoded string

        Returns:
            Decoded JSON as dict, or None on failure
        """
        try:
            # Add padding if needed
            padding = 4 - len(b64_string) % 4
            if padding != 4:
                b64_string += "=" * padding

            # Replace URL-safe characters
            b64_string = b64_string.replace("-", "+").replace("_", "/")

            decoded = base64.b64decode(b64_string)
            return json.loads(decoded)
        except Exception:
            return None

    def _validate_hs256_signature(
        self, message: str, signature_b64: str, secret: str
    ) -> bool:
        """Validate an HS256 signature.

        Args:
            message: The signed message (header.payload)
            signature_b64: The base64url-encoded signature
            secret: The secret key

        Returns:
            True if signature is valid
        """
        try:
            # Compute expected signature
            expected = hmac.new(
                secret.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).digest()

            # Decode actual signature
            padding = 4 - len(signature_b64) % 4
            if padding != 4:
                signature_b64 += "=" * padding
            signature_b64 = signature_b64.replace("-", "+").replace("_", "/")
            actual = base64.b64decode(signature_b64)

            return hmac.compare_digest(expected, actual)
        except Exception:
            return False


def create_test_jwt(
    user_id: str,
    tenant_id: str,
    roles: List[str],
    secret_key: str,
    expires_in_seconds: int = 3600,
    **extra_claims: Any,
) -> str:
    """Create a test JWT token for development/testing.

    Args:
        user_id: The user identifier (sub claim)
        tenant_id: The tenant identifier
        roles: List of role names
        secret_key: The secret key for signing
        expires_in_seconds: Token validity period
        **extra_claims: Additional claims to include

    Returns:
        Signed JWT token string
    """
    import time

    now = int(time.time())

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "roles": roles,
        "iat": now,
        "exp": now + expires_in_seconds,
        **extra_claims,
    }

    def b64_encode(data: dict) -> str:
        json_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(json_bytes).rstrip(b"=").decode("utf-8")

    header_b64 = b64_encode(header)
    payload_b64 = b64_encode(payload)

    message = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("utf-8")

    return f"{message}.{signature_b64}"
