import logging
import os
from zoneinfo import ZoneInfo

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger('autopkg_runner')

_scheduler = None


def get_system_timezone() -> ZoneInfo:
    """Detect the host system's IANA timezone (DST-aware). Falls back to UTC.

    Deliberately skips the TZ environment variable because Django sets it to
    settings.TIME_ZONE ('UTC') on startup, which would mask the real host
    timezone. Filesystem sources are authoritative on macOS and Linux.

    Resolution order:
      1. /etc/localtime symlink (macOS, most Linux distros)
      2. /etc/timezone plain-text file (Debian/Ubuntu)
      3. UTC
    """
    # 1. /etc/localtime symlink → .../zoneinfo/<Region/City>
    try:
        real = os.path.realpath('/etc/localtime')
        idx = real.find('/zoneinfo/')
        if idx != -1:
            tz_name = real[idx + len('/zoneinfo/'):]
            if tz_name:
                return ZoneInfo(tz_name)
    except Exception:
        pass

    # 2. /etc/timezone plain text (Debian/Ubuntu)
    try:
        with open('/etc/timezone') as f:
            tz_name = f.read().strip()
            if tz_name:
                return ZoneInfo(tz_name)
    except Exception:
        pass

    return ZoneInfo('UTC')


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        tz = get_system_timezone()
        _scheduler = BackgroundScheduler(
            jobstores={'default': MemoryJobStore()},
            timezone=tz,
        )
        logger.info('Scheduler created (timezone: %s)', tz.key)
    return _scheduler


def _safe_trigger_scheduled_run():
    """Wrapper called by APScheduler; skips the run if one is already active."""
    from webapp.runner import trigger_manual_run, RunAlreadyRunningError
    logger.info('Scheduler firing scheduled run')
    try:
        trigger_manual_run(triggered_by='scheduler')
    except RunAlreadyRunningError:
        logger.warning('Scheduled run skipped — a run is already in progress.')
    except Exception:
        logger.exception('Unhandled error in scheduled run trigger')


def reschedule_job():
    """Re-read the Schedule model and update the APScheduler cron job."""
    from webapp.models import Schedule

    scheduler = get_scheduler()

    # Safety net: if the scheduler isn't running yet (e.g. --noreload without
    # a prior start_scheduler call, or a startup error), start it now.
    if not scheduler.running:
        scheduler.start()
        logger.info('Scheduler started (from reschedule_job)')

    tz = get_system_timezone()

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
            timezone=tz,
            minute=schedule.minute,
            hour=schedule.hour,
            day_of_week=schedule.day_of_week,
            day=schedule.day_of_month,
            month=schedule.month,
            misfire_grace_time=300,
        )
        job = scheduler.get_job('autopkg_scheduled_run')
        next_rt = getattr(job, 'next_run_time', None) if job else None
        logger.info(
            'Scheduled job registered: %s %s %s %s %s (%s) — next run: %s',
            schedule.minute, schedule.hour,
            schedule.day_of_week, schedule.day_of_month, schedule.month,
            tz.key,
            next_rt or '(scheduler not yet started — will fire once running)',
        )
    else:
        logger.info('Scheduled job removed (schedule disabled)')


def start_scheduler():
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info('Scheduler started')
    try:
        reschedule_job()
    except Exception:
        logger.exception('Failed to register scheduled job on startup')
