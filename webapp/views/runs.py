import os
import plistlib
import ssl
import threading
import time
import urllib.request

import certifi
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import close_old_connections
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse


class _AsyncStreamingHttpResponse(StreamingHttpResponse):
    """Work around a Django 4.2 bug where StreamingHttpResponse.streaming_content
    synchronously consumes async generators via async_to_sync even when is_async=True,
    causing a spurious warning and defeating the async streaming.  Overriding
    __aiter__ to iterate _iterator directly bypasses the broken getter."""

    async def __aiter__(self):
        async for chunk in self._iterator:
            yield self.make_bytes(chunk)
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

_MUNKI_CATALOG_CACHE: dict = {'data': None, 'url': '', 'auth': '', 'catalog': '', 'ts': 0.0}

# Limit concurrent icon proxy requests to prevent exhausting the sync thread pool
# that Django uses for non-async views under ASGI.
_ICON_PROXY_SEMAPHORE = threading.Semaphore(3)


def _make_auth_header(username: str, password: str) -> str:
    if not username:
        return ''
    import base64
    creds = base64.b64encode(f'{username}:{password}'.encode()).decode()
    return f'Basic {creds}'


def _fetch_munki_catalog(public_url: str, catalog: str = 'all', auth_header: str = '') -> dict[str, str]:
    """Return {name: icon_path} from <public_url>/catalogs/<catalog>. Empty on error."""
    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        url = public_url.rstrip('/') + '/catalogs/' + catalog
        headers = {'Authorization': auth_header} if auth_header else {}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            raw = r.read()
        items = plistlib.loads(raw)
        result = {}
        for item in items:
            name = item.get('name', '')
            raw_icon = item.get('icon_name')
            if raw_icon:
                icon_name = raw_icon if os.path.splitext(raw_icon)[1] else raw_icon + '.png'
            else:
                icon_name = name + '.png'
            if name:
                result[name] = 'icons/' + icon_name
        return result
    except Exception:
        return {}


def _get_munki_icon_map(public_url: str, catalog: str = 'all', auth_header: str = '') -> dict[str, str]:
    now = time.time()
    if (
        _MUNKI_CATALOG_CACHE['url'] == public_url
        and _MUNKI_CATALOG_CACHE['auth'] == auth_header
        and _MUNKI_CATALOG_CACHE['catalog'] == catalog
        and _MUNKI_CATALOG_CACHE['data'] is not None
        and now - _MUNKI_CATALOG_CACHE['ts'] < 300
    ):
        return _MUNKI_CATALOG_CACHE['data']
    data = _fetch_munki_catalog(public_url, catalog, auth_header)
    _MUNKI_CATALOG_CACHE.update({'data': data, 'url': public_url, 'auth': auth_header, 'catalog': catalog, 'ts': now})
    return data

from webapp.perms import (
    RunAccessRequired, RunManagerRequired,
    perm_required, PERM_VIEW_RUNS, PERM_TRIGGER_RUNS,
)


class RunListView(LoginRequiredMixin, TemplateView):
    template_name = 'webapp/runs/list.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/runs/list.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from webapp.models import Run
        ctx['active_tab'] = 'runs'
        qs = Run.objects.order_by('-started_at')
        paginator = Paginator(qs, 25)
        page = self.request.GET.get('page', 1)
        ctx['page_obj'] = paginator.get_page(page)
        return ctx


class RunDetailView(RunAccessRequired, TemplateView):
    template_name = 'webapp/runs/detail.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/runs/detail.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from collections import defaultdict
        from webapp.models import Run
        run = get_object_or_404(Run, id=self.kwargs['run_id'])
        ctx['active_tab'] = 'runs'
        ctx['run'] = run
        ctx['stages'] = run.stage_executions.order_by('order')

        logs_by_stage: dict[str, list] = defaultdict(list)
        last_log_id = 0
        for entry in run.log_entries.order_by('timestamp'):
            logs_by_stage[entry.stage_name or '__general__'].append(entry)
            if entry.id > last_log_id:
                last_log_id = entry.id
        ctx['logs_by_stage'] = dict(logs_by_stage)
        ctx['last_log_id'] = last_log_id

        ctx['results'] = run.recipe_results.all()

        munki_import_rows = {}
        try:
            from webapp.models import Setting
            from django.urls import reverse
            public_url = Setting.get('repository.public_url', '')
            if public_url:
                auth_header = _make_auth_header(
                    Setting.get('repository.public_url_username', ''),
                    Setting.get('repository.public_url_password', ''),
                )
                catalog = 'all'
                for r in ctx['results']:
                    if r.result_type == 'munki_import' and r.data:
                        cats = r.data[0].get('catalogs', [])
                        if isinstance(cats, list) and cats:
                            catalog = cats[0]
                        elif isinstance(cats, str) and cats:
                            catalog = cats
                        break
                icon_map = _get_munki_icon_map(public_url, catalog, auth_header)
                proxy_base = reverse('munki-icon-proxy')
                for result in ctx['results']:
                    if result.result_type == 'munki_import':
                        munki_import_rows[result.pk] = [
                            {
                                **row,
                                'icon_url': f'{proxy_base}?path={icon_map[row["name"]]}' if row.get('name') and icon_map.get(row['name']) else '',
                            }
                            for row in result.data
                        ]
        except Exception:
            pass
        ctx['munki_import_rows'] = munki_import_rows

        return ctx


class TriggerRunView(RunManagerRequired, View):
    def post(self, request):
        from webapp.runner import trigger_manual_run, RunAlreadyRunningError
        try:
            task_id = trigger_manual_run(triggered_by='manual')
        except RunAlreadyRunningError:
            msg = 'A run is already in progress.'
            if request.headers.get('HX-Request'):
                return JsonResponse({'status': 'error', 'message': msg}, status=409)
            from django.contrib import messages
            messages.error(request, msg)
            return redirect('run-list')

        from webapp.models import Task
        task = Task.objects.get(id=task_id)
        run_id = task.run_id

        if request.headers.get('HX-Request'):
            return JsonResponse({'status': 'ok', 'run_id': str(run_id)})
        return redirect('run-detail', run_id=run_id)


class RunDeleteView(RunManagerRequired, View):
    """POST - delete one or more completed runs by UUID.

    Accepts ``run_ids`` as a multi-value POST field (one UUID per value).
    Active runs (pending / running) are silently skipped.
    Share tokens cascade-delete automatically via the FK relationship.
    """

    def post(self, request):
        from webapp.models import Run
        ids = request.POST.getlist('run_ids')
        if ids:
            Run.objects.filter(
                id__in=ids,
            ).exclude(
                status__in=('pending', 'running'),
            ).delete()
        return redirect('run-list')


class RunCancelView(RunManagerRequired, View):
    """POST - cancel a single active (pending or running) run."""

    def post(self, request, run_id):
        from django.utils import timezone
        from webapp.models import Run, StageExecution

        now = timezone.now()
        run = Run.objects.filter(id=run_id, status__in=('pending', 'running')).first()
        if run:
            StageExecution.objects.filter(
                run=run, status__in=('pending', 'running'),
            ).update(status='cancelled', completed_at=now)
            run.status = 'cancelled'
            run.completed_at = now
            run.save(update_fields=['status', 'completed_at'])

        if request.headers.get('HX-Request'):
            from django.http import HttpResponse
            return HttpResponse(status=204)
        return redirect('run-list')


@login_required
def run_status(request, run_id):
    """Lightweight JSON endpoint — returns run status and latest stage statuses.

    Used as an SSE fallback: when the SSE stream closes before the ``complete``
    event is received, the JS polls this once to sync final state.
    """
    from webapp.models import Run, StageExecution
    from webapp.perms import user_has_perm, PERM_VIEW_RUNS, PERM_TRIGGER_RUNS
    if not (user_has_perm(request.user, PERM_VIEW_RUNS) or
            user_has_perm(request.user, PERM_TRIGGER_RUNS)):
        return JsonResponse({}, status=403)
    run = Run.objects.filter(id=run_id).first()
    if not run:
        return JsonResponse({}, status=404)
    stages = {
        s.name: s.status
        for s in StageExecution.objects.filter(run_id=run_id)
    }
    return JsonResponse({'status': run.status, 'stages': stages})


async def run_stream(request, run_id):
    """SSE endpoint — async, fan-out via RunBroadcaster.

    Uses an async generator so each viewer is a cheap coroutine rather than
    a blocked thread.  All DB work is done by the broadcaster's single daemon
    thread, so the database is polled once per second per run regardless of
    how many clients are connected.
    """
    import asyncio
    from asgiref.sync import sync_to_async
    from webapp.run_broadcaster import broadcaster_manager
    from webapp.perms import user_has_perm, PERM_VIEW_RUNS, PERM_TRIGGER_RUNS

    # Inline auth — sync decorators don't compose cleanly with async views.
    # auser() is only available on ASGIRequest; fall back under WSGI dev server.
    # request.user is a SimpleLazyObject that hits the DB — must be evaluated
    # in a thread via sync_to_async to satisfy Django's async safety guard.
    if hasattr(request, 'auser'):
        user = await request.auser()
    else:
        from django.contrib.auth import get_user as _get_user
        user = await sync_to_async(_get_user)(request)
    if not user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    has_perm = await sync_to_async(
        lambda: user_has_perm(user, PERM_VIEW_RUNS) or user_has_perm(user, PERM_TRIGGER_RUNS)
    )()
    if not has_perm:
        return HttpResponse(status=403)

    from webapp.models import Run
    run_exists = await sync_to_async(Run.objects.filter(id=run_id).exists)()
    if not run_exists:
        return HttpResponse(status=404)

    broadcaster = broadcaster_manager.get(run_id)

    # The Last-Event-ID header is sent automatically by EventSource on reconnect.
    try:
        cursor = int(request.META.get('HTTP_LAST_EVENT_ID', -1))
    except (ValueError, TypeError):
        cursor = -1

    async def event_stream():
        nonlocal cursor
        while True:
            frames, done = broadcaster.events_since(cursor)
            for frame in frames:
                yield frame
                cursor += 1
            if done and not frames:
                break
            await asyncio.sleep(0.5)

    response = _AsyncStreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    # Prevent GZipMiddleware from buffering the stream before compressing it —
    # SSE requires each event to be flushed immediately.
    response['Content-Encoding'] = 'identity'
    return response


@login_required
@perm_required(PERM_VIEW_RUNS)
def munki_icon_proxy(request):
    """Proxy Munki repo icon requests server-side so auth headers can be applied."""
    from django.http import HttpResponse
    from webapp.models import Setting

    path = request.GET.get('path', '')
    if not path.startswith('icons/') or '..' in path or '\x00' in path:
        return HttpResponse(status=400)

    public_url = Setting.get('repository.public_url', '').rstrip('/')
    if not public_url:
        return HttpResponse(status=404)

    auth_header = _make_auth_header(
        Setting.get('repository.public_url_username', ''),
        Setting.get('repository.public_url_password', ''),
    )
    if not _ICON_PROXY_SEMAPHORE.acquire(blocking=False):
        return HttpResponse(status=503)

    ctx = ssl.create_default_context(cafile=certifi.where())
    headers = {'Authorization': auth_header} if auth_header else {}
    from urllib.parse import quote
    encoded_path = quote(path, safe='/')
    req = urllib.request.Request(f'{public_url}/{encoded_path}', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=4, context=ctx) as r:
            content_type = r.headers.get('Content-Type', 'image/png')
            data = r.read()
        response = HttpResponse(data, content_type=content_type)
        response['Cache-Control'] = 'public, max-age=3600'
        return response
    except Exception:
        return HttpResponse(status=404)
    finally:
        _ICON_PROXY_SEMAPHORE.release()
