"""Tests for webapp.db_logger - thread-local helpers and DBLogHandler."""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest


class TestThreadLocals:
    def test_set_and_get_run_id(self):
        from webapp.db_logger import set_run_id, get_run_id
        import uuid
        run_id = uuid.uuid4()
        set_run_id(run_id)
        assert get_run_id() == run_id

    def test_get_run_id_returns_none_in_fresh_thread(self):
        from webapp.db_logger import get_run_id
        result = {}

        def worker():
            result['val'] = get_run_id()

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert result['val'] is None

    def test_set_and_get_current_stage(self):
        from webapp.db_logger import set_current_stage, get_current_stage
        set_current_stage('RunRecipes')
        assert get_current_stage() == 'RunRecipes'

    def test_get_current_stage_returns_empty_in_fresh_thread(self):
        from webapp.db_logger import get_current_stage
        result = {}

        def worker():
            result['val'] = get_current_stage()

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert result['val'] == ''


@pytest.mark.django_db
class TestDBLogHandler:
    def _clear_run_id(self):
        import webapp.db_logger as dl
        if hasattr(dl._local, 'run_id'):
            del dl._local.run_id

    def test_emit_with_no_run_id_does_nothing(self):
        from webapp.db_logger import DBLogHandler
        from webapp.models import LogEntry

        self._clear_run_id()
        handler = DBLogHandler()
        record = MagicMock()
        handler.emit(record)
        assert LogEntry.objects.count() == 0

    def test_emit_creates_log_entry(self, run):
        from webapp.db_logger import DBLogHandler, set_run_id
        from webapp.models import LogEntry

        set_run_id(run.id)
        handler = DBLogHandler()
        record = MagicMock()
        record.level_name = 'INFO'
        record.message = 'pipeline started'

        handler.emit(record)
        assert LogEntry.objects.filter(run=run, message='pipeline started', level='INFO').exists()

    def test_emit_uses_current_stage(self, run):
        from webapp.db_logger import DBLogHandler, set_run_id, set_current_stage
        from webapp.models import LogEntry

        set_run_id(run.id)
        set_current_stage('UpdateRepos')
        handler = DBLogHandler()
        record = MagicMock()
        record.level_name = 'DEBUG'
        record.message = 'updating repos'

        handler.emit(record)
        entry = LogEntry.objects.get(run=run)
        assert entry.stage_name == 'UpdateRepos'

    def test_emit_swallows_exceptions(self, run):
        from webapp.db_logger import DBLogHandler, set_run_id

        set_run_id(run.id)
        handler = DBLogHandler()
        record = MagicMock()
        record.level_name = 'ERROR'
        record.message = 'boom'

        with patch('webapp.models.LogEntry.objects.create', side_effect=Exception('DB down')):
            handler.emit(record)  # must not raise
