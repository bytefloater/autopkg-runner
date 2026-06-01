"""Tests for webapp.views.schedule.ScheduleView."""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.django_db
class TestScheduleView:
    url = '/schedule/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_get_renders_schedule_form(self, client, schedule):
        resp = client.get(self.url)
        assert resp.status_code == 200

    def test_post_updates_schedule(self, client, schedule):
        with patch('webapp.scheduler.reschedule_job'):
            resp = client.post(self.url, {
                'enabled': 'on',
                'minute': '30',
                'hour': '3',
                'day_of_week': '*',
                'day_of_month': '*',
                'month': '*',
            })
        schedule.refresh_from_db()
        assert schedule.minute == '30'
        assert schedule.hour == '3'

    def test_post_calls_reschedule_job(self, client, schedule):
        with patch('webapp.scheduler.reschedule_job') as mock_reschedule:
            client.post(self.url, {
                'minute': '0',
                'hour': '2',
                'day_of_week': '*',
                'day_of_month': '*',
                'month': '*',
            })
        mock_reschedule.assert_called_once()

    def test_post_empty_fields_use_defaults(self, client, schedule):
        with patch('webapp.scheduler.reschedule_job'):
            client.post(self.url, {
                'minute': '',
                'hour': '',
                'day_of_week': '',
                'day_of_month': '',
                'month': '',
            })
        schedule.refresh_from_db()
        # Empty fields should be replaced with defaults, not stored as blank
        assert schedule.minute != ''
        assert schedule.hour != ''
