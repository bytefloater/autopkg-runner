"""
Gunicorn configuration for AutoPkg Runner.

Passed to gunicorn via --config python:autopkgrunner.gunicorn_conf.

The post_fork hook starts background services (scheduler, stale-run cleanup,
recipe cache warm-up) inside each worker after forking, keeping the master
process completely thread-free.  This prevents the macOS ObjC fork-safety
crash that occurs when the master has active threads at fork time.

Scheduler election: whichever worker first acquires the flock on
BASE_DIR/scheduler.lock runs APScheduler.  The OS releases the lock when
that worker exits, so gunicorn's replacement worker picks it up automatically.

Worker class: we subclass UvicornWorker to force the asyncio event loop even
when uvloop is installed.  uvloop initialises libuv state at import time which
is not fork-safe on macOS, causing an immediate SIGSEGV in every child process
if the parent imported uvloop before forking.
"""

import logging
import signal
import threading

from uvicorn.workers import UvicornWorker

logger = logging.getLogger('autopkg_runner')


# Custom logging format: [YYYY-MM-DD HH:MM:SS +0000] [PID] [LEVEL] message
# Matches gunicorn's format for consistent output across all logs
class _GunicornFormatter(logging.Formatter):
    """Formatter for gunicorn's error logs matching application format."""
    _level_names = {'WARNING': 'WARN', 'DEBUG': 'DEBUG', 'INFO': 'INFO', 'ERROR': 'ERROR'}

    def format(self, record):
        record.levelname = self._level_names.get(record.levelname, record.levelname)
        timestamp = self.formatTime(record, '%Y-%m-%d %H:%M:%S')
        return f'[{timestamp} +0000] [{record.process}] [{record.levelname}] {record.getMessage()}'


class _AsyncioUvicornWorker(UvicornWorker):
    """UvicornWorker pinned to the stdlib asyncio loop (never uvloop)."""
    CONFIG_KWARGS = {**UvicornWorker.CONFIG_KWARGS, "loop": "asyncio"}


worker_class = f"{__name__}._AsyncioUvicornWorker"


def when_ready(server):
    """Apply unified formatter to gunicorn loggers after initialization."""
    formatter = _GunicornFormatter()
    for logger_name in ['gunicorn.error', 'gunicorn.access']:
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers:
            handler.setFormatter(formatter)


def post_fork(server, worker):
    """Called in each worker process immediately after it is forked."""
    from django.apps import apps
    from webapp.apps import WebappConfig

    def _shutdown_scheduler(signum, frame):
        """Gracefully shutdown APScheduler on SIGTERM during worker shutdown."""
        from webapp import scheduler as scheduler_module
        if scheduler_module._scheduler and scheduler_module._scheduler.running:
            logger.info('Scheduler shutting down gracefully')
            try:
                scheduler_module._scheduler.shutdown(wait=True)
                logger.info('Scheduler shutdown complete')
            except Exception as e:
                logger.warning('Error during scheduler shutdown: %s', e)

    # Register SIGTERM handler so APScheduler shuts down cleanly within
    # gunicorn's graceful_timeout (default 30s) instead of being SIGKILL'd
    signal.signal(signal.SIGTERM, _shutdown_scheduler)

    webapp_config: WebappConfig = apps.get_app_config('webapp')  # type: ignore[assignment]
    threading.Thread(
        target=webapp_config._start_services_in_worker,
        daemon=True,
    ).start()
