"""Tests for webapp.views.recipe_index."""
from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest


def _repos():
    return [{'url': 'https://github.com/autopkg/recipes', 'name': 'autopkg/recipes'}]


@pytest.mark.django_db
class TestRecipeIndexView:
    def test_renders_template(self, admin_client):
        with patch('webapp.views.recipe_index.idx.ensure_fresh'):
            resp = admin_client.get('/recipes/find/')
        assert resp.status_code == 200
        assert b'recipe_index' in resp.content or resp.template_name[0].endswith('recipe_index.html')

    def test_calls_ensure_fresh(self, admin_client):
        with patch('webapp.views.recipe_index.idx.ensure_fresh') as mock_ef:
            admin_client.get('/recipes/find/')
        mock_ef.assert_called_once()

    def test_requires_login(self, client):
        resp = client.get('/recipes/find/')
        assert resp.status_code in (302, 403)


@pytest.mark.django_db
class TestRecipeIndexSearchView:
    def test_returns_202_while_building(self, admin_client):
        with patch('webapp.views.recipe_index.idx.ensure_fresh'), \
             patch('webapp.views.recipe_index.idx.is_ready', return_value=False):
            resp = admin_client.get('/recipes/find/search/')
        assert resp.status_code == 202
        assert json.loads(resp.content)['building'] is True

    def test_returns_results_when_ready(self, admin_client):
        fake_result = {
            'results': [{'identifier': 'com.test.firefox.pkg', 'name': 'Firefox',
                         'app_display_name': 'Firefox', 'repo': 'autopkg/recipes',
                         'path': 'Firefox.recipe', 'parent': '', 'repo_url': '', 'recipe_url': ''}],
            'total': 1, 'page': 1, 'page_size': 50, 'pages': 1,
        }
        with patch('webapp.views.recipe_index.idx.ensure_fresh'), \
             patch('webapp.views.recipe_index.idx.is_ready', return_value=True), \
             patch('webapp.views.recipe_index.idx.search', return_value=fake_result), \
             patch('webapp.views.recipe_index.idx.last_error', return_value=None), \
             patch('webapp.views.recipe_index._list_repos', return_value=_repos()):
            resp = admin_client.get('/recipes/find/search/?q=firefox')
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['total'] == 1
        assert 'installed_repos' in data

    def test_installed_repos_normalised(self, admin_client):
        with patch('webapp.views.recipe_index.idx.ensure_fresh'), \
             patch('webapp.views.recipe_index.idx.is_ready', return_value=True), \
             patch('webapp.views.recipe_index.idx.search', return_value={
                 'results': [], 'total': 0, 'page': 1, 'page_size': 50, 'pages': 1}), \
             patch('webapp.views.recipe_index.idx.last_error', return_value=None), \
             patch('webapp.views.recipe_index._list_repos', return_value=[
                 {'url': 'https://github.com/autopkg/recipes'},
                 {'url': 'git@github.com:autopkg/jss-recipes'},
             ]):
            resp = admin_client.get('/recipes/find/search/')
        data = json.loads(resp.content)
        assert 'autopkg/recipes' in data['installed_repos']
        assert 'autopkg/jss-recipes' in data['installed_repos']

    def test_page_and_page_size_params(self, admin_client):
        fake_result = {'results': [], 'total': 0, 'page': 2, 'page_size': 25, 'pages': 1}
        with patch('webapp.views.recipe_index.idx.ensure_fresh'), \
             patch('webapp.views.recipe_index.idx.is_ready', return_value=True), \
             patch('webapp.views.recipe_index.idx.search', return_value=fake_result) as mock_search, \
             patch('webapp.views.recipe_index.idx.last_error', return_value=None), \
             patch('webapp.views.recipe_index._list_repos', return_value=[]):
            admin_client.get('/recipes/find/search/?page=2&page_size=25')
        mock_search.assert_called_once_with('', page=2, page_size=25)

    def test_invalid_page_size_defaults_to_50(self, admin_client):
        fake_result = {'results': [], 'total': 0, 'page': 1, 'page_size': 50, 'pages': 1}
        with patch('webapp.views.recipe_index.idx.ensure_fresh'), \
             patch('webapp.views.recipe_index.idx.is_ready', return_value=True), \
             patch('webapp.views.recipe_index.idx.search', return_value=fake_result) as mock_search, \
             patch('webapp.views.recipe_index.idx.last_error', return_value=None), \
             patch('webapp.views.recipe_index._list_repos', return_value=[]):
            admin_client.get('/recipes/find/search/?page_size=bad')
        mock_search.assert_called_once_with('', page=1, page_size=50)

    def test_invalid_page_defaults_to_1(self, admin_client):
        fake_result = {'results': [], 'total': 0, 'page': 1, 'page_size': 50, 'pages': 1}
        with patch('webapp.views.recipe_index.idx.ensure_fresh'), \
             patch('webapp.views.recipe_index.idx.is_ready', return_value=True), \
             patch('webapp.views.recipe_index.idx.search', return_value=fake_result) as mock_search, \
             patch('webapp.views.recipe_index.idx.last_error', return_value=None), \
             patch('webapp.views.recipe_index._list_repos', return_value=[]):
            admin_client.get('/recipes/find/search/?page=abc')
        mock_search.assert_called_once_with('', page=1, page_size=50)


@pytest.mark.django_db
class TestRecipeIndexRepoRequirementsView:
    def test_missing_identifier_returns_400(self, admin_client):
        resp = admin_client.get('/recipes/find/repo-requirements/')
        assert resp.status_code == 400

    def test_returns_repos_with_installed_status(self, admin_client):
        with patch('webapp.views.recipe_index.idx.resolve_repo_requirements',
                   return_value=['autopkg/recipes', 'autopkg/jss-recipes']), \
             patch('webapp.views.recipe_index.idx.repo_url',
                   side_effect=lambda s: f'https://github.com/{s}'), \
             patch('webapp.views.recipe_index._list_repos', return_value=_repos()):
            resp = admin_client.get('/recipes/find/repo-requirements/?identifier=com.test.recipe')
        assert resp.status_code == 200
        data = json.loads(resp.content)
        repos = {r['repo']: r for r in data['repos']}
        assert repos['autopkg/recipes']['installed'] is True
        assert repos['autopkg/jss-recipes']['installed'] is False


@pytest.mark.django_db
class TestRecipeIndexRefreshView:
    def test_post_triggers_refresh(self, admin_client):
        with patch('webapp.views.recipe_index.idx.ensure_fresh') as mock_ef:
            resp = admin_client.post('/recipes/find/refresh/')
        assert resp.status_code == 200
        mock_ef.assert_called_once_with(force=True)

    def test_get_not_allowed(self, admin_client):
        resp = admin_client.get('/recipes/find/refresh/')
        assert resp.status_code == 405


@pytest.mark.django_db
class TestRecipeIndexAddRepoView:
    def test_missing_repo_returns_400(self, admin_client):
        resp = admin_client.post('/recipes/find/add-repo/', {})
        assert resp.status_code == 400

    def test_successful_add(self, admin_client):
        mock_result = MagicMock(returncode=0, stderr='', stdout='')
        with patch('webapp.views.recipe_index.idx.repo_url', return_value='https://github.com/autopkg/recipes'), \
             patch('webapp.views.recipe_index._autopkg', return_value='/usr/local/bin/autopkg'), \
             patch('subprocess.run', return_value=mock_result), \
             patch('webapp.views.recipe_index._invalidate_recipe_cache'):
            resp = admin_client.post('/recipes/find/add-repo/', {'repo': 'autopkg/recipes'})
        assert resp.status_code == 200
        assert json.loads(resp.content)['ok'] is True

    def test_failed_add_returns_400(self, admin_client):
        mock_result = MagicMock(returncode=1, stderr='error message', stdout='')
        with patch('webapp.views.recipe_index.idx.repo_url', return_value='https://github.com/autopkg/recipes'), \
             patch('webapp.views.recipe_index._autopkg', return_value='/usr/local/bin/autopkg'), \
             patch('subprocess.run', return_value=mock_result):
            resp = admin_client.post('/recipes/find/add-repo/', {'repo': 'autopkg/recipes'})
        assert resp.status_code == 400
        assert 'error' in json.loads(resp.content)

    def test_timeout_returns_504(self, admin_client):
        with patch('webapp.views.recipe_index.idx.repo_url', return_value='https://github.com/autopkg/recipes'), \
             patch('webapp.views.recipe_index._autopkg', return_value='/usr/local/bin/autopkg'), \
             patch('subprocess.run', side_effect=subprocess.TimeoutExpired('autopkg', 60)):
            resp = admin_client.post('/recipes/find/add-repo/', {'repo': 'autopkg/recipes'})
        assert resp.status_code == 504

    def test_autopkg_not_found_returns_500(self, admin_client):
        with patch('webapp.views.recipe_index.idx.repo_url', return_value='https://github.com/autopkg/recipes'), \
             patch('webapp.views.recipe_index._autopkg', return_value='/usr/local/bin/autopkg'), \
             patch('subprocess.run', side_effect=FileNotFoundError):
            resp = admin_client.post('/recipes/find/add-repo/', {'repo': 'autopkg/recipes'})
        assert resp.status_code == 500
