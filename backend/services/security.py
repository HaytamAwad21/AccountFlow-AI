"""Password hashing and session tokens (standard library only).

Passwords are stored as PBKDF2-HMAC-SHA256 with a per-user random salt:
    pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>
Session tokens are random URL-safe strings; only their SHA-256 digest is stored in the DB,
so a leaked database cannot be replayed as live sessions.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 240_000
MIN_PASSWORD_LENGTH = 6


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def password_problem(password: str | None) -> str | None:
    """Hebrew validation message, or None when the password is acceptable."""
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f"הסיסמה חייבת להכיל לפחות {MIN_PASSWORD_LENGTH} תווים"
    if len(password) > 128:
        return "הסיסמה ארוכה מדי (עד 128 תווים)"
    return None
