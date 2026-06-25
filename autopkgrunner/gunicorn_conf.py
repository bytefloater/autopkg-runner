"""
Gunicorn configuration for AutoPkg Runner.

Passed to gunicorn via --config python:autopkgrunner.gunicorn_conf.

on_starting runs once in the master process (pre-fork) and handles tasks that
must only happen once regardless of worker count: static file collection.

The post_fork hook starts background services (scheduler, stale-run cleanup,
recipe cache warm-up) inside each worker after forking, keeping the master
process completely thread-free.  This prevents the macOS ObjC fork-safety
crash that occurs when the master has active threads at fork time.

Scheduler election: whichever worker first acquires the flock on
BASE_DIR/scheduler.lock runs APScheduler.  The OS releases the lock when
that worker exits, so gunicorn's replacement worker picks it up automatically.
"""



def post_fork(server, worker):
    """Called in each worker process immediately after it is forked."""
    from django.apps import apps
    apps.get_app_config('webapp')._start_services_in_worker()
