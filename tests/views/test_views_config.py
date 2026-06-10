"""Tests for webapp.views.config.ConfigSectionView."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestConfigRootView:
    url = '/config/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_requires_permission(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 403

    def test_renders_for_superuser(self, admin_client):
        resp = admin_client.get(self.url)
        assert resp.status_code == 200


@pytest.mark.django_db
class TestConfigSectionViewGet:
    def test_autopkg_section_renders(self, admin_client):
        resp = admin_client.get('/config/autopkg/')
        assert resp.status_code == 200
        assert 's' in resp.context

    def test_workflow_section_renders(self, admin_client):
        resp = admin_client.get('/config/workflow/')
        assert resp.status_code == 200

    def test_repository_section_renders(self, admin_client):
        resp = admin_client.get('/config/repository/')
        assert resp.status_code == 200

    def test_gc_section_renders(self, admin_client):
        resp = admin_client.get('/config/gc/')
        assert resp.status_code == 200

    def test_logging_section_renders(self, admin_client):
        resp = admin_client.get('/config/logging/')
        assert resp.status_code == 200

    def test_ui_section_renders(self, admin_client):
        resp = admin_client.get('/config/ui/')
        assert resp.status_code == 200

    def test_context_contains_settings(self, admin_client):
        resp = admin_client.get('/config/autopkg/')
        assert 's' in resp.context
        assert isinstance(resp.context['s'], dict)

    def test_requires_permission(self, client):
        resp = client.get('/config/autopkg/')
        assert resp.status_code == 403


@pytest.mark.django_db
class TestConfigSectionViewPost:
    def test_post_saves_text_setting(self, admin_client):
        from webapp.models import Setting
        resp = admin_client.post('/config/autopkg/', {
            'autopkg.bin_path': '/new/autopkg',
            'autopkg.cache_path': '~/Cache',
            'autopkg.recipe_list': '~/list.txt',
        })
        assert resp.status_code == 302
        assert Setting.get('autopkg.bin_path') == '/new/autopkg'

    def test_post_saves_bool_setting_true(self, admin_client):
        from webapp.models import Setting
        admin_client.post('/config/workflow/', {'workflow.update_repos': 'on'})
        assert Setting.get('workflow.update_repos') == 'true'

    def test_post_bool_key_absent_stores_false(self, admin_client):
        from webapp.models import Setting
        # No 'workflow.update_repos' key in POST → should be set to 'false'
        admin_client.post('/config/workflow/', {})
        assert Setting.get('workflow.update_repos') == 'false'

    def test_post_blank_sensitive_key_does_not_overwrite(self, admin_client):
        from webapp.models import Setting
        # First, set a real password
        Setting.set('repository.password', 'original-password')
        # POST with blank password - should not overwrite
        admin_client.post('/config/repository/', {
            'repository.type': 'remote',
            'repository.connection_type': 'smb',
            'repository.local_path': '',
            'repository.host': 'server',
            'repository.share': 'Munki',
            'repository.mount_path': '/tmp/Munki',
            'repository.public_url': '',
            'repository.username': 'admin',
            'repository.password': '',  # blank - should be skipped
        })
        assert Setting.get('repository.password') == 'original-password'

    def test_post_redirects_on_success(self, admin_client):
        resp = admin_client.post('/config/autopkg/', {
            'autopkg.bin_path': '/usr/local/bin/autopkg',
            'autopkg.cache_path': '~/Cache',
            'autopkg.recipe_list': '~/list.txt',
        })
        assert resp.status_code == 302

    def test_post_saves_int_setting(self, admin_client):
        from webapp.models import Setting
        admin_client.post('/config/gc/', {
            'gc.keep_versions': '3',
            'gc.repoclean_bin_path': '/usr/local/bin/repoclean',
        })
        assert Setting.get('gc.keep_versions') == '3'

    def test_post_invalid_int_stores_zero(self, admin_client):
        from webapp.models import Setting
        admin_client.post('/config/gc/', {
            'gc.keep_versions': 'notanumber',
        })
        assert Setting.get('gc.keep_versions') == '0'

    def test_logging_level_query_param_overrides_stored_value(self, admin_client):
        """GET /config/logging/?level=DEBUG should reflect DEBUG in context."""
        resp = admin_client.get('/config/logging/?level=DEBUG')
        assert resp.status_code == 200
        assert resp.context['s'].get('logging.level') == 'DEBUG'

    def test_logging_level_invalid_param_ignored(self, admin_client):
        """GET /config/logging/?level=NOTVALID should not apply the override."""
        from webapp.models import Setting
        Setting.set('logging.level', 'INFO')
        resp = admin_client.get('/config/logging/?level=NOTVALID')
        assert resp.status_code == 200
        assert resp.context['s'].get('logging.level') == 'INFO'

    def test_requires_permission(self, client):
        resp = client.post('/config/autopkg/', {'autopkg.bin_path': '/evil'})
        assert resp.status_code == 403


@pytest.mark.django_db
class TestLogLevelPickerView:
    url = '/config/logging/level/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_requires_permission(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 403

    def test_renders_for_superuser(self, admin_client):
        resp = admin_client.get(self.url)
        assert resp.status_code == 200

    def test_context_has_log_levels(self, admin_client):
        resp = admin_client.get(self.url)
        assert 'log_levels' in resp.context
        assert len(resp.context['log_levels']) > 0

    def test_current_level_from_query_param(self, admin_client):
        resp = admin_client.get(f'{self.url}?current=ERROR')
        assert resp.status_code == 200
        assert resp.context['current_level'] == 'ERROR'

    def test_current_level_falls_back_to_stored_setting(self, admin_client):
        from webapp.models import Setting
        Setting.set('logging.level', 'WARNING')
        resp = admin_client.get(self.url)
        assert resp.context['current_level'] == 'WARNING'
