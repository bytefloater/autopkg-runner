"""AutoPkg recipe index cache.

Fetches https://raw.githubusercontent.com/autopkg/index/main/index.json
once per hour and caches the result in memory.  All public functions are
thread-safe and never block the caller — the fetch happens in a daemon thread.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional
import urllib.request
import urllib.error
import json

from notifiers._ssl import ssl_context

logger = logging.getLogger('autopkg_runner')

_INDEX_URL = 'https://raw.githubusercontent.com/autopkg/index/main/index.json'
_FETCH_TIMEOUT = 30   # seconds for the HTTP request
_CACHE_TTL = 3600     # 1 hour

_cache_lock = threading.Lock()
_cache: dict = {
    'identifiers': {},   # identifier → {name, path, repo, parent?, app_display_name?}
    'shortnames':  {},   # shortname  → [identifier, ...]
    'fetched_at': 0.0,
    'error': None,
    'building': False,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_ready() -> bool:
    """Return True when the cache holds data (even if stale)."""
    return bool(_cache['identifiers'])


def is_stale() -> bool:
    now = time.monotonic()
    return (now - _cache['fetched_at']) >= _CACHE_TTL


def last_error() -> Optional[str]:
    return _cache['error']


def search(query: str, page: int = 1, page_size: int = 50) -> dict:
    """Search the in-memory index.

    Returns a dict with keys:
        results   – list of entry dicts for this page
        total     – total matching entries (before pagination)
        page      – current page number (1-based)
        page_size – entries per page
        pages     – total number of pages
    """
    q = query.strip().lower()
    identifiers = _cache['identifiers']

    if q:
        hits = [
            _enrich(ident, entry)
            for ident, entry in identifiers.items()
            if (
                q in ident.lower()
                or q in (entry.get('name') or '').lower()
                or q in (entry.get('app_display_name') or '').lower()
                or q in (entry.get('repo') or '').lower()
                or q in (entry.get('path') or '').lower()
            )
        ]
    else:
        hits = [_enrich(ident, entry) for ident, entry in identifiers.items()]

    hits.sort(key=lambda e: e['identifier'].lower())
    total = len(hits)
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, pages))
    start = (page - 1) * page_size
    return {
        'results': hits[start:start + page_size],
        'total': total,
        'page': page,
        'page_size': page_size,
        'pages': pages,
    }


def get_entry(identifier: str) -> Optional[dict]:
    """Return a single enriched entry by identifier, or None."""
    entry = _cache['identifiers'].get(identifier)
    if entry is None:
        return None
    return _enrich(identifier, entry)


def repo_url(repo_slug: str) -> str:
    """Convert an 'org/name' slug to a GitHub URL."""
    return f'https://github.com/{repo_slug}'


def recipe_github_url(repo_slug: str, path: str) -> str:
    """Construct a direct GitHub URL to view a recipe file."""
    return f'https://github.com/{repo_slug}/blob/HEAD/{path}'


def resolve_repo_requirements(identifier: str) -> list[str]:
    """Walk the parent chain for *identifier* and return the set of distinct
    GitHub repo slugs needed to satisfy it (including its own repo).

    The walk is depth-limited to avoid infinite loops on malformed data.
    """
    identifiers = _cache['identifiers']
    repos: list[str] = []
    seen: set[str] = set()
    current = identifier
    depth = 0
    while current and depth < 20:
        entry = identifiers.get(current)
        if entry is None:
            break
        slug = entry.get('repo', '')
        if slug and slug not in seen:
            seen.add(slug)
            repos.append(slug)
        parent = entry.get('parent')
        if parent == current:
            break
        current = parent
        depth += 1
    return repos


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def ensure_fresh(force: bool = False):
    """Start a background fetch if the cache is missing or stale.

    Safe to call from any thread / request handler.
    """
    with _cache_lock:
        if _cache['building']:
            return
        if not force and is_ready() and not is_stale():
            return
        _cache['building'] = True

    threading.Thread(target=_fetch, daemon=True, name='recipe-index-fetch').start()


def _fetch():
    try:
        from __info__ import APP_VERSION_STR
        logger.info('Fetching AutoPkg recipe index from %s', _INDEX_URL)
        req = urllib.request.Request(
            _INDEX_URL,
            headers={
                'Accept': 'application/json',
                'User-Agent': f'autopkg-runner/{APP_VERSION_STR}',
            },
        )
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT, context=ssl_context()) as resp:
            raw = resp.read()
        data = json.loads(raw)
        identifiers = data.get('identifiers', {})
        shortnames = data.get('shortnames', {})
        with _cache_lock:
            _cache['identifiers'] = identifiers
            _cache['shortnames'] = shortnames
            _cache['fetched_at'] = time.monotonic()
            _cache['error'] = None
        logger.info('Recipe index fetched: %d identifiers', len(identifiers))
    except urllib.error.HTTPError as exc:
        error_msg = f'HTTP {exc.code}: {exc.reason}'
        try:
            error_body = exc.read().decode('utf-8', errors='replace')[:500]
            if error_body:
                error_msg += f' — {error_body}'
        except Exception:
            pass
        with _cache_lock:
            _cache['error'] = error_msg
        logger.warning('Failed to fetch recipe index: %s', error_msg)
    except Exception as exc:
        with _cache_lock:
            _cache['error'] = str(exc)
        logger.warning('Failed to fetch recipe index: %s', exc)
    finally:
        with _cache_lock:
            _cache['building'] = False
        try:
            from django.db import close_old_connections
            close_old_connections()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enrich(identifier: str, entry: dict) -> dict:
    """Return a flat dict suitable for JSON serialisation to the frontend."""
    repo = entry.get('repo', '')
    path = entry.get('path', '')
    return {
        'identifier': identifier,
        'name': entry.get('name') or entry.get('app_display_name') or '',
        'app_display_name': entry.get('app_display_name') or '',
        'repo': repo,
        'path': path,
        'parent': entry.get('parent') or '',
        'repo_url': repo_url(repo) if repo else '',
        'recipe_url': recipe_github_url(repo, path) if repo and path else '',
    }
