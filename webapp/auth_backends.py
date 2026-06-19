"""
Custom authentication backend for zero-knowledge challenge-response login.

Used by the web UI login form (and the same challenge mechanism as the API).
The backend authenticates a user given a pre-issued challenge_id and an
HMAC response computed by the browser — the plaintext password is never sent.

Falls through to ModelBackend when called with a raw password (legacy /
fallback path, active only when no challenge_id is provided).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class ChallengeResponseBackend:
    def authenticate(self, request, username=None, challenge_id=None, response=None, **kwargs):
        if not (username and challenge_id and response):
            return None

        from webapp.models import AuthChallenge
        from api.challenge_auth import verify_challenge_response

        try:
            challenge = AuthChallenge.objects.get(
                challenge_id=challenge_id,
                username=username,
                used=False,
            )
        except AuthChallenge.DoesNotExist:
            return None

        if challenge.expires_at < timezone.now():
            return None

        try:
            user = User.objects.get(username=username, is_active=True)
        except User.DoesNotExist:
            return None

        if not verify_challenge_response(
            django_hash=user.password,
            nonce=challenge.nonce,
            username=username,
            challenge_id=challenge_id,
            client_response=response,
        ):
            return None

        challenge.used = True
        challenge.save(update_fields=['used'])

        # Upgrade hash to Argon2id if it was PBKDF2 — can't do this without
        # the plaintext password, so ZK users will stay on whatever hasher
        # their password was last set with.
        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
