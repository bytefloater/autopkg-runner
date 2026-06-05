"""
Views for the Recipes section.

Covers:
  - Repository management  (/recipes/repos/)
  - Unified recipe list    (/recipes/list/)
  - Override editor        (/recipes/overrides/<fname>/edit/)
"""
import json
import plistlib
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.views.generic import TemplateView, View


# -- Shared helpers ------------------------------------------------------------

_SUBTABS = [
    {'name': 'repos', 't_key': 'SUBTAB_REPOS',    'url_name': 'recipes-repos'},
    {'name': 'list',  't_key': 'SUBTAB_RECIPES',  'url_name': 'recipes-list'},
]


def _autopkg() -> str:
    from webapp.models import Setting
    return Setting.get('autopkg.path', '/usr/local/bin/autopkg')


def _recipe_list_path() -> Path:
    from webapp.models import Setting
    raw = Setting.get(
        'autopkg.recipe_list',
        '~/Library/Application Support/AutoPkgr/recipe_list.txt',
    )
    return Path(raw).expanduser()


def _overrides_dir() -> Path:
    return Path('~/Library/AutoPkg/RecipeOverrides').expanduser()


def _read_run_list() -> list:
    p = _recipe_list_path()
    if not p.exists():
        return []
    return [
        line.strip()
        for line in p.read_text().splitlines()
        if line.strip() and not line.startswith('#')
    ]


def _write_run_list(recipe_ids: list):
    p = _recipe_list_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('\n'.join(recipe_ids) + '\n')


def _safe_override_path(fname: str) -> Path:
    """Resolve an override filename and verify it stays inside the overrides dir.

    Raises ValueError if the path would escape the overrides directory.
    """
    base = _overrides_dir().resolve()
    target = (base / fname).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError(f"Unsafe override path: {fname!r}")
    return target


def _git_behind_count(repo_path: str) -> int:
    """Return how many commits the local branch is behind its upstream.

    Returns -1 if git status cannot be determined (no upstream, not a git repo, etc.).
    This check is local-only - no network call.
    """
    try:
        r = subprocess.run(
            ['git', '-C', repo_path, 'rev-list', '--count', 'HEAD..@{u}'],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return int(r.stdout.strip() or '0')
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return -1


def _list_repos() -> list:
    """Run ``autopkg repo-list`` and return a list of dicts with path/url/behind."""
    try:
        r = subprocess.run(
            [_autopkg(), 'repo-list'],
            capture_output=True, text=True, timeout=30,
        )
        output = r.stdout if r.returncode == 0 else ''
    except (subprocess.TimeoutExpired, FileNotFoundError):
        output = ''

    repos = []
    for line in output.splitlines():
        line = line.strip()
        m = re.match(r'^(.*?)\s+\(([^)]+)\)$', line)
        if m:
            path, url = m.group(1).strip(), m.group(2).strip()
            repos.append({'path': path, 'url': url, 'behind': _git_behind_count(path)})
    return repos


# -- Repository views ----------------------------------------------------------

class ReposView(LoginRequiredMixin, TemplateView):
    template_name = 'webapp/recipes/repos.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab']     = 'recipes'
        ctx['recipes_subtab'] = 'repos'
        ctx['recipes_subtabs'] = _SUBTABS
        ctx['repos']          = _list_repos()
        return ctx


class RepoAddView(LoginRequiredMixin, View):
    def post(self, request):
        url = request.POST.get('url', '').strip()
        if not url:
            messages.error(request, 'Repository URL is required.')
            return redirect('recipes-repos')
        try:
            r = subprocess.run(
                [_autopkg(), 'repo-add', url],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                messages.success(request, f'Repository added: {url}')
                _invalidate_recipe_cache()
            else:
                err = r.stderr.strip() or r.stdout.strip()
                messages.error(request, f'Failed to add repository: {err}')
        except subprocess.TimeoutExpired:
            messages.error(request, 'Timed out while adding repository.')
        except FileNotFoundError:
            messages.error(request, 'autopkg not found. Check the path in Configuration.')
        return redirect('recipes-repos')


class RepoDeleteView(LoginRequiredMixin, View):
    def post(self, request):
        url = request.POST.get('url', '').strip()
        if not url:
            messages.error(request, 'Repository URL is required.')
            return redirect('recipes-repos')
        try:
            r = subprocess.run(
                [_autopkg(), 'repo-delete', url],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0:
                messages.success(request, f'Repository removed: {url}')
                _invalidate_recipe_cache()
            else:
                err = r.stderr.strip() or r.stdout.strip()
                messages.error(request, f'Failed to remove repository: {err}')
        except subprocess.TimeoutExpired:
            messages.error(request, 'Timed out while removing repository.')
        except FileNotFoundError:
            messages.error(request, 'autopkg not found. Check the path in Configuration.')
        return redirect('recipes-repos')


class RepoUpdateView(LoginRequiredMixin, View):
    """HTMX endpoint - runs ``autopkg repo-update`` and returns a refreshed table row."""

    def post(self, request):
        from django.template.loader import render_to_string
        from webapp import translations as _trans
        from webapp.models import Setting

        repo_path = request.POST.get('repo_path', '').strip()
        repo_url  = request.POST.get('repo_url',  '').strip()

        error_msg = None
        if not repo_url:
            error_msg = 'Repository URL is required.'
        else:
            try:
                r = subprocess.run(
                    [_autopkg(), 'repo-update', repo_url],
                    capture_output=True, text=True, timeout=120,
                )
                if r.returncode != 0:
                    err = r.stderr.strip() or r.stdout.strip()
                    error_msg = f'Update failed: {err}'
                else:
                    _invalidate_recipe_cache()
            except subprocess.TimeoutExpired:
                error_msg = 'Timed out while updating repository.'
            except FileNotFoundError:
                error_msg = 'autopkg not found. Check the path in Configuration.'

        behind = _git_behind_count(repo_path) if not error_msg else -1
        repo = {
            'path': repo_path,
            'url':  repo_url,
            'behind': behind,
        }

        lang = Setting.get('ui.language', 'en-US')
        t    = _trans.load(lang)
        html = render_to_string(
            'webapp/partials/repo_row.html',
            {'repo': repo, 't': t, 'error_msg': error_msg},
            request=request,
        )
        return HttpResponse(html)


# -- Recipe list helpers -------------------------------------------------------

def _sort_run_list(identifiers: list) -> list:
    """Sort alphabetically; any MakeCatalogs variant goes last."""
    def _key(ident):
        return (1 if 'makecatalogs' in ident.lower() else 0, ident.lower())
    return sorted(identifiers, key=_key)


def _autopkg_prefs() -> dict:
    """Read autopkg's preference plist (~/.../com.github.autopkg.plist). Returns {} on failure."""
    p = Path('~/Library/Preferences/com.github.autopkg.plist').expanduser()
    if not p.exists():
        return {}
    try:
        with p.open('rb') as fh:
            return plistlib.load(fh)
    except Exception:
        return {}


def _recipe_search_dirs() -> list:
    """Return the directories autopkg searches for recipes.

    Reads RECIPE_SEARCH_DIRS from autopkg preferences, falling back to all
    subdirectories of ~/Library/AutoPkg/RecipeRepos/ if the key is absent.
    """
    prefs = _autopkg_prefs()
    dirs = [d for d in prefs.get('RECIPE_SEARCH_DIRS', []) if d and d != '.']
    if not dirs:
        repos_root = Path('~/Library/AutoPkg/RecipeRepos').expanduser()
        if repos_root.exists():
            dirs = [str(d) for d in repos_root.iterdir() if d.is_dir()]
    return [str(Path(d).expanduser()) for d in dirs]


_IDENT_RE_XML  = re.compile(r'<key>Identifier</key>\s*<string>([^<]+)</string>')
_IDENT_RE_YAML = re.compile(r'^Identifier:\s*([^\s#][^\n]*)', re.MULTILINE)


def _recipe_stem(path: Path) -> str:
    """Return the base name, stripping .recipe or .recipe.yaml suffixes."""
    name = path.name
    if name.endswith('.recipe.yaml'):
        return name[: -len('.recipe.yaml')]
    return path.stem


def _read_recipe_identifier(path: Path) -> str:
    """Extract the Identifier value from a recipe file (XML plist or YAML).

    Falls back to the base stem if the key is absent or the file is unreadable.
    """
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
        pattern = _IDENT_RE_YAML if path.suffix == '.yaml' else _IDENT_RE_XML
        m = pattern.search(text)
        if m:
            return m.group(1).strip()
    except OSError:
        pass
    return _recipe_stem(path)


_RECIPES_CACHE: dict = {'data': None, 'ts': 0.0}
_RECIPES_CACHE_TTL = 300  # seconds - re-scan after 5 minutes
_RECIPES_BUILD_LOCK = threading.Lock()
_RECIPES_BUILDING = False


def _list_parent_recipes() -> list:
    """Return the cached recipe list (never blocks). Returns [] if not ready yet."""
    return _RECIPES_CACHE['data'] or []


def _is_cache_ready() -> bool:
    now = time.monotonic()
    return (_RECIPES_CACHE['data'] is not None
            and (now - _RECIPES_CACHE['ts']) < _RECIPES_CACHE_TTL)


def _start_cache_build():
    """Spawn a background thread to scan recipe files if the cache is cold or stale.

    Safe to call from any request handler - the lock prevents duplicate builds.
    """
    global _RECIPES_BUILDING
    if _is_cache_ready() or _RECIPES_BUILDING:
        return
    with _RECIPES_BUILD_LOCK:
        if _is_cache_ready() or _RECIPES_BUILDING:
            return
        _RECIPES_BUILDING = True

    def _build():
        global _RECIPES_BUILDING
        try:
            # Phase 1 - collect unique recipe file paths (sequential; deduplicates stems).
            # Scans both .recipe (XML plist) and .recipe.yaml (YAML) formats.
            # XML is preferred over YAML when both exist for the same base stem.
            all_files: list = []
            seen_stems: set = set()
            for search_dir in _recipe_search_dirs():
                p = Path(search_dir)
                if not p.is_dir():
                    continue
                for pattern in ('*.recipe', '*.recipe.yaml'):
                    for recipe_file in p.rglob(pattern):
                        stem = _recipe_stem(recipe_file)
                        if stem not in seen_stems:
                            seen_stems.add(stem)
                            all_files.append(recipe_file)

            # Phase 2 - read Identifier from each file in parallel
            stem_to_ident: dict = {}
            workers = min(16, max(1, len(all_files)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_map = {pool.submit(_read_recipe_identifier, f): f
                              for f in all_files}
                for fut in as_completed(future_map):
                    f = future_map[fut]
                    stem = _recipe_stem(f)
                    try:
                        ident = fut.result()
                    except Exception:
                        ident = stem
                    stem_to_ident[stem] = ident

            results = [{'stem': s, 'identifier': i}
                       for s, i in stem_to_ident.items()]
            results.sort(key=lambda r: r['stem'].lower())
            _RECIPES_CACHE['data'] = results
            _RECIPES_CACHE['ts'] = time.monotonic()
        finally:
            _RECIPES_BUILDING = False

    threading.Thread(target=_build, daemon=True, name='recipe-cache-build').start()


def _invalidate_recipe_cache():
    """Bust the recipe list cache and trigger a background rebuild."""
    _RECIPES_CACHE['ts'] = 0.0
    _start_cache_build()


def _build_recipe_entries(run_list_set: set) -> tuple:
    """Return (entries, load_error).

    Each entry is a dict:
        identifier    – run-list identifier
                        (XML Identifier for overrides; file stem for parents)
        name          – short display name including type suffix, e.g. "Firefox.munki"
        is_override   – True when sourced from the overrides directory
        override_fname – filename in overrides dir (or None)
        in_run_list   – True when currently in the run list
    """
    # Collect overrides: stem → {'fname', 'identifier'}
    # We read the XML Identifier from each override file (few in number, fast regex).
    override_map: dict = {}
    od = _overrides_dir()
    if od.exists():
        for f in od.glob('*.recipe'):
            ov_id = _read_recipe_identifier(f)
            override_map[f.stem] = {'fname': f.name, 'identifier': ov_id}

    # Collect parent recipes by globbing + reading Identifier from each file (cached)
    load_error = False
    parent_recipes = _list_parent_recipes()  # list of {'stem', 'identifier'}

    # Build unified map keyed by stem.
    # Override file stems match parent stems → deduplication aligns naturally.
    # Each logical recipe appears once: override row supersedes parent row.
    entries_by_key: dict = {}

    for recipe in parent_recipes:
        stem = recipe['stem']
        parent_id = recipe['identifier']
        o_info = override_map.get(stem)
        if o_info:
            ov_id = o_info['identifier']
            entries_by_key[stem] = {
                'identifier':    ov_id,
                'name':          stem,
                'is_override':   True,
                'override_fname': o_info['fname'],
                'in_run_list':   ov_id in run_list_set,
            }
        else:
            entries_by_key[stem] = {
                'identifier':    parent_id,
                'name':          stem,
                'is_override':   False,
                'override_fname': None,
                'in_run_list':   parent_id in run_list_set,
            }

    # Orphan overrides - no matching parent stem found in the search dirs
    for stem, o_info in override_map.items():
        if stem not in entries_by_key:
            ov_id = o_info['identifier']
            entries_by_key[stem] = {
                'identifier':    ov_id,
                'name':          stem,
                'is_override':   True,
                'override_fname': o_info['fname'],
                'in_run_list':   ov_id in run_list_set,
            }

    entries = sorted(entries_by_key.values(), key=lambda e: e['name'].lower())

    # Identifiers that are in the run list but have no matching recipe file.
    all_known_identifiers = {e['identifier'] for e in entries_by_key.values()}
    orphaned = sorted(run_list_set - all_known_identifiers)

    return entries, load_error, orphaned


# -- Recipe list views ---------------------------------------------------------

class RecipeListView(LoginRequiredMixin, TemplateView):
    """Renders the page shell immediately; recipe data is fetched asynchronously."""

    template_name = 'webapp/recipes/recipe_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab']      = 'recipes'
        ctx['recipes_subtab']  = 'list'
        ctx['recipes_subtabs'] = _SUBTABS
        _start_cache_build()  # kick off background scan if not already running
        return ctx

    def post(self, request):
        selected = request.POST.getlist('selected')
        _write_run_list(_sort_run_list(selected))
        messages.success(request, 'Run list saved.')
        return redirect('recipes-list')


class RecipeDataView(LoginRequiredMixin, View):
    """JSON endpoint polled by the recipe list page.

    Returns HTTP 202 while the background cache build is running so the server
    thread is never blocked waiting for file I/O.  The client polls until 200.
    """

    def get(self, request):
        _start_cache_build()  # no-op if already running or cache is fresh
        if not _is_cache_ready():
            return JsonResponse({'building': True}, status=202)
        run_list_set = set(_read_run_list())
        entries, load_error, orphaned = _build_recipe_entries(run_list_set)
        return JsonResponse({
            'recipes': entries,
            'load_error': load_error,
            'orphaned_run_list': orphaned,
        })


# -- Override views ------------------------------------------------------------

class OverrideCreateView(LoginRequiredMixin, View):
    def post(self, request):
        identifier = request.POST.get('identifier', '').strip()
        if not identifier:
            messages.error(request, 'Recipe identifier is required.')
            return redirect('recipes-list')
        try:
            r = subprocess.run(
                [_autopkg(), 'make-override', identifier],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                err = r.stderr.strip() or r.stdout.strip()
                messages.error(request, f'Could not create override: {err}')
                return redirect('recipes-list')
        except subprocess.TimeoutExpired:
            messages.error(request, 'Timed out while creating override.')
            return redirect('recipes-list')
        except FileNotFoundError:
            messages.error(request, 'autopkg not found. Check the path in Configuration.')
            return redirect('recipes-list')

        # Find the newly created file and open the editor
        od = _overrides_dir()
        stem = Path(identifier).stem
        candidates = list(od.glob(f'{stem}*.recipe'))
        if candidates:
            exact = [c for c in candidates if c.stem == stem]
            chosen = exact[0] if exact else candidates[0]
            return redirect('recipes-override-edit', fname=chosen.name)

        messages.success(request, f'Override created for {identifier}.')
        return redirect('recipes-list')


class OverrideEditView(LoginRequiredMixin, View):
    template_name = 'webapp/recipes/override_editor.html'

    def _get_path(self, fname: str) -> Path:
        try:
            return _safe_override_path(fname)
        except ValueError:
            return None

    def _ctx(self, fname, content, error=None):
        return {
            'active_tab':      'recipes',
            'recipes_subtab':  'list',
            'recipes_subtabs': _SUBTABS,
            'fname':   fname,
            'content': content,
            'error':   error,
        }

    def get(self, request, fname: str):
        path = self._get_path(fname)
        if path is None or not path.exists():
            messages.error(request, 'Override file not found.')
            return redirect('recipes-list')
        return TemplateResponse(request, self.template_name,
                                self._ctx(fname, path.read_text()))

    def post(self, request, fname: str):
        path = self._get_path(fname)
        if path is None:
            messages.error(request, 'Invalid override path.')
            return redirect('recipes-list')
        content = request.POST.get('content', '')
        try:
            ET.fromstring(content)
        except ET.ParseError as exc:
            return TemplateResponse(request, self.template_name,
                                    self._ctx(fname, content,
                                              error=f'XML parse error: {exc}'))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        messages.success(request, f'{fname} saved.')
        return redirect('recipes-override-edit', fname=fname)
