"""
Zero-knowledge challenge-response authentication helpers.

The server stores the Argon2id hash of each user's password.  During
challenge-response auth:

  1. Client requests a challenge → server returns nonce + Argon2id params
     extracted from the stored hash.
  2. Client computes H = Argon2id(password, salt, params) locally — identical
     to the server-stored hash — then sends HMAC-SHA256(key=H, msg=message).
  3. Server extracts the stored hash bytes and verifies the HMAC.

The plaintext password never crosses the wire.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass
from typing import Optional


_DJANGO_ARGON2_PREFIX = 'argon2'   # Django stores 'argon2' + '$argon2id$v=...'


@dataclass
class Argon2Params:
    """Parameters extracted from a Django-stored Argon2id hash."""
    salt_b64:     str   # unpadded base64 (as stored in hash string)
    time_cost:    int
    memory_cost:  int   # in KiB
    parallelism:  int
    hash_len:     int
    hash_b64:     str   # unpadded base64 (the actual hash output)


def parse_argon2_hash(django_hash: str) -> Optional[Argon2Params]:
    """
    Parse a Django Argon2id password hash and return its parameters.

    Django stores: ``argon2$argon2id$v=19$m=65536,t=3,p=4$<salt_b64>$<hash_b64>``
    Returns None if the hash is not Argon2id (e.g. still PBKDF2).
    """
    if not django_hash.startswith(_DJANGO_ARGON2_PREFIX):
        return None
    inner = django_hash[len(_DJANGO_ARGON2_PREFIX):]   # strip 'argon2$'

    # inner: $argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>
    parts = inner.split('$')
    # parts: ['', 'argon2id', 'v=19', 'm=65536,t=3,p=4', '<salt>', '<hash>']
    if len(parts) < 6 or parts[1] != 'argon2id':
        return None

    cost_str = parts[3]  # 'm=65536,t=3,p=4'
    cost_map: dict[str, int] = {}
    for segment in cost_str.split(','):
        k, v = segment.split('=')
        cost_map[k] = int(v)

    hash_b64 = parts[5]
    hash_bytes = _b64decode_unpadded(hash_b64)
    return Argon2Params(
        salt_b64=parts[4],
        time_cost=cost_map.get('t', 3),
        memory_cost=cost_map.get('m', 65536),
        parallelism=cost_map.get('p', 4),
        hash_len=len(hash_bytes),
        hash_b64=hash_b64,
    )


def _b64decode_unpadded(value: str) -> bytes:
    """Decode an unpadded base64 string (standard alphabet, not url-safe)."""
    padding = 4 - len(value) % 4
    if padding != 4:
        value = value + '=' * padding
    return base64.b64decode(value)


def make_challenge_message(nonce: str, username: str, challenge_id: str) -> str:
    """Return the canonical string that the client signs with HMAC."""
    return f'{nonce}|{username}|{challenge_id}'


def verify_challenge_response(
    django_hash: str,
    nonce: str,
    username: str,
    challenge_id: str,
    client_response: str,
) -> bool:
    """
    Verify a challenge-response proof.

    The HMAC key is the raw bytes of the stored Argon2id hash output (not
    re-computed — just decoded from the stored hash string), so the server
    never needs to run Argon2id during verification.

    Returns True iff the response is valid.  Always uses constant-time
    comparison to prevent timing leaks.
    """
    params = parse_argon2_hash(django_hash)
    if params is None:
        return False

    key_bytes = _b64decode_unpadded(params.hash_b64)
    message   = make_challenge_message(nonce, username, challenge_id)
    expected  = hmac.new(key_bytes, message.encode(), hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected, client_response)
    except (TypeError, ValueError):
        return False
