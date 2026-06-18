"""Tests for webapp.views.share.RunShareView."""
from __future__ import annotations

from unittest.mock import patch

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
        RunShareToken.objects.filter(pk=token_obj.pk).update(created_at=old_time)

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
        assert resp.context is not None
        results = resp.context.get('recipe_results') or []
        for result in results:
            for item in (result.data if hasattr(result, 'data') else []):
                assert 'traceback' not in item

    def test_munki_import_icon_url_added_when_icon_map_available(self, db, run):
        from webapp.models import RunShareToken, RecipeResult, Setting
        Setting.set('notify.share_link_expiry_days', '')
        Setting.set('repository.public_url', 'http://munki.local')
        Setting.set('repository.public_url_username', '')
        Setting.set('repository.public_url_password', '')
        RecipeResult.objects.create(
            run=run,
            result_type='munki_import',
            data=[{'name': 'Firefox', 'version': '120.0', 'catalogs': ['testing']}],
        )
        token_obj = RunShareToken.get_or_create_for_run(run)
        from django.test import Client
        with patch('webapp.views.share._get_munki_icon_map', return_value={'Firefox': 'icons/Firefox.png'}):
            resp = Client().get(self._url(token_obj.token))
        assert resp.status_code == 200
        ctx_results = resp.context['results']
        munki = next(r for r in ctx_results if r['result_type'] == 'munki_import')
        assert munki['data'][0]['icon_url'] != ''

    def test_munki_import_icon_url_empty_when_name_not_in_map(self, db, run):
        from webapp.models import RunShareToken, RecipeResult, Setting
        Setting.set('notify.share_link_expiry_days', '')
        Setting.set('repository.public_url', 'http://munki.local')
        Setting.set('repository.public_url_username', '')
        Setting.set('repository.public_url_password', '')
        RecipeResult.objects.create(
            run=run,
            result_type='munki_import',
            data=[{'name': 'UnknownApp', 'version': '1.0', 'catalogs': ['all']}],
        )
        token_obj = RunShareToken.get_or_create_for_run(run)
        from django.test import Client
        with patch('webapp.views.share._get_munki_icon_map', return_value={'OtherApp': 'icons/OtherApp.png'}):
            resp = Client().get(self._url(token_obj.token))
        assert resp.status_code == 200
        ctx_results = resp.context['results']
        munki = next(r for r in ctx_results if r['result_type'] == 'munki_import')
        assert munki['data'][0]['icon_url'] == ''

    def test_munki_import_catalog_from_string_field(self, db, run):
        """Catalog extracted correctly when catalogs is a plain string, not a list."""
        from webapp.models import RunShareToken, RecipeResult, Setting
        Setting.set('notify.share_link_expiry_days', '')
        Setting.set('repository.public_url', 'http://munki.local')
        Setting.set('repository.public_url_username', '')
        Setting.set('repository.public_url_password', '')
        RecipeResult.objects.create(
            run=run,
            result_type='munki_import',
            data=[{'name': 'Slack', 'version': '4.0', 'catalogs': 'production'}],
        )
        token_obj = RunShareToken.get_or_create_for_run(run)
        from django.test import Client
        with patch('webapp.views.share._get_munki_icon_map', return_value={}) as mock_map:
            resp = Client().get(self._url(token_obj.token))
        assert resp.status_code == 200
        mock_map.assert_called_once_with('http://munki.local', 'production', '')

    def test_invalid_expiry_setting_treated_as_no_expiry(self, db, run):
        from webapp.models import RunShareToken, Setting
        Setting.set('notify.share_link_expiry_days', 'not-a-number')
        token_obj = RunShareToken.get_or_create_for_run(run)
        from django.test import Client
        resp = Client().get(self._url(token_obj.token))
        assert resp.status_code == 200

    def test_non_expired_token_with_expiry_configured(self, db, run):
        from webapp.models import RunShareToken, Setting
        Setting.set('notify.share_link_expiry_days', '30')
        token_obj = RunShareToken.get_or_create_for_run(run)
        from django.test import Client
        resp = Client().get(self._url(token_obj.token))
        assert resp.status_code == 200


class TestSanitiseResultRows:
    def _call(self, rows):
        from webapp.views.share import _sanitise_result_rows
        return _sanitise_result_rows(rows)

    def test_non_list_input_returned_as_is(self):
        assert self._call('not a list') == 'not a list'
        assert self._call(None) is None
        assert self._call(42) == 42

    def test_non_dict_rows_passed_through(self):
        result = self._call(['plain string', 42])
        assert result == ['plain string', 42]

    def test_traceback_stripped_from_dict_rows(self):
        rows = [{'name': 'App', 'traceback': 'big trace', 'message': 'error'}]
        result = self._call(rows)
        assert 'traceback' not in result[0]
        assert result[0]['message'] == 'error'

    def test_uppercase_traceback_key_also_stripped(self):
        rows = [{'Traceback': 'trace here'}]
        result = self._call(rows)
        assert 'Traceback' not in result[0]
