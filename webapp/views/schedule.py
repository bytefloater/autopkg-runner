from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView


class ScheduleView(LoginRequiredMixin, TemplateView):
    template_name = 'webapp/schedule.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/schedule.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from webapp.models import Schedule
        ctx['active_tab'] = 'schedule'
        s, _ = Schedule.objects.get_or_create(pk=1)
        ctx['schedule'] = s
        ctx['cron_fields'] = [
            ('Minute',       'minute',       s.minute,       '0-59 or *'),
            ('Hour',         'hour',         s.hour,         '0-23 or *'),
            ('Day of Week',  'day_of_week',  s.day_of_week,  '0-6 or *'),
            ('Day of Month', 'day_of_month', s.day_of_month, '1-31 or *'),
            ('Month',        'month',        s.month,        '1-12 or *'),
        ]
        return ctx

    def post(self, request):
        from webapp.models import Schedule
        from webapp.scheduler import reschedule_job

        schedule, _ = Schedule.objects.get_or_create(pk=1)
        schedule.enabled = request.POST.get('enabled') == 'on'
        schedule.minute = request.POST.get('minute', '0').strip() or '0'
        schedule.hour = request.POST.get('hour', '2').strip() or '2'
        schedule.day_of_week = request.POST.get('day_of_week', '*').strip() or '*'
        schedule.day_of_month = request.POST.get('day_of_month', '*').strip() or '*'
        schedule.month = request.POST.get('month', '*').strip() or '*'
        schedule.save()

        try:
            reschedule_job()
            messages.success(request, 'Schedule saved and applied.')
        except Exception as exc:
            messages.error(request, f'Schedule saved but scheduler error: {exc}')

        return redirect('schedule')
