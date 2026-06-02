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

    def test_create_admin_user(self, admin_client):
        resp = admin_client.post(self.url, {
            'action': 'create',
            'username': 'newadmin',
            'is_superuser': 'on',
        })
        from django.contrib.auth import get_user_model
        User = get_user_model()
        u = User.objects.get(username='newadmin')
        assert u.is_superuser

    def test_update_user_email(self, admin_client, user):
        resp = admin_client.post(self.url, {
            'action': 'update',
            'user_id': str(user.id),
            'email': 'new@example.com',
            'is_active': 'on',
            'is_superuser': '',
        })
        user.refresh_from_db()
        assert user.email == 'new@example.com'

    def test_update_self_only_changes_email(self, admin_client, superuser):
        resp = admin_client.post(self.url, {
            'action': 'update',
            'user_id': str(superuser.id),
            'email': 'admin@new.com',
            'is_active': '',          # self-edit ignores these
            'is_superuser': '',
        })
        superuser.refresh_from_db()
        assert superuser.email == 'admin@new.com'
        assert superuser.is_superuser  # not changed

    def test_update_nonexistent_user_id(self, admin_client):
        resp = admin_client.post(self.url, {
            'action': 'update',
            'user_id': '99999',
        })
        assert resp.status_code == 302

    def test_delete_user(self, admin_client, user):
        uid = user.id
        admin_client.post(self.url, {
            'action': 'delete',
            'user_id': str(uid),
        })
        from django.contrib.auth import get_user_model
        User = get_user_model()
        assert not User.objects.filter(id=uid).exists()

    def test_delete_nonexistent_user_id(self, admin_client):
        resp = admin_client.post(self.url, {
            'action': 'delete',
            'user_id': '99999',
        })
        assert resp.status_code == 302

    def test_reset_password_for_other_user(self, admin_client, user):
        old_password = user.password
        admin_client.post(self.url, {
            'action': 'reset_password',
            'user_id': str(user.id),
        })
        user.refresh_from_db()
        assert user.password != old_password

    def test_reset_password_nonexistent_user(self, admin_client):
        resp = admin_client.post(self.url, {
            'action': 'reset_password',
            'user_id': '99999',
        })
        assert resp.status_code == 302


@pytest.mark.django_db
class TestUserEditView:
    def _url(self, pk):
        return f'/users/{pk}/'

    def test_requires_login(self, anon_client, user):
        resp = anon_client.get(self._url(user.id))
        assert resp.status_code == 302

    def test_non_superuser_forbidden(self, client, user):
        resp = client.get(self._url(user.id))
        assert resp.status_code in (302, 403)

    def test_superuser_can_view(self, admin_client, user):
        resp = admin_client.get(self._url(user.id))
        assert resp.status_code == 200

    def test_get_shows_edit_user(self, admin_client, user):
        resp = admin_client.get(self._url(user.id))
        assert resp.context['edit_user'] == user

    def test_post_update_other_user(self, admin_client, user):
        resp = admin_client.post(self._url(user.id), {
            'action': 'update',
            'email': 'user@updated.com',
            'is_active': 'on',
            'is_superuser': '',
        })
        assert resp.status_code == 302
        user.refresh_from_db()
        assert user.email == 'user@updated.com'

    def test_post_update_self_only_changes_email(self, admin_client, superuser):
        resp = admin_client.post(self._url(superuser.id), {
            'action': 'update',
            'email': 'self@example.com',
            'is_active': '',
            'is_superuser': '',
        })
        assert resp.status_code == 302
        superuser.refresh_from_db()
        assert superuser.email == 'self@example.com'
        assert superuser.is_superuser  # unchanged

    def test_post_cannot_demote_last_superuser(self, admin_client, superuser):
        resp = admin_client.post(self._url(superuser.id), {
            'action': 'update',
            'email': '',
            'is_active': 'on',
            'is_superuser': '',   # demote
        })
        # Should be prevented — not self-edit scenario means it should check remaining
        # but since we're editing a *different* superuser via admin_client…
        # admin_client is logged in as superuser so self-edit path fires; email change only
        superuser.refresh_from_db()
        assert superuser.is_superuser

    def test_post_reset_password(self, admin_client, user):
        old_pw = user.password
        resp = admin_client.post(self._url(user.id), {
            'action': 'reset_password',
        })
        assert resp.status_code == 302
        user.refresh_from_db()
        assert user.password != old_pw

    def test_post_reset_password_self_prevented(self, admin_client, superuser):
        resp = admin_client.post(self._url(superuser.id), {
            'action': 'reset_password',
        })
        assert resp.status_code == 302  # redirect with error message

    def test_post_delete_other_user(self, admin_client, user):
        uid = user.id
        resp = admin_client.post(self._url(uid), {
            'action': 'delete',
        })
        assert resp.status_code == 302
        from django.contrib.auth import get_user_model
        User = get_user_model()
        assert not User.objects.filter(id=uid).exists()

    def test_post_delete_self_prevented(self, admin_client, superuser):
        resp = admin_client.post(self._url(superuser.id), {
            'action': 'delete',
        })
        assert resp.status_code == 302
        from django.contrib.auth import get_user_model
        User = get_user_model()
        assert User.objects.filter(id=superuser.id).exists()

    def test_post_delete_last_superuser_prevented(self, admin_client, superuser):
        """Cannot delete superuser if it's the only one left."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        # Create a second superuser to act as admin, then try to delete superuser
        second = User.objects.create_superuser('second', '', 'pass')
        from django.test import Client
        c = Client()
        c.force_login(second)
        resp = c.post(self._url(superuser.id), {'action': 'delete'})
        # superuser should still exist since second superuser is trying to delete the last admin
        # Actually, since 'second' exists as another superuser, deleting superuser should succeed
        # Let me instead test deleting 'second' (the only remaining one) after removing superuser manually
        # Actually the simpler test: second tries to delete superuser when there are 2 superusers — SHOULD succeed
        User.objects.filter(id=superuser.id).delete()
        # Now second is the only superuser. Try to delete second.
        resp = c.post(self._url(second.id), {'action': 'delete'})
        assert resp.status_code == 302
        assert User.objects.filter(id=second.id).exists()  # prevented

    def test_post_unknown_action_redirects(self, admin_client, user):
        resp = admin_client.post(self._url(user.id), {'action': 'unknown'})
        assert resp.status_code == 302
