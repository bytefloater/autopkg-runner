"""Tests for webapp.perms."""
from __future__ import annotations

import pytest


class TestUserHasPerm:
    def test_unauthenticated_user_returns_false(self):
        from webapp.perms import user_has_perm, PERM_VIEW_RUNS
        from unittest.mock import MagicMock
        user = MagicMock()
        user.is_authenticated = False
        assert user_has_perm(user, PERM_VIEW_RUNS) is False

    def test_none_user_returns_false(self):
        from webapp.perms import user_has_perm, PERM_VIEW_RUNS
        assert user_has_perm(None, PERM_VIEW_RUNS) is False

    def test_superuser_always_has_perm(self):
        from webapp.perms import user_has_perm, PERM_MANAGE_USERS
        from unittest.mock import MagicMock
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = True
        assert user_has_perm(user, PERM_MANAGE_USERS) is True


class TestGetUserPerms:
    def test_unauthenticated_returns_all_false(self):
        from webapp.perms import get_user_perms, ALL_PERMS
        from unittest.mock import MagicMock
        user = MagicMock()
        user.is_authenticated = False
        result = get_user_perms(user)
        assert all(v is False for v in result.values())
        assert set(result.keys()) == set(ALL_PERMS)

    def test_none_returns_all_false(self):
        from webapp.perms import get_user_perms, ALL_PERMS
        result = get_user_perms(None)
        assert all(v is False for v in result.values())

    def test_superuser_returns_all_true(self):
        from webapp.perms import get_user_perms, ALL_PERMS
        from unittest.mock import MagicMock
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = True
        result = get_user_perms(user)
        assert all(v is True for v in result.values())


@pytest.mark.django_db
class TestPermRequiredDecorator:
    def test_unauthenticated_redirects_to_login(self, rf):
        from webapp.perms import perm_required, PERM_VIEW_RUNS
        from unittest.mock import MagicMock

        @perm_required(PERM_VIEW_RUNS)
        def view(request):
            return MagicMock(status_code=200)

        request = rf.get('/some/path/')
        user = MagicMock()
        user.is_authenticated = False
        request.user = user
        resp = view(request)
        assert resp.status_code == 302

    def test_authenticated_without_perm_returns_403(self, rf, user, db):
        from webapp.perms import perm_required, PERM_MANAGE_USERS
        from unittest.mock import MagicMock
        from django.template import RequestContext

        @perm_required(PERM_MANAGE_USERS)
        def view(request):
            return MagicMock(status_code=200)

        request = rf.get('/some/path/')
        request.user = user
        request.is_mobile = False
        # user fixture is not superuser and has no permissions by default
        resp = view(request)
        assert resp.status_code == 403


@pytest.fixture
def rf():
    from django.test import RequestFactory
    return RequestFactory()
