from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView


# ── Human-readable cron description ──────────────────────────────────────────

_DOW_NAMES = {
    '0': 'Sunday', '1': 'Monday', '2': 'Tuesday', '3': 'Wednesday',
    '4': 'Thursday', '5': 'Friday', '6': 'Saturday',
    # APScheduler also accepts sun/mon/… — handle numeric only here
}

_MONTH_NAMES = {
    '1': 'January',   '2': 'February', '3': 'March',    '4': 'April',
    '5': 'May',       '6': 'June',     '7': 'July',     '8': 'August',
    '9': 'September', '10': 'October', '11': 'November','12': 'December',
}


def _describe_cron(s) -> str:
    """Return a plain-English description of when the cron schedule fires."""
    minute      = s.minute.strip()
    hour        = s.hour.strip()
    day_of_week = s.day_of_week.strip()
    day_of_month = s.day_of_month.strip()
    month       = s.month.strip()

    # Time part
    if minute == '*' and hour == '*':
        time_str = 'every minute'
    elif minute == '*':
        time_str = f'every minute past {_fmt_hour(hour)}'
    elif hour == '*':
        time_str = f'every hour at :{minute.zfill(2)}'
    else:
        time_str = f'at {_fmt_time(hour, minute)} UTC'

    # Day/month part
    parts = []
    if day_of_week != '*':
        days = [_DOW_NAMES.get(d.strip(), d.strip()) for d in day_of_week.split(',')]
        parts.append('on ' + ', '.join(days))
    if day_of_month != '*':
        parts.append(f'on day {day_of_month} of the month')
    if month != '*':
        months = [_MONTH_NAMES.get(m.strip(), m.strip()) for m in month.split(',')]
        parts.append('in ' + ', '.join(months))

    when = ', '.join(parts) if parts else 'every day'
    return f'Runs {time_str}, {when}.'


def _fmt_hour(h: str) -> str:
    """Format a 24-hour value as a readable hour label (no minutes)."""
    try:
        n = int(h)
        suffix = 'AM' if n < 12 else 'PM'
        n12 = n % 12 or 12
        return f'{n12} {suffix}'
    except ValueError:
        return h


def _fmt_time(h: str, m: str) -> str:
    """Format hour + minute as a 12-hour clock string, e.g. '2:00 AM'."""
    try:
        hn = int(h)
        mn = int(m)
        suffix = 'AM' if hn < 12 else 'PM'
        h12 = hn % 12 or 12
        return f'{h12}:{mn:02d} {suffix}'
    except ValueError:
        return f'{h}:{m}'


def _next_run_time(s):
    """Compute the next fire time for the schedule directly from its cron fields."""
    try:
        from apscheduler.triggers.cron import CronTrigger
        from datetime import datetime, timezone as dt_timezone
        trigger = CronTrigger(
            minute=s.minute,
            hour=s.hour,
            day_of_week=s.day_of_week,
            day=s.day_of_month,
            month=s.month,
            timezone='UTC',
        )
        now = datetime.now(tz=dt_timezone.utc)
        return trigger.get_next_fire_time(None, now)
    except Exception:
        return None


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
        ctx['cron_description'] = _describe_cron(s) if s.enabled else None
        ctx['next_run'] = _next_run_time(s) if s.enabled else None
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
