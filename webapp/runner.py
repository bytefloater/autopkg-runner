"""Background pipeline execution. Implemented fully in Phase 4."""
import subprocess as _subprocess
import threading
import uuid as _uuid
from datetime import datetime, timezone


class RunAlreadyRunningError(Exception):
    """Raised when a run is already in progress and a new trigger is attempted."""


# ---------------------------------------------------------------------------
# Cancellation registry
# ---------------------------------------------------------------------------
# Maps run_id (str) → (cancel_event, active_subprocess | None).
# Used by cancel_run() to signal the pipeline thread to abort cleanly and
# to SIGTERM any running child process (e.g. autopkg) immediately.

_cancel_lock = threading.Lock()
_cancel_events: dict[str, threading.Event] = {}
_active_procs: dict[str, _subprocess.Popen] = {}


def _register_run(run_id: str, event: threading.Event) -> None:
    with _cancel_lock:
        _cancel_events[str(run_id)] = event


def _unregister_run(run_id: str) -> None:
    with _cancel_lock:
        _cancel_events.pop(str(run_id), None)
        _active_procs.pop(str(run_id), None)


def register_active_proc(run_id: str, proc: _subprocess.Popen) -> None:
    """Called by RunAutoPkg when a child process starts."""
    with _cancel_lock:
        _active_procs[str(run_id)] = proc


def unregister_active_proc(run_id: str) -> None:
    """Called by RunAutoPkg when a child process finishes."""
    with _cancel_lock:
        _active_procs.pop(str(run_id), None)


def cancel_run(run_id: str) -> None:
    """Signal the pipeline thread for *run_id* to abort and kill any running subprocess."""
    run_id = str(run_id)
    with _cancel_lock:
        event = _cancel_events.get(run_id)
        proc = _active_procs.get(run_id)
    if event:
        event.set()
    if proc and proc.poll() is None:
        proc.terminate()


def trigger_manual_run(triggered_by: str = 'manual') -> _uuid.UUID:
    from webapp.models import Run, Task
    from libs.config import config_from_settings, pipeline_config_to_dict

    # Guard against concurrent runs. The underlying pipeline is not thread-safe
    # (mounts a filesystem, writes files) so only one run may be active at a time.
    if Run.objects.filter(status__in=('pending', 'running')).exists():
        raise RunAlreadyRunningError(
            'A run is already in progress. Please wait for it to complete before starting another.'
        )

    config = config_from_settings()

    run = Run.objects.create(
        status='pending',
        triggered_by=triggered_by,
        config_snapshot=pipeline_config_to_dict(config),
    )
    task = Task.objects.create(
        task_type='pipeline_run',
        status='pending',
        run=run,
    )

    t = threading.Thread(
        target=_execute_run,
        args=(run.id, task.id),
        daemon=True,
        name=f'pipeline-run-{run.id}',
    )
    t.start()
    return task.id


def trigger_db_cleanup() -> _uuid.UUID:
    from webapp.models import Task

    task = Task.objects.create(task_type='db_cleanup', status='pending')
    t = threading.Thread(
        target=_execute_db_cleanup,
        args=(task.id,),
        daemon=True,
        name=f'db-cleanup-{task.id}',
    )
    t.start()
    return task.id


def _execute_run(run_id: _uuid.UUID, task_id: _uuid.UUID):
    import django.db
    # Import models first - these are always available once Django is set up.
    # All other imports (orchestrator, stages, logbook) happen inside the
    # try/finally so that an ImportError or SyntaxError in any stage module
    # still lets the finally block mark the run as failed instead of leaving
    # it stuck in 'pending' forever.
    from webapp.models import Run, Task, StageExecution

    cancel_event = threading.Event()
    _register_run(str(run_id), cancel_event)

    final_status = 'failed'
    db_handler = None

    try:
        from webapp.db_logger import DBLogHandler, set_run_id, set_current_stage
        from libs.config import config_from_settings
        from libs.orchestrator import Orchestrator
        from logbook import Logger

        set_run_id(run_id)
        db_handler = DBLogHandler()
        db_handler.push_thread()

        Run.objects.filter(id=run_id).update(
            status='running',
            started_at=datetime.now(timezone.utc),
        )
        Task.objects.filter(id=task_id).update(status='running')

        stage_order_counter = [0]

        def stage_callback(stage_name: str, status: str, timestamp: datetime):
            if status == 'running':
                # Tag this thread so every log record emitted by DBLogHandler
                # gets the correct stage_name while this stage is executing.
                set_current_stage(stage_name)
                order = stage_order_counter[0]
                stage_order_counter[0] += 1
                StageExecution.objects.update_or_create(
                    run_id=run_id,
                    name=stage_name,
                    defaults={'status': status, 'order': order, 'started_at': timestamp},
                )
            else:
                # Stage finished (success or failed) - clear the thread-local so
                # any inter-stage log lines don't get attributed to the last stage.
                set_current_stage('')
                StageExecution.objects.filter(run_id=run_id, name=stage_name).update(
                    status=status,
                    completed_at=timestamp,
                )

        logger = Logger('autopkg_runner')
        config = config_from_settings()
        ctx = {'run_id': run_id}

        orchestrator = Orchestrator(
            config=config,
            logger=logger,
            stage_callback=stage_callback,
        )
        orchestrator.ctx = ctx
        orchestrator.configure_stages(override_stage_name=None)
        success = orchestrator.execute(cancel_flag=cancel_event)
        final_status = 'success' if success else 'failed'
    except Exception:
        # Log if we got far enough to have a logger/handler; otherwise the
        # traceback will already have been printed to stderr by Python.
        try:
            from logbook import Logger
            Logger('autopkg_runner').exception('Pipeline failed during setup or execution')
        except Exception:
            pass
        final_status = 'failed'
    finally:
        _unregister_run(str(run_id))
        completed_at = datetime.now(timezone.utc)
        # Only update if the run hasn't been cancelled from outside
        # (e.g. the user hit "Cancel" in the UI while the pipeline was running).
        Run.objects.filter(id=run_id).exclude(status='cancelled').update(
            status=final_status,
            completed_at=completed_at,
        )
        Task.objects.filter(id=task_id).exclude(status='cancelled').update(
            status=final_status,
            completed_at=completed_at,
        )
        if db_handler is not None:
            db_handler.pop_thread()
        django.db.connection.close()


def _execute_db_cleanup(task_id: _uuid.UUID):
    import django.db
    from datetime import timedelta
    from django.utils import timezone as tz
    from webapp.models import Task, Run, LogEntry, RecipeResult, StageExecution

    Task.objects.filter(id=task_id).update(status='running')
    try:
        cutoff = tz.now() - timedelta(days=90)
        old_runs = Run.objects.filter(
            completed_at__lt=cutoff,
            status__in=('success', 'failed', 'cancelled'),
        )
        LogEntry.objects.filter(run__in=old_runs).delete()
        RecipeResult.objects.filter(run__in=old_runs).delete()
        StageExecution.objects.filter(run__in=old_runs).delete()
        old_runs.delete()
        Task.objects.filter(id=task_id).update(
            status='success',
            completed_at=datetime.now(timezone.utc),
        )
    except Exception:
        Task.objects.filter(id=task_id).update(
            status='failed',
            completed_at=datetime.now(timezone.utc),
        )
    finally:
        django.db.connection.close()
