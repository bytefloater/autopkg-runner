"""Tests for webapp.views.account: login and ChangePasswordView."""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.django_db
class TestMobileAwareLoginView:
    url = '/login/'

    def test_get_renders_login_page(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 200

    def test_zk_login_success_redirects(self, anon_client, user):
        with patch('webapp.views.account.authenticate', return_value=user), \
             patch('webapp.views.account.auth_login'):
            resp = anon_client.post(self.url, {
                'username': user.username,
                'challenge_id': 'fake-challenge-id',
                'response': 'fake-response-hex',
            })
        assert resp.status_code == 302

    def test_zk_login_failure_rerenders_form(self, anon_client, user):
        with patch('webapp.views.account.authenticate', return_value=None):
            resp = anon_client.post(self.url, {
                'username': user.username,
                'challenge_id': 'bad-challenge-id',
                'response': 'bad-response',
            })
        assert resp.status_code == 200
        assert resp.context.get('zk_failed') is True

    def test_standard_password_login_falls_through(self, anon_client, user):
        resp = anon_client.post(self.url, {
            'username': user.username,
            'password': 'testpass123',
        })
        assert resp.status_code in (200, 302)

    def test_mobile_ua_uses_mobile_template(self, anon_client):
        ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'
        resp = anon_client.get(self.url, HTTP_USER_AGENT=ua)
        assert resp.status_code == 200
        assert 'mobile' in resp.template_name[0]


@pytest.mark.django_db
class TestChangePasswordView:
    url = '/account/change-password/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url, {})
        assert resp.status_code == 302

    def test_wrong_current_password_rejected(self, client, user):
        # The view always redirects (302) and sets a flash message on validation
        # errors rather than returning 400; the key assertion is that the
        # password is NOT changed.
        resp = client.post(self.url, {
            'current_password': 'wrongpassword',
            'new_password': 'newpass1234',
            'confirm_password': 'newpass1234',
        })
        assert resp.status_code in (200, 302, 400)
        # Password should be unchanged
        user.refresh_from_db()
        assert user.check_password('testpass123')

    def test_new_password_too_short_rejected(self, client, user):
        resp = client.post(self.url, {
            'current_password': 'testpass123',
            'new_password': 'short',
            'confirm_password': 'short',
        })
        assert resp.status_code in (200, 302, 400)
        user.refresh_from_db()
        assert user.check_password('testpass123')

    def test_mismatched_confirmation_rejected(self, client, user):
        resp = client.post(self.url, {
            'current_password': 'testpass123',
            'new_password': 'newpassword123',
            'confirm_password': 'differentpassword',
        })
        assert resp.status_code in (200, 302, 400)
        user.refresh_from_db()
        assert user.check_password('testpass123')

    def test_valid_change_updates_password(self, client, user):
        resp = client.post(self.url, {
            'current_password': 'testpass123',
            'new_password': 'mynewpassword',
            'confirm_password': 'mynewpassword',
        })
        user.refresh_from_db()
        assert user.check_password('mynewpassword')

    def test_valid_change_keeps_session_active(self, client, user):
        """After password change the user should remain logged in."""
        resp = client.post(self.url, {
            'current_password': 'testpass123',
            'new_password': 'mynewpassword',
            'confirm_password': 'mynewpassword',
        })
        # If session was killed we'd get a redirect to login on a subsequent request
        resp2 = client.get('/dashboard/')
        assert resp2.status_code == 200
