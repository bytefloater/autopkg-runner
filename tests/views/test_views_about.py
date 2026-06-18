"""Tests for webapp.views.about - helper functions and AboutView."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestRun:
    def _call(self, *args, **kwargs):
        from webapp.views.about import _run
        return _run(*args, **kwargs)

    def test_returns_stdout_on_success(self):
        mock_result = MagicMock()
        mock_result.stdout = 'v2.7.2\n'
        with patch('subprocess.run', return_value=mock_result):
            assert self._call('/usr/local/bin/autopkg', 'version') == 'v2.7.2'

    def test_returns_empty_on_exception(self):
        with patch('subprocess.run', side_effect=Exception('not found')):
            assert self._call('/nonexistent') == ''

    def test_timeout_is_forwarded(self):
        mock_result = MagicMock()
        mock_result.stdout = 'ok\n'
        with patch('subprocess.run', return_value=mock_result) as mock_sp:
            self._call('cmd', timeout=3)
        assert mock_sp.call_args.kwargs['timeout'] == 3


class TestAutopkgVersion:
    def test_returns_version_string(self):
        from webapp.views.about import _autopkg_version
        with patch('webapp.views.about._run', return_value='2.7.2'):
            assert _autopkg_version('/usr/local/bin/autopkg') == '2.7.2'

    def test_returns_none_when_empty(self):
        from webapp.views.about import _autopkg_version
        with patch('webapp.views.about._run', return_value=''):
            assert _autopkg_version('/usr/local/bin/autopkg') is None


class TestAutopkgLatestRelease:
    def test_returns_version_from_github(self):
        from webapp.views.about import _autopkg_latest_release
        payload = json.dumps({'tag_name': 'v2.8.0'}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            assert _autopkg_latest_release() == '2.8.0'

    def test_strips_leading_v(self):
        from webapp.views.about import _autopkg_latest_release
        payload = json.dumps({'tag_name': 'v3.0.0'}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            assert _autopkg_latest_release() == '3.0.0'

    def test_returns_none_on_network_error(self):
        from webapp.views.about import _autopkg_latest_release
        with patch('urllib.request.urlopen', side_effect=Exception('network')):
            assert _autopkg_latest_release() is None

    def test_returns_none_when_tag_empty(self):
        from webapp.views.about import _autopkg_latest_release
        payload = json.dumps({'tag_name': ''}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            assert _autopkg_latest_release() is None


class TestMunkiVersion:
    def test_returns_version_from_managedsoftwareupdate(self):
        from webapp.views.about import _munki_version
        with patch('webapp.views.about._run', return_value='5.7.1'):
            assert _munki_version() == '5.7.1'

    def test_falls_back_to_second_candidate(self):
        from webapp.views.about import _munki_version

        def fake_run(cmd, *args, **kwargs):
            if 'managedsoftwareupdate' in cmd:
                return ''
            return '5.6.0'

        with patch('webapp.views.about._run', side_effect=fake_run):
            assert _munki_version() == '5.6.0'

    def test_returns_none_when_all_fail(self):
        from webapp.views.about import _munki_version
        with patch('webapp.views.about._run', return_value=''), \
             patch('pathlib.Path.read_bytes', side_effect=FileNotFoundError):
            assert _munki_version() is None

    def test_falls_back_to_plist(self):
        from webapp.views.about import _munki_version
        import plistlib
        plist_data = plistlib.dumps({'ManagedInstallVersion': '5.5.0'})
        with patch('webapp.views.about._run', return_value=''), \
             patch('pathlib.Path.read_bytes', return_value=plist_data):
            assert _munki_version() == '5.5.0'

    def test_plist_with_no_version_returns_none(self):
        from webapp.views.about import _munki_version
        import plistlib
        plist_data = plistlib.dumps({'OtherKey': 'value'})
        with patch('webapp.views.about._run', return_value=''), \
             patch('pathlib.Path.read_bytes', return_value=plist_data):
            assert _munki_version() is None


class TestParseVersion:
    def _call(self, v):
        from webapp.views.about import _parse_version
        return _parse_version(v)

    def test_simple_version(self):
        assert self._call('2.7.2') == (2, 7, 2)

    def test_single_component(self):
        assert self._call('3') == (3,)

    def test_invalid_returns_empty_tuple(self):
        # 'not-a-version' has no digit segments so the generator is empty
        assert self._call('not-a-version') == ()

    def test_mixed_components(self):
        assert self._call('2.7.2') > self._call('2.7.1')


@pytest.mark.django_db
class TestAboutView:
    url = '/about/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_renders_for_authenticated_user(self, client):
        with patch('webapp.views.about._autopkg_version', return_value='2.7.2'), \
             patch('webapp.views.about._autopkg_latest_release', return_value='2.7.2'), \
             patch('webapp.views.about._munki_version', return_value='5.7.1'):
            resp = client.get(self.url)
        assert resp.status_code == 200

    def test_context_contains_versions(self, client):
        with patch('webapp.views.about._autopkg_version', return_value='2.7.2'), \
             patch('webapp.views.about._autopkg_latest_release', return_value='2.8.0'), \
             patch('webapp.views.about._munki_version', return_value='5.7.1'):
            resp = client.get(self.url)
        assert resp.context['autopkg_version'] == '2.7.2'
        assert resp.context['autopkg_latest'] == '2.8.0'
        assert resp.context['munki_version'] == '5.7.1'

    def test_update_available_flag(self, client):
        with patch('webapp.views.about._autopkg_version', return_value='2.7.2'), \
             patch('webapp.views.about._autopkg_latest_release', return_value='2.8.0'), \
             patch('webapp.views.about._munki_version', return_value=None):
            resp = client.get(self.url)
        assert resp.context['autopkg_update_available'] is True

    def test_no_update_when_autopkg_not_installed(self, client):
        with patch('webapp.views.about._autopkg_version', return_value=None), \
             patch('webapp.views.about._munki_version', return_value=None):
            resp = client.get(self.url)
        # When autopkg is not installed, update_available is falsy (None or False)
        assert not resp.context['autopkg_update_available']
        assert resp.context['autopkg_latest'] is None


IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'


@pytest.mark.django_db
class TestAboutViewMobileTemplate:
    def test_mobile_ua_uses_mobile_template(self, client):
        with patch('webapp.views.about._autopkg_version', return_value=None), \
             patch('webapp.views.about._autopkg_latest_release', return_value=None), \
             patch('webapp.views.about._munki_version', return_value=None):
            resp = client.get('/about/', HTTP_USER_AGENT=IPHONE_UA)
        assert resp.status_code == 200
        assert 'mobile' in resp.template_name[0]


class TestRunFileNotFoundAndGenericException:
    def test_file_not_found_returns_empty(self):
        from webapp.views.about import _run
        with patch('subprocess.run', side_effect=FileNotFoundError('not found')):
            assert _run('/nonexistent/bin') == ''

    def test_generic_exception_returns_empty(self):
        from webapp.views.about import _run
        with patch('subprocess.run', side_effect=RuntimeError('crash')):
            assert _run('/some/bin') == ''


class TestMunkiVersionFileNotFoundAndGenericException:
    def test_generic_plist_exception_returns_none(self):
        from webapp.views.about import _munki_version
        with patch('webapp.views.about._run', return_value=''), \
             patch('pathlib.Path.read_bytes', side_effect=OSError('permission denied')):
            result = _munki_version()
            assert result is None


class TestParseVersionEdgeCases:
    def test_none_input_returns_fallback(self):
        from webapp.views.about import _parse_version
        # None.split() raises AttributeError → except → (0,)
        result = _parse_version(None)
        assert result == (0,)

    def test_integer_input_returns_fallback(self):
        from webapp.views.about import _parse_version
        # int has no .split() → AttributeError → except → (0,)
        result = _parse_version(42)
        assert result == (0,)
