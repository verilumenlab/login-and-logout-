"""
Security, Argon2id Password Hashing, JWT Tokens & Cryptographic Utilities
"""

from __future__ import annotations

import hashlib
import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.low_level import Type
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Enterprise Argon2id Hasher
# m=65536 (64 MiB), t=3 iterations, p=4 parallelism, type=Argon2id
argon2_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# Legacy fallback context for bcrypt compatibility
_legacy_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Hash password using Argon2id."""
    return argon2_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against Argon2id hash.
    Gracefully falls back to bcrypt if legacy hash format is encountered.
    """
    if hashed_password.startswith("$argon2"):
        try:
            return argon2_hasher.verify(hashed_password, plain_password)
        except (VerifyMismatchError, InvalidHashError):
            return False
    elif hashed_password.startswith("$2"):
        try:
            return _legacy_pwd_context.verify(plain_password, hashed_password)
        except Exception:
            return False
    return False


def create_access_token(
    subject: str | Any,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Generate signed JWT access token with payload claims."""
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: dict[str, Any] = {"sub": str(subject), "exp": expire}
    if extra_claims:
        to_encode.update(extra_claims)

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate signature/expiration of JWT access token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def generate_secure_token(nbytes: int = 32) -> str:
    """Generate cryptographically secure URL-safe random string for refresh or reset tokens."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Generate SHA-256 hex digest of a token for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_otp_code(length: int = 6) -> str:
    """Generate cryptographically secure numeric OTP."""
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(length))


def _admin_password_fernet():
    """Derive a Fernet key from SECRET_KEY for admin-visible password storage."""
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    # url-safe base64 32-byte key
    import base64

    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_admin_password(plain_password: str) -> str:
    """Encrypt a password so admins can later view the last password they assigned."""
    return _admin_password_fernet().encrypt(plain_password.encode("utf-8")).decode("utf-8")


def decrypt_admin_password(cipher_text: str | None) -> str | None:
    """Decrypt an admin-visible password; returns None if missing or corrupt."""
    if not cipher_text:
        return None
    try:
        return _admin_password_fernet().decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


def store_admin_visible_password(user: Any, plain_password: str) -> None:
    """Persist the admin-assigned password (encrypted) alongside the Argon2 login hash."""
    from datetime import UTC, datetime

    user.admin_password_encrypted = encrypt_admin_password(plain_password)
    user.admin_password_updated_at = datetime.now(UTC)


def clear_admin_visible_password(user: Any) -> None:
    """Clear admin-visible password after the employee changes it themselves."""
    user.admin_password_encrypted = None
    user.admin_password_updated_at = None
