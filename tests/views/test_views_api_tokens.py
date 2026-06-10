"""Tests for webapp.views.api_tokens.ApiTokensView."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestApiTokensView:
    url = '/api-tokens/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_get_renders(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 200

    def test_create_token(self, client, user):
        from webapp.models import APIToken
        resp = client.post(self.url, {'action': 'create', 'name': 'My Token'})
        assert resp.status_code in (200, 302)
        assert APIToken.objects.filter(user=user, name='My Token').exists()

    def test_new_token_visible_once_in_session(self, client, user):
        resp = client.post(self.url, {'action': 'create', 'name': 'Once Token'})
        # On the response or redirect, the token credentials should be accessible.
        # The view uses context keys 'new_token_id' and 'new_token_secret'.
        if resp.status_code == 302:
            follow_resp = client.get(resp['Location'])
            assert follow_resp.context.get('new_token_id') is not None
            assert follow_resp.context.get('new_token_secret') is not None
            # On a second request the session keys are cleared - credentials gone.
            resp2 = client.get(self.url)
            assert resp2.context.get('new_token_id') is None
            assert resp2.context.get('new_token_secret') is None
        else:
            # View may render directly (no redirect) - token still in context.
            assert resp.context.get('new_token_id') is not None

    def test_revoke_token(self, client, user, api_token):
        from webapp.models import APIToken
        resp = client.post(self.url, {'action': 'revoke', 'token_id': str(api_token.pk)})
        assert resp.status_code in (200, 302)
        assert not APIToken.objects.filter(pk=api_token.pk).exists()
