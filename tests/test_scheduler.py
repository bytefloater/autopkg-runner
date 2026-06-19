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

    def test_falls_back_to_utc_when_both_sources_fail(self):
        from webapp.scheduler import get_system_timezone
        with patch('os.path.realpath', side_effect=OSError('no symlink')), \
             patch('builtins.open', side_effect=OSError('no file')):
            tz = get_system_timezone()
        assert str(tz) == 'UTC'

    def test_reads_localtime_symlink_successfully(self):
        from webapp.scheduler import get_system_timezone
        with patch('os.path.realpath', return_value='/usr/share/zoneinfo/Europe/London'):
            tz = get_system_timezone()
        assert str(tz) == 'Europe/London'

    def test_falls_back_to_etc_timezone(self):
        """When /etc/localtime has no /zoneinfo/ component, reads /etc/timezone."""
        from webapp.scheduler import get_system_timezone
        from unittest.mock import mock_open
        with patch('os.path.realpath', return_value='/etc/localtime'), \
             patch('builtins.open', mock_open(read_data='America/New_York')):
            tz = get_system_timezone()
        assert str(tz) == 'America/New_York'

    def test_falls_back_to_utc_when_localtime_no_zoneinfo(self):
        """realpath returns a path without /zoneinfo/ and /etc/timezone fails."""
        from webapp.scheduler import get_system_timezone
        with patch('os.path.realpath', return_value='/etc/localtime'), \
             patch('builtins.open', side_effect=OSError('no timezone file')):
            tz = get_system_timezone()
        assert str(tz) == 'UTC'


class TestGetScheduler:
    def test_creates_new_scheduler_when_none_exists(self):
        import webapp.scheduler as sched_mod
        from apscheduler.schedulers.background import BackgroundScheduler

        original = sched_mod._scheduler
        sched_mod._scheduler = None
        try:
            with patch.object(sched_mod, 'BackgroundScheduler') as mock_bgs_cls:
                mock_instance = MagicMock()
                mock_bgs_cls.return_value = mock_instance
                result = sched_mod.get_scheduler()
            assert result is mock_instance
            mock_bgs_cls.assert_called_once()
        finally:
            sched_mod._scheduler = original

    def test_returns_existing_scheduler(self):
        import webapp.scheduler as sched_mod
        fake = MagicMock()
        original = sched_mod._scheduler
        sched_mod._scheduler = fake
        try:
            result = sched_mod.get_scheduler()
            assert result is fake
        finally:
            sched_mod._scheduler = original


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
        # Two add_job calls: autopkg_scheduled_run + recipe_index_refresh
        assert mock_sched.add_job.call_count >= 1
        ids = [c[1].get('id') for c in mock_sched.add_job.call_args_list]
        assert 'autopkg_scheduled_run' in ids

    def test_disabled_schedule_removes_job(self, schedule):
        from webapp.models import Schedule
        from webapp.scheduler import reschedule_job
        Schedule.objects.filter(pk=1).update(enabled=False)
        mock_sched = self._mock_scheduler()
        with patch('webapp.scheduler.get_scheduler', return_value=mock_sched):
            reschedule_job()
        # Index refresh job is still added even when the run schedule is disabled
        ids = [c[1].get('id') for c in mock_sched.add_job.call_args_list]
        assert 'autopkg_scheduled_run' not in ids
        assert 'recipe_index_refresh' in ids

    def test_starts_scheduler_when_not_running(self, schedule):
        from webapp.scheduler import reschedule_job
        mock_sched = self._mock_scheduler()
        mock_sched.running = False  # not yet started
        with patch('webapp.scheduler.get_scheduler', return_value=mock_sched):
            reschedule_job()
        mock_sched.start.assert_called_once()

    def test_remove_job_exception_is_swallowed(self, schedule):
        """If remove_job raises (e.g. job doesn't exist), it is silently ignored."""
        from webapp.scheduler import reschedule_job
        mock_sched = self._mock_scheduler()
        mock_sched.remove_job.side_effect = Exception('job not found')
        with patch('webapp.scheduler.get_scheduler', return_value=mock_sched):
            reschedule_job()   # must not raise
        # Two jobs are always registered (run + index refresh)
        assert mock_sched.add_job.call_count >= 1


@pytest.mark.django_db
class TestStartScheduler:
    def test_starts_scheduler_if_not_running(self, schedule):
        from webapp.scheduler import start_scheduler
        mock_sched = MagicMock()
        mock_sched.running = False
        with patch('webapp.scheduler.get_scheduler', return_value=mock_sched), \
             patch('webapp.scheduler.reschedule_job'):
            start_scheduler()
        mock_sched.start.assert_called_once()

    def test_does_not_restart_already_running_scheduler(self, schedule):
        from webapp.scheduler import start_scheduler
        mock_sched = MagicMock()
        mock_sched.running = True
        with patch('webapp.scheduler.get_scheduler', return_value=mock_sched), \
             patch('webapp.scheduler.reschedule_job'):
            start_scheduler()
        mock_sched.start.assert_not_called()

    def test_reschedule_exception_is_logged(self, schedule):
        from webapp.scheduler import start_scheduler
        mock_sched = MagicMock()
        mock_sched.running = True
        with patch('webapp.scheduler.get_scheduler', return_value=mock_sched), \
             patch('webapp.scheduler.reschedule_job', side_effect=Exception('db gone')):
            start_scheduler()  # must not raise


@pytest.mark.django_db
class TestSafeTriggerScheduledRun:
    def test_calls_trigger_manual_run_with_scheduler(self):
        from webapp.scheduler import _safe_trigger_scheduled_run
        # trigger_manual_run is imported inside _safe_trigger_scheduled_run from
        # webapp.runner - patch it at the source module.
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


class TestAcquireSchedulerLock:
    def test_acquires_lock_and_returns_true(self, tmp_path, settings):
        settings.BASE_DIR = tmp_path
        import webapp.scheduler as sched_mod
        original_fd = sched_mod._lock_fd
        sched_mod._lock_fd = None
        try:
            result = sched_mod.acquire_scheduler_lock()
            assert result is True
        finally:
            if sched_mod._lock_fd:
                sched_mod._lock_fd.close()
            sched_mod._lock_fd = original_fd

    def test_returns_false_when_lock_unavailable(self, tmp_path, settings):
        settings.BASE_DIR = tmp_path
        import webapp.scheduler as sched_mod
        import fcntl
        # Pre-acquire the lock with an independent fd
        lock_path = tmp_path / 'scheduler.lock'
        fd = open(lock_path, 'w')
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            result = sched_mod.acquire_scheduler_lock()
            assert result is False
        finally:
            fd.close()


@pytest.mark.django_db
class TestStartSchedulerDbNotReady:
    def test_catches_operational_error_from_reschedule(self, schedule):
        from webapp.scheduler import start_scheduler
        from django.db import OperationalError
        mock_sched = MagicMock()
        mock_sched.running = True
        with patch('webapp.scheduler.get_scheduler', return_value=mock_sched), \
             patch('webapp.scheduler.reschedule_job', side_effect=OperationalError('no table')):
            start_scheduler()  # must not raise — logs debug and continues

    def test_catches_programming_error_from_reschedule(self, schedule):
        from webapp.scheduler import start_scheduler
        from django.db import ProgrammingError
        mock_sched = MagicMock()
        mock_sched.running = True
        with patch('webapp.scheduler.get_scheduler', return_value=mock_sched), \
             patch('webapp.scheduler.reschedule_job', side_effect=ProgrammingError('relation does not exist')):
            start_scheduler()  # must not raise


class TestAcquireSchedulerLockFdCloseFails:
    def test_fd_close_exception_is_swallowed(self, tmp_path, settings):
        """When open() raises, fd is undefined, and fd.close() raises NameError,
        which is caught by the inner except Exception: pass (lines 36-37)."""
        import webapp.scheduler as sched_mod
        settings.BASE_DIR = tmp_path
        original_fd = sched_mod._lock_fd
        sched_mod._lock_fd = None
        try:
            with patch('builtins.open', side_effect=IOError('permission denied')):
                result = sched_mod.acquire_scheduler_lock()
            assert result is False
        finally:
            sched_mod._lock_fd = original_fd
