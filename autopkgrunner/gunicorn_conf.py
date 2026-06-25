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

from uvicorn.workers import UvicornWorker


class _AsyncioUvicornWorker(UvicornWorker):
    """UvicornWorker pinned to the stdlib asyncio loop (never uvloop)."""
    CONFIG_KWARGS = {**UvicornWorker.CONFIG_KWARGS, "loop": "asyncio"}


worker_class = f"{__name__}._AsyncioUvicornWorker"


def post_fork(server, worker):
    """Called in each worker process immediately after it is forked."""
    import threading
    from django.apps import apps
    threading.Thread(
        target=apps.get_app_config('webapp')._start_services_in_worker,
        daemon=True,
    ).start()
