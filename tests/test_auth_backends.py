"""Tests for webapp.auth_backends.ChallengeResponseBackend."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def backend():
    from webapp.auth_backends import ChallengeResponseBackend
    return ChallengeResponseBackend()


@pytest.mark.django_db
class TestChallengeResponseBackendAuthenticate:
    def test_returns_none_with_missing_credentials(self, backend):
        assert backend.authenticate(None) is None
        assert backend.authenticate(None, username='alice') is None
        assert backend.authenticate(None, username='alice', challenge_id='x') is None

    def test_returns_none_for_unknown_challenge(self, backend, user):
        result = backend.authenticate(
            None,
            username=user.username,
            challenge_id='nonexistent-uuid',
            response='abc123',
        )
        assert result is None

    def test_returns_none_for_used_challenge(self, backend, user, db):
        from webapp.models import AuthChallenge
        from django.utils import timezone
        challenge = AuthChallenge.objects.create(
            username=user.username,
            challenge_id='used-challenge-id',
            nonce='some-nonce',
            used=True,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        result = backend.authenticate(
            None,
            username=user.username,
            challenge_id='used-challenge-id',
            response='any',
        )
        assert result is None

    def test_returns_none_for_expired_challenge(self, backend, user, db):
        from webapp.models import AuthChallenge
        from django.utils import timezone
        AuthChallenge.objects.create(
            username=user.username,
            challenge_id='expired-challenge-id',
            nonce='some-nonce',
            used=False,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        result = backend.authenticate(
            None,
            username=user.username,
            challenge_id='expired-challenge-id',
            response='any',
        )
        assert result is None

    def test_returns_none_for_inactive_user(self, backend, db):
        from django.contrib.auth import get_user_model
        from webapp.models import AuthChallenge
        from django.utils import timezone
        User = get_user_model()
        inactive = User.objects.create_user(
            username='inactive', password='pass', is_active=False
        )
        AuthChallenge.objects.create(
            username='inactive',
            challenge_id='inactive-challenge',
            nonce='nonce',
            used=False,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        result = backend.authenticate(
            None,
            username='inactive',
            challenge_id='inactive-challenge',
            response='any',
        )
        assert result is None

    def test_returns_none_for_wrong_response(self, backend, user, db):
        from webapp.models import AuthChallenge
        from django.utils import timezone
        AuthChallenge.objects.create(
            username=user.username,
            challenge_id='valid-challenge-id',
            nonce='nonce',
            used=False,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        with patch('api.challenge_auth.verify_challenge_response', return_value=False):
            result = backend.authenticate(
                None,
                username=user.username,
                challenge_id='valid-challenge-id',
                response='wrong-response',
            )
        assert result is None

    def test_returns_user_for_valid_response(self, backend, user, db):
        from webapp.models import AuthChallenge
        from django.utils import timezone
        AuthChallenge.objects.create(
            username=user.username,
            challenge_id='good-challenge-id',
            nonce='nonce',
            used=False,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        with patch('api.challenge_auth.verify_challenge_response', return_value=True):
            result = backend.authenticate(
                None,
                username=user.username,
                challenge_id='good-challenge-id',
                response='correct',
            )
        assert result is not None
        assert result.pk == user.pk

    def test_challenge_marked_used_after_success(self, backend, user, db):
        from webapp.models import AuthChallenge
        from django.utils import timezone
        AuthChallenge.objects.create(
            username=user.username,
            challenge_id='mark-used-challenge',
            nonce='nonce',
            used=False,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        with patch('api.challenge_auth.verify_challenge_response', return_value=True):
            backend.authenticate(
                None,
                username=user.username,
                challenge_id='mark-used-challenge',
                response='correct',
            )
        challenge = AuthChallenge.objects.get(challenge_id='mark-used-challenge')
        assert challenge.used is True


@pytest.mark.django_db
class TestChallengeResponseBackendGetUser:
    def test_returns_user_for_valid_id(self, backend, user):
        result = backend.get_user(user.pk)
        assert result is not None
        assert result.pk == user.pk

    def test_returns_none_for_invalid_id(self, backend):
        result = backend.get_user(999999)
        assert result is None
