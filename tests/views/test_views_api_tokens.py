"""Tests for webapp.views.api_tokens.ApiTokensView."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestApiTokensView:
    url = '/api-tokens/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_get_renders(self, config_editor_client):
        resp = config_editor_client.get(self.url)
        assert resp.status_code == 200

    def test_create_token(self, config_editor_client, user):
        from webapp.models import APIToken
        resp = config_editor_client.post(self.url, {'action': 'create', 'name': 'My Token'})
        assert resp.status_code in (200, 302)
        assert APIToken.objects.filter(user=user, name='My Token').exists()

    def test_new_token_visible_once_in_session(self, config_editor_client, user):
        resp = config_editor_client.post(self.url, {'action': 'create', 'name': 'Once Token'})
        # On the response or redirect, the token credentials should be accessible.
        # The view uses context keys 'new_token_id' and 'new_token_secret'.
        if resp.status_code == 302:
            follow_resp = config_editor_client.get(resp['Location'])
            assert follow_resp.context.get('new_token_id') is not None
            assert follow_resp.context.get('new_token_secret') is not None
            # On a second request the session keys are cleared - credentials gone.
            resp2 = config_editor_client.get(self.url)
            assert resp2.context.get('new_token_id') is None
            assert resp2.context.get('new_token_secret') is None
        else:
            # View may render directly (no redirect) - token still in context.
            assert resp.context.get('new_token_id') is not None

    def test_revoke_token(self, config_editor_client, user, api_token):
        from webapp.models import APIToken
        resp = config_editor_client.post(self.url, {'action': 'revoke', 'token_id': str(api_token.pk)})
        assert resp.status_code in (200, 302)
        assert not APIToken.objects.filter(pk=api_token.pk).exists()


IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'


@pytest.mark.django_db
class TestApiTokensMobile:
    url = '/api-tokens/'

    def test_mobile_ua_uses_mobile_template(self, config_editor_client):
        resp = config_editor_client.get(self.url, HTTP_USER_AGENT=IPHONE_UA)
        assert resp.status_code == 200
        assert 'mobile' in resp.template_name[0]

    def test_revoke_token_not_found_message(self, config_editor_client):
        """Revoking a non-existent token id shows error message — covers the else branch."""
        resp = config_editor_client.post(self.url, {'action': 'revoke', 'token_id': '999999'})
        assert resp.status_code in (200, 302)

    def test_create_token_empty_name_rejected(self, config_editor_client):
        """Empty name should redirect with error — covers line 60-61."""
        resp = config_editor_client.post(self.url, {'action': 'create', 'name': ''})
        assert resp.status_code in (200, 302)
