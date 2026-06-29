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

    def test_get_renders_empty_repo_list(self, config_editor_client):
        with patch('webapp.views.recipes._list_repos', return_value=[]):
            resp = config_editor_client.get(self.url)
        assert resp.status_code == 200
        assert resp.context['repos'] == []
        assert resp.context['active_tab'] == 'recipes'

    def test_get_passes_repos_to_context(self, config_editor_client):
        repos = [{'path': '/p', 'url': 'https://example.com/r.git', 'behind': 0}]
        with patch('webapp.views.recipes._list_repos', return_value=repos):
            resp = config_editor_client.get(self.url)
        assert resp.context['repos'] == repos


@pytest.mark.django_db
class TestRepoAddView:
    url = '/recipes/repos/add/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_empty_url_redirects(self, config_editor_client):
        resp = config_editor_client.post(self.url, {'url': ''})
        assert resp.status_code == 302
        assert resp['Location'].endswith('/recipes/repos/')

    def test_success_redirects_to_repos(self, config_editor_client):
        r = MagicMock(returncode=0, stdout='', stderr='')
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._invalidate_recipe_cache'):
            resp = config_editor_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_autopkg_failure_redirects(self, config_editor_client):
        r = MagicMock(returncode=1, stdout='', stderr='oops')
        with patch('subprocess.run', return_value=r):
            resp = config_editor_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_autopkg_stdout_used_when_stderr_empty(self, config_editor_client):
        r = MagicMock(returncode=1, stdout='stdout error', stderr='')
        with patch('subprocess.run', return_value=r):
            resp = config_editor_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_timeout_redirects(self, config_editor_client):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('autopkg', 60)):
            resp = config_editor_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_file_not_found_redirects(self, config_editor_client):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            resp = config_editor_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302


@pytest.mark.django_db
class TestRepoDeleteView:
    url = '/recipes/repos/delete/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_empty_url_redirects(self, config_editor_client):
        resp = config_editor_client.post(self.url, {'url': ''})
        assert resp.status_code == 302

    def test_success_redirects(self, config_editor_client):
        r = MagicMock(returncode=0, stdout='', stderr='')
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._invalidate_recipe_cache'):
            resp = config_editor_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_autopkg_failure_redirects(self, config_editor_client):
        r = MagicMock(returncode=1, stdout='', stderr='not found')
        with patch('subprocess.run', return_value=r):
            resp = config_editor_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_timeout_redirects(self, config_editor_client):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('autopkg', 30)):
            resp = config_editor_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_file_not_found_redirects(self, config_editor_client):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            resp = config_editor_client.post(self.url, {'url': 'https://example.com/r.git'})
        assert resp.status_code == 302


@pytest.mark.django_db
class TestRepoUpdateView:
    url = '/recipes/repos/update/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url, {'repo_url': 'https://example.com/r.git'})
        assert resp.status_code == 302

    def test_missing_url_returns_html_with_error(self, config_editor_client):
        resp = config_editor_client.post(self.url, {'repo_url': '', 'repo_path': ''})
        assert resp.status_code == 200
        assert b'<' in resp.content

    def test_success_returns_row_html(self, config_editor_client):
        r = MagicMock(returncode=0, stdout='', stderr='')
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._git_behind_count', return_value=0), \
             patch('webapp.views.recipes._invalidate_recipe_cache'):
            resp = config_editor_client.post(self.url, {
                'repo_url': 'https://example.com/r.git',
                'repo_path': '/path/to/repo',
            })
        assert resp.status_code == 200

    def test_autopkg_failure_returns_html(self, config_editor_client):
        r = MagicMock(returncode=1, stdout='', stderr='update failed')
        with patch('subprocess.run', return_value=r):
            resp = config_editor_client.post(self.url, {
                'repo_url': 'https://example.com/r.git',
                'repo_path': '/path/to/repo',
            })
        assert resp.status_code == 200

    def test_timeout_returns_html(self, config_editor_client):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('autopkg', 120)):
            resp = config_editor_client.post(self.url, {
                'repo_url': 'https://example.com/r.git',
                'repo_path': '/path/to/repo',
            })
        assert resp.status_code == 200

    def test_file_not_found_returns_html(self, config_editor_client):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            resp = config_editor_client.post(self.url, {
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

    def test_get_renders(self, config_editor_client):
        with patch('webapp.views.recipes._start_cache_build'):
            resp = config_editor_client.get(self.url)
        assert resp.status_code == 200
        assert resp.context['active_tab'] == 'recipes'

    def test_post_saves_and_redirects(self, config_editor_client):
        with patch('webapp.views.recipes._write_run_list') as mock_write, \
             patch('webapp.views.recipes._sort_run_list', side_effect=lambda x: x):
            resp = config_editor_client.post(self.url, {'selected': ['Foo.munki', 'Bar.pkg']})
        assert resp.status_code == 302
        mock_write.assert_called_once_with(['Foo.munki', 'Bar.pkg'])

    def test_post_empty_selection_writes_empty_list(self, config_editor_client):
        with patch('webapp.views.recipes._write_run_list') as mock_write, \
             patch('webapp.views.recipes._sort_run_list', side_effect=lambda x: x):
            resp = config_editor_client.post(self.url, {})  # no 'selected' key
        assert resp.status_code == 302
        mock_write.assert_called_once_with([])


@pytest.mark.django_db
class TestRecipeDataView:
    url = '/recipes/list/data/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_returns_202_while_building(self, config_editor_client):
        with patch('webapp.views.recipes._start_cache_build'), \
             patch('webapp.views.recipes._is_cache_ready', return_value=False):
            resp = config_editor_client.get(self.url)
        assert resp.status_code == 202
        data = json.loads(resp.content)
        assert data.get('building') is True

    def test_returns_200_with_recipe_data_when_ready(self, config_editor_client):
        entries = [{'identifier': 'com.test', 'name': 'Test', 'is_override': False,
                    'override_fname': None, 'in_run_list': False}]
        with patch('webapp.views.recipes._start_cache_build'), \
             patch('webapp.views.recipes._is_cache_ready', return_value=True), \
             patch('webapp.views.recipes._read_run_list', return_value=[]), \
             patch('webapp.views.recipes._build_recipe_entries', return_value=(entries, False, [])):
            resp = config_editor_client.get(self.url)
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

    def test_empty_identifier_redirects(self, config_editor_client):
        resp = config_editor_client.post(self.url, {'identifier': ''})
        assert resp.status_code == 302
        assert 'list' in resp['Location']

    def test_autopkg_failure_redirects_with_error(self, config_editor_client):
        r = MagicMock(returncode=1, stdout='', stderr='recipe not found')
        with patch('subprocess.run', return_value=r):
            resp = config_editor_client.post(self.url, {'identifier': 'NoSuchRecipe.munki'})
        assert resp.status_code == 302

    def test_timeout_redirects(self, config_editor_client):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('autopkg', 30)):
            resp = config_editor_client.post(self.url, {'identifier': 'Firefox.munki'})
        assert resp.status_code == 302

    def test_file_not_found_redirects(self, config_editor_client):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            resp = config_editor_client.post(self.url, {'identifier': 'Firefox.munki'})
        assert resp.status_code == 302

    def test_success_redirects_to_editor_when_file_found(self, config_editor_client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()

        def create_file(cmd, **kwargs):
            (od / 'Firefox.recipe').write_text('<plist/>')
            return MagicMock(returncode=0, stdout='', stderr='')

        with patch('subprocess.run', side_effect=create_file), \
             patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = config_editor_client.post(self.url, {'identifier': 'Firefox.munki'})
        assert resp.status_code == 302
        assert 'Firefox' in resp['Location']

    def test_success_redirects_to_list_when_no_file_found(self, config_editor_client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()  # subprocess succeeds but creates no file
        r = MagicMock(returncode=0, stdout='', stderr='')
        with patch('subprocess.run', return_value=r), \
             patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = config_editor_client.post(self.url, {'identifier': 'Firefox.munki'})
        assert resp.status_code == 302
        assert 'list' in resp['Location']

    def test_success_prefers_exact_stem_match(self, config_editor_client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        # Subprocess creates two candidates — exact stem match should win
        def create_both(cmd, **kwargs):
            (od / 'Firefox.recipe').write_text('<plist/>')
            (od / 'Firefox-extra.recipe').write_text('<plist/>')
            return MagicMock(returncode=0, stdout='', stderr='')

        with patch('subprocess.run', side_effect=create_both), \
             patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = config_editor_client.post(self.url, {'identifier': 'Firefox.munki'})
        assert 'Firefox.recipe' in resp['Location']


@pytest.mark.django_db
class TestOverrideEditView:
    def _url(self, fname: str) -> str:
        return f'/recipes/overrides/{fname}/edit/'

    def test_requires_login(self, anon_client, tmp_path):
        resp = anon_client.get(self._url('Test.recipe'))
        assert resp.status_code == 302

    def test_get_renders_existing_file(self, config_editor_client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        (od / 'Test.recipe').write_text('<plist><dict/></plist>')
        with patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = config_editor_client.get(self._url('Test.recipe'))
        assert resp.status_code == 200
        assert resp.context['fname'] == 'Test.recipe'
        assert '<plist>' in resp.context['content']

    def test_get_missing_file_redirects(self, config_editor_client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()  # file doesn't exist inside
        with patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = config_editor_client.get(self._url('Missing.recipe'))
        assert resp.status_code == 302

    def test_get_unsafe_path_redirects(self, config_editor_client, tmp_path):
        # _safe_override_path raises ValueError for traversal; _get_path returns None
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        with patch('webapp.views.recipes._safe_override_path',
                   side_effect=ValueError('Unsafe override path')):
            resp = config_editor_client.get(self._url('evil.recipe'))
        assert resp.status_code == 302

    def test_post_valid_xml_saves_file(self, config_editor_client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        f = od / 'Test.recipe'
        f.write_text('<plist/>')
        content = '<plist><dict><key>Identifier</key><string>com.test</string></dict></plist>'
        with patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = config_editor_client.post(self._url('Test.recipe'), {'content': content})
        assert resp.status_code == 302
        assert f.read_text() == content

    def test_post_invalid_xml_rerenders_with_error(self, config_editor_client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        (od / 'Test.recipe').write_text('<plist/>')
        with patch('webapp.views.recipes._overrides_dir', return_value=od):
            resp = config_editor_client.post(self._url('Test.recipe'), {'content': '<unclosed'})
        assert resp.status_code == 200
        assert resp.context['error'] is not None
        assert 'XML' in resp.context['error']

    def test_post_unsafe_path_redirects(self, config_editor_client, tmp_path):
        od = tmp_path / 'RecipeOverrides'
        od.mkdir()
        with patch('webapp.views.recipes._safe_override_path',
                   side_effect=ValueError('Unsafe override path')):
            resp = config_editor_client.post(self._url('evil.recipe'), {'content': '<plist/>'})
        assert resp.status_code == 302


# --- Helper: _recipe_list_path -----------------------------------------------

@pytest.mark.django_db
class TestRecipeListPath:
    def test_returns_path_from_setting(self, db):
        from webapp.models import Setting
        from webapp.views.recipes import _recipe_list_path
        Setting.set('autopkg.recipe_list', '/tmp/my_recipe_list.txt')
        result = _recipe_list_path()
        assert str(result) == '/tmp/my_recipe_list.txt'


# --- Helper: _recipe_stem yaml -----------------------------------------------

class TestRecipeStem:
    def test_yaml_recipe_strips_both_suffixes(self):
        from webapp.views.recipes import _recipe_stem
        p = Path('/some/dir/Firefox.munki.recipe.yaml')
        assert _recipe_stem(p) == 'Firefox.munki'

    def test_regular_recipe_strips_recipe_suffix(self):
        from webapp.views.recipes import _recipe_stem
        p = Path('/some/dir/Firefox.munki.recipe')
        assert _recipe_stem(p) == 'Firefox.munki'


# --- Helper: _recipe_search_dirs ---------------------------------------------

@pytest.mark.django_db
class TestRecipeSearchDirs:
    def test_returns_dirs_from_prefs_excluding_overrides(self, tmp_path, db):
        from webapp.views.recipes import _recipe_search_dirs
        from webapp.models import Setting

        # Create two subdirs
        repo1 = tmp_path / 'repo1'
        repo1.mkdir()
        repo2 = tmp_path / 'repo2'
        repo2.mkdir()

        prefs = {'RECIPE_SEARCH_DIRS': [str(repo1), str(repo2)]}
        Setting.set('autopkg.overrides_dir', str(tmp_path / 'overrides'))

        with patch('webapp.views.recipes._autopkg_prefs', return_value=prefs):
            result = _recipe_search_dirs()

        # Both repos should be present, overrides dir excluded
        assert str(repo1) in result
        assert str(repo2) in result

    def test_overrides_resolve_exception_uses_str_fallback(self, tmp_path, db):
        """Lines 282-283: if _overrides_dir().resolve() raises, falls back to str()."""
        from webapp.views.recipes import _recipe_search_dirs
        prefs = {'RECIPE_SEARCH_DIRS': [str(tmp_path / 'repo1')]}
        (tmp_path / 'repo1').mkdir()
        with patch('webapp.views.recipes._autopkg_prefs', return_value=prefs), \
             patch('webapp.views.recipes._overrides_dir') as mock_od:
            ov_path = MagicMock()
            ov_path.resolve.side_effect = OSError('resolve failed')
            ov_path.__str__.return_value = str(tmp_path / 'overrides')
            mock_od.return_value = ov_path
            result = _recipe_search_dirs()
        assert isinstance(result, list)

    def test_dir_resolve_exception_uses_str_fallback(self, tmp_path, db):
        """Lines 290-291: if expanded.resolve() raises for a search dir, falls back to str()."""
        from webapp.views.recipes import _recipe_search_dirs
        repo = tmp_path / 'myrepo'
        repo.mkdir()
        prefs = {'RECIPE_SEARCH_DIRS': [str(repo)]}
        with patch('webapp.views.recipes._autopkg_prefs', return_value=prefs), \
             patch('webapp.views.recipes._overrides_dir', return_value=tmp_path / 'overrides'), \
             patch('pathlib.Path.resolve', side_effect=OSError('no resolve')):
            result = _recipe_search_dirs()
        assert isinstance(result, list)

    def test_falls_back_to_repos_root_when_no_search_dirs(self, tmp_path, db):
        from webapp.views.recipes import _recipe_search_dirs
        from webapp.models import Setting

        repos_root = tmp_path / 'RecipeRepos'
        repos_root.mkdir()
        (repos_root / 'myrepo').mkdir()
        Setting.set('autopkg.recipe_repos_dir', str(repos_root))
        Setting.set('autopkg.overrides_dir', str(tmp_path / 'overrides'))

        with patch('webapp.views.recipes._autopkg_prefs', return_value={}):
            result = _recipe_search_dirs()

        assert any('myrepo' in d for d in result)


# --- RecipeCacheResetView ---------------------------------------------------

@pytest.mark.django_db
class TestRecipeCacheResetView:
    url = '/recipes/list/cache-reset/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self.url)
        assert resp.status_code == 302

    def test_post_returns_204(self, config_editor_client):
        resp = config_editor_client.post(self.url)
        assert resp.status_code == 204


# --- OverrideDeleteView -----------------------------------------------------

@pytest.mark.django_db
class TestOverrideDeleteView:
    def _url(self, fname):
        return f'/recipes/overrides/{fname}/delete/'

    def test_requires_login(self, anon_client):
        resp = anon_client.post(self._url('Firefox.recipe'))
        assert resp.status_code == 302

    def test_deletes_existing_override(self, config_editor_client, tmp_path):
        from webapp.models import Setting
        Setting.set('autopkg.overrides_dir', str(tmp_path))
        override_file = tmp_path / 'Firefox.recipe'
        override_file.write_text('<plist/>')

        with patch('webapp.views.recipes._overrides_dir', return_value=tmp_path):
            resp = config_editor_client.post(self._url('Firefox.recipe'))
        assert resp.status_code == 302
        assert not override_file.exists()

    def test_missing_file_redirects(self, config_editor_client, tmp_path):
        with patch('webapp.views.recipes._overrides_dir', return_value=tmp_path):
            resp = config_editor_client.post(self._url('Nonexistent.recipe'))
        assert resp.status_code == 302

    def test_unsafe_path_redirects(self, config_editor_client, tmp_path):
        with patch('webapp.views.recipes._overrides_dir', return_value=tmp_path):
            resp = config_editor_client.post(self._url('../evil.recipe'))
        assert resp.status_code == 302


# --- _start_cache_build / _build thread ----------------------------------------

@pytest.mark.real_cache_build
@pytest.mark.django_db
class TestStartCacheBuild:
    def test_build_thread_runs_and_populates_cache(self, tmp_path):
        """Lines 368-422: extract the _build() closure via a capturing thread stub,
        then invoke it directly from the test body so coverage.py traces it."""
        from webapp.views import recipes as recipes_mod

        recipe_dir = tmp_path / 'recipes'
        recipe_dir.mkdir()
        (recipe_dir / 'Firefox.munki.recipe').write_text(
            '<?xml version="1.0"?>\n'
            '<plist><dict>'
            '<key>Identifier</key><string>com.example.Firefox</string>'
            '</dict></plist>'
        )

        original_cache = dict(recipes_mod._RECIPES_CACHE)
        original_building = recipes_mod._RECIPES_BUILDING
        recipes_mod._RECIPES_CACHE['data'] = None
        recipes_mod._RECIPES_CACHE['ts'] = 0.0
        recipes_mod._RECIPES_BUILDING = False

        captured = {}

        class CapturingThread:
            def __init__(self, target, **kw):
                captured['fn'] = target
            def start(self):
                pass  # do not start a real thread

        build_result = {}
        try:
            with patch('webapp.views.recipes._recipe_search_dirs', return_value=[str(recipe_dir)]), \
                 patch('webapp.views.recipes._overrides_dir', return_value=tmp_path / 'overrides'), \
                 patch('webapp.views.recipes.threading.Thread', CapturingThread):
                recipes_mod._start_cache_build()

            # Call _build directly in the test body so coverage.py can trace it.
            assert 'fn' in captured, '_start_cache_build did not create a thread'
            with patch('webapp.views.recipes._recipe_search_dirs', return_value=[str(recipe_dir)]), \
                 patch('webapp.views.recipes._overrides_dir', return_value=tmp_path / 'overrides'):
                captured['fn']()
            build_result['data'] = recipes_mod._RECIPES_CACHE['data']
        finally:
            recipes_mod._RECIPES_CACHE.update(original_cache)
            recipes_mod._RECIPES_BUILDING = original_building

        assert build_result.get('data') is not None

    def test_build_skips_when_cache_is_ready(self):
        """Line 360: _start_cache_build returns early when cache is warm."""
        from webapp.views import recipes as recipes_mod
        original_cache = dict(recipes_mod._RECIPES_CACHE)
        original_building = recipes_mod._RECIPES_BUILDING
        try:
            recipes_mod._RECIPES_CACHE['data'] = [{'stem': 'X', 'identifier': 'com.x'}]
            recipes_mod._RECIPES_CACHE['ts'] = time.monotonic()
            recipes_mod._RECIPES_BUILDING = False
            captured = {}
            class CapturingThread:
                def __init__(self, target, **kw):
                    captured['fn'] = target
                def start(self):
                    pass
            with patch('webapp.views.recipes.threading.Thread', CapturingThread):
                recipes_mod._start_cache_build()
        finally:
            recipes_mod._RECIPES_CACHE.update(original_cache)
            recipes_mod._RECIPES_BUILDING = original_building
        assert 'fn' not in captured  # did not launch a thread

    def test_build_nonexistent_dir_is_skipped(self, tmp_path):
        """Line 377: _build() skips search dirs that don't exist on disk."""
        from webapp.views import recipes as recipes_mod
        original_cache = dict(recipes_mod._RECIPES_CACHE)
        original_building = recipes_mod._RECIPES_BUILDING
        recipes_mod._RECIPES_CACHE['data'] = None
        recipes_mod._RECIPES_CACHE['ts'] = 0.0
        recipes_mod._RECIPES_BUILDING = False
        captured = {}

        class CapturingThread:
            def __init__(self, target, **kw):
                captured['fn'] = target
            def start(self):
                pass

        nonexistent = str(tmp_path / 'does_not_exist')
        try:
            with patch('webapp.views.recipes._recipe_search_dirs', return_value=[nonexistent]), \
                 patch('webapp.views.recipes._overrides_dir', return_value=tmp_path / 'ov'), \
                 patch('webapp.views.recipes.threading.Thread', CapturingThread):
                recipes_mod._start_cache_build()
            assert 'fn' in captured
            with patch('webapp.views.recipes._recipe_search_dirs', return_value=[nonexistent]), \
                 patch('webapp.views.recipes._overrides_dir', return_value=tmp_path / 'ov'):
                captured['fn']()
        finally:
            recipes_mod._RECIPES_CACHE.update(original_cache)
            recipes_mod._RECIPES_BUILDING = original_building

    def test_build_recipe_info_exception_uses_fallback(self, tmp_path):
        """Lines 397-398: exception from ThreadPoolExecutor future falls back to stem."""
        from webapp.views import recipes as recipes_mod
        recipe_dir = tmp_path / 'recipes'
        recipe_dir.mkdir()
        (recipe_dir / 'Bad.munki.recipe').write_text('not valid xml')
        original_cache = dict(recipes_mod._RECIPES_CACHE)
        original_building = recipes_mod._RECIPES_BUILDING
        recipes_mod._RECIPES_CACHE['data'] = None
        recipes_mod._RECIPES_CACHE['ts'] = 0.0
        recipes_mod._RECIPES_BUILDING = False
        captured = {}

        class CapturingThread:
            def __init__(self, target, **kw):
                captured['fn'] = target
            def start(self):
                pass

        try:
            with patch('webapp.views.recipes._recipe_search_dirs', return_value=[str(recipe_dir)]), \
                 patch('webapp.views.recipes._overrides_dir', return_value=tmp_path / 'ov'), \
                 patch('webapp.views.recipes._read_recipe_info', side_effect=RuntimeError('parse error')), \
                 patch('webapp.views.recipes.threading.Thread', CapturingThread):
                recipes_mod._start_cache_build()
            assert 'fn' in captured
            with patch('webapp.views.recipes._recipe_search_dirs', return_value=[str(recipe_dir)]), \
                 patch('webapp.views.recipes._overrides_dir', return_value=tmp_path / 'ov'), \
                 patch('webapp.views.recipes._read_recipe_info', side_effect=RuntimeError('parse error')):
                captured['fn']()
        finally:
            recipes_mod._RECIPES_CACHE.update(original_cache)
            recipes_mod._RECIPES_BUILDING = original_building

    def test_build_outer_exception_sets_building_false(self, tmp_path):
        """Lines 411-412: exception during scan is caught; building flag is cleared."""
        from webapp.views import recipes as recipes_mod
        original_cache = dict(recipes_mod._RECIPES_CACHE)
        original_building = recipes_mod._RECIPES_BUILDING
        recipes_mod._RECIPES_CACHE['data'] = None
        recipes_mod._RECIPES_CACHE['ts'] = 0.0
        recipes_mod._RECIPES_BUILDING = False
        captured = {}

        class CapturingThread:
            def __init__(self, target, **kw):
                captured['fn'] = target
            def start(self):
                pass

        try:
            with patch('webapp.views.recipes._recipe_search_dirs', side_effect=RuntimeError('boom')), \
                 patch('webapp.views.recipes._overrides_dir', return_value=tmp_path / 'ov'), \
                 patch('webapp.views.recipes.threading.Thread', CapturingThread):
                recipes_mod._start_cache_build()
            assert 'fn' in captured
            with patch('webapp.views.recipes._recipe_search_dirs', side_effect=RuntimeError('boom')), \
                 patch('webapp.views.recipes._overrides_dir', return_value=tmp_path / 'ov'):
                captured['fn']()
        finally:
            recipes_mod._RECIPES_CACHE.update(original_cache)
            recipes_mod._RECIPES_BUILDING = original_building

        assert not recipes_mod._RECIPES_BUILDING  # finally block cleared it

    def test_build_close_connections_exception_is_swallowed(self, tmp_path):
        """Lines 421-422: exception from close_old_connections is swallowed."""
        from webapp.views import recipes as recipes_mod
        original_cache = dict(recipes_mod._RECIPES_CACHE)
        original_building = recipes_mod._RECIPES_BUILDING
        recipes_mod._RECIPES_CACHE['data'] = None
        recipes_mod._RECIPES_CACHE['ts'] = 0.0
        recipes_mod._RECIPES_BUILDING = False
        captured = {}

        class CapturingThread:
            def __init__(self, target, **kw):
                captured['fn'] = target
            def start(self):
                pass

        try:
            with patch('webapp.views.recipes._recipe_search_dirs', return_value=[]), \
                 patch('webapp.views.recipes._overrides_dir', return_value=tmp_path / 'ov'), \
                 patch('webapp.views.recipes.threading.Thread', CapturingThread):
                recipes_mod._start_cache_build()
            assert 'fn' in captured
            with patch('webapp.views.recipes._recipe_search_dirs', return_value=[]), \
                 patch('webapp.views.recipes._overrides_dir', return_value=tmp_path / 'ov'), \
                 patch('django.db.close_old_connections', side_effect=RuntimeError('db gone')):
                captured['fn']()  # should not raise despite the error
        finally:
            recipes_mod._RECIPES_CACHE.update(original_cache)
            recipes_mod._RECIPES_BUILDING = original_building


# --- _build_recipe_entries with parent lookups --------------------------------

class TestBuildRecipeEntriesParentLookups:
    def _make_override_file(self, directory, stem, identifier, parent=None):
        content = (
            '<?xml version="1.0"?>\n<plist><dict>'
            f'<key>Identifier</key><string>{identifier}</string>'
        )
        if parent:
            content += f'<key>ParentRecipe</key><string>{parent}</string>'
        content += '</dict></plist>'
        path = directory / f'{stem}.recipe'
        path.write_text(content)
        return path

    def test_override_targets_scanned_parent(self, tmp_path):
        """Lines 525-527: override with ParentRecipe matching a scanned parent gets emitted."""
        from webapp.views.recipes import _build_recipe_entries

        overrides_dir = tmp_path / 'overrides'
        overrides_dir.mkdir()
        self._make_override_file(
            overrides_dir, 'Firefox-Override',
            'com.example.Override', parent='com.example.Firefox.munki',
        )

        parent_recipes = [
            {'stem': 'Firefox.munki', 'identifier': 'com.example.Firefox.munki', 'parent': None},
        ]

        with patch('webapp.views.recipes._list_parent_recipes', return_value=parent_recipes), \
             patch('webapp.views.recipes._overrides_dir', return_value=overrides_dir), \
             patch('webapp.views.recipes._read_run_list', return_value=[]):
            entries, _, _ = _build_recipe_entries(set())

        override_entries = [e for e in entries if e['is_override']]
        assert any(e['identifier'] == 'com.example.Override' for e in override_entries)

    def test_orphan_override_with_scanned_parent(self, tmp_path):
        """Line 483: orphan override where parent IS in all_scanned_identifiers → uses parent's own parent."""
        from webapp.views.recipes import _build_recipe_entries

        overrides_dir = tmp_path / 'overrides'
        overrides_dir.mkdir()
        # Override has a parent that IS scanned, so effective_parent = that parent's own parent
        self._make_override_file(
            overrides_dir, 'Chrome-Custom',
            'com.example.Chrome.Custom', parent='com.example.Chrome',
        )

        # Chrome IS in scanned list, and Chrome's own parent is 'com.example.download.Chrome'
        parent_recipes = [
            {'stem': 'Chrome.munki', 'identifier': 'com.example.Chrome', 'parent': 'com.example.download.Chrome'},
        ]

        with patch('webapp.views.recipes._list_parent_recipes', return_value=parent_recipes), \
             patch('webapp.views.recipes._overrides_dir', return_value=overrides_dir), \
             patch('webapp.views.recipes._read_run_list', return_value=[]):
            entries, _, _ = _build_recipe_entries(set())

        # Chrome-Custom should be an orphan override with effective_parent derived from Chrome's parent
        all_ids = {e['identifier'] for e in entries}
        assert 'com.example.Chrome.Custom' in all_ids
