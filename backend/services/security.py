"""Password hashing and session tokens (standard library only).

Passwords are stored as PBKDF2-HMAC-SHA256 with a per-user random salt:
    pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>
Session tokens are random URL-safe strings; only their SHA-256 digest is stored in the DB,
so a leaked database cannot be replayed as live sessions.

Two-step login uses TOTP (RFC 6238: 30-second steps, 6 digits, SHA-1), the codes of Google Authenticator,
Microsoft Authenticator and similar phone apps. A code is accepted one step early or late (clock drift) and
only once: the last used step is stored, so a code someone saw cannot be replayed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
from urllib.parse import quote

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


TOTP_STEP_SECONDS = 30


def new_totp_secret() -> str:
    """160 random bits in base32, the format authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{number % 1_000_000:06d}"


def verify_totp(secret: str, code: str | None, last_step: int = 0) -> int | None:
    """The step the code belongs to (now, one before or one after), or None. A step at or before `last_step`
    was already used and is refused."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if not secret or len(code) != 6:
        return None
    now = int(time.time()) // TOTP_STEP_SECONDS
    for step in (now, now - 1, now + 1):
        if step > last_step and hmac.compare_digest(totp_code(secret, step), code):
            return step
    return None


def otpauth_uri(secret: str, account: str, issuer: str = "AccountFlow AI") -> str:
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits=6&period={TOTP_STEP_SECONDS}"


def qr_data_uri(text: str) -> str:
    import qrcode

    image = qrcode.make(text, box_size=6, border=2)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def password_problem(password: str | None) -> str | None:
    """Hebrew validation message, or None when the password is acceptable."""
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f"הסיסמה חייבת להכיל לפחות {MIN_PASSWORD_LENGTH} תווים"
    if len(password) > 128:
        return "הסיסמה ארוכה מדי (עד 128 תווים)"
    return None
