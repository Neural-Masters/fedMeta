"""Local account password hashing and opaque session-token helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

PASSWORD_ITERATIONS = 600_000
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def normalize_username(username: str) -> str:
    """Validate a local username and return its case-insensitive key."""
    username = username.strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Username must be 3-32 characters: letters, numbers, dot, dash, underscore")
    return username.casefold()


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a random salt."""
    if not 10 <= len(password) <= 128:
        raise ValueError("Password must be between 10 and 128 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a password hash without leaking comparison timing."""
    try:
        algorithm, rounds_text, salt_text, digest_text = encoded_hash.split("$", 3)
        rounds = int(rounds_text)
        if algorithm != "pbkdf2_sha256" or not 100_000 <= rounds <= 1_000_000:
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError):
        return False


def create_session_token() -> str:
    """Generate an unguessable bearer token; only its hash is persisted."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Hash a bearer token before database lookup/storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
