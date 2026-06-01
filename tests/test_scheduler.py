"""Tests for webapp.scheduler: get_system_timezone, reschedule_job, _safe_trigger."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

import pytest


class TestGetSystemTimezone:
    def test_returns_zoneinfo_object(self):
        from webapp.scheduler import get_system_timezone
        tz = get_system_timezone()
        assert isinstance(tz, ZoneInfo)

    def test_falls_back_to_utc_when_os_readlink_fails(self):
        from webapp.scheduler import get_system_timezone
        with patch('os.readlink', side_effect=OSError('no symlink')), \
             patch('builtins.open', side_effect=OSError('no file')):
            tz = get_system_timezone()
        assert isinstance(tz, ZoneInfo)
        # Should be UTC as final fallback
        assert str(tz) == 'UTC'


@pytest.mark.django_db
class TestRescheduleJob:
    def _mock_scheduler(self):
        sched = MagicMock()
        sched.running = True
        return sched

    def test_enabled_schedule_adds_cron_job(self, schedule):
        from webapp.scheduler import reschedule_job
        mock_sched = self._mock_scheduler()
        with patch('webapp.scheduler.get_scheduler', return_value=mock_sched):
            reschedule_job()
        mock_sched.add_job.assert_called_once()
        call_kwargs = mock_sched.add_job.call_args[1]
        assert call_kwargs.get('id') == 'autopkg_scheduled_run'

    def test_disabled_schedule_removes_job(self, schedule):
        from webapp.models import Schedule
        from webapp.scheduler import reschedule_job
        Schedule.objects.filter(pk=1).update(enabled=False)
        mock_sched = self._mock_scheduler()
        with patch('webapp.scheduler.get_scheduler', return_value=mock_sched):
            reschedule_job()
        mock_sched.add_job.assert_not_called()


@pytest.mark.django_db
class TestSafeTriggerScheduledRun:
    def test_calls_trigger_manual_run_with_scheduler(self):
        from webapp.scheduler import _safe_trigger_scheduled_run
        # trigger_manual_run is imported inside _safe_trigger_scheduled_run from
        # webapp.runner — patch it at the source module.
        with patch('webapp.runner.trigger_manual_run') as mock_trigger, \
             patch('django.db.close_old_connections'):
            _safe_trigger_scheduled_run()
        mock_trigger.assert_called_once_with(triggered_by='scheduler')

    def test_catches_run_already_running_error(self):
        from webapp.scheduler import _safe_trigger_scheduled_run
        from webapp.runner import RunAlreadyRunningError
        with patch('webapp.runner.trigger_manual_run', side_effect=RunAlreadyRunningError('busy')), \
             patch('django.db.close_old_connections'):
            # Should not raise
            _safe_trigger_scheduled_run()

    def test_catches_other_exceptions(self):
        from webapp.scheduler import _safe_trigger_scheduled_run
        with patch('webapp.runner.trigger_manual_run', side_effect=RuntimeError('boom')), \
             patch('django.db.close_old_connections'):
            # Should not raise
            _safe_trigger_scheduled_run()
