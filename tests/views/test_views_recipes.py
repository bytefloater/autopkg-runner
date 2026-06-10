"""Tests for webapp.views.recipes — helpers and views."""
from __future__ import annotations

import json
import plistlib
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# --- Helper: _git_behind_count -----------------------------------------------

class TestGitBehindCount:
    def test_returns_zero_when_up_to_date(self):
        from webapp.views.recipes import _git_behind_count
        r = MagicMock(returncode=0, stdout='0\n')
        with patch('subprocess.run', return_value=r):
            assert _git_behind_count('/some/repo') == 0

    def test_returns_count_when_behind(self):
        from webapp.views.recipes import _git_behind_count
        r = MagicMock(returncode=0, stdout='5\n')
        with patch('subprocess.run', return_value=r):
            assert _git_behind_count('/some/repo') == 5

    def test_returns_minus_one_on_nonzero_return(self):
        from webapp.views.recipes import _git_behind_count
        r = MagicMock(returncode=128, stdout='')
        with patch('subprocess.run', return_value=r):
            assert _git_behind_count('/some/repo') == -1

    def test_returns_minus_one_on_timeout(self):
        from webapp.views.recipes import _git_behind_count
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('git', 5)):
            assert _git_behind_count('/some/repo') == -1

    def test_returns_minus_one_when_git_not_found(self):
        from webapp.views.recipes import _git_behind_count
        with patch('subprocess.run', side_effect=FileNotFoundError):
            assert _git_behind_count('/some/repo') == -1

    def test_returns_minus_one_on_value_error(self):
        from webapp.views.recipes import _git_behind_count
        r = MagicMock(returncode=0, stdout='not-a-number\n')
        with patch('subprocess.run', return_value=r):
            assert _git_behind_count('/some/repo') == -1


# --- Helper: _list_repos -----------------------------------------------------

class TestListRepos:
    def test_parses_single_repo(self):
        from webapp.views.recipes import _list_repos
        r = MagicMock(returncode=0,
                      stdout='/Users/me/Library/AutoPkg/RecipeRepos/autopkg (https://github.com/autopkg/autopkg.git)\n')
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._autopkg', return_value='/usr/local/bin/autopkg'), \
             patch('webapp.views.recipes._git_behind_count', return_value=0):
            repos = _list_repos()
        assert len(repos) == 1
        assert repos[0]['url'] == 'https://github.com/autopkg/autopkg.git'
        assert repos[0]['behind'] == 0

    def test_parses_multiple_repos(self):
        from webapp.views.recipes import _list_repos
        output = (
            '/path/repo1 (https://github.com/org/repo1.git)\n'
            '/path/repo2 (https://github.com/org/repo2.git)\n'
        )
        r = MagicMock(returncode=0, stdout=output)
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._autopkg', return_value='/usr/local/bin/autopkg'), \
             patch('webapp.views.recipes._git_behind_count', return_value=2):
            repos = _list_repos()
        assert len(repos) == 2

    def test_returns_empty_list_on_nonzero_exit(self):
        from webapp.views.recipes import _list_repos
        r = MagicMock(returncode=1, stdout='')
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._autopkg', return_value='/usr/local/bin/autopkg'):
            assert _list_repos() == []

    def test_returns_empty_on_timeout(self):
        from webapp.views.recipes import _list_repos
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('autopkg', 30)), \
             patch('webapp.views.recipes._autopkg', return_value='/usr/local/bin/autopkg'):
            assert _list_repos() == []

    def test_returns_empty_when_binary_missing(self):
        from webapp.views.recipes import _list_repos
        with patch('subprocess.run', side_effect=FileNotFoundError), \
             patch('webapp.views.recipes._autopkg', return_value='/usr/local/bin/autopkg'):
            assert _list_repos() == []

    def test_ignores_malformed_lines(self):
        from webapp.views.recipes import _list_repos
        r = MagicMock(returncode=0, stdout='not a valid repo line\n')
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._autopkg', return_value='/usr/local/bin/autopkg'):
            assert _list_repos() == []


# --- Helper: _read_run_list / _write_run_list ---------------------------------

class TestRunListIO:
    def test_read_returns_empty_when_file_missing(self, tmp_path):
        from webapp.views.recipes import _read_run_list
        with patch('webapp.views.recipes._recipe_list_path',
                   return_value=tmp_path / 'nonexistent.txt'):
            assert _read_run_list() == []

    def test_read_skips_comments_and_blanks(self, tmp_path):
        f = tmp_path / 'recipe_list.txt'
        f.write_text('# header comment\nFoo.munki\n\nBar.pkg\n')
        from webapp.views.recipes import _read_run_list
        with patch('webapp.views.recipes._recipe_list_path', return_value=f):
            assert _read_run_list() == ['Foo.munki', 'Bar.pkg']

    def test_write_creates_file_with_newline(self, tmp_path):
        f = tmp_path / 'recipe_list.txt'
        from webapp.views.recipes import _write_run_list
        with patch('webapp.views.recipes._recipe_list_path', return_value=f):
            _write_run_list(['Alpha.munki', 'Beta.pkg'])
        assert f.read_text() == 'Alpha.munki\nBeta.pkg\n'

    def test_write_creates_parent_dirs(self, tmp_path):
        f = tmp_path / 'nested' / 'dir' / 'recipe_list.txt'
        from webapp.views.recipes import _write_run_list
        with patch('webapp.views.recipes._recipe_list_path', return_value=f):
            _write_run_list([])
        assert f.exists()


# --- Helper: _safe_override_path ---------------------------------------------

class TestSafeOverridePath:
    def test_valid_filename_returns_path(self, tmp_path):
        from webapp.views.recipes import _safe_override_path
        with patch('webapp.views.recipes._overrides_dir', return_value=tmp_path):
            result = _safe_override_path('MyOverride.recipe')
        assert result == (tmp_path / 'MyOverride.recipe').resolve()

    def test_path_traversal_raises_value_error(self, tmp_path):
        from webapp.views.recipes import _safe_override_path
        with patch('webapp.views.recipes._overrides_dir', return_value=tmp_path):
            with pytest.raises(ValueError, match='Unsafe override path'):
                _safe_override_path('../../../etc/passwd')


# --- Helper: _sort_run_list ---------------------------------------------------

class TestSortRunList:
    def test_sorts_alphabetically(self):
        from webapp.views.recipes import _sort_run_list
        result = _sort_run_list(['Zoo.pkg', 'Alpha.munki', 'Beta.pkg'])
        assert result == ['Alpha.munki', 'Beta.pkg', 'Zoo.pkg']

    def test_makecatalogs_sorted_last(self):
        from webapp.views.recipes import _sort_run_list
        result = _sort_run_list(['Alpha.munki', 'MakeCatalogs.munki', 'Beta.pkg'])
        assert result[-1] == 'MakeCatalogs.munki'

    def test_makecatalogs_case_insensitive(self):
        from webapp.views.recipes import _sort_run_list
        result = _sort_run_list(['Alpha.munki', 'makecatalogs.munki'])
        assert result[-1] == 'makecatalogs.munki'

    def test_empty_list(self):
        from webapp.views.recipes import _sort_run_list
        assert _sort_run_list([]) == []


# --- Helper: _read_recipe_identifier -----------------------------------------

class TestReadRecipeIdentifier:
    def test_extracts_identifier_from_xml(self, tmp_path):
        f = tmp_path / 'Firefox.recipe'
        f.write_text(
            '<plist><dict>'
            '<key>Identifier</key><string>com.github.autopkg.firefox</string>'
            '</dict></plist>'
        )
        from webapp.views.recipes import _read_recipe_identifier
        assert _read_recipe_identifier(f) == 'com.github.autopkg.firefox'

    def test_falls_back_to_stem_when_no_identifier(self, tmp_path):
        f = tmp_path / 'MyRecipe.recipe'
        f.write_text('<plist><dict></dict></plist>')
        from webapp.views.recipes import _read_recipe_identifier
        assert _read_recipe_identifier(f) == 'MyRecipe'

    def test_falls_back_to_stem_on_oserror(self, tmp_path):
        f = tmp_path / 'Broken.recipe'
        from webapp.views.recipes import _read_recipe_identifier
        with patch.object(Path, 'read_text', side_effect=OSError('permission denied')):
            assert _read_recipe_identifier(f) == 'Broken'


# --- Helper: _autopkg_prefs ---------------------------------------------------

class TestAutopkgPrefs:
    def test_returns_empty_when_file_missing(self):
        from webapp.views.recipes import _autopkg_prefs
        with patch('webapp.views.recipes.Path') as MockPath:
            inst = MockPath.return_value.expanduser.return_value
            inst.exists.return_value = False
            result = _autopkg_prefs()
        assert result == {}

    def test_reads_valid_plist(self, tmp_path):
        plist_file = tmp_path / 'com.github.autopkg.plist'
        with open(plist_file, 'wb') as fh:
            plistlib.dump({'RECIPE_SEARCH_DIRS': ['/some/dir']}, fh)
        from webapp.views.recipes import _autopkg_prefs
        with patch('webapp.views.recipes.Path') as MockPath:
            inst = MockPath.return_value.expanduser.return_value
            inst.exists.return_value = True
            inst.open = lambda mode: open(plist_file, mode)
            result = _autopkg_prefs()
        assert result.get('RECIPE_SEARCH_DIRS') == ['/some/dir']

    def test_returns_empty_on_corrupt_plist(self, tmp_path):
        bad_file = tmp_path / 'bad.plist'
        bad_file.write_bytes(b'not a plist')
        from webapp.views.recipes import _autopkg_prefs
        with patch('webapp.views.recipes.Path') as MockPath:
            inst = MockPath.return_value.expanduser.return_value
            inst.exists.return_value = True
            inst.open = lambda mode: open(bad_file, mode)
            result = _autopkg_prefs()
        assert result == {}


# --- Helper: cache helpers ----------------------------------------------------

class TestCacheHelpers:
    def _reset_cache(self):
        import webapp.views.recipes as rv
        rv._RECIPES_CACHE['data'] = None
        rv._RECIPES_CACHE['ts'] = 0.0
        rv._RECIPES_BUILDING = False

    def test_is_cache_ready_false_when_empty(self):
        self._reset_cache()
        from webapp.views.recipes import _is_cache_ready
        assert not _is_cache_ready()

    def test_is_cache_ready_true_when_fresh(self):
        import webapp.views.recipes as rv
        rv._RECIPES_CACHE['data'] = [{'stem': 'A', 'identifier': 'com.a'}]
        rv._RECIPES_CACHE['ts'] = time.monotonic()
        from webapp.views.recipes import _is_cache_ready
        assert _is_cache_ready()

    def test_is_cache_ready_false_when_stale(self):
        import webapp.views.recipes as rv
        rv._RECIPES_CACHE['data'] = [{'stem': 'A', 'identifier': 'com.a'}]
        rv._RECIPES_CACHE['ts'] = time.monotonic() - 400  # past 300s TTL
        from webapp.views.recipes import _is_cache_ready
        assert not _is_cache_ready()

    def test_list_parent_recipes_returns_empty_when_none(self):
        self._reset_cache()
        from webapp.views.recipes import _list_parent_recipes
        assert _list_parent_recipes() == []

    def test_list_parent_recipes_returns_cached_data(self):
        import webapp.views.recipes as rv
        data = [{'stem': 'Chrome', 'identifier': 'com.chrome'}]
        rv._RECIPES_CACHE['data'] = data
        from webapp.views.recipes import _list_parent_recipes
        assert _list_parent_recipes() == data

    def test_invalidate_clears_timestamp(self):
        import webapp.views.recipes as rv
        rv._RECIPES_CACHE['ts'] = time.monotonic()
        with patch('webapp.views.recipes._start_cache_build'):
            from webapp.views.recipes import _invalidate_recipe_cache
            _invalidate_recipe_cache()
        assert rv._RECIPES_CACHE['ts'] == 0.0

    def test_start_cache_build_skips_when_ready(self):
        import webapp.views.recipes as rv
        rv._RECIPES_CACHE['data'] = [{'stem': 'A', 'identifier': 'com.a'}]
        rv._RECIPES_CACHE['ts'] = time.monotonic()
        rv._RECIPES_BUILDING = False
        with patch('threading.Thread') as mock_thread:
            from webapp.views.recipes import _start_cache_build
            _start_cache_build()
        mock_thread.assert_not_called()

    def test_start_cache_build_skips_when_already_building(self):
        import webapp.views.recipes as rv
        rv._RECIPES_CACHE['data'] = None
        rv._RECIPES_CACHE['ts'] = 0.0
        rv._RECIPES_BUILDING = True
        with patch('threading.Thread') as mock_thread:
            from webapp.views.recipes import _start_cache_build
            _start_cache_build()
        mock_thread.assert_not_called()
        # Reset so other tests are not affected
        rv._RECIPES_BUILDING = False

    @pytest.mark.real_cache_build
    def test_start_cache_build_launches_thread_when_cold(self):
        import webapp.views.recipes as rv
        rv._RECIPES_CACHE['data'] = None
        rv._RECIPES_CACHE['ts'] = 0.0
        rv._RECIPES_BUILDING = False
        with patch('threading.Thread') as mock_thread:
            from webapp.views.recipes import _start_cache_build
            _start_cache_build()
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        # Reset building flag since thread was mocked
        rv._RECIPES_BUILDING = False


# --- Helper: _build_recipe_entries -------------------------------------------

class TestBuildRecipeEntries:
    def test_parent_recipe_no_override(self, tmp_path):
        od = tmp_path / 'RecipeOverrides'  # does not exist
        from webapp.views.recipes import _build_recipe_entries
        with patch('webapp.views.recipes._overrides_dir', return_value=od), \
             patch('webapp.views.recipes._list_parent_recipes', return_value=[
                 {'stem': 'Firefox', 'identifier': 'com.github.autopkg.firefox-pkg'}
             ]):
            entries, _, _orphaned = _build_recipe_entries(set())
        assert len(entries) == 1
        assert entries[0]['is_override'] is False
        assert entries[0]['identifier'] == 'com.github.autopkg.firefox-pkg'
        assert entries[0]['in_run_list'] is False

    def test_parent_in_run_list(self, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        from webapp.views.recipes import _build_recipe_entries
        with patch('webapp.views.recipes._overrides_dir', return_value=od), \
             patch('webapp.views.recipes._list_parent_recipes', return_value=[
                 {'stem': 'Firefox', 'identifier': 'com.github.autopkg.firefox-pkg'}
             ]):
            entries, _, _orphaned = _build_recipe_entries({'com.github.autopkg.firefox-pkg'})
        assert entries[0]['in_run_list'] is True

    def test_override_supersedes_parent(self, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        override_file = od / 'Firefox.recipe'
        override_file.write_text(
            '<plist><dict>'
            '<key>Identifier</key><string>local.firefox.override</string>'
            '</dict></plist>'
        )
        from webapp.views.recipes import _build_recipe_entries
        with patch('webapp.views.recipes._overrides_dir', return_value=od), \
             patch('webapp.views.recipes._list_parent_recipes', return_value=[
                 {'stem': 'Firefox', 'identifier': 'com.github.autopkg.firefox-pkg'}
             ]):
            entries, _, _orphaned = _build_recipe_entries(set())
        assert len(entries) == 1
        assert entries[0]['is_override'] is True
        assert entries[0]['identifier'] == 'local.firefox.override'
        assert entries[0]['override_fname'] == 'Firefox.recipe'

    def test_override_in_run_list(self, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        (od / 'Chrome.recipe').write_text(
            '<plist><dict>'
            '<key>Identifier</key><string>local.chrome.override</string>'
            '</dict></plist>'
        )
        from webapp.views.recipes import _build_recipe_entries
        with patch('webapp.views.recipes._overrides_dir', return_value=od), \
             patch('webapp.views.recipes._list_parent_recipes', return_value=[
                 {'stem': 'Chrome', 'identifier': 'com.github.autopkg.chrome'}
             ]):
            entries, _, _orphaned = _build_recipe_entries({'local.chrome.override'})
        assert entries[0]['in_run_list'] is True

    def test_orphan_override_no_parent(self, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        (od / 'Orphan.recipe').write_text(
            '<plist><dict>'
            '<key>Identifier</key><string>local.orphan</string>'
            '</dict></plist>'
        )
        from webapp.views.recipes import _build_recipe_entries
        with patch('webapp.views.recipes._overrides_dir', return_value=od), \
             patch('webapp.views.recipes._list_parent_recipes', return_value=[]):
            entries, _, _orphaned = _build_recipe_entries(set())
        assert len(entries) == 1
        assert entries[0]['name'] == 'Orphan'
        assert entries[0]['is_override'] is True

    def test_sorted_alphabetically(self, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        from webapp.views.recipes import _build_recipe_entries
        with patch('webapp.views.recipes._overrides_dir', return_value=od), \
             patch('webapp.views.recipes._list_parent_recipes', return_value=[
                 {'stem': 'Zoo', 'identifier': 'com.zoo'},
                 {'stem': 'Alpha', 'identifier': 'com.alpha'},
             ]):
            entries, _, _orphaned = _build_recipe_entries(set())
        assert entries[0]['name'] == 'Alpha'
        assert entries[1]['name'] == 'Zoo'


# --- Views --------------------------------------------------------------------

@pytest.mark.django_db
class TestReposView:
    url = '/recipes/repos/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_get_renders_empty_repo_list(self, client):
        with patch('webapp.views.recipes._list_repos', return_value=[]):
            resp = client.get(self.url)
        assert resp.status_code == 200
        assert resp.context['repos'] == []
        assert resp.context['active_tab'] == 'recipes'

    def test_get_passes_repos_to_context(self, client):
        repos = [{'path': '/p', 'url': 'https://example.com/r.git', 'behind': 0}]
        with patch('webapp.views.recipes._list_repos', return_value=repos):
            resp = client.get(self.url)
        assert resp.context['repos'] == repos


@pytest.mark.django_db
class TestRepoAddView:
    url = '/recipes/repos/add/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_empty_url_redirects(self, client):
        resp = client.post(self.url, {'url': ''})
        assert resp.status_code == 302
        assert resp['Location'].endswith('/recipes/repos/')

    def test_success_redirects_to_repos(self, client):
        r = MagicMock(returncode=0, stdout='', stderr='')
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._invalidate_recipe_cache'):
            resp = client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_autopkg_failure_redirects(self, client):
        r = MagicMock(returncode=1, stdout='', stderr='oops')
        with patch('subprocess.run', return_value=r):
            resp = client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_autopkg_stdout_used_when_stderr_empty(self, client):
        r = MagicMock(returncode=1, stdout='stdout error', stderr='')
        with patch('subprocess.run', return_value=r):
            resp = client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_timeout_redirects(self, client):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('autopkg', 60)):
            resp = client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_file_not_found_redirects(self, client):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            resp = client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302


@pytest.mark.django_db
class TestRepoDeleteView:
    url = '/recipes/repos/delete/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_empty_url_redirects(self, client):
        resp = client.post(self.url, {'url': ''})
        assert resp.status_code == 302

    def test_success_redirects(self, client):
        r = MagicMock(returncode=0, stdout='', stderr='')
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._invalidate_recipe_cache'):
            resp = client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_autopkg_failure_redirects(self, client):
        r = MagicMock(returncode=1, stdout='', stderr='not found')
        with patch('subprocess.run', return_value=r):
            resp = client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_timeout_redirects(self, client):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('autopkg', 30)):
            resp = client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_file_not_found_redirects(self, client):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            resp = client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302


@pytest.mark.django_db
class TestRepoUpdateView:
    url = '/recipes/repos/update/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url, {'repo_url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_missing_url_returns_html_with_error(self, client):
        resp = client.post(self.url, {'repo_url': '', 'repo_path': ''})
        assert resp.status_code == 200
        assert b'<' in resp.content

    def test_success_returns_row_html(self, client):
        r = MagicMock(returncode=0, stdout='', stderr='')
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._git_behind_count', return_value=0), \
             patch('webapp.views.recipes._invalidate_recipe_cache'):
            resp = client.post(self.url, {
                'repo_url': 'https://example.com/r.git',
                'repo_path': '/path/to/repo',
            })
        assert resp.status_code == 200

    def test_autopkg_failure_returns_html(self, client):
        r = MagicMock(returncode=1, stdout='', stderr='update failed')
        with patch('subprocess.run', return_value=r):
            resp = client.post(self.url, {
                'repo_url': 'https://example.com/r.git',
                'repo_path': '/path/to/repo',
            })
        assert resp.status_code == 200

    def test_timeout_returns_html(self, client):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('autopkg', 120)):
            resp = client.post(self.url, {
                'repo_url': 'https://example.com/r.git',
                'repo_path': '/path/to/repo',
            })
        assert resp.status_code == 200

    def test_file_not_found_returns_html(self, client):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            resp = client.post(self.url, {
                'repo_url': 'https://example.com/r.git',
                'repo_path': '/path/to/repo',
            })
        assert resp.status_code == 200


@pytest.mark.django_db
class TestRecipeListView:
    url = '/recipes/list/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_get_renders(self, client):
        with patch('webapp.views.recipes._start_cache_build'):
            resp = client.get(self.url)
        assert resp.status_code == 200
        assert resp.context['active_tab'] == 'recipes'

    def test_post_saves_and_redirects(self, client):
        with patch('webapp.views.recipes._write_run_list') as mock_write, \
             patch('webapp.views.recipes._sort_run_list', side_effect=lambda x: x):
            resp = client.post(self.url, {'selected': ['Foo.munki', 'Bar.pkg']})
        assert resp.status_code == 302
        mock_write.assert_called_once_with(['Foo.munki', 'Bar.pkg'])

    def test_post_empty_selection_writes_empty_list(self, client):
        with patch('webapp.views.recipes._write_run_list') as mock_write, \
             patch('webapp.views.recipes._sort_run_list', side_effect=lambda x: x):
            resp = client.post(self.url, {})  # no 'selected' key
        assert resp.status_code == 302
        mock_write.assert_called_once_with([])


@pytest.mark.django_db
class TestRecipeDataView:
    url = '/recipes/list/data/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_returns_202_while_building(self, client):
        with patch('webapp.views.recipes._start_cache_build'), \
             patch('webapp.views.recipes._is_cache_ready', return_value=False):
            resp = client.get(self.url)
        assert resp.status_code == 202
        data = json.loads(resp.content)
        assert data.get('building') is True

    def test_returns_200_with_recipe_data_when_ready(self, client):
        entries = [{'identifier': 'com.test', 'name': 'Test', 'is_override': False,
                    'override_fname': None, 'in_run_list': False}]
        with patch('webapp.views.recipes._start_cache_build'), \
             patch('webapp.views.recipes._is_cache_ready', return_value=True), \
             patch('webapp.views.recipes._read_run_list', return_value=[]), \
             patch('webapp.views.recipes._build_recipe_entries', return_value=(entries, False, [])):
            resp = client.get(self.url)
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert 'recipes' in data
        assert data['load_error'] is False


@pytest.mark.django_db
class TestOverrideCreateView:
    url = '/recipes/overrides/create/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url, {'identifier': 'Firefox.munki'})
        assert resp.status_code == 302

    def test_empty_identifier_redirects(self, client):
        resp = client.post(self.url, {'identifier': ''})
        assert resp.status_code == 302
        assert 'list' in resp['Location']

    def test_autopkg_failure_redirects_with_error(self, client):
        r = MagicMock(returncode=1, stdout='', stderr='recipe not found')
        with patch('subprocess.run', return_value=r):
            resp = client.post(self.url, {'identifier': 'NoSuchRecipe.munki'})
        assert resp.status_code == 302

    def test_timeout_redirects(self, client):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('autopkg', 30)):
            resp = client.post(self.url, {'identifier': 'Firefox.munki'})
        assert resp.status_code == 302

    def test_file_not_found_redirects(self, client):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            resp = client.post(self.url, {'identifier': 'Firefox.munki'})
        assert resp.status_code == 302

    def test_success_redirects_to_editor_when_file_found(self, client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()

        def create_file(cmd, **kwargs):
            (od / 'Firefox.recipe').write_text('<plist/>')
            return MagicMock(returncode=0, stdout='', stderr='')

        with patch('subprocess.run', side_effect=create_file), \
             patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = client.post(self.url, {'identifier': 'Firefox.munki'})
        assert resp.status_code == 302
        assert 'Firefox' in resp['Location']

    def test_success_redirects_to_list_when_no_file_found(self, client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()  # subprocess succeeds but creates no file
        r = MagicMock(returncode=0, stdout='', stderr='')
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = client.post(self.url, {'identifier': 'Firefox.munki'})
        assert resp.status_code == 302
        assert 'list' in resp['Location']

    def test_success_prefers_exact_stem_match(self, client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        # Subprocess creates two candidates — exact stem match should win
        def create_both(cmd, **kwargs):
            (od / 'Firefox.recipe').write_text('<plist/>')
            (od / 'Firefox-extra.recipe').write_text('<plist/>')
            return MagicMock(returncode=0, stdout='', stderr='')

        with patch('subprocess.run', side_effect=create_both), \
             patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = client.post(self.url, {'identifier': 'Firefox.munki'})
        assert 'Firefox.recipe' in resp['Location']


@pytest.mark.django_db
class TestOverrideEditView:
    def _url(self, fname: str) -> str:
        return f'/recipes/overrides/{fname}/edit/'

    def test_requires_login(self, anon_client, tmp_path):
        resp = anon_client.get(self._url('Test.recipe'))
        assert resp.status_code == 302

    def test_get_renders_existing_file(self, client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        (od / 'Test.recipe').write_text('<plist><dict/></plist>')
        with patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = client.get(self._url('Test.recipe'))
        assert resp.status_code == 200
        assert resp.context['fname'] == 'Test.recipe'
        assert '<plist>' in resp.context['content']

    def test_get_missing_file_redirects(self, client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()  # file doesn't exist inside
        with patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = client.get(self._url('Missing.recipe'))
        assert resp.status_code == 302

    def test_get_unsafe_path_redirects(self, client, tmp_path):
        # _safe_override_path raises ValueError for traversal; _get_path returns None
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        with patch('webapp.views.recipes._safe_override_path',
                   side_effect=ValueError('Unsafe override path')):
            resp = client.get(self._url('evil.recipe'))
        assert resp.status_code == 302

    def test_post_valid_xml_saves_file(self, client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        f = od / 'Test.recipe'
        f.write_text('<plist/>')
        content = '<plist><dict><key>Identifier</key><string>com.test</string></dict></plist>'
        with patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = client.post(self._url('Test.recipe'), {'content': content})
        assert resp.status_code == 302
        assert f.read_text() == content

    def test_post_invalid_xml_rerenders_with_error(self, client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        (od / 'Test.recipe').write_text('<plist/>')
        with patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = client.post(self._url('Test.recipe'), {'content': '<unclosed'})
        assert resp.status_code == 200
        assert resp.context['error'] is not None
        assert 'XML' in resp.context['error']

    def test_post_unsafe_path_redirects(self, client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        with patch('webapp.views.recipes._safe_override_path',
                   side_effect=ValueError('Unsafe override path')):
            resp = client.post(self._url('evil.recipe'), {'content': '<plist/>'})
        assert resp.status_code == 302
