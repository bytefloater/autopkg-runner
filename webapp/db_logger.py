import threading

import logbook

_local = threading.local()


# -- Thread-local run / stage tracking -----------------------------------------

def set_run_id(run_id):
    _local.run_id = run_id


def get_run_id():
    return getattr(_local, 'run_id', None)


def set_current_stage(stage_name: str):
    """Called by runner.stage_callback so every log record knows its stage."""
    _local.stage_name = stage_name


def get_current_stage() -> str:
    return getattr(_local, 'stage_name', '')


# -- Handler -------------------------------------------------------------------

class DBLogHandler(logbook.Handler):
    """Logbook handler that persists log records to the LogEntry model.

    The handler is pushed per-thread (push_thread / pop_thread) in the
    pipeline background thread so it only intercepts logs from that thread.
    Stage attribution relies on set_current_stage() being called by the
    orchestrator's stage_callback before each stage runs.
    """

    def emit(self, record):
        run_id = get_run_id()
        if run_id is None:
            return
        try:
            from django.utils import timezone
            from webapp.models import LogEntry

            LogEntry.objects.create(
                run_id=run_id,
                level=record.level_name,
                message=record.message,
                stage_name=get_current_stage(),
                timestamp=timezone.now(),
            )
        except Exception:
            pass
