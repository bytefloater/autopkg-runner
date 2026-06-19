"""Tests for webapp.views.runs: list, detail, trigger, cancel, delete, SSE."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest


IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'


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

    def test_mobile_ua_uses_mobile_template(self, run_manager_client, run):
        resp = run_manager_client.get(self.url, HTTP_USER_AGENT=IPHONE_UA)
        assert resp.status_code == 200
        assert 'mobile' in resp.template_name[0]


@pytest.mark.django_db
class TestRunDetailView:
    def _url(self, run_id):
        return f'/runs/{run_id}/'

    def test_requires_login(self, anon_client, run):
        resp = anon_client.get(self._url(run.id))
        assert resp.status_code == 302

    def test_valid_run_returns_200(self, run_manager_client, run):
        resp = run_manager_client.get(self._url(run.id))
        assert resp.status_code == 200

    def test_invalid_uuid_returns_404(self, run_manager_client):
        resp = run_manager_client.get(self._url(uuid.uuid4()))
        assert resp.status_code == 404

    def test_mobile_ua_uses_mobile_template(self, run_manager_client, run):
        resp = run_manager_client.get(self._url(run.id), HTTP_USER_AGENT=IPHONE_UA)
        assert resp.status_code == 200
        assert 'mobile' in resp.template_name[0]

    def test_detail_with_munki_import_result(self, run_manager_client, run):
        from webapp.models import RecipeResult, Setting
        Setting.set('repository.public_url', 'http://munki.local')
        Setting.set('repository.public_url_username', '')
        Setting.set('repository.public_url_password', '')
        RecipeResult.objects.create(
            run=run,
            result_type='munki_import',
            data=[{'name': 'Firefox', 'version': '120.0', 'catalogs': ['testing']}],
        )
        with patch('webapp.views.runs._get_munki_icon_map', return_value={'Firefox': 'icons/Firefox.png'}):
            resp = run_manager_client.get(self._url(run.id))
        assert resp.status_code == 200
        munki_rows = resp.context['munki_import_rows']
        assert munki_rows

    def test_detail_with_log_entries(self, run_manager_client, run):
        """Log entries are included in logs_by_stage context — covers loop body."""
        from webapp.models import LogEntry
        LogEntry.objects.create(
            run=run, level='INFO', message='step done',
            stage_name='UpdateRepos', timestamp=datetime.now(timezone.utc),
        )
        resp = run_manager_client.get(self._url(run.id))
        assert resp.status_code == 200
        assert 'UpdateRepos' in resp.context['logs_by_stage']

    def test_detail_munki_exception_is_silenced(self, run_manager_client, run):
        """Exception inside the munki icon block is swallowed; view still returns 200."""
        from webapp.models import RecipeResult, Setting
        Setting.set('repository.public_url', 'http://munki.local')
        RecipeResult.objects.create(
            run=run, result_type='munki_import',
            data=[{'name': 'App', 'version': '1.0', 'catalogs': ['all']}],
        )
        with patch('webapp.views.runs._get_munki_icon_map', side_effect=RuntimeError('boom')):
            resp = run_manager_client.get(self._url(run.id))
        assert resp.status_code == 200
        assert resp.context['munki_import_rows'] == {}

    def test_detail_munki_catalog_from_string(self, run_manager_client, run):
        """Catalog extracted when catalogs field is a plain string."""
        from webapp.models import RecipeResult, Setting
        Setting.set('repository.public_url', 'http://munki.local')
        Setting.set('repository.public_url_username', '')
        Setting.set('repository.public_url_password', '')
        RecipeResult.objects.create(
            run=run,
            result_type='munki_import',
            data=[{'name': 'Chrome', 'version': '1.0', 'catalogs': 'production'}],
        )
        with patch('webapp.views.runs._get_munki_icon_map', return_value={}) as mock_map:
            resp = run_manager_client.get(self._url(run.id))
        assert resp.status_code == 200
        mock_map.assert_called_once_with('http://munki.local', 'production', '')


@pytest.mark.django_db
class TestTriggerRunView:
    url = '/runs/trigger/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url)
        assert resp.status_code == 302

    def test_post_creates_run_and_redirects(self, run_manager_client):
        # trigger_manual_run is imported inside the view function;
        # patch at its source module so the import sees the mock.
        with patch('webapp.runner.trigger_manual_run') as mock_trigger, \
             patch('webapp.models.Task') as mock_task_cls:
            fake_task_id = uuid.uuid4()
            mock_trigger.return_value = fake_task_id
            mock_task = MagicMock()
            mock_task.run_id = uuid.uuid4()
            mock_task_cls.objects.get.return_value = mock_task
            resp = run_manager_client.post(self.url)
        assert resp.status_code in (302, 200)

    def test_post_while_already_running_redirects(self, run_manager_client):
        # Non-HTMX requests get a flash message + redirect rather than 409.
        from webapp.runner import RunAlreadyRunningError
        with patch('webapp.runner.trigger_manual_run', side_effect=RunAlreadyRunningError('busy')):
            resp = run_manager_client.post(self.url)
        assert resp.status_code == 302

    def test_htmx_post_while_already_running_returns_409(self, run_manager_client):
        from webapp.runner import RunAlreadyRunningError
        with patch('webapp.runner.trigger_manual_run', side_effect=RunAlreadyRunningError('busy')):
            resp = run_manager_client.post(self.url, HTTP_HX_REQUEST='true')
        assert resp.status_code == 409

    def test_htmx_post_success_returns_json(self, run_manager_client):
        with patch('webapp.runner.trigger_manual_run') as mock_trigger, \
             patch('webapp.models.Task') as mock_task_cls:
            fake_task_id = uuid.uuid4()
            mock_trigger.return_value = fake_task_id
            mock_task = MagicMock()
            mock_task.run_id = uuid.uuid4()
            mock_task_cls.objects.get.return_value = mock_task
            resp = run_manager_client.post(self.url, HTTP_HX_REQUEST='true')
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['status'] == 'ok'
        assert 'run_id' in data


@pytest.mark.django_db
class TestRunCancelView:
    def _url(self, run_id):
        return f'/runs/{run_id}/cancel/'

    def test_requires_login(self, anon_client, pending_run):
        resp = anon_client.post(self._url(pending_run.id))
        assert resp.status_code == 302

    def test_cancel_pending_run(self, run_manager_client, pending_run):
        resp = run_manager_client.post(self._url(pending_run.id))
        assert resp.status_code in (200, 204, 302)
        pending_run.refresh_from_db()
        assert pending_run.status == 'cancelled'

    def test_cancel_already_completed_run_is_noop(self, run_manager_client, run):
        # run fixture has status='success'
        resp = run_manager_client.post(self._url(run.id))
        # Should not raise; run remains success
        run.refresh_from_db()
        assert run.status == 'success'

    def test_htmx_cancel_returns_204(self, run_manager_client, pending_run):
        resp = run_manager_client.post(self._url(pending_run.id), HTTP_HX_REQUEST='true')
        assert resp.status_code == 204


@pytest.mark.django_db
class TestRunDeleteView:
    url = '/runs/delete/'

    def test_requires_login(self, anon_client, run):
        resp = anon_client.post(self.url, {'run_ids': [str(run.id)]})
        assert resp.status_code == 302

    def test_deletes_completed_runs(self, run_manager_client, run):
        resp = run_manager_client.post(self.url, {'run_ids': [str(run.id)]})
        assert resp.status_code in (200, 302)
        from webapp.models import Run
        assert not Run.objects.filter(id=run.id).exists()

    def test_does_not_delete_pending_runs(self, run_manager_client, pending_run):
        run_manager_client.post(self.url, {'run_ids': [str(pending_run.id)]})
        from webapp.models import Run
        assert Run.objects.filter(id=pending_run.id).exists()


@pytest.mark.django_db
class TestRunStream:
    def _url(self, run_id):
        return f'/runs/{run_id}/stream/'

    def test_requires_login(self, anon_client, run):
        resp = anon_client.get(self._url(run.id))
        assert resp.status_code == 302

    def test_returns_event_stream_content_type(self, run_manager_client, run):
        resp = run_manager_client.get(self._url(run.id))
        assert resp.status_code == 200
        assert 'text/event-stream' in resp.get('Content-Type', '')

    def test_stream_emits_complete_event_for_finished_run(self, run_manager_client, run):
        """Consuming the generator for a completed run yields a 'complete' event."""
        resp = run_manager_client.get(self._url(run.id))
        chunks = b''.join(resp.streaming_content)
        assert b'complete' in chunks
        assert run.status.encode() in chunks

    def test_stream_emits_log_entries(self, run_manager_client, run):
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
        resp = run_manager_client.get(self._url(run.id))
        chunks = b''.join(resp.streaming_content)
        assert b'Test log message' in chunks

    def test_stream_emits_stage_updates(self, run_manager_client, run):
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
        resp = run_manager_client.get(self._url(run.id))
        chunks = b''.join(resp.streaming_content)
        assert b'UpdateRepos' in chunks

    def test_stream_sends_error_for_nonexistent_run(self, run_manager_client):
        """A nonexistent run_id causes an error event to be emitted."""
        missing_id = uuid.uuid4()
        resp = run_manager_client.get(self._url(missing_id))
        chunks = b''.join(resp.streaming_content)
        assert b'error' in chunks or b'not found' in chunks

    def test_stream_respects_from_param(self, run_manager_client, run):
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
        resp = run_manager_client.get(self._url(run.id) + f'?from={entry.id}')
        chunks = b''.join(resp.streaming_content)
        assert b'older message' not in chunks

    def test_stream_no_cache_control_header(self, run_manager_client, run):
        resp = run_manager_client.get(self._url(run.id))
        assert resp.get('Cache-Control') == 'no-cache'

    def test_stream_polls_until_run_completes(self, run_manager_client, db):
        """Stream loop sleeps once for a running run, then emits complete after status changes."""
        from webapp.models import Run, LogEntry, StageExecution
        now = datetime.now(timezone.utc)

        # Build two fake run objects: first 'running', then 'success'
        def make_fake_run(status):
            r = MagicMock()
            r.status = status
            r.id = uuid.uuid4()
            return r

        running_run = make_fake_run('running')
        success_run = make_fake_run('success')
        call_count = {'n': 0}

        def fake_run_filter(**kwargs):
            qs = MagicMock()
            call_count['n'] += 1
            qs.first.return_value = running_run if call_count['n'] == 1 else success_run
            return qs

        empty_qs = MagicMock()
        empty_qs.__iter__ = MagicMock(return_value=iter([]))
        empty_qs.filter.return_value = empty_qs
        empty_qs.order_by.return_value = iter([])

        with patch('webapp.models.Run.objects') as mock_run_mgr, \
             patch('webapp.models.LogEntry.objects') as mock_log_mgr, \
             patch('webapp.models.StageExecution.objects') as mock_stage_mgr, \
             patch('time.sleep'):
            mock_run_mgr.filter.side_effect = fake_run_filter
            mock_log_mgr.filter.return_value.order_by.return_value = iter([])
            mock_stage_mgr.filter.return_value.__iter__ = MagicMock(return_value=iter([]))
            resp = run_manager_client.get(self._url(running_run.id))
            chunks = b''.join(resp.streaming_content)
        assert b'complete' in chunks
