"""Shared pytest fixtures for the autopkg-runner test suite."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta

import django
import pytest

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
def api_client(api_token):
    """DRF APIClient authenticated with the user's token."""
    from rest_framework.test import APIClient
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Token {api_token.key}')
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
