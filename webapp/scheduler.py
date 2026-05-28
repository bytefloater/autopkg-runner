from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore

_scheduler = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.add_jobstore(DjangoJobStore(), 'default')
    return _scheduler


def reschedule_job():
    from webapp.models import Schedule
    from webapp.runner import trigger_manual_run

    scheduler = get_scheduler()
    try:
        scheduler.remove_job('autopkg_scheduled_run')
    except Exception:
        pass

    schedule = Schedule.objects.get(pk=1)
    if schedule.enabled:
        scheduler.add_job(
            trigger_manual_run,
            trigger='cron',
            id='autopkg_scheduled_run',
            replace_existing=True,
            kwargs={'triggered_by': 'scheduler'},
            minute=schedule.minute,
            hour=schedule.hour,
            day_of_week=schedule.day_of_week,
            day=schedule.day_of_month,
            month=schedule.month,
            jobstore='default',
            misfire_grace_time=300,
        )


def start_scheduler():
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
    try:
        reschedule_job()
    except Exception:
        pass
