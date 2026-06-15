"""Tests for webapp.apps.WebappConfig: ready() guards and startup helpers."""
from __future__ import annotations

import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.django_db
class TestMarkInterruptedRuns:
    def test_marks_running_runs_as_failed(self):
        from webapp.models import Run
        from webapp.apps import WebappConfig

        run = Run.objects.create(status='running', config_snapshot={})
        cfg = WebappConfig('webapp', __import__('webapp'))
        cfg._mark_interrupted_runs()
        run.refresh_from_db()
        assert run.status == 'failed'

    def test_marks_pending_runs_as_failed(self):
        from webapp.models import Run
        from webapp.apps import WebappConfig

        run = Run.objects.create(status='pending', config_snapshot={})
        cfg = WebappConfig('webapp', __import__('webapp'))
        cfg._mark_interrupted_runs()
        run.refresh_from_db()
        assert run.status == 'failed'

    def test_leaves_completed_runs_unchanged(self):
        from webapp.models import Run
        from webapp.apps import WebappConfig

        run = Run.objects.create(status='success', config_snapshot={})
        cfg = WebappConfig('webapp', __import__('webapp'))
        cfg._mark_interrupted_runs()
        run.refresh_from_db()
        assert run.status == 'success'

    def test_marks_stale_tasks_as_failed(self):
        from webapp.models import Task
        from webapp.apps import WebappConfig

        task = Task.objects.create(task_type='pipeline_run', status='running')
        cfg = WebappConfig('webapp', __import__('webapp'))
        cfg._mark_interrupted_runs()
        task.refresh_from_db()
        assert task.status == 'failed'

    def test_marks_stale_stage_executions_as_failed(self):
        from webapp.models import Run, StageExecution
        from webapp.apps import WebappConfig

        run = Run.objects.create(status='running', config_snapshot={})
        stage = StageExecution.objects.create(
            run=run, name='TestStage', status='running', order=0,
        )
        cfg = WebappConfig('webapp', __import__('webapp'))
        cfg._mark_interrupted_runs()
        stage.refresh_from_db()
        assert stage.status == 'failed'

    def test_swallows_operational_error(self):
        """Should not raise if tables don't exist yet (pre-migration)."""
        from django.db.utils import OperationalError
        from webapp.apps import WebappConfig

        cfg = WebappConfig('webapp', __import__('webapp'))
        with patch('webapp.models.Run.objects') as mock_run_mgr:
            mock_run_mgr.filter.side_effect = OperationalError('no such table')
            cfg._mark_interrupted_runs()  # must not raise


@pytest.mark.django_db
class TestStartServices:
    def test_calls_start_scheduler_and_mark_interrupted(self):
        from webapp.apps import WebappConfig

        cfg = WebappConfig('webapp', __import__('webapp'))
        with patch('webapp.scheduler.start_scheduler') as mock_sched, \
             patch.object(cfg, '_mark_interrupted_runs') as mock_mark:
            cfg._start_services()

        mock_sched.assert_called_once()
        mock_mark.assert_called_once()


def _load_original_apps_module():
    """Load a fresh, unpatched copy of webapp.apps from source.

    test_settings.py replaces WebappConfig.ready with a no-op lambda so that
    background services never start during tests.  To exercise the guard logic
    we reload the module directly from its .py file (bypassing the patch).
    """
    import importlib.util
    import types
    import webapp.apps as apps_mod

    spec = importlib.util.spec_from_file_location('_apps_orig', apps_mod.__file__)
    assert spec is not None and spec.loader is not None
    fresh = types.ModuleType('_apps_orig')
    fresh.__spec__ = spec
    spec.loader.exec_module(fresh)
    return fresh


class TestReadyGuards:
    """Test that WebappConfig.ready() does NOT start background services
    for non-serving management commands."""

    # Fresh module loaded once for the whole class.
    _fresh_apps = _load_original_apps_module()

    def _call_ready(self, argv, env_overrides=None):
        """Call the original ready() with the given argv and env overrides.

        Returns the list of threads that had .start() called on them.
        We patch *_fresh_apps.threading* (the module the function actually
        reads its globals from) rather than webapp.apps.threading.
        """
        original_argv = sys.argv[:]
        saved_env = {}
        if env_overrides:
            for k, v in env_overrides.items():
                saved_env[k] = os.environ.get(k)
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        thread_started = []
        mock_thread_instance = MagicMock()
        mock_thread_instance.start.side_effect = lambda: thread_started.append(True)

        cfg = MagicMock()  # only _start_services is needed; threading is mocked
        try:
            sys.argv[:] = argv
            with patch.object(self._fresh_apps, 'threading') as mock_t:
                mock_t.Thread.return_value = mock_thread_instance
                self._fresh_apps.WebappConfig.ready(cfg)
        finally:
            sys.argv[:] = original_argv
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        return thread_started

    def test_migrate_command_skips_startup(self):
        assert self._call_ready(['manage.py', 'migrate']) == []

    def test_setup_command_skips_startup(self):
        assert self._call_ready(['manage.py', 'setup']) == []

    def test_generate_vapid_keys_skips_startup(self):
        assert self._call_ready(['manage.py', 'generate_vapid_keys']) == []

    def test_resetpassword_skips_startup(self):
        assert self._call_ready(['manage.py', 'resetpassword']) == []

    def test_no_subcommand_skips_startup(self):
        assert self._call_ready(['manage.py']) == []

    def test_runserver_with_run_main_starts_services(self):
        result = self._call_ready(
            ['manage.py', 'runserver'],
            env_overrides={'RUN_MAIN': 'true'},
        )
        assert len(result) == 1

    def test_runserver_without_run_main_skips_startup(self):
        result = self._call_ready(
            ['manage.py', 'runserver'],
            env_overrides={'RUN_MAIN': None},
        )
        assert result == []

    def test_noreload_starts_services_without_run_main_check(self):
        result = self._call_ready(
            ['manage.py', 'runserver', '--noreload'],
            env_overrides={'RUN_MAIN': None},
        )
        assert len(result) == 1
