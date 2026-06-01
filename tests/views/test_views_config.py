"""Tests for webapp.views.config.ConfigSectionView."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestConfigRootView:
    url = '/config/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_renders_for_authenticated_user(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 200


@pytest.mark.django_db
class TestConfigSectionViewGet:
    def test_autopkg_section_renders(self, client):
        resp = client.get('/config/autopkg/')
        assert resp.status_code == 200
        assert 's' in resp.context

    def test_workflow_section_renders(self, client):
        resp = client.get('/config/workflow/')
        assert resp.status_code == 200

    def test_repository_section_renders(self, client):
        resp = client.get('/config/repository/')
        assert resp.status_code == 200

    def test_gc_section_renders(self, client):
        resp = client.get('/config/gc/')
        assert resp.status_code == 200

    def test_logging_section_renders(self, client):
        resp = client.get('/config/logging/')
        assert resp.status_code == 200

    def test_ui_section_renders(self, client):
        resp = client.get('/config/ui/')
        assert resp.status_code == 200

    def test_context_contains_settings(self, client):
        resp = client.get('/config/autopkg/')
        assert 's' in resp.context
        assert isinstance(resp.context['s'], dict)


@pytest.mark.django_db
class TestConfigSectionViewPost:
    def test_post_saves_text_setting(self, client):
        from webapp.models import Setting
        resp = client.post('/config/autopkg/', {
            'autopkg.bin_path': '/new/autopkg',
            'autopkg.cache_path': '~/Cache',
            'autopkg.recipe_list': '~/list.txt',
        })
        assert resp.status_code == 302
        assert Setting.get('autopkg.bin_path') == '/new/autopkg'

    def test_post_saves_bool_setting_true(self, client):
        from webapp.models import Setting
        client.post('/config/workflow/', {'workflow.update_repos': 'on'})
        assert Setting.get('workflow.update_repos') == 'true'

    def test_post_bool_key_absent_stores_false(self, client):
        from webapp.models import Setting
        # No 'workflow.update_repos' key in POST → should be set to 'false'
        client.post('/config/workflow/', {})
        assert Setting.get('workflow.update_repos') == 'false'

    def test_post_blank_sensitive_key_does_not_overwrite(self, client):
        from webapp.models import Setting
        # First, set a real password
        Setting.set('repository.password', 'original-password')
        # POST with blank password — should not overwrite
        client.post('/config/repository/', {
            'repository.type': 'remote',
            'repository.connection_type': 'smb',
            'repository.local_path': '',
            'repository.host': 'server',
            'repository.share': 'Munki',
            'repository.mount_path': '/tmp/Munki',
            'repository.public_url': '',
            'repository.username': 'admin',
            'repository.password': '',  # blank — should be skipped
        })
        assert Setting.get('repository.password') == 'original-password'

    def test_post_redirects_on_success(self, client):
        resp = client.post('/config/autopkg/', {
            'autopkg.bin_path': '/usr/local/bin/autopkg',
            'autopkg.cache_path': '~/Cache',
            'autopkg.recipe_list': '~/list.txt',
        })
        assert resp.status_code == 302
