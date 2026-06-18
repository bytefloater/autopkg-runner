"""Tests for api.views.auth: ChallengeView, GetTokenView, CheckTokenView."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

import pytest


def _compute_zk_response(challenge_json: dict, password: str) -> str:
    """
    Reproduce the browser-side ZK computation in Python for tests.

    Runs Argon2id locally with the server's params, then HMAC-SHA256s the
    canonical message with the resulting hash bytes.
    """
    from argon2.low_level import hash_secret_raw, Type
    import base64

    params = challenge_json['argon2_params']
    salt_b64 = params['salt']
    padding = 4 - len(salt_b64) % 4
    if padding != 4:
        salt_b64 = salt_b64 + '=' * padding
    salt_bytes = base64.b64decode(salt_b64)

    hash_bytes = hash_secret_raw(
        secret=password.encode(),
        salt=salt_bytes,
        time_cost=params['time_cost'],
        memory_cost=params['memory_cost'],
        parallelism=params['parallelism'],
        hash_len=params['hash_len'],
        type=Type.ID,
    )

    nonce        = challenge_json['nonce']
    challenge_id = challenge_json['challenge_id']
    username_field = challenge_json.get('username', '')
    msg = f'{nonce}|{username_field}|{challenge_id}'.encode()
    return hmac.new(hash_bytes, msg, hashlib.sha256).hexdigest()


def _hmac_auth_header(token_id: str, token_secret: str,
                      method: str, path: str, body: bytes = b'',
                      query: str = '') -> str:
    timestamp  = int(time.time())
    nonce      = secrets.token_hex(16)
    body_hash  = hashlib.sha256(body).hexdigest()
    canonical  = '\n'.join([method.upper(), path, query, str(timestamp), nonce, body_hash])
    sig        = hmac.new(token_secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return (
        f'HMAC-SHA256 Credential={token_id}, Timestamp={timestamp}, '
        f'Nonce={nonce}, Signature={sig}'
    )


@pytest.mark.django_db
class TestChallengeView:
    url = '/api/auth/challenge/'

    def test_returns_challenge_for_valid_user(self, anon_api_client, user):
        resp = anon_api_client.get(self.url, {'username': 'testuser'})
        assert resp.status_code == 200
        data = resp.json()
        assert 'challenge_id' in data
        assert 'nonce' in data
        assert 'argon2_params' in data
        p = data['argon2_params']
        assert all(k in p for k in ('salt', 'time_cost', 'memory_cost', 'parallelism', 'hash_len'))

    def test_missing_username_returns_error(self, anon_api_client):
        resp = anon_api_client.get(self.url)
        assert resp.status_code == 400

    def test_unknown_user_returns_400(self, anon_api_client, db):
        resp = anon_api_client.get(self.url, {'username': 'nobody'})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestGetTokenView:
    challenge_url = '/api/auth/challenge/'
    url           = '/api/auth/get_token/'

    def _get_token(self, client, username: str, password: str):
        ch_resp = client.get(self.challenge_url, {'username': username})
        assert ch_resp.status_code == 200
        ch = ch_resp.json()
        ch['username'] = username
        response_hex = _compute_zk_response(ch, password)
        return client.post(self.url, {
            'username':     username,
            'challenge_id': ch['challenge_id'],
            'response':     response_hex,
        }, format='json')

    def test_valid_credentials_return_token(self, anon_api_client, user):
        resp = self._get_token(anon_api_client, 'testuser', 'testpass123')
        assert resp.status_code == 200
        data = resp.json()
        assert 'token_id' in data
        assert 'token_secret' in data
        assert data['username'] == 'testuser'

    def test_wrong_password_returns_401(self, anon_api_client, user):
        ch_resp = anon_api_client.get(self.challenge_url, {'username': 'testuser'})
        ch = ch_resp.json()
        ch['username'] = 'testuser'
        resp = anon_api_client.post(self.url, {
            'username':     'testuser',
            'challenge_id': ch['challenge_id'],
            'response':     'deadbeef' * 8,  # wrong HMAC
        }, format='json')
        assert resp.status_code == 401

    def test_missing_fields_return_400(self, anon_api_client, user):
        resp = anon_api_client.post(self.url, {'username': 'testuser'}, format='json')
        assert resp.status_code == 400

    def test_challenge_cannot_be_reused(self, anon_api_client, user):
        ch_resp = anon_api_client.get(self.challenge_url, {'username': 'testuser'})
        ch = ch_resp.json()
        ch['username'] = 'testuser'
        response_hex = _compute_zk_response(ch, 'testpass123')
        payload = {
            'username':     'testuser',
            'challenge_id': ch['challenge_id'],
            'response':     response_hex,
        }
        r1 = anon_api_client.post(self.url, payload, format='json')
        r2 = anon_api_client.post(self.url, payload, format='json')
        assert r1.status_code == 200
        assert r2.status_code == 401   # challenge marked used


@pytest.mark.django_db
class TestCheckTokenView:
    url = '/api/auth/check_token/'

    def test_valid_hmac_signature_returns_valid_true(self, anon_api_client, api_token):
        auth = _hmac_auth_header(
            api_token.token_id,
            api_token.decrypted_secret,
            'GET', self.url,
        )
        anon_api_client.credentials(HTTP_AUTHORIZATION=auth)
        resp = anon_api_client.get(self.url)
        assert resp.status_code == 200
        assert resp.json().get('valid') is True

    def test_no_auth_returns_401(self, anon_api_client):
        resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)

    def test_wrong_signature_returns_401(self, anon_api_client, api_token):
        auth = _hmac_auth_header(
            api_token.token_id,
            'wrongsecret' * 5,
            'GET', self.url,
        )
        anon_api_client.credentials(HTTP_AUTHORIZATION=auth)
        resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)

    def test_replayed_nonce_returns_401(self, anon_api_client, api_token):
        auth = _hmac_auth_header(
            api_token.token_id,
            api_token.decrypted_secret,
            'GET', self.url,
        )
        anon_api_client.credentials(HTTP_AUTHORIZATION=auth)
        anon_api_client.get(self.url)          # first use — succeeds
        resp2 = anon_api_client.get(self.url)  # same nonce reused
        assert resp2.status_code in (401, 403)

    def test_old_token_format_returns_401(self, anon_api_client):
        anon_api_client.credentials(HTTP_AUTHORIZATION='Token ' + 'a' * 40)
        resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)


@pytest.mark.django_db
class TestHmacAuthenticationEdgeCases:
    url = '/api/auth/check_token/'

    def test_malformed_hmac_header_returns_401(self, anon_api_client):
        """Line 49: header starts with hmac-sha256 but doesn't match full regex."""
        anon_api_client.credentials(HTTP_AUTHORIZATION='HMAC-SHA256 InvalidFormat')
        resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)

    def test_inactive_user_returns_401(self, anon_api_client, api_token, user):
        """Line 66: user is inactive → AuthenticationFailed."""
        user.is_active = False
        user.save()
        auth = _hmac_auth_header(
            api_token.token_id,
            api_token.decrypted_secret,
            'GET', self.url,
        )
        anon_api_client.credentials(HTTP_AUTHORIZATION=auth)
        resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)

    def test_timestamp_drift_returns_401(self, anon_api_client, api_token):
        """Line 81: timestamp too old → AuthenticationFailed."""
        import secrets as _secrets
        import hashlib as _hashlib
        old_ts = int(time.time()) - 700  # 700s ago, beyond tolerance
        nonce = _secrets.token_hex(16)
        body_hash = _hashlib.sha256(b'').hexdigest()
        canonical = '\n'.join(['GET', self.url, '', str(old_ts), nonce, body_hash])
        sig = hmac.new(api_token.decrypted_secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        auth = (
            f'HMAC-SHA256 Credential={api_token.token_id}, Timestamp={old_ts}, '
            f'Nonce={nonce}, Signature={sig}'
        )
        anon_api_client.credentials(HTTP_AUTHORIZATION=auth)
        resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)

    def test_invalid_token_id_returns_401(self, anon_api_client, db):
        """Lines 89-90: token_id not in DB → AuthenticationFailed."""
        import secrets as _sec
        # 32 lowercase hex chars — matches _HEADER_RE but no APIToken exists with this id
        fake_id = _sec.token_hex(16)  # 32 hex chars
        auth = _hmac_auth_header(fake_id, 'anysecret', 'GET', self.url)
        anon_api_client.credentials(HTTP_AUTHORIZATION=auth)
        resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)


@pytest.mark.django_db
class TestHmacAuthenticationRareEdgeCases:
    url = '/api/auth/check_token/'

    def test_concurrent_nonce_replay_via_integrity_error(self, anon_api_client, api_token):
        """Lines 111-113: IntegrityError in _record_nonce → AuthenticationFailed."""
        from unittest.mock import patch
        from django.db import IntegrityError

        auth = _hmac_auth_header(
            api_token.token_id,
            api_token.decrypted_secret,
            'GET', self.url,
        )
        anon_api_client.credentials(HTTP_AUTHORIZATION=auth)
        with patch('webapp.models.UsedNonce.objects') as mock_mgr:
            mock_mgr.filter.return_value.exists.return_value = False  # nonce not in DB yet
            mock_mgr.create.side_effect = IntegrityError('duplicate key')
            mock_mgr.filter.return_value.delete.return_value = None
            resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)

    def test_compare_digest_type_error_returns_401(self, anon_api_client, api_token):
        """Line 136: TypeError in hmac.compare_digest → AuthenticationFailed."""
        from unittest.mock import patch

        auth = _hmac_auth_header(
            api_token.token_id,
            api_token.decrypted_secret,
            'GET', self.url,
        )
        anon_api_client.credentials(HTTP_AUTHORIZATION=auth)
        with patch('hmac.compare_digest', side_effect=TypeError('bad type')):
            resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)
