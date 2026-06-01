"""Tests for api.views.tasks: TriggerRunView, TriggerDbCleanupView, GetTaskStatusView."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import uuid

import pytest


@pytest.mark.django_db
class TestTriggerRunView:
    url = '/api/tasks/trigger_run/'

    def test_unauthenticated_returns_401(self, anon_api_client):
        resp = anon_api_client.post(self.url)
        assert resp.status_code in (401, 403)

    def test_trigger_run_returns_202_with_task_uuid(self, api_client):
        fake_uuid = uuid.uuid4()
        with patch('webapp.runner.trigger_manual_run', return_value=fake_uuid) as mock_trigger:
            resp = api_client.post(self.url)
        assert resp.status_code == 202
        data = resp.json()
        assert 'task_uuid' in data
        assert data['task_uuid'] == str(fake_uuid)
        mock_trigger.assert_called_once_with(triggered_by='api')

    def test_trigger_run_while_running_returns_409(self, api_client):
        from webapp.runner import RunAlreadyRunningError
        with patch('webapp.runner.trigger_manual_run', side_effect=RunAlreadyRunningError('already running')):
            resp = api_client.post(self.url)
        assert resp.status_code == 409
        data = resp.json()
        assert 'error' in data


@pytest.mark.django_db
class TestTriggerDbCleanupView:
    url = '/api/tasks/trigger_db_cleanup/'

    def test_unauthenticated_returns_401(self, anon_api_client):
        resp = anon_api_client.post(self.url)
        assert resp.status_code in (401, 403)

    def test_trigger_cleanup_returns_202_with_task_uuid(self, api_client):
        fake_uuid = uuid.uuid4()
        with patch('webapp.runner.trigger_db_cleanup', return_value=fake_uuid):
            resp = api_client.post(self.url)
        assert resp.status_code == 202
        data = resp.json()
        assert 'task_uuid' in data
        assert data['task_uuid'] == str(fake_uuid)


@pytest.mark.django_db
class TestGetTaskStatusView:
    url = '/api/tasks/get_task_status/'

    def test_unauthenticated_returns_401(self, anon_api_client):
        resp = anon_api_client.get(self.url, {'uuid': str(uuid.uuid4())})
        assert resp.status_code in (401, 403)

    def test_missing_uuid_returns_400(self, api_client):
        resp = api_client.get(self.url)
        assert resp.status_code == 400

    def test_nonexistent_uuid_returns_404(self, api_client):
        resp = api_client.get(self.url, {'uuid': str(uuid.uuid4())})
        assert resp.status_code == 404

    def test_invalid_uuid_returns_404(self, api_client):
        resp = api_client.get(self.url, {'uuid': 'not-a-uuid'})
        assert resp.status_code == 404

    def test_existing_task_returns_status_fields(self, api_client):
        from webapp.models import Task
        fake_uuid = uuid.uuid4()
        with patch('webapp.runner.trigger_manual_run', return_value=fake_uuid):
            task = Task.objects.create(
                id=fake_uuid,
                task_type='run',
                status='pending',
            )
        resp = api_client.get(self.url, {'uuid': str(fake_uuid)})
        assert resp.status_code == 200
        data = resp.json()
        assert data['id'] == str(fake_uuid)
        assert data['task_type'] == 'run'
        assert data['status'] == 'pending'
        assert 'run_uuid' in data
        assert 'created_at' in data
