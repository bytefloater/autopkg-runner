"""Shared pytest fixtures for the autopkg-runner test suite."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import django
import pytest


@pytest.fixture(autouse=True)
def _no_recipe_cache_thread(request):
    """Suppress background recipe-cache threads in all tests.

    The _build() thread opens Django DB connections that can outlive test
    teardown, producing ResourceWarning noise. Mark a test with
    ``@pytest.mark.real_cache_build`` to skip this patch and exercise the
    real function.
    """
    if request.node.get_closest_marker('real_cache_build'):
        yield
    else:
        with patch('webapp.views.recipes._start_cache_build'):
            yield

# Ensure the required environment variable is present before Django loads.
os.environ.setdefault('DJANGO_SECRET_KEY', 'test-secret-key-not-for-production')
os.environ.setdefault('DJANGO_DEBUG', 'true')


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def user(db):
    """A standard (non-super) user."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(username='testuser', password='testpass123')


@pytest.fixture
def superuser(db):
    """A superuser."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_superuser(username='admin', email='admin@example.com', password='adminpass123')


# ---------------------------------------------------------------------------
# Client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(user):
    """Django test client logged in as a regular user."""
    from django.test import Client
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def admin_client(superuser):
    """Django test client logged in as a superuser."""
    from django.test import Client
    c = Client()
    c.force_login(superuser)
    return c


@pytest.fixture
def anon_client():
    """Unauthenticated Django test client."""
    from django.test import Client
    return Client()


# ---------------------------------------------------------------------------
# API token / API client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_token(db, user):
    """An APIToken for the regular user."""
    from webapp.models import APIToken
    return APIToken.objects.create(user=user, name='Test Token')


@pytest.fixture
def grant_perm(db):
    """Helper: create/update a UserPermission row for a user.

    Usage::

        def test_something(user, client, grant_perm):
            grant_perm(user, can_trigger_runs=True)
    """
    def _grant(user, **perms):
        from webapp.models import UserPermission
        row, _ = UserPermission.objects.get_or_create(user=user)
        for field, value in perms.items():
            setattr(row, field, value)
        row.save()
    return _grant


@pytest.fixture
def run_manager_client(user, grant_perm):
    """Client logged in as a user with can_trigger_runs + can_view_runs."""
    grant_perm(user, can_trigger_runs=True, can_view_runs=True)
    from django.test import Client
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def config_editor_client(user, grant_perm):
    """Client logged in as a user with can_edit_config."""
    grant_perm(user, can_edit_config=True)
    from django.test import Client
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def api_run_manager_client(user, grant_perm):
    """DRF APIClient force-authenticated with can_trigger_runs + can_view_runs."""
    grant_perm(user, can_trigger_runs=True, can_view_runs=True)
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def api_client(user):
    """DRF APIClient force-authenticated as the regular user.

    Uses force_authenticate so view tests don't depend on the HMAC signing
    scheme — use test_api_auth.py to test the auth layer itself.
    """
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def anon_api_client():
    """Unauthenticated DRF APIClient."""
    from rest_framework.test import APIClient
    return APIClient()


# ---------------------------------------------------------------------------
# Model fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def run(db):
    """A completed (success) Run with timestamps."""
    from webapp.models import Run
    now = datetime.now(timezone.utc)
    # started_at is auto_now_add=True so we set it via update() after creation.
    r = Run.objects.create(
        status='success',
        triggered_by='manual',
        completed_at=now,
        config_snapshot={},
    )
    Run.objects.filter(pk=r.pk).update(started_at=now - timedelta(minutes=5))
    r.refresh_from_db()
    return r


@pytest.fixture
def pending_run(db):
    """A pending Run (not yet started)."""
    from webapp.models import Run
    return Run.objects.create(
        status='pending',
        triggered_by='manual',
        config_snapshot={},
    )


@pytest.fixture
def notifier(db):
    """A Pushover notifier for notification view tests."""
    from webapp.models import Notifier
    return Notifier.objects.create(
        name='Test Notifier',
        notifier_type='pushover',
        enabled=True,
        config={},
    )


@pytest.fixture
def webpush_notifier(db):
    """A WebPush notifier (no config fields)."""
    from webapp.models import Notifier
    return Notifier.objects.create(
        name='WebPush Notifier',
        notifier_type='webpush',
        enabled=True,
        config={},
    )


@pytest.fixture
def schedule(db):
    """The singleton Schedule row (pk=1) in its default enabled state."""
    from webapp.models import Schedule
    s = Schedule.get()
    s.enabled = True
    s.minute = '0'
    s.hour = '2'
    s.day_of_week = '*'
    s.day_of_month = '*'
    s.month = '*'
    s.save()
    return s
