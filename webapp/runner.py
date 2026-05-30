"""Background pipeline execution. Implemented fully in Phase 4."""
import threading
import uuid as _uuid
from datetime import datetime, timezone


def trigger_manual_run(triggered_by: str = 'manual') -> _uuid.UUID:
    from webapp.models import Run, Task
    from libs.config import config_from_settings, pipeline_config_to_dict

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
    # Import models first — these are always available once Django is set up.
    # All other imports (orchestrator, stages, logbook) happen inside the
    # try/finally so that an ImportError or SyntaxError in any stage module
    # still lets the finally block mark the run as failed instead of leaving
    # it stuck in 'pending' forever.
    from webapp.models import Run, Task, StageExecution

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
                # Stage finished (success or failed) — clear the thread-local so
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
        success = orchestrator.execute()
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
        completed_at = datetime.now(timezone.utc)
        Run.objects.filter(id=run_id).update(
            status=final_status,
            completed_at=completed_at,
        )
        Task.objects.filter(id=task_id).update(
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
