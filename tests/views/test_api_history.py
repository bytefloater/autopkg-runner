"""Tests for api.views.history: GetRunDataView, ListRunsView."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


@pytest.mark.django_db
class TestListRunsView:
    url = '/api/history/list_runs/'

    def test_unauthenticated_returns_401(self, anon_api_client):
        resp = anon_api_client.get(self.url)
        assert resp.status_code in (401, 403)

    def test_no_filters_returns_all_runs(self, api_run_manager_client, run):
        resp = api_run_manager_client.get(self.url)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        ids = [r['id'] for r in data]
        assert str(run.id) in ids

    def _create_run_with_started_at(self, dt):
        """Create a Run and use update() to set started_at (auto_now_add field)."""
        from webapp.models import Run
        r = Run.objects.create(status='success', config_snapshot={})
        Run.objects.filter(pk=r.pk).update(started_at=dt)
        r.refresh_from_db()
        return r

    def test_start_date_filters_older_runs(self, api_run_manager_client):
        old_run = self._create_run_with_started_at(
            datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        )
        recent_run = self._create_run_with_started_at(
            datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        )
        resp = api_run_manager_client.get(self.url, {'start_date': '2024-01-01'})
        assert resp.status_code == 200
        data = resp.json()
        ids = [r['id'] for r in data]
        assert str(recent_run.id) in ids
        assert str(old_run.id) not in ids

    def test_end_date_filters_newer_runs(self, api_run_manager_client):
        old_run = self._create_run_with_started_at(
            datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        )
        recent_run = self._create_run_with_started_at(
            datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        )
        resp = api_run_manager_client.get(self.url, {'end_date': '2021-01-01'})
        assert resp.status_code == 200
        data = resp.json()
        ids = [r['id'] for r in data]
        assert str(old_run.id) in ids
        assert str(recent_run.id) not in ids

    def test_invalid_start_date_returns_400(self, api_run_manager_client):
        resp = api_run_manager_client.get(self.url, {'start_date': 'bad-date'})
        assert resp.status_code == 400
        data = resp.json()
        assert 'error' in data

    def test_invalid_end_date_returns_400(self, api_run_manager_client):
        resp = api_run_manager_client.get(self.url, {'end_date': 'not-a-date'})
        assert resp.status_code == 400
        data = resp.json()
        assert 'error' in data

    def test_run_fields_present(self, api_run_manager_client, run):
        resp = api_run_manager_client.get(self.url)
        assert resp.status_code == 200
        data = resp.json()
        run_data = next((r for r in data if r['id'] == str(run.id)), None)
        assert run_data is not None
        assert 'status' in run_data
        assert 'triggered_by' in run_data
        assert 'started_at' in run_data
        assert 'completed_at' in run_data
        assert 'duration_seconds' in run_data


@pytest.mark.django_db
class TestGetRunDataView:
    url = '/api/history/get_run_data/'

    def test_unauthenticated_returns_401(self, anon_api_client, run):
        resp = anon_api_client.get(self.url, {'uuid': str(run.id)})
        assert resp.status_code in (401, 403)

    def test_missing_uuid_returns_400(self, api_run_manager_client):
        resp = api_run_manager_client.get(self.url)
        assert resp.status_code == 400

    def test_nonexistent_uuid_returns_404(self, api_run_manager_client):
        resp = api_run_manager_client.get(self.url, {'uuid': str(uuid.uuid4())})
        assert resp.status_code == 404

    def test_invalid_uuid_returns_404(self, api_run_manager_client):
        resp = api_run_manager_client.get(self.url, {'uuid': 'not-a-uuid'})
        assert resp.status_code == 404

    def test_valid_run_returns_200_with_nested_data(self, api_run_manager_client, run):
        resp = api_run_manager_client.get(self.url, {'uuid': str(run.id)})
        assert resp.status_code == 200
        data = resp.json()
        assert data['id'] == str(run.id)
        assert data['status'] == run.status
        assert 'stages' in data
        assert 'logs' in data
        assert 'results' in data
        assert 'config_snapshot' in data
        assert isinstance(data['stages'], list)
        assert isinstance(data['logs'], list)
        assert isinstance(data['results'], list)

    def test_run_with_stage_execution_included(self, api_run_manager_client, run):
        from webapp.models import StageExecution
        stage = StageExecution.objects.create(
            run=run,
            name='UpdateRepos',
            status='success',
            order=1,
        )
        resp = api_run_manager_client.get(self.url, {'uuid': str(run.id)})
        assert resp.status_code == 200
        data = resp.json()
        stage_names = [s['name'] for s in data['stages']]
        assert 'UpdateRepos' in stage_names

    def test_run_with_log_entries_included(self, api_run_manager_client, run):
        from django.utils import timezone
        from webapp.models import LogEntry
        LogEntry.objects.create(
            run=run,
            timestamp=timezone.now(),
            level='INFO',
            stage_name='UpdateRepos',
            message='Updating repos...',
        )
        resp = api_run_manager_client.get(self.url, {'uuid': str(run.id)})
        assert resp.status_code == 200
        data = resp.json()
        messages = [e['message'] for e in data['logs']]
        assert 'Updating repos...' in messages

    def test_run_with_recipe_results_included(self, api_run_manager_client, run):
        from webapp.models import RecipeResult
        RecipeResult.objects.create(
            run=run,
            result_type='success',
            data=[{'name': 'Firefox', 'version': '120.0'}],
        )
        resp = api_run_manager_client.get(self.url, {'uuid': str(run.id)})
        assert resp.status_code == 200
        data = resp.json()
        result_types = [r['result_type'] for r in data['results']]
        assert 'success' in result_types
