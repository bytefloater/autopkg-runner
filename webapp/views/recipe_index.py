"""Views for the 'Find Recipes' tab."""
from __future__ import annotations

import json
import subprocess

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.generic import TemplateView, View

from webapp.perms import ConfigEditorRequired
from webapp import recipe_index as idx
from webapp.views.recipes import _SUBTABS, _autopkg, _invalidate_recipe_cache, _list_repos


class RecipeIndexView(ConfigEditorRequired, TemplateView):
    template_name = 'webapp/recipes/recipe_index.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'recipes'
        ctx['recipes_subtab'] = 'find'
        ctx['recipes_subtabs'] = _SUBTABS
        idx.ensure_fresh()
        return ctx


class RecipeIndexSearchView(ConfigEditorRequired, View):
    """JSON search endpoint polled by the Find Recipes page.

    GET params:
        q         – search query (empty = return first page)
        page      – 1-based page number (default 1)
        page_size – results per page (default 50, max 200)

    Response when index not yet ready:
        {"building": true}  HTTP 202

    Response when ready:
        {
            "results": [...],   // enriched entry dicts
            "total": int,
            "page": int,
            "pages": int,
            "page_size": int,
            "installed_repos": ["org/repo", ...],
            "error": null | "message"
        }
    """

    def get(self, request):
        idx.ensure_fresh()
        if not idx.is_ready():
            return JsonResponse({'building': True}, status=202)

        q = request.GET.get('q', '').strip()
        try:
            page = max(1, int(request.GET.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = min(200, max(10, int(request.GET.get('page_size', 50))))
        except (ValueError, TypeError):
            page_size = 50

        result = idx.search(q, page=page, page_size=page_size)

        # Annotate with installed repos so the frontend can show status badges
        installed_repos = {r['url'].rstrip('/') for r in _list_repos()}
        # Normalise to 'org/repo' slug format for comparison with index entries
        installed_slugs = set()
        for url in installed_repos:
            # e.g. https://github.com/autopkg/recipes → autopkg/recipes
            for prefix in ('https://github.com/', 'http://github.com/', 'git@github.com:'):
                if url.startswith(prefix):
                    slug = url[len(prefix):].rstrip('.git').rstrip('/')
                    installed_slugs.add(slug)
                    break

        # For each result, check if all parent dependencies are installed
        for recipe in result['results']:
            repos_needed = idx.resolve_repo_requirements(recipe['identifier'])
            recipe['all_deps_installed'] = all(repo in installed_slugs for repo in repos_needed)

        result['installed_repos'] = list(installed_slugs)
        result['error'] = idx.last_error()
        return JsonResponse(result)


class RecipeIndexRepoRequirementsView(ConfigEditorRequired, View):
    """Return the repo slugs required to use an identifier (walks parent chain)."""

    def get(self, request):
        identifier = request.GET.get('identifier', '').strip()
        if not identifier:
            return JsonResponse({'error': 'identifier required'}, status=400)
        repos = idx.resolve_repo_requirements(identifier)
        installed_repos = {r['url'].rstrip('/') for r in _list_repos()}
        installed_slugs = set()
        for url in installed_repos:
            for prefix in ('https://github.com/', 'http://github.com/', 'git@github.com:'):
                if url.startswith(prefix):
                    slug = url[len(prefix):].rstrip('.git').rstrip('/')
                    installed_slugs.add(slug)
                    break
        result = [
            {'repo': r, 'installed': r in installed_slugs, 'url': idx.repo_url(r)}
            for r in repos
        ]
        return JsonResponse({'repos': result})


class RecipeIndexRefreshView(ConfigEditorRequired, View):
    """POST: bust the index cache and trigger a fresh background fetch."""

    def post(self, request):
        idx.ensure_fresh(force=True)
        return JsonResponse({'ok': True})


class RecipeIndexAddRepoView(ConfigEditorRequired, View):
    """POST: add a single repo via autopkg repo-add."""

    def post(self, request):
        repo_slug = request.POST.get('repo', '').strip()
        if not repo_slug:
            return JsonResponse({'error': 'repo slug required'}, status=400)
        url = idx.repo_url(repo_slug)
        try:
            r = subprocess.run(
                [_autopkg(), 'repo-add', url],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                _invalidate_recipe_cache()
                return JsonResponse({'ok': True, 'url': url})
            err = r.stderr.strip() or r.stdout.strip()
            return JsonResponse({'error': f'Failed to add repository: {err}'}, status=400)
        except subprocess.TimeoutExpired:
            return JsonResponse({'error': 'Timed out while adding repository.'}, status=504)
        except FileNotFoundError:
            return JsonResponse(
                {'error': 'autopkg not found. Check the path in Configuration.'}, status=500)
