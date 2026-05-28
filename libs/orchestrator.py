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
    STAGE_CLASSES: list[Stage] = [
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

    def execute(self) -> bool:
        """Run all configured stages. Returns True on full success, False otherwise."""
        if not hasattr(self, 'stages'):
            self.logger.error('Stages not configured')
            return False

        completed = []
        current_stage = None
        success = True

        try:
            for stage in self.stages:
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

        return success

    def _notify(self, stage_name: str, status: str):
        if self.stage_callback:
            try:
                self.stage_callback(stage_name, status, datetime.now(timezone.utc))
            except Exception:
                pass
