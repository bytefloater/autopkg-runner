"""Tests for webapp.views.dashboard.DashboardView."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest


@pytest.mark.django_db
class TestDashboardView:
    url = '/dashboard/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302
        assert '/login/' in resp['Location']

    def test_renders_for_authenticated_user(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 200

    def test_empty_db_renders_without_error(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 200
        ctx = resp.context
        assert ctx['last_run'] is None

    def test_last_run_is_most_recent(self, client, db):
        from webapp.models import Run
        now = datetime.now(timezone.utc)
        old = Run.objects.create(status='success', started_at=now - timedelta(days=2),
                                 completed_at=now - timedelta(days=2), config_snapshot={})
        recent = Run.objects.create(status='success', started_at=now - timedelta(minutes=5),
                                    completed_at=now, config_snapshot={})
        resp = client.get(self.url)
        assert resp.context['last_run'].id == recent.id

    def test_success_rate_50_percent(self, client, db):
        from webapp.models import Run
        now = datetime.now(timezone.utc)
        Run.objects.create(status='success', started_at=now - timedelta(days=1),
                           completed_at=now - timedelta(days=1), config_snapshot={})
        Run.objects.create(status='failed', started_at=now - timedelta(hours=1),
                           completed_at=now - timedelta(hours=1), config_snapshot={})
        resp = client.get(self.url)
        assert resp.context['success_rate_30d'] == 50

    def test_schedule_disabled_shows_no_next_run(self, client, db):
        from webapp.models import Schedule
        s = Schedule.get()
        s.enabled = False
        s.save()
        resp = client.get(self.url)
        assert resp.context['next_run_formatted'] is None
