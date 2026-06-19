"""Tests for webapp.recipe_index."""
from __future__ import annotations

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


def _reset_cache():
    import webapp.recipe_index as idx
    with idx._cache_lock:
        idx._cache['identifiers'] = {}
        idx._cache['shortnames'] = {}
        idx._cache['fetched_at'] = 0.0
        idx._cache['error'] = None
        idx._cache['building'] = False


def _populate_cache():
    import webapp.recipe_index as idx
    with idx._cache_lock:
        idx._cache['identifiers'] = {
            'com.github.autopkg.firefox.pkg': {
                'name': 'Firefox',
                'app_display_name': 'Firefox',
                'path': 'Firefox/Firefox.pkg.recipe',
                'repo': 'autopkg/recipes',
            },
            'com.github.autopkg.chrome.munki': {
                'name': 'GoogleChrome',
                'app_display_name': 'Google Chrome',
                'path': 'GoogleChrome/GoogleChrome.munki.recipe',
                'repo': 'autopkg/recipes',
                'parent': 'com.github.autopkg.chrome.pkg',
            },
            'com.github.autopkg.chrome.pkg': {
                'name': 'GoogleChrome',
                'app_display_name': 'Google Chrome',
                'path': 'GoogleChrome/GoogleChrome.pkg.recipe',
                'repo': 'autopkg/recipes',
            },
        }
        idx._cache['fetched_at'] = time.monotonic()
        idx._cache['error'] = None
        idx._cache['building'] = False


@pytest.fixture(autouse=True)
def clean_cache():
    _reset_cache()
    yield
    _reset_cache()


class TestIsReady:
    def test_false_when_empty(self):
        from webapp.recipe_index import is_ready
        assert is_ready() is False

    def test_true_when_populated(self):
        _populate_cache()
        from webapp.recipe_index import is_ready
        assert is_ready() is True


class TestIsStale:
    def test_stale_when_never_fetched(self):
        from webapp.recipe_index import is_stale
        assert is_stale() is True

    def test_not_stale_immediately_after_fetch(self):
        import webapp.recipe_index as idx
        with idx._cache_lock:
            idx._cache['fetched_at'] = time.monotonic()
        from webapp.recipe_index import is_stale
        assert is_stale() is False


class TestLastError:
    def test_returns_none_on_success(self):
        from webapp.recipe_index import last_error
        assert last_error() is None

    def test_returns_error_string(self):
        import webapp.recipe_index as idx
        with idx._cache_lock:
            idx._cache['error'] = 'connection refused'
        from webapp.recipe_index import last_error
        assert last_error() == 'connection refused'


class TestSearch:
    def setup_method(self):
        _populate_cache()

    def test_empty_query_returns_all(self):
        from webapp.recipe_index import search
        result = search('')
        assert result['total'] == 3

    def test_query_filters_by_identifier(self):
        from webapp.recipe_index import search
        result = search('firefox')
        assert result['total'] == 1
        assert result['results'][0]['identifier'] == 'com.github.autopkg.firefox.pkg'

    def test_query_filters_by_app_display_name(self):
        from webapp.recipe_index import search
        result = search('Google Chrome')
        assert result['total'] == 2

    def test_pagination(self):
        from webapp.recipe_index import search
        result = search('', page=1, page_size=2)
        assert len(result['results']) == 2
        assert result['pages'] == 2
        assert result['total'] == 3

    def test_page_clamped_to_valid_range(self):
        from webapp.recipe_index import search
        result = search('', page=999, page_size=10)
        assert result['page'] == result['pages']

    def test_results_sorted_alphabetically(self):
        from webapp.recipe_index import search
        result = search('')
        ids = [r['identifier'] for r in result['results']]
        assert ids == sorted(ids, key=str.lower)

    def test_query_filters_by_repo(self):
        from webapp.recipe_index import search
        result = search('autopkg/recipes')
        assert result['total'] == 3


class TestGetEntry:
    def setup_method(self):
        _populate_cache()

    def test_returns_enriched_entry(self):
        from webapp.recipe_index import get_entry
        entry = get_entry('com.github.autopkg.firefox.pkg')
        assert entry is not None
        assert entry['identifier'] == 'com.github.autopkg.firefox.pkg'
        assert entry['repo_url'] == 'https://github.com/autopkg/recipes'
        assert '/blob/HEAD/' in entry['recipe_url']

    def test_returns_none_for_missing(self):
        from webapp.recipe_index import get_entry
        assert get_entry('com.example.nonexistent') is None


class TestRepoUrl:
    def test_converts_slug_to_url(self):
        from webapp.recipe_index import repo_url
        assert repo_url('autopkg/recipes') == 'https://github.com/autopkg/recipes'


class TestRecipeGithubUrl:
    def test_uses_blob_head(self):
        from webapp.recipe_index import recipe_github_url
        url = recipe_github_url('autopkg/recipes', 'Firefox/Firefox.pkg.recipe')
        assert url == 'https://github.com/autopkg/recipes/blob/HEAD/Firefox/Firefox.pkg.recipe'


class TestResolveRepoRequirements:
    def setup_method(self):
        _populate_cache()

    def test_single_repo(self):
        from webapp.recipe_index import resolve_repo_requirements
        repos = resolve_repo_requirements('com.github.autopkg.firefox.pkg')
        assert repos == ['autopkg/recipes']

    def test_walks_parent_chain(self):
        from webapp.recipe_index import resolve_repo_requirements
        repos = resolve_repo_requirements('com.github.autopkg.chrome.munki')
        assert repos == ['autopkg/recipes']  # both in same repo, deduped

    def test_stops_on_missing_identifier(self):
        from webapp.recipe_index import resolve_repo_requirements
        repos = resolve_repo_requirements('com.example.unknown')
        assert repos == []

    def test_stops_on_self_referential_parent(self):
        import webapp.recipe_index as idx
        with idx._cache_lock:
            idx._cache['identifiers']['com.example.loop'] = {
                'repo': 'example/repo',
                'parent': 'com.example.loop',
            }
        from webapp.recipe_index import resolve_repo_requirements
        repos = resolve_repo_requirements('com.example.loop')
        assert repos == ['example/repo']


class TestEnsureFresh:
    def test_starts_background_thread_when_stale(self):
        from webapp.recipe_index import ensure_fresh
        with patch('threading.Thread') as mock_thread_cls:
            mock_t = MagicMock()
            mock_thread_cls.return_value = mock_t
            ensure_fresh()
        mock_t.start.assert_called_once()

    def test_no_thread_when_already_building(self):
        import webapp.recipe_index as idx
        with idx._cache_lock:
            idx._cache['building'] = True
        from webapp.recipe_index import ensure_fresh
        with patch('threading.Thread') as mock_thread_cls:
            ensure_fresh()
        mock_thread_cls.assert_not_called()

    def test_no_thread_when_fresh(self):
        _populate_cache()
        from webapp.recipe_index import ensure_fresh
        with patch('threading.Thread') as mock_thread_cls:
            ensure_fresh()
        mock_thread_cls.assert_not_called()

    def test_force_triggers_fetch_even_when_fresh(self):
        _populate_cache()
        from webapp.recipe_index import ensure_fresh
        with patch('threading.Thread') as mock_thread_cls:
            mock_t = MagicMock()
            mock_thread_cls.return_value = mock_t
            ensure_fresh(force=True)
        mock_t.start.assert_called_once()


class TestFetch:
    def test_populates_cache_on_success(self):
        import webapp.recipe_index as idx
        fake_data = {
            'identifiers': {'com.example.test': {'name': 'Test', 'repo': 'x/y', 'path': 'Test.recipe'}},
            'shortnames': {},
        }
        fake_resp = MagicMock()
        fake_resp.read.return_value = json.dumps(fake_data).encode()
        fake_resp.__enter__ = lambda s: s
        fake_resp.__exit__ = MagicMock(return_value=False)

        with patch('urllib.request.urlopen', return_value=fake_resp), \
             patch('webapp.recipe_index.ssl_context', return_value=None):
            idx._fetch()

        assert idx._cache['identifiers'] == fake_data['identifiers']
        assert idx._cache['error'] is None
        assert idx._cache['building'] is False

    def test_stores_error_on_failure(self):
        import webapp.recipe_index as idx
        with patch('urllib.request.urlopen', side_effect=OSError('no route')), \
             patch('webapp.recipe_index.ssl_context', return_value=None):
            idx._fetch()

        assert idx._cache['error'] == 'no route'
        assert idx._cache['building'] is False

    def test_close_old_connections_called(self):
        import webapp.recipe_index as idx
        fake_resp = MagicMock()
        fake_resp.read.return_value = json.dumps({'identifiers': {}, 'shortnames': {}}).encode()
        fake_resp.__enter__ = lambda s: s
        fake_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=fake_resp), \
             patch('webapp.recipe_index.ssl_context', return_value=None), \
             patch('django.db.close_old_connections') as mock_close:
            idx._fetch()
        mock_close.assert_called_once()
