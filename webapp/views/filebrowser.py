"""
File-system browser API views.

Used by the path-picker UI to let admins navigate directories and create
folders without leaving the browser.  Both endpoints require authentication.
"""
import json
import logging
from pathlib import Path

from django.contrib.auth.mixins import LoginRequiredMixin
from webapp.perms import ConfigEditorRequired
from django.http import JsonResponse
from django.views import View

logger = logging.getLogger('autopkg_runner')


def _resolve(raw: str) -> Path:
    """Expand ~ and resolve to an absolute Path."""
    return Path(raw or '~').expanduser().resolve()


class BrowseView(ConfigEditorRequired, View):
    """GET /api/browse/?path=<path>

    Returns a directory listing for *path*.  If *path* is a file, its parent
    is listed instead.  Hidden entries (names starting with ``'.'``) are
    omitted.

    Response JSON::

        {
            "path":    "/absolute/resolved/path",
            "parent":  "/absolute/parent"  | null,
            "entries": [{"name": "foo", "is_dir": true}, ...]
        }
    """

    def get(self, request):
        raw = request.GET.get('path', '~')
        try:
            p = _resolve(raw)
            if not p.is_dir():
                p = p.parent

            entries = []
            for child in sorted(p.iterdir(),
                                key=lambda c: (not c.is_dir(), c.name.lower())):
                if child.name.startswith('.'):
                    continue
                entries.append({'name': child.name, 'is_dir': child.is_dir()})

            parent = str(p.parent) if p != p.parent else None
            return JsonResponse({'path': str(p), 'parent': parent, 'entries': entries})
        except PermissionError as exc:
            logger.debug('File browser permission error: %s', exc)
            return JsonResponse({
                'error':        'Permission denied.',
                'error_code':   f'Permission Denied (errno {exc.errno})' if exc.errno else 'Permission Denied',
                'error_detail': 'You do not have permission to read this directory.',
            }, status=403)
        except OSError as exc:
            logger.debug('File browser OS error: %s', exc)
            return JsonResponse({
                'error':        'Could not read directory.',
                'error_code':   f'Error {exc.errno}' if exc.errno else 'Error',
                'error_detail': exc.strerror or 'An unexpected error occurred.',
            }, status=400)


class MkdirView(ConfigEditorRequired, View):
    """POST /api/browse/mkdir/

    Request body (JSON)::

        {"path": "/absolute/or/tilde/path/new-folder"}

    Creates *path* (including parents) and responds with the resolved path.

    Response JSON::

        {"path": "/absolute/resolved/new-folder"}
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

        raw = (data.get('path') or '').strip()
        if not raw:
            return JsonResponse({'error': 'path is required.'}, status=400)

        try:
            p = _resolve(raw)
            p.mkdir(parents=True, exist_ok=True)
            return JsonResponse({'path': str(p)})
        except PermissionError:
            return JsonResponse({'error': 'Permission denied.'}, status=403)
        except OSError as exc:
            logger.debug('File browser mkdir error: %s', exc)
            return JsonResponse({'error': 'Could not create directory.'}, status=400)
