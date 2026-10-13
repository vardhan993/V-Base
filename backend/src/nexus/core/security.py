from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

#: OWASP-recommended Argon2id parameters (64 MiB, t=3, p=4).
ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)

#: Bcrypt-style maximum. Argon2 itself has no limit, but rejecting absurd
#: inputs keeps hashing time bounded for unauthenticated endpoints.
MAX_PASSWORD_BYTES = 1024


def hash_password(plain_password: str) -> str:
    if len(plain_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError("Password is too long")
    return ph.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        ph.verify(hashed_password, plain_password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed_password: str) -> bool:
    try:
        return ph.check_needs_rehash(hashed_password)
    except Exception:
        return False


def generate_token() -> str:
    """Opaque session token. Only its hash is ever stored."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """SHA-256 of the session token, hex encoded.

    Session tokens are high-entropy random values, so a fast digest is the
    right tool: the lookup is a single indexed equality test and there is no
    low-entropy secret to brute force.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_equals(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return hmac.compare_digest(left, right)


def parse_bool_env(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)
