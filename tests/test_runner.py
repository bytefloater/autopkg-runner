"""Tests for webapp.runner: trigger_manual_run, trigger_db_cleanup, _execute_db_cleanup."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest


@pytest.mark.django_db(transaction=True)
class TestTriggerManualRun:
    def _patch_execute(self):
        """Patch _execute_run so no real pipeline runs."""
        return patch('webapp.runner._execute_run')

    def _patch_config(self):
        # config_from_settings is imported inside trigger_manual_run; patch source.
        return patch('libs.config.config_from_settings', return_value=MagicMock())

    def _patch_pipeline_config_to_dict(self):
        # pipeline_config_to_dict is imported inside trigger_manual_run; patch source.
        return patch('libs.config.pipeline_config_to_dict', return_value={})

    def test_creates_run_and_task(self):
        from webapp.models import Run, Task
        from webapp.runner import trigger_manual_run
        with self._patch_execute(), self._patch_config(), self._patch_pipeline_config_to_dict():
            task_id = trigger_manual_run()
        assert Run.objects.filter(status='pending').exists()
        assert Task.objects.filter(id=task_id, task_type='pipeline_run').exists()

    def test_run_has_correct_triggered_by(self):
        from webapp.models import Run
        from webapp.runner import trigger_manual_run
        with self._patch_execute(), self._patch_config(), self._patch_pipeline_config_to_dict():
            trigger_manual_run(triggered_by='scheduler')
        run = Run.objects.get(triggered_by='scheduler')
        assert run.triggered_by == 'scheduler'

    def test_raises_when_run_already_running(self):
        from webapp.models import Run
        from webapp.runner import trigger_manual_run, RunAlreadyRunningError
        Run.objects.create(status='running', config_snapshot={})
        with self._patch_execute(), self._patch_config(), self._patch_pipeline_config_to_dict():
            with pytest.raises(RunAlreadyRunningError):
                trigger_manual_run()

    def test_raises_when_run_pending(self):
        from webapp.models import Run
        from webapp.runner import trigger_manual_run, RunAlreadyRunningError
        Run.objects.create(status='pending', config_snapshot={})
        with self._patch_execute(), self._patch_config(), self._patch_pipeline_config_to_dict():
            with pytest.raises(RunAlreadyRunningError):
                trigger_manual_run()

    def test_does_not_raise_after_completed_run(self):
        from webapp.models import Run
        from webapp.runner import trigger_manual_run
        Run.objects.create(status='success', config_snapshot={})
        with self._patch_execute(), self._patch_config(), self._patch_pipeline_config_to_dict():
            task_id = trigger_manual_run()  # should not raise
        assert task_id is not None

    def test_spawns_daemon_thread(self):
        spawned = []
        original_start = threading.Thread.start

        def fake_start(self_thread):
            spawned.append(self_thread)

        from webapp.runner import trigger_manual_run
        with self._patch_execute(), self._patch_config(), self._patch_pipeline_config_to_dict(), \
             patch.object(threading.Thread, 'start', fake_start):
            trigger_manual_run()

        assert len(spawned) == 1
        assert spawned[0].daemon is True

    def test_returns_uuid(self):
        from webapp.runner import trigger_manual_run
        with self._patch_execute(), self._patch_config(), self._patch_pipeline_config_to_dict():
            result = trigger_manual_run()
        assert isinstance(result, uuid.UUID)


@pytest.mark.django_db(transaction=True)
class TestTriggerDbCleanup:
    def test_creates_task_with_correct_type(self):
        from webapp.models import Task
        from webapp.runner import trigger_db_cleanup
        with patch('webapp.runner._execute_db_cleanup'):
            task_id = trigger_db_cleanup()
        task = Task.objects.get(id=task_id)
        assert task.task_type == 'db_cleanup'

    def test_returns_uuid(self):
        from webapp.runner import trigger_db_cleanup
        with patch('webapp.runner._execute_db_cleanup'):
            result = trigger_db_cleanup()
        assert isinstance(result, uuid.UUID)


@pytest.mark.django_db(transaction=True)
class TestExecuteDbCleanup:
    def test_deletes_old_runs_and_leaves_recent(self):
        from webapp.models import Run, Task
        from webapp.runner import _execute_db_cleanup

        now = datetime.now(timezone.utc)
        old = Run.objects.create(
            status='success',
            started_at=now - timedelta(days=100),
            completed_at=now - timedelta(days=100),
            config_snapshot={},
        )
        recent = Run.objects.create(
            status='success',
            started_at=now - timedelta(days=5),
            completed_at=now - timedelta(days=5),
            config_snapshot={},
        )
        task = Task.objects.create(task_type='db_cleanup', status='pending')

        _execute_db_cleanup(task.id)

        assert not Run.objects.filter(id=old.id).exists()
        assert Run.objects.filter(id=recent.id).exists()

    def test_task_marked_success_on_clean_run(self):
        from webapp.models import Task
        from webapp.runner import _execute_db_cleanup
        task = Task.objects.create(task_type='db_cleanup', status='pending')
        _execute_db_cleanup(task.id)
        task.refresh_from_db()
        assert task.status == 'success'

    def test_task_marked_failed_on_exception(self):
        from webapp.models import Task
        from webapp.runner import _execute_db_cleanup

        task = Task.objects.create(task_type='db_cleanup', status='pending')
        with patch('webapp.models.Run.objects') as mock_run:
            mock_run.filter.side_effect = Exception('DB error')
            _execute_db_cleanup(task.id)
        task.refresh_from_db()
        assert task.status == 'failed'


@pytest.mark.django_db(transaction=True)
class TestExecuteRun:
    """Tests for the _execute_run background function."""

    def _make_mock_orchestrator(self, success=True):
        mock_orch = MagicMock()
        mock_orch.execute.return_value = success
        return mock_orch

    def _patches(self, mock_orch):
        """Return a stack of patches needed to run _execute_run without real pipeline."""
        mock_handler = MagicMock()
        mock_handler_cls = MagicMock(return_value=mock_handler)
        return [
            patch('webapp.db_logger.DBLogHandler', mock_handler_cls),
            patch('webapp.db_logger.set_run_id'),
            patch('webapp.db_logger.set_current_stage'),
            patch('libs.config.config_from_settings', return_value=MagicMock()),
            patch('libs.orchestrator.Orchestrator', return_value=mock_orch),
        ]

    def test_run_marked_success_when_pipeline_succeeds(self):
        from webapp.models import Run, Task
        from webapp.runner import _execute_run

        run = Run.objects.create(status='pending', config_snapshot={})
        task = Task.objects.create(task_type='pipeline_run', status='pending', run=run)
        mock_orch = self._make_mock_orchestrator(success=True)

        with patch('webapp.db_logger.DBLogHandler', MagicMock(return_value=MagicMock())), \
             patch('webapp.db_logger.set_run_id'), \
             patch('webapp.db_logger.set_current_stage'), \
             patch('libs.config.config_from_settings', return_value=MagicMock()), \
             patch('libs.orchestrator.Orchestrator', return_value=mock_orch):
            _execute_run(run.id, task.id)

        run.refresh_from_db()
        assert run.status == 'success'

    def test_run_marked_failed_when_pipeline_returns_false(self):
        from webapp.models import Run, Task
        from webapp.runner import _execute_run

        run = Run.objects.create(status='pending', config_snapshot={})
        task = Task.objects.create(task_type='pipeline_run', status='pending', run=run)
        mock_orch = self._make_mock_orchestrator(success=False)

        with patch('webapp.db_logger.DBLogHandler', MagicMock(return_value=MagicMock())), \
             patch('webapp.db_logger.set_run_id'), \
             patch('webapp.db_logger.set_current_stage'), \
             patch('libs.config.config_from_settings', return_value=MagicMock()), \
             patch('libs.orchestrator.Orchestrator', return_value=mock_orch):
            _execute_run(run.id, task.id)

        run.refresh_from_db()
        assert run.status == 'failed'

    def test_run_marked_failed_when_exception_raised(self):
        from webapp.models import Run, Task
        from webapp.runner import _execute_run

        run = Run.objects.create(status='pending', config_snapshot={})
        task = Task.objects.create(task_type='pipeline_run', status='pending', run=run)

        with patch('webapp.db_logger.DBLogHandler', MagicMock(return_value=MagicMock())), \
             patch('webapp.db_logger.set_run_id'), \
             patch('webapp.db_logger.set_current_stage'), \
             patch('libs.config.config_from_settings', side_effect=Exception('config failed')):
            _execute_run(run.id, task.id)

        run.refresh_from_db()
        assert run.status == 'failed'

    def test_mid_flight_cancel_preserved_in_finally(self):
        """If a run is cancelled externally while the pipeline runs,
        the finally block must not overwrite the 'cancelled' status."""
        from webapp.models import Run, Task
        from webapp.runner import _execute_run

        run = Run.objects.create(status='pending', config_snapshot={})
        task = Task.objects.create(task_type='pipeline_run', status='pending', run=run)

        def cancel_run_during_execution():
            # Simulate user clicking Cancel while pipeline is running
            Run.objects.filter(id=run.id).update(status='cancelled')
            Task.objects.filter(id=task.id).update(status='cancelled')
            return True  # orchestrator returns True (success) but run is already cancelled

        mock_orch = MagicMock()
        mock_orch.execute.side_effect = cancel_run_during_execution

        with patch('webapp.db_logger.DBLogHandler', MagicMock(return_value=MagicMock())), \
             patch('webapp.db_logger.set_run_id'), \
             patch('webapp.db_logger.set_current_stage'), \
             patch('libs.config.config_from_settings', return_value=MagicMock()), \
             patch('libs.orchestrator.Orchestrator', return_value=mock_orch):
            _execute_run(run.id, task.id)

        run.refresh_from_db()
        # The finally block uses exclude(status='cancelled') so 'cancelled' is preserved
        assert run.status == 'cancelled'

    def test_task_marked_success_on_success(self):
        from webapp.models import Run, Task
        from webapp.runner import _execute_run

        run = Run.objects.create(status='pending', config_snapshot={})
        task = Task.objects.create(task_type='pipeline_run', status='pending', run=run)
        mock_orch = self._make_mock_orchestrator(success=True)

        with patch('webapp.db_logger.DBLogHandler', MagicMock(return_value=MagicMock())), \
             patch('webapp.db_logger.set_run_id'), \
             patch('webapp.db_logger.set_current_stage'), \
             patch('libs.config.config_from_settings', return_value=MagicMock()), \
             patch('libs.orchestrator.Orchestrator', return_value=mock_orch):
            _execute_run(run.id, task.id)

        task.refresh_from_db()
        assert task.status == 'success'

    def test_stage_callback_creates_stage_execution(self):
        """stage_callback with status='running' creates a StageExecution row."""
        from datetime import datetime, timezone
        from webapp.models import Run, Task, StageExecution
        from webapp.runner import _execute_run

        run = Run.objects.create(status='pending', config_snapshot={})
        task = Task.objects.create(task_type='pipeline_run', status='pending', run=run)

        captured_callback = []

        def fake_orchestrator_cls(**kwargs):
            mock_orch = MagicMock()
            # Capture the stage_callback so we can call it in execute()
            cb = kwargs.get('stage_callback')

            def execute_with_callback():
                if cb:
                    cb('UpdateRepos', 'running', datetime.now(timezone.utc))
                    cb('UpdateRepos', 'success', datetime.now(timezone.utc))
                return True

            mock_orch.execute.side_effect = execute_with_callback
            return mock_orch

        with patch('webapp.db_logger.DBLogHandler', MagicMock(return_value=MagicMock())), \
             patch('webapp.db_logger.set_run_id'), \
             patch('webapp.db_logger.set_current_stage'), \
             patch('libs.config.config_from_settings', return_value=MagicMock()), \
             patch('libs.orchestrator.Orchestrator', side_effect=fake_orchestrator_cls):
            _execute_run(run.id, task.id)

        assert StageExecution.objects.filter(run=run, name='UpdateRepos').exists()


@pytest.mark.django_db
class TestExecuteRunLogbookFallback:
    def test_logbook_import_failure_is_swallowed(self, db):
        """Lines 129-130: if logbook.Logger import fails inside the except handler, it's swallowed."""
        from webapp.runner import _execute_run
        from webapp.models import Run, Task
        run = Run.objects.create(status='pending', triggered_by='manual', config_snapshot={})
        task = Task.objects.create(task_type='pipeline', status='running', run_id=run.id)

        with patch('libs.config.config_from_settings', side_effect=RuntimeError('crash during setup')), \
             patch('logbook.Logger', side_effect=RuntimeError('logbook broken')):
            _execute_run(run.id, task.id)

        run.refresh_from_db()
        assert run.status == 'failed'
