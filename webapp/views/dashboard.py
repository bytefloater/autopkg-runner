from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'webapp/dashboard.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/dashboard.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from webapp.models import Run
        from django.utils import timezone
        from datetime import timedelta

        ctx['active_tab'] = 'dashboard'
        ctx['recent_runs'] = list(Run.objects.order_by('-started_at')[:5])
        ctx['last_run'] = ctx['recent_runs'][0] if ctx['recent_runs'] else None

        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent = Run.objects.filter(started_at__gte=thirty_days_ago)
        ctx['total_runs_30d'] = recent.count()
        success = recent.filter(status='success').count()
        ctx['success_rate_30d'] = round(success / ctx['total_runs_30d'] * 100) if ctx['total_runs_30d'] else 0

        try:
            from webapp.models import Schedule
            from webapp.views.schedule import _next_run_time
            s = Schedule.objects.get(pk=1)
            next_run = _next_run_time(s) if s.enabled else None
            ctx['next_run'] = next_run
            ctx['next_run_formatted'] = (
                next_run.strftime('%a, %d %b at %H:%M %Z') if next_run else None
            )
        except Exception:
            ctx['next_run'] = None
            ctx['next_run_formatted'] = None

        return ctx
