"""Tests for api.views.auth: GetTokenView, CheckTokenView."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestGetTokenView:
    url = '/api/auth/get_token/'

    def test_valid_credentials_return_token(self, anon_api_client, user):
        resp = anon_api_client.post(self.url, {
            'username': 'testuser',
            'password': 'testpass123',
        })
        assert resp.status_code == 200
        data = resp.json()
        assert 'token' in data
        assert data['username'] == 'testuser'

    def test_invalid_credentials_return_400(self, anon_api_client, user):
        resp = anon_api_client.post(self.url, {
            'username': 'testuser',
            'password': 'wrongpassword',
        })
        assert resp.status_code in (400, 401, 403)

    def test_missing_username_returns_error(self, anon_api_client):
        resp = anon_api_client.post(self.url, {'password': 'pass'})
        assert resp.status_code in (400, 401, 403)

    def test_subsequent_call_returns_same_token(self, anon_api_client, user):
        resp1 = anon_api_client.post(self.url, {
            'username': 'testuser',
            'password': 'testpass123',
        })
        resp2 = anon_api_client.post(self.url, {
            'username': 'testuser',
            'password': 'testpass123',
        })
        assert resp1.json()['token'] == resp2.json()['token']


@pytest.mark.django_db
class TestCheckTokenView:
    url = '/api/auth/check_token/'

    def test_valid_token_returns_valid_true(self, api_client):
        resp = api_client.get(self.url)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get('valid') is True

    def test_no_token_returns_401_or_403(self, anon_api_client):
        resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)

    def test_invalid_token_returns_401_or_403(self, anon_api_client):
        anon_api_client.credentials(HTTP_AUTHORIZATION='Token invalidtoken000000000000000000000000')
        resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)
