import time

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import close_old_connections
from django.http import StreamingHttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView


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


class RunDetailView(LoginRequiredMixin, TemplateView):
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

        # Group log entries by stage for the accordion view.
        # Entries with no stage_name go under the '__general__' key.
        logs_by_stage: dict[str, list] = defaultdict(list)
        last_log_id = 0
        for entry in run.log_entries.order_by('timestamp'):
            logs_by_stage[entry.stage_name or '__general__'].append(entry)
            if entry.id > last_log_id:
                last_log_id = entry.id
        ctx['logs_by_stage'] = dict(logs_by_stage)
        ctx['last_log_id'] = last_log_id

        ctx['results'] = run.recipe_results.all()

        return ctx


class TriggerRunView(LoginRequiredMixin, View):
    def post(self, request):
        from webapp.runner import trigger_manual_run, RunAlreadyRunningError
        try:
            task_id = trigger_manual_run(triggered_by='manual')
        except RunAlreadyRunningError as exc:
            if request.headers.get('HX-Request'):
                return JsonResponse({'status': 'error', 'message': str(exc)}, status=409)
            from django.contrib import messages
            messages.error(request, str(exc))
            return redirect('run-list')

        from webapp.models import Task
        task = Task.objects.get(id=task_id)
        run_id = task.run_id

        if request.headers.get('HX-Request'):
            return JsonResponse({'status': 'ok', 'run_id': str(run_id)})
        return redirect('run-detail', run_id=run_id)


class RunDeleteView(LoginRequiredMixin, View):
    """POST — delete one or more completed runs by UUID.

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


class RunCancelView(LoginRequiredMixin, View):
    """POST — cancel a single active (pending or running) run.

    Marks the run as 'cancelled' so the UI is unblocked.  If a pipeline thread
    is still alive it will finish naturally but won't overwrite the cancelled
    status (the _execute_run finally block excludes cancelled rows).
    """

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


def run_stream(request, run_id):
    """SSE endpoint: streams LogEntry rows for a running pipeline."""
    from webapp.models import LogEntry, Run, StageExecution
    import json

    def event_stream():
        # Honour ?from=<id> so the stream only delivers log entries that
        # weren't already rendered server-side, eliminating duplicates.
        last_log_id = int(request.GET.get('from', 0))
        last_stage_data = {}

        while True:
            close_old_connections()

            run = Run.objects.filter(id=run_id).first()
            if not run:
                yield 'event: error\ndata: {"error": "run not found"}\n\n'
                break

            # Push new log entries
            entries = LogEntry.objects.filter(
                run_id=run_id, id__gt=last_log_id
            ).order_by('id')
            for entry in entries:
                payload = json.dumps({
                    'type': 'log',
                    'level': entry.level,
                    'stage': entry.stage_name,
                    'message': entry.message,
                    'timestamp': entry.timestamp.isoformat(),
                })
                yield f'data: {payload}\n\n'
                last_log_id = entry.id

            # Push stage status updates
            for stage in StageExecution.objects.filter(run_id=run_id):
                key = f'{stage.name}:{stage.status}'
                if last_stage_data.get(stage.name) != key:
                    last_stage_data[stage.name] = key
                    payload = json.dumps({
                        'type': 'stage',
                        'name': stage.name,
                        'status': stage.status,
                        'order': stage.order,
                        'started_at': stage.started_at.isoformat() if stage.started_at else None,
                        'completed_at': stage.completed_at.isoformat() if stage.completed_at else None,
                    })
                    yield f'data: {payload}\n\n'

            if run.status in ('success', 'failed', 'cancelled'):
                # Tell the browser to wait 24 h before reconnecting — effectively
                # disabling auto-reconnect so a client close() wins the race.
                yield 'retry: 86400000\n\n'
                payload = json.dumps({'type': 'complete', 'status': run.status})
                yield f'data: {payload}\n\n'
                yield 'event: done\ndata: {}\n\n'
                break

            time.sleep(1)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
