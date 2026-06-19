"""
Field-level encryption for sensitive settings stored in the database.

The Fernet key is derived deterministically from Django's SECRET_KEY so that
no additional environment variable is required.  Changing SECRET_KEY will make
all encrypted credentials unreadable - re-enter them after any key rotation.

Stored format:  "enc:<fernet-url-safe-base64-token>"
Legacy / empty values (no "enc:" prefix) are returned unchanged so that
existing plain-text rows continue to work until they are next saved.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

ENCRYPTED_PREFIX = 'enc:'


def _get_fernet() -> Fernet:
    from django.conf import settings
    raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()   # 32 bytes
    key = base64.urlsafe_b64encode(raw)                           # Fernet-compatible
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Return ``"enc:<token>"`` for *plaintext*.  Empty strings are returned as-is."""
    if not plaintext:
        return plaintext
    token = _get_fernet().encrypt(plaintext.encode()).decode()
    return ENCRYPTED_PREFIX + token


def decrypt(value: str) -> str:
    """
    Decrypt an ``"enc:<token>"`` string.

    * If *value* has no ``enc:`` prefix it is treated as legacy plain-text and
      returned unchanged.
    * If decryption fails (wrong key, corrupted token) an empty string is
      returned so the application does not hard-crash - the user will need to
      re-enter the credential.
    """
    if not value or not value.startswith(ENCRYPTED_PREFIX):
        return value
    try:
        token = value[len(ENCRYPTED_PREFIX):]
        return _get_fernet().decrypt(token.encode()).decode()
    except (InvalidToken, Exception):
        return ''


def is_encrypted(value: str) -> bool:
    """Return True if *value* is already stored in encrypted form."""
    return bool(value and value.startswith(ENCRYPTED_PREFIX))
