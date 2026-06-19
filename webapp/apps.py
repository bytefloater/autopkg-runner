import os
import sys
import threading

from django.apps import AppConfig

# Management commands that should never start background services.
# Anything NOT in this set is assumed to be a serving command (runserver,
# serve, gunicorn workers via their own argv[0] path, etc.).
_SKIP_COMMANDS = frozenset({
    # Database
    'migrate', 'makemigrations', 'showmigrations', 'sqlmigrate',
    'squashmigrations', 'optimizemigration',
    # Static files
    'collectstatic', 'findstatic',
    # Auth / user management
    'createsuperuser', 'changepassword',
    # Inspection / development
    'shell', 'dbshell', 'check', 'inspectdb', 'diffsettings',
    'sendtestemail', 'startapp', 'startproject',
    # Testing
    'test', 'testserver',
    # Project-specific non-serving commands
    'configure', 'setup', 'install_sftp_deps',
    'generate_vapid_keys', 'resetpassword',
    'install_service_daemon', 'remove_service_daemon',
})


class WebappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'webapp'

    def ready(self):
        # Only start background services (scheduler, stale-run cleanup) when
        # the process is actually *serving requests*.
        #
        # Strategy: block known non-serving management commands; allow
        # everything else (runserver, our custom `serve` wrapper, gunicorn
        # workers, etc.) to proceed.  This is safer than a whitelist because
        # it works with any custom serving wrapper without needing code changes.
        #
        # Auto-reload guard: Django's StatReloader forks a parent (watcher)
        # and a child (server).  RUN_MAIN=true is set only in the child.
        # We must not start the scheduler in the parent or we'd get two
        # schedulers firing concurrently.  When --noreload is in argv there is
        # only a single process, so we skip the RUN_MAIN check entirely.

        # AUTOPKG_MODE is set by run.py: 'server' for serve, 'manage' for everything else.
        # Falls back to argv inspection for direct manage.py invocations.
        autopkg_mode = os.environ.get('AUTOPKG_MODE')
        if autopkg_mode == 'manage':
            return
        if autopkg_mode == 'server':
            # Services are started in each gunicorn worker via the post_fork hook
            # in autopkgrunner/gunicorn_conf.py.  Starting threads here (in the
            # master process) would cause macOS ObjC fork-safety crashes when
            # gunicorn forks workers.
            return

        via_manage = sys.argv and os.path.basename(sys.argv[0]) in ('manage.py', 'manage')

        if via_manage:
            # No subcommand at all → just showing help, do nothing.
            if len(sys.argv) < 2:
                return
            # Known non-serving command → do nothing.
            if sys.argv[1] in _SKIP_COMMANDS:
                return
            # Serving command with auto-reload: skip the parent watcher process.
            # Only the child (RUN_MAIN=true) or a --noreload single-process
            # invocation should start background services.
            noreload = '--noreload' in sys.argv or '--no-reload' in sys.argv
            if not noreload and os.environ.get('RUN_MAIN') != 'true':
                return

        # Defer all DB-touching work to a daemon thread.  AppConfig.ready()
        # is called while the app registry is still being populated
        # (Apps.ready is False), so any ORM query triggers a RuntimeWarning.
        # Running the same work one tick later avoids the warning without
        # changing the effective startup behaviour.
        threading.Thread(target=self._start_services, daemon=True).start()

    def _start_services(self):
        """Start services for direct manage.py serving (runserver / --noreload).
        Runs in a daemon thread so it executes after the app registry is fully
        initialised."""
        from webapp.scheduler import start_scheduler
        from webapp.views.recipes import _start_cache_build
        from webapp.recipe_index import ensure_fresh as index_ensure_fresh
        start_scheduler()
        self._mark_interrupted_runs()
        _start_cache_build()
        index_ensure_fresh()

    def _start_services_in_worker(self):
        """Start services inside a gunicorn worker (called from post_fork hook).

        All workers run the one-shot startup tasks.  Only the worker that wins
        the scheduler lock starts APScheduler, preventing duplicate scheduled
        runs when workers > 1.
        """
        from webapp.scheduler import acquire_scheduler_lock, start_scheduler
        from webapp.views.recipes import _start_cache_build
        from webapp.recipe_index import ensure_fresh as index_ensure_fresh
        self._mark_interrupted_runs()
        _start_cache_build()
        index_ensure_fresh()
        if acquire_scheduler_lock():
            start_scheduler()

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
