"""Tests for munki icon helpers and proxy view in webapp.views.runs."""
from __future__ import annotations

import plistlib
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest


class TestMakeAuthHeader:
    def _call(self, username, password=''):
        from webapp.views.runs import _make_auth_header
        return _make_auth_header(username, password)

    def test_no_username_returns_empty(self):
        assert self._call('') == ''
        assert self._call(None) == ''

    def test_username_password_returns_basic_header(self):
        import base64
        result = self._call('alice', 'secret')
        assert result.startswith('Basic ')
        decoded = base64.b64decode(result[6:]).decode()
        assert decoded == 'alice:secret'

    def test_username_only_returns_basic_header(self):
        result = self._call('alice', '')
        assert result.startswith('Basic ')


class TestFetchMunkiCatalog:
    def _call(self, public_url='http://munki.local', catalog='all', auth_header=''):
        from webapp.views.runs import _fetch_munki_catalog
        return _fetch_munki_catalog(public_url, catalog, auth_header)

    def _make_plist_response(self, items):
        raw = plistlib.dumps(items)
        mock_resp = MagicMock()
        mock_resp.read.return_value = raw
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_returns_empty_on_network_error(self):
        with patch('urllib.request.urlopen', side_effect=OSError('connection refused')):
            result = self._call()
        assert result == {}

    def test_parses_items_with_icon_name(self):
        items = [{'name': 'Firefox', 'icon_name': 'Firefox.png'}]
        resp = self._make_plist_response(items)
        with patch('urllib.request.urlopen', return_value=resp):
            result = self._call()
        assert result == {'Firefox': 'icons/Firefox.png'}

    def test_appends_png_when_icon_name_has_no_extension(self):
        items = [{'name': 'Chrome', 'icon_name': 'Chrome'}]
        resp = self._make_plist_response(items)
        with patch('urllib.request.urlopen', return_value=resp):
            result = self._call()
        assert result == {'Chrome': 'icons/Chrome.png'}

    def test_falls_back_to_name_plus_png_when_no_icon_name(self):
        items = [{'name': 'Slack'}]
        resp = self._make_plist_response(items)
        with patch('urllib.request.urlopen', return_value=resp):
            result = self._call()
        assert result == {'Slack': 'icons/Slack.png'}

    def test_skips_items_with_no_name(self):
        items = [{'icon_name': 'orphan.png'}]
        resp = self._make_plist_response(items)
        with patch('urllib.request.urlopen', return_value=resp):
            result = self._call()
        assert result == {}

    def test_includes_auth_header(self):
        items = [{'name': 'App', 'icon_name': 'App.png'}]
        resp = self._make_plist_response(items)
        captured = []
        def fake_urlopen(req, **kw):
            captured.append(req)
            return resp
        with patch('urllib.request.urlopen', fake_urlopen):
            self._call(auth_header='Basic abc123')
        assert captured[0].get_header('Authorization') == 'Basic abc123'


class TestGetMunkiIconMap:
    def setup_method(self):
        from webapp.views import runs
        runs._MUNKI_CATALOG_CACHE.update({'data': None, 'url': '', 'auth': '', 'catalog': '', 'ts': 0.0})

    def _call(self, public_url='http://munki.local', catalog='all', auth_header=''):
        from webapp.views.runs import _get_munki_icon_map
        return _get_munki_icon_map(public_url, catalog, auth_header)

    def test_fetches_and_caches_on_first_call(self):
        with patch('webapp.views.runs._fetch_munki_catalog', return_value={'App': 'icons/App.png'}) as mock:
            result = self._call()
        assert result == {'App': 'icons/App.png'}
        mock.assert_called_once()

    def test_returns_cached_result_on_second_call(self):
        with patch('webapp.views.runs._fetch_munki_catalog', return_value={'App': 'icons/App.png'}) as mock:
            self._call()
            result = self._call()
        assert mock.call_count == 1
        assert result == {'App': 'icons/App.png'}

    def test_refetches_when_url_changes(self):
        with patch('webapp.views.runs._fetch_munki_catalog', return_value={'A': 'icons/A.png'}) as mock:
            self._call(public_url='http://server1.local')
            self._call(public_url='http://server2.local')
        assert mock.call_count == 2

    def test_refetches_when_catalog_changes(self):
        with patch('webapp.views.runs._fetch_munki_catalog', return_value={}) as mock:
            self._call(catalog='all')
            self._call(catalog='testing')
        assert mock.call_count == 2


@pytest.mark.django_db
class TestMunkiIconProxy:
    url = '/runs/munki-icon/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url, {'path': 'icons/App.png'})
        assert resp.status_code == 302

    def test_rejects_path_without_icons_prefix(self, run_manager_client):
        resp = run_manager_client.get(self.url, {'path': 'etc/passwd'})
        assert resp.status_code == 400

    def test_rejects_path_with_dotdot(self, run_manager_client):
        resp = run_manager_client.get(self.url, {'path': 'icons/../etc/passwd'})
        assert resp.status_code == 400

    def test_returns_404_when_no_public_url_configured(self, run_manager_client):
        from webapp.models import Setting
        Setting.set('repository.public_url', '')
        resp = run_manager_client.get(self.url, {'path': 'icons/App.png'})
        assert resp.status_code == 404

    def test_returns_icon_data_on_success(self, run_manager_client):
        from webapp.models import Setting
        Setting.set('repository.public_url', 'http://munki.local')
        Setting.set('repository.public_url_username', '')
        Setting.set('repository.public_url_password', '')
        fake_data = b'\x89PNG\r\n\x1a\n'
        mock_resp = MagicMock()
        mock_resp.headers.get.return_value = 'image/png'
        mock_resp.read.return_value = fake_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            resp = run_manager_client.get(self.url, {'path': 'icons/App.png'})
        assert resp.status_code == 200
        assert resp.content == fake_data
        assert 'image/png' in resp['Content-Type']

    def test_returns_404_on_fetch_error(self, run_manager_client):
        from webapp.models import Setting
        Setting.set('repository.public_url', 'http://munki.local')
        Setting.set('repository.public_url_username', '')
        Setting.set('repository.public_url_password', '')
        with patch('urllib.request.urlopen', side_effect=OSError('not found')):
            resp = run_manager_client.get(self.url, {'path': 'icons/App.png'})
        assert resp.status_code == 404
