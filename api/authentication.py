"""
HMAC-SHA256 request signing authentication for the AutoPkg Runner API.

Authorization header format:
    HMAC-SHA256 Credential=<token_id>, Timestamp=<unix_epoch_seconds>, Nonce=<16-byte-hex>, Signature=<64-byte-hex>

Canonical request string (what the client signs):
    METHOD\nURL_PATH\nTIMESTAMP\nNONCE\nSHA256(request_body_bytes)

The token_secret is the HMAC key (stored encrypted at rest).

Replay protection:
  - Timestamp must be within ±5 minutes of server time.
  - Nonce must not have been used before within that window (tracked in UsedNonce).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from typing import Optional

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

_TIMESTAMP_TOLERANCE = 300  # seconds
_HEADER_RE = re.compile(
    r'HMAC-SHA256\s+'
    r'Credential=(?P<credential>[0-9a-f]+),\s*'
    r'Timestamp=(?P<timestamp>\d+),\s*'
    r'Nonce=(?P<nonce>[0-9a-f]+),\s*'
    r'Signature=(?P<signature>[0-9a-f]+)',
    re.IGNORECASE,
)


class APITokenAuthentication(BaseAuthentication):
    """Authenticate requests using HMAC-SHA256 signed Authorization headers."""

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.lower().startswith('hmac-sha256'):
            return None

        m = _HEADER_RE.match(auth_header)
        if not m:
            raise AuthenticationFailed(
                'Malformed HMAC-SHA256 Authorization header. '
                'Expected: HMAC-SHA256 Credential=<token_id>, Timestamp=<ts>, Nonce=<nonce>, Signature=<sig>'
            )

        token_id  = m.group('credential')
        timestamp = int(m.group('timestamp'))
        nonce     = m.group('nonce')
        signature = m.group('signature')

        self._check_timestamp(timestamp)
        token = self._get_token(token_id)
        self._check_nonce(token_id, nonce)
        self._verify_signature(request, token, timestamp, nonce, signature)
        self._record_nonce(token_id, nonce)

        if not token.user.is_active:
            raise AuthenticationFailed('User account is disabled.')

        return (token.user, token)

    def authenticate_header(self, request) -> Optional[str]:   # type: ignore[override]
        return (
            'HMAC-SHA256 Credential=<token_id>, Timestamp=<unix_ts>, '
            'Nonce=<16-byte-hex>, Signature=<sha256-hex>'
        )

    # ------------------------------------------------------------------

    def _check_timestamp(self, timestamp: int) -> None:
        delta = abs(time.time() - timestamp)
        if delta > _TIMESTAMP_TOLERANCE:
            raise AuthenticationFailed(
                f'Request timestamp is too far from server time ({int(delta)}s drift, max {_TIMESTAMP_TOLERANCE}s).'
            )

    def _get_token(self, token_id: str):
        from webapp.models import APIToken
        try:
            return APIToken.objects.select_related('user').get(token_id=token_id)
        except APIToken.DoesNotExist:
            raise AuthenticationFailed('Invalid or revoked token.')

    def _check_nonce(self, token_id: str, nonce: str) -> None:
        from webapp.models import UsedNonce
        if UsedNonce.objects.filter(token_id=token_id, nonce=nonce).exists():
            raise AuthenticationFailed('Nonce has already been used — possible replay attack.')

    def _record_nonce(self, token_id: str, nonce: str) -> None:
        from webapp.models import UsedNonce
        UsedNonce.objects.create(
            token_id=token_id,
            nonce=nonce,
            used_at=timezone.now(),
        )
        # Prune nonces older than the timestamp window to keep the table small.
        cutoff = timezone.now() - timezone.timedelta(seconds=_TIMESTAMP_TOLERANCE)
        UsedNonce.objects.filter(token_id=token_id, used_at__lt=cutoff).delete()

    def _verify_signature(self, request, token, timestamp: int, nonce: str, signature: str) -> None:
        body  = request.body  # bytes
        body_hash = hashlib.sha256(body).hexdigest()
        canonical = '\n'.join([
            request.method.upper(),
            request.path,
            str(timestamp),
            nonce,
            body_hash,
        ])

        secret_bytes = token.decrypted_secret.encode()
        expected = hmac.new(secret_bytes, canonical.encode(), hashlib.sha256).hexdigest()
        try:
            if not hmac.compare_digest(expected, signature.lower()):
                raise AuthenticationFailed('HMAC signature verification failed.')
        except (TypeError, ValueError):
            raise AuthenticationFailed('HMAC signature verification failed.')
