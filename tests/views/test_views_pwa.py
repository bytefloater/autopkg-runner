"""Tests for webapp.views.pwa - ManifestView and ServiceWorkerView."""
from __future__ import annotations

import json
from unittest.mock import mock_open, patch

import pytest


@pytest.mark.django_db
class TestManifestView:
    url = '/manifest.json'

    def test_returns_200(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 200

    def test_content_type_is_manifest_json(self, client):
        resp = client.get(self.url)
        assert 'manifest' in resp.get('Content-Type', '')

    def test_manifest_has_required_keys(self, client):
        resp = client.get(self.url)
        data = json.loads(resp.content)
        assert 'name' in data
        assert 'start_url' in data
        assert 'icons' in data
        assert 'display' in data

    def test_manifest_name_is_autopkg_runner(self, client):
        resp = client.get(self.url)
        data = json.loads(resp.content)
        assert data['name'] == 'AutoPkg Runner'

    def test_cache_control_is_no_cache(self, client):
        resp = client.get(self.url)
        assert resp.get('Cache-Control') == 'no-cache'

    def test_accessible_without_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 200


@pytest.mark.django_db
class TestServiceWorkerView:
    url = '/sw.js'

    def test_returns_200_when_sw_exists(self, client):
        sw_content = b'self.addEventListener("install", function(e){});'
        with patch('builtins.open', mock_open(read_data=sw_content)):
            resp = client.get(self.url)
        assert resp.status_code == 200

    def test_service_worker_allowed_header(self, client):
        sw_content = b'// sw'
        with patch('builtins.open', mock_open(read_data=sw_content)):
            resp = client.get(self.url)
        assert resp.get('Service-Worker-Allowed') == '/'
