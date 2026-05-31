from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore

_scheduler = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.add_jobstore(DjangoJobStore(), 'default')
    return _scheduler


def _safe_trigger_scheduled_run():
    """Wrapper called by APScheduler; skips the run if one is already active."""
    from webapp.runner import trigger_manual_run, RunAlreadyRunningError
    try:
        trigger_manual_run(triggered_by='scheduler')
    except RunAlreadyRunningError:
        import logging
        logging.getLogger('autopkg_runner').warning(
            'Scheduled run skipped — a run is already in progress.'
        )


def reschedule_job():
    from webapp.models import Schedule

    scheduler = get_scheduler()
    try:
        scheduler.remove_job('autopkg_scheduled_run')
    except Exception:
        pass

    schedule = Schedule.objects.get(pk=1)
    if schedule.enabled:
        scheduler.add_job(
            _safe_trigger_scheduled_run,
            trigger='cron',
            id='autopkg_scheduled_run',
            replace_existing=True,
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
