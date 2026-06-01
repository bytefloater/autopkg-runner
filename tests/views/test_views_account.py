"""Tests for webapp.views.account.ChangePasswordView."""
from __future__ import annotations

import pytest


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
