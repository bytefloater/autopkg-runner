"""Tests for webapp.views.share.RunShareView."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestRunShareView:
    def _url(self, token):
        return f'/share/{token}/'

    def test_valid_token_returns_200(self, db, run):
        from webapp.models import RunShareToken, Setting
        # Ensure no expiry is set
        Setting.set('notify.share_link_expiry_days', '')
        token_obj = RunShareToken.get_or_create_for_run(run)
        from django.test import Client
        resp = Client().get(self._url(token_obj.token))
        assert resp.status_code == 200

    def test_invalid_token_returns_404(self, db):
        from django.test import Client
        resp = Client().get(self._url('completely-invalid-token-xyz'))
        assert resp.status_code == 404

    def test_expired_token_returns_404(self, db):
        from datetime import timedelta
        from django.utils import timezone
        from webapp.models import Run, RunShareToken, Setting

        Setting.set('notify.share_link_expiry_days', '7')
        # Create a run that is 10 days old
        old_time = timezone.now() - timedelta(days=10)
        run = Run.objects.create(status='success', config_snapshot={})
        token_obj = RunShareToken.objects.create(run=run, token='expired-token-abc123456789')
        # Manually backdate the created_at
        RunShareToken.objects.filter(id=token_obj.id).update(created_at=old_time)

        from django.test import Client
        resp = Client().get(self._url('expired-token-abc123456789'))
        assert resp.status_code == 404

    def test_traceback_key_stripped_from_recipe_data(self, db, run):
        from webapp.models import RunShareToken, RecipeResult, Setting
        Setting.set('notify.share_link_expiry_days', '')
        # Create a recipe result with a traceback field
        RecipeResult.objects.create(
            run=run,
            result_type='failure',
            data=[{'name': 'MyApp', 'traceback': 'Traceback (most recent call last)...'}],
        )
        token_obj = RunShareToken.get_or_create_for_run(run)
        from django.test import Client
        resp = Client().get(self._url(token_obj.token))
        assert resp.status_code == 200
        # The context should have sanitised results
        results = resp.context.get('recipe_results', [])
        for result in results:
            for item in (result.data if hasattr(result, 'data') else []):
                assert 'traceback' not in item
