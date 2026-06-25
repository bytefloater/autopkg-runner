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


def _collect_stream(resp):
    """Consume a streaming response body — handles both sync and async generators."""
    from asgiref.sync import async_to_sync
    sc = resp.streaming_content
    if hasattr(sc, '__aiter__'):
        async def _gather():
            return b''.join([c async for c in sc])
        return async_to_sync(_gather)()
    return b''.join(sc)


class FakeBroadcaster:
    """Minimal RunBroadcaster substitute that returns pre-built SSE frames."""

    def __init__(self, frames=(), done=True):
        self._frames = list(frames)
        self._done = done

    def events_since(self, cursor):
        raw = self._frames[cursor + 1:]
        start = cursor + 1
        out = [f'id: {start + i}\n'.encode() + f for i, f in enumerate(raw)]
        return out, self._done


@pytest.mark.django_db
class TestRunStream:
    def _url(self, run_id):
        return f'/runs/{run_id}/stream/'

    def test_requires_login(self, anon_client, run):
        resp = anon_client.get(self._url(run.id))
        assert resp.status_code == 302

    def test_returns_event_stream_content_type(self, run_manager_client, run):
        fake = FakeBroadcaster()
        with patch('webapp.run_broadcaster.broadcaster_manager') as m:
            m.get.return_value = fake
            resp = run_manager_client.get(self._url(run.id))
        assert resp.status_code == 200
        assert 'text/event-stream' in resp.get('Content-Type', '')

    def test_stream_emits_complete_event_for_finished_run(self, run_manager_client, run):
        """Broadcaster frames containing a complete event are passed through."""
        complete = f'data: {json.dumps({"type": "complete", "status": run.status})}\n\n'.encode()
        done_frame = b'event: done\ndata: {}\n\n'
        fake = FakeBroadcaster(frames=[complete, done_frame])
        with patch('webapp.run_broadcaster.broadcaster_manager') as m:
            m.get.return_value = fake
            resp = run_manager_client.get(self._url(run.id))
            chunks = _collect_stream(resp)
        assert b'complete' in chunks
        assert run.status.encode() in chunks

    def test_stream_emits_log_entries(self, run_manager_client, run):
        """Log frames from the broadcaster are forwarded to the client."""
        log_frame = f'data: {json.dumps({"type": "log", "level": "INFO", "stage": "", "message": "Test log message", "timestamp": "2024-01-01T00:00:00+00:00"})}\n\n'.encode()
        complete = b'data: {"type": "complete", "status": "success"}\n\n'
        done_frame = b'event: done\ndata: {}\n\n'
        fake = FakeBroadcaster(frames=[log_frame, complete, done_frame])
        with patch('webapp.run_broadcaster.broadcaster_manager') as m:
            m.get.return_value = fake
            resp = run_manager_client.get(self._url(run.id))
            chunks = _collect_stream(resp)
        assert b'Test log message' in chunks

    def test_stream_emits_stage_updates(self, run_manager_client, run):
        """Stage frames from the broadcaster are forwarded to the client."""
        stage_frame = f'data: {json.dumps({"type": "stage", "name": "UpdateRepos", "status": "success", "order": 0, "started_at": None, "completed_at": None})}\n\n'.encode()
        complete = b'data: {"type": "complete", "status": "success"}\n\n'
        done_frame = b'event: done\ndata: {}\n\n'
        fake = FakeBroadcaster(frames=[stage_frame, complete, done_frame])
        with patch('webapp.run_broadcaster.broadcaster_manager') as m:
            m.get.return_value = fake
            resp = run_manager_client.get(self._url(run.id))
            chunks = _collect_stream(resp)
        assert b'UpdateRepos' in chunks

    def test_stream_returns_404_for_nonexistent_run(self, run_manager_client):
        """A nonexistent run_id returns 404 before the stream is opened."""
        resp = run_manager_client.get(self._url(uuid.uuid4()))
        assert resp.status_code == 404

    def test_stream_respects_last_event_id(self, run_manager_client, run):
        """Last-Event-ID header sets the cursor so already-seen frames are skipped."""
        older = b'data: {"type": "log", "message": "older"}\n\n'
        newer = b'data: {"type": "log", "message": "newer"}\n\n'
        complete = b'data: {"type": "complete", "status": "success"}\n\n'
        done_frame = b'event: done\ndata: {}\n\n'
        # older is at index 0; sending Last-Event-ID: 0 means cursor starts at 0
        # so events_since(0) returns only [newer, complete, done_frame]
        fake = FakeBroadcaster(frames=[older, newer, complete, done_frame])
        with patch('webapp.run_broadcaster.broadcaster_manager') as m:
            m.get.return_value = fake
            resp = run_manager_client.get(self._url(run.id), HTTP_LAST_EVENT_ID='0')
            chunks = _collect_stream(resp)
        assert b'older' not in chunks
        assert b'newer' in chunks

    def test_stream_no_cache_control_header(self, run_manager_client, run):
        fake = FakeBroadcaster()
        with patch('webapp.run_broadcaster.broadcaster_manager') as m:
            m.get.return_value = fake
            resp = run_manager_client.get(self._url(run.id))
        assert resp.get('Cache-Control') == 'no-cache'

    def test_stream_polls_until_run_completes(self, run_manager_client, run):
        """Generator keeps polling the broadcaster until done=True."""
        complete = b'data: {"type": "complete", "status": "success"}\n\n'
        done_frame = b'event: done\ndata: {}\n\n'

        call_count = {'n': 0}
        frames = [complete, done_frame]

        class SlowBroadcaster:
            def events_since(self, cursor):
                call_count['n'] += 1
                done = call_count['n'] >= 3
                raw = frames[cursor + 1:] if done else []
                start = cursor + 1
                out = [f'id: {start + i}\n'.encode() + f for i, f in enumerate(raw)]
                return out, done

        with patch('webapp.run_broadcaster.broadcaster_manager') as m:
            m.get.return_value = SlowBroadcaster()
            resp = run_manager_client.get(self._url(run.id))
            chunks = _collect_stream(resp)
        assert b'complete' in chunks
        assert call_count['n'] >= 3
