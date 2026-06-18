"""Tests for webapp.views.filebrowser: BrowseView and MkdirView."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


@pytest.mark.django_db
class TestBrowseView:
    url = '/api/browse/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_requires_config_editor_permission(self, client):
        resp = client.get(self.url)
        assert resp.status_code in (302, 403)

    def test_returns_directory_listing(self, config_editor_client):
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved = str(Path(tmpdir).resolve())
            Path(tmpdir, 'subdir').mkdir()
            Path(tmpdir, 'file.txt').write_text('hello')
            resp = config_editor_client.get(self.url, {'path': tmpdir})
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['path'] == resolved
        names = [e['name'] for e in data['entries']]
        assert 'subdir' in names
        assert 'file.txt' in names

    def test_hidden_entries_excluded(self, config_editor_client):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, '.hidden').write_text('secret')
            Path(tmpdir, 'visible.txt').write_text('public')
            resp = config_editor_client.get(self.url, {'path': tmpdir})
        data = json.loads(resp.content)
        names = [e['name'] for e in data['entries']]
        assert '.hidden' not in names
        assert 'visible.txt' in names

    def test_file_path_resolves_to_parent(self, config_editor_client):
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved = str(Path(tmpdir).resolve())
            filepath = Path(tmpdir, 'somefile.txt')
            filepath.write_text('content')
            resp = config_editor_client.get(self.url, {'path': str(filepath)})
        data = json.loads(resp.content)
        assert data['path'] == resolved

    def test_parent_is_null_at_root(self, config_editor_client):
        resp = config_editor_client.get(self.url, {'path': '/'})
        data = json.loads(resp.content)
        assert data['parent'] is None

    def test_directories_flagged_correctly(self, config_editor_client):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, 'adir').mkdir()
            Path(tmpdir, 'afile.txt').write_text('x')
            resp = config_editor_client.get(self.url, {'path': tmpdir})
        data = json.loads(resp.content)
        by_name = {e['name']: e for e in data['entries']}
        assert by_name['adir']['is_dir'] is True
        assert by_name['afile.txt']['is_dir'] is False

    def test_permission_error_returns_403(self, config_editor_client):
        from unittest.mock import patch
        from pathlib import Path
        with patch.object(Path, 'iterdir', side_effect=PermissionError(13, 'Permission denied')):
            with tempfile.TemporaryDirectory() as tmpdir:
                resp = config_editor_client.get(self.url, {'path': tmpdir})
        assert resp.status_code == 403

    def test_generic_oserror_returns_400(self, config_editor_client):
        from unittest.mock import patch
        from pathlib import Path
        err = OSError(5, 'Input/output error')
        with patch.object(Path, 'iterdir', side_effect=err):
            with tempfile.TemporaryDirectory() as tmpdir:
                resp = config_editor_client.get(self.url, {'path': tmpdir})
        assert resp.status_code == 400
        data = json.loads(resp.content)
        assert 'error' in data


@pytest.mark.django_db
class TestMkdirView:
    url = '/api/browse/mkdir/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url, content_type='application/json',
                                data=json.dumps({'path': '/tmp/test'}))
        assert resp.status_code == 302

    def test_invalid_json_returns_400(self, config_editor_client):
        resp = config_editor_client.post(self.url, content_type='application/json',
                                         data='not-json')
        assert resp.status_code == 400

    def test_missing_path_returns_400(self, config_editor_client):
        resp = config_editor_client.post(self.url, content_type='application/json',
                                         data=json.dumps({}))
        assert resp.status_code == 400

    def test_creates_directory(self, config_editor_client):
        with tempfile.TemporaryDirectory() as tmpdir:
            newdir = str(Path(tmpdir, 'newsubdir'))
            resp = config_editor_client.post(self.url, content_type='application/json',
                                              data=json.dumps({'path': newdir}))
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert 'path' in data

    def test_creates_nested_directories(self, config_editor_client):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = str(Path(tmpdir, 'a', 'b', 'c'))
            resp = config_editor_client.post(self.url, content_type='application/json',
                                              data=json.dumps({'path': nested}))
        assert resp.status_code == 200

    def test_permission_denied_returns_403(self, config_editor_client):
        from unittest.mock import patch
        from pathlib import Path as PathType
        with patch.object(PathType, 'mkdir', side_effect=PermissionError('denied')):
            resp = config_editor_client.post(self.url, content_type='application/json',
                                              data=json.dumps({'path': '/root/nope'}))
        assert resp.status_code == 403

    def test_generic_oserror_returns_400(self, config_editor_client):
        from unittest.mock import patch
        from pathlib import Path as PathType
        with patch.object(PathType, 'mkdir', side_effect=OSError('read-only filesystem')):
            resp = config_editor_client.post(self.url, content_type='application/json',
                                              data=json.dumps({'path': '/mnt/readonly/newdir'}))
        assert resp.status_code == 400
