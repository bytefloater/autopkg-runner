import os
import sys

from django.apps import AppConfig


class WebappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'webapp'

    def ready(self):
        # Only start background services (scheduler, stale-run cleanup) when
        # the process is actually *serving*.
        #
        # Management commands (migrate, shell, check, createsuperuser, …) and
        # bare invocations ("python manage.py" with no subcommand) must never
        # touch the database here — the tables may not exist yet.
        #
        # Detection logic:
        #  • If argv[0] looks like manage.py we are in a management-command
        #    context.  Only 'runserver' should proceed, and only in the child
        #    reloader process (RUN_MAIN=true) to avoid double-starting.
        #  • Any other argv[0] (gunicorn, uvicorn, …) means we are a real
        #    WSGI/ASGI server — proceed unconditionally.

        via_manage = sys.argv and os.path.basename(sys.argv[0]) in ('manage.py', 'manage')

        if via_manage:
            # No subcommand at all → just showing help, do nothing.
            if len(sys.argv) < 2:
                return
            # Any management command other than runserver → do nothing.
            if sys.argv[1] != 'runserver':
                return
            # runserver: the parent watcher process re-execs itself as a child
            # with RUN_MAIN=true.  Only start services in the child so that the
            # scheduler and stale-run cleanup are not registered twice.
            if os.environ.get('RUN_MAIN') != 'true':
                return

        from webapp.scheduler import start_scheduler
        start_scheduler()
        self._mark_interrupted_runs()

    def _mark_interrupted_runs(self):
        """
        Mark any run/task left in running or pending state as failed.
        These are orphaned by a previous process crash or SIGKILL.

        Wrapped in OperationalError so that running 'runserver' on a
        fresh install (before migrate) does not crash.
        """
        from django.db.utils import OperationalError
        from django.utils import timezone
        from webapp.models import Run, StageExecution, Task

        now = timezone.now()
        stale = ('running', 'pending')

        try:
            stale_runs = Run.objects.filter(status__in=stale)
            if stale_runs.exists():
                StageExecution.objects.filter(
                    run__in=stale_runs,
                    status__in=stale,
                ).update(status='failed', completed_at=now)
                stale_runs.update(status='failed', completed_at=now)

            Task.objects.filter(status__in=stale).update(
                status='failed', completed_at=now,
            )
        except OperationalError:
            # Tables do not exist yet (pre-migration).  Safe to ignore.
            pass
