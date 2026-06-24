from datetime import datetime, timezone
from typing import Callable, Optional

from logbook import Logger

from libs.stage import Stage
from libs.config import PipelineConfig
from stages import (
    EnvironmentCheck, TrustVerification, MountRepository, RunAutoPkg,
    GarbageCollector, NotifyOnCompletion, UpdateRepos
)


class Orchestrator:
    STAGE_CLASSES: list[type[Stage]] = [
        EnvironmentCheck,
        MountRepository,
        UpdateRepos,
        TrustVerification,
        RunAutoPkg,
        GarbageCollector,
        NotifyOnCompletion,
    ]

    def __init__(
        self,
        config: PipelineConfig,
        logger: Logger,
        stage_callback: Optional[Callable[[str, str, datetime], None]] = None,
    ):
        self.config = config
        self.ctx: dict = {}
        self.logger: Logger = logger
        self.stage_callback = stage_callback

    def configure_stages(self, override_stage_name):
        override_stage_class = None
        if override_stage_name:
            override_stage_class = next(
                ([cls] for cls in self.STAGE_CLASSES if cls.__name__ == override_stage_name),
                None,
            )

        self.stages: list[Stage] = [
            cls(self.config, self.ctx, self.logger)
            for cls in (override_stage_class if override_stage_class is not None else self.STAGE_CLASSES)
        ]

        enabled_stage_names = [cls.__class__.__name__ for cls in self.stages]
        self.logger.info(f"Configured stages: {enabled_stage_names}")

    def execute(self, cancel_flag=None) -> bool:
        """Run all configured stages. Returns True on full success, False otherwise.

        cancel_flag is an optional threading.Event; when set the pipeline aborts
        before the next stage and cleanup runs for all completed stages.
        """
        if not hasattr(self, 'stages'):
            self.logger.error('Stages not configured')
            return False

        # Separate the notification stage so it always runs even when earlier
        # stages fail - otherwise a pipeline error skips the notification entirely.
        notify_stage = next(
            (s for s in self.stages if isinstance(s, NotifyOnCompletion)), None
        )
        pipeline_stages = [s for s in self.stages if not isinstance(s, NotifyOnCompletion)]

        completed = []
        current_stage = None
        success = True

        try:
            for stage in pipeline_stages:
                if cancel_flag and cancel_flag.is_set():
                    self.logger.info('Run cancelled — stopping pipeline before next stage.')
                    success = False
                    break
                current_stage = stage
                self._notify(stage.name, 'running')
                stage()
                self._notify(stage.name, 'success')
                completed.append(stage)
        except Exception:
            success = False
            if current_stage is not None:
                self._notify(current_stage.name, 'failed')
            self.logger.exception('Pipeline failed, starting cleanup…')
        finally:
            for s in reversed(completed):
                try:
                    s.cleanup()
                except Exception:
                    self.logger.exception(f'Cleanup error in {s.name}')

            # Always dispatch notifications - success or failure.
            if notify_stage is not None:
                try:
                    self._notify(notify_stage.name, 'running')
                    notify_stage()
                    self._notify(notify_stage.name, 'success')
                except Exception:
                    self._notify(notify_stage.name, 'failed')
                    self.logger.exception('Notification stage failed')

        return success

    def _notify(self, stage_name: str, status: str):
        if self.stage_callback:
            try:
                self.stage_callback(stage_name, status, datetime.now(timezone.utc))
            except Exception:
                pass
