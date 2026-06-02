"""Tests for webapp.views.runs: list, detail, trigger, cancel, delete, SSE."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest


@pytest.mark.django_db
class TestRunListView:
    url = '/runs/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_renders_empty(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 200

    def test_renders_with_runs(self, client, run):
        resp = client.get(self.url)
        assert resp.status_code == 200


@pytest.mark.django_db
class TestRunDetailView:
    def _url(self, run_id):
        return f'/runs/{run_id}/'

    def test_requires_login(self, anon_client, run):
        resp = anon_client.get(self._url(run.id))
        assert resp.status_code == 302

    def test_valid_run_returns_200(self, client, run):
        resp = client.get(self._url(run.id))
        assert resp.status_code == 200

    def test_invalid_uuid_returns_404(self, client):
        resp = client.get(self._url(uuid.uuid4()))
        assert resp.status_code == 404


@pytest.mark.django_db
class TestTriggerRunView:
    url = '/runs/trigger/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url)
        assert resp.status_code == 302

    def test_post_creates_run_and_redirects(self, client):
        # trigger_manual_run is imported inside the view function;
        # patch at its source module so the import sees the mock.
        with patch('webapp.runner.trigger_manual_run') as mock_trigger, \
             patch('webapp.models.Task') as mock_task_cls:
            fake_task_id = uuid.uuid4()
            mock_trigger.return_value = fake_task_id
            mock_task = MagicMock()
            mock_task.run_id = uuid.uuid4()
            mock_task_cls.objects.get.return_value = mock_task
            resp = client.post(self.url)
        assert resp.status_code in (302, 200)

    def test_post_while_already_running_redirects(self, client):
        # Non-HTMX requests get a flash message + redirect rather than 409.
        from webapp.runner import RunAlreadyRunningError
        with patch('webapp.runner.trigger_manual_run', side_effect=RunAlreadyRunningError('busy')):
            resp = client.post(self.url)
        assert resp.status_code == 302

    def test_htmx_post_while_already_running_returns_409(self, client):
        from webapp.runner import RunAlreadyRunningError
        with patch('webapp.runner.trigger_manual_run', side_effect=RunAlreadyRunningError('busy')):
            resp = client.post(self.url, HTTP_HX_REQUEST='true')
        assert resp.status_code == 409


@pytest.mark.django_db
class TestRunCancelView:
    def _url(self, run_id):
        return f'/runs/{run_id}/cancel/'

    def test_requires_login(self, anon_client, pending_run):
        resp = anon_client.post(self._url(pending_run.id))
        assert resp.status_code == 302

    def test_cancel_pending_run(self, client, pending_run):
        resp = client.post(self._url(pending_run.id))
        assert resp.status_code in (200, 204, 302)
        pending_run.refresh_from_db()
        assert pending_run.status == 'cancelled'

    def test_cancel_already_completed_run_is_noop(self, client, run):
        # run fixture has status='success'
        resp = client.post(self._url(run.id))
        # Should not raise; run remains success
        run.refresh_from_db()
        assert run.status == 'success'


@pytest.mark.django_db
class TestRunDeleteView:
    url = '/runs/delete/'

    def test_requires_login(self, anon_client, run):
        resp = anon_client.post(self.url, {'run_ids': [str(run.id)]})
        assert resp.status_code == 302

    def test_deletes_completed_runs(self, client, run):
        resp = client.post(self.url, {'run_ids': [str(run.id)]})
        assert resp.status_code in (200, 302)
        from webapp.models import Run
        assert not Run.objects.filter(id=run.id).exists()

    def test_does_not_delete_pending_runs(self, client, pending_run):
        client.post(self.url, {'run_ids': [str(pending_run.id)]})
        from webapp.models import Run
        assert Run.objects.filter(id=pending_run.id).exists()


@pytest.mark.django_db
class TestRunStream:
    def _url(self, run_id):
        return f'/runs/{run_id}/stream/'

    def test_accessible_without_login(self, anon_client, run):
        # The SSE endpoint is a plain function view with no login_required
        # decorator; it streams to anyone who can reach it (the run UUID acts
        # as an implicit access token for live-log consumers).
        resp = anon_client.get(self._url(run.id))
        assert resp.status_code == 200

    def test_returns_event_stream_content_type(self, client, run):
        resp = client.get(self._url(run.id))
        assert resp.status_code == 200
        assert 'text/event-stream' in resp.get('Content-Type', '')

    def test_stream_emits_complete_event_for_finished_run(self, client, run):
        """Consuming the generator for a completed run yields a 'complete' event."""
        resp = client.get(self._url(run.id))
        chunks = b''.join(resp.streaming_content)
        assert b'complete' in chunks
        assert run.status.encode() in chunks

    def test_stream_emits_log_entries(self, client, run):
        """Log entries are included in the SSE stream."""
        from datetime import datetime, timezone
        from webapp.models import LogEntry
        LogEntry.objects.create(
            run=run,
            level='INFO',
            message='Test log message',
            stage_name='',
            timestamp=datetime.now(timezone.utc),
        )
        resp = client.get(self._url(run.id))
        chunks = b''.join(resp.streaming_content)
        assert b'Test log message' in chunks

    def test_stream_emits_stage_updates(self, client, run):
        """Stage execution records are included in the SSE stream."""
        from webapp.models import StageExecution
        from datetime import datetime, timezone
        StageExecution.objects.create(
            run=run,
            name='UpdateRepos',
            status='success',
            order=0,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        resp = client.get(self._url(run.id))
        chunks = b''.join(resp.streaming_content)
        assert b'UpdateRepos' in chunks

    def test_stream_sends_error_for_nonexistent_run(self, client):
        """A nonexistent run_id causes an error event to be emitted."""
        missing_id = uuid.uuid4()
        resp = client.get(self._url(missing_id))
        chunks = b''.join(resp.streaming_content)
        assert b'error' in chunks or b'not found' in chunks

    def test_stream_respects_from_param(self, client, run):
        """?from=<id> skips log entries with id <= that value."""
        from datetime import datetime, timezone
        from webapp.models import LogEntry
        entry = LogEntry.objects.create(
            run=run,
            level='DEBUG',
            message='older message',
            stage_name='',
            timestamp=datetime.now(timezone.utc),
        )
        # Request with from=entry.id → should skip the entry above
        resp = client.get(self._url(run.id) + f'?from={entry.id}')
        chunks = b''.join(resp.streaming_content)
        assert b'older message' not in chunks

    def test_stream_no_cache_control_header(self, client, run):
        resp = client.get(self._url(run.id))
        assert resp.get('Cache-Control') == 'no-cache'
