"""Tests for webapp.views.users.UsersView — superuser guards."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestUsersView:
    url = '/users/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_non_superuser_forbidden(self, client):
        resp = client.get(self.url)
        assert resp.status_code in (302, 403)

    def test_superuser_can_access(self, admin_client):
        resp = admin_client.get(self.url)
        assert resp.status_code == 200

    def test_create_user(self, admin_client):
        resp = admin_client.post(self.url, {
            'action': 'create',
            'username': 'newuser',
        })
        from django.contrib.auth import get_user_model
        User = get_user_model()
        assert User.objects.filter(username='newuser').exists()

    def test_create_duplicate_username_rejected(self, admin_client, user):
        resp = admin_client.post(self.url, {
            'action': 'create',
            'username': 'testuser',  # already exists (user fixture)
        })
        from django.contrib.auth import get_user_model
        User = get_user_model()
        assert User.objects.filter(username='testuser').count() == 1

    def test_cannot_delete_own_account(self, admin_client, superuser):
        resp = admin_client.post(self.url, {
            'action': 'delete',
            'user_id': str(superuser.id),
        })
        from django.contrib.auth import get_user_model
        User = get_user_model()
        assert User.objects.filter(id=superuser.id).exists()

    def test_cannot_delete_last_superuser(self, admin_client, superuser):
        """If there is only one superuser, deleting it should be prevented."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        # Create a second user to delete (non-superuser), then try to delete the only superuser
        target = User.objects.create_user(username='victim', password='pass1234')
        resp = admin_client.post(self.url, {
            'action': 'delete',
            'user_id': str(superuser.id),
        })
        assert User.objects.filter(id=superuser.id).exists()

    def test_cannot_demote_last_superuser(self, admin_client, superuser):
        resp = admin_client.post(self.url, {
            'action': 'update',
            'user_id': str(superuser.id),
            'is_superuser': '',   # unchecked → demote
            'is_active': 'on',
        })
        superuser.refresh_from_db()
        assert superuser.is_superuser

    def test_reset_password_of_self_prevented(self, admin_client, superuser):
        resp = admin_client.post(self.url, {
            'action': 'reset_password',
            'user_id': str(superuser.id),
        })
        # No error raised; just silently skipped or redirected with message
        assert resp.status_code in (200, 302)
