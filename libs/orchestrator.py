from logbook import Logger

from libs.stage import Stage
from libs.config import PipelineConfig
from stages import (
    EnvironmentCheck, TrustVerification, MountRepository, RunAutoPkg,
    GarbageCollector, GenerateReport, NotifyOnCompletion
)

class Orchestrator:
    STAGE_CLASSES: list[Stage] = [
        EnvironmentCheck,
        MountRepository,
        TrustVerification,
        RunAutoPkg,
        GarbageCollector,
        GenerateReport,
        NotifyOnCompletion
    ]

    def __init__(self, config: PipelineConfig, logger: Logger):
        # Shared “scratch‐space” between stages
        self.config = config
        self.ctx: dict = {}
        self.logger: Logger = logger

    def configure_stages(self, override_stage_name):
        if override_stage_name:
            override_stage_class: list[Stage] = next(
                ([cls] for cls in self.STAGE_CLASSES if cls.__name__ == override_stage_name),
                []
            )

        # Instantiate each stage with the same configuration
        self.stages: list[Stage] = [
            cls(self.config, self.ctx, self.logger)
            for cls in (override_stage_class if 'override_stage_class' in locals() else self.STAGE_CLASSES)
        ]

        enabled_stage_names = [cls.__class__.__name__ for cls in self.stages]
        self.logger.info(f"Configured stages: {enabled_stage_names}")

    def execute(self):
        if not hasattr(self, "stages"):
            self.logger.error("Stages not configured")
            return

        completed = []
        try:
            for stage in self.stages:
                # Execute the 'pre_check(), run(), and post_check()
                stage()
                completed.append(stage)
        except Exception:
            self.logger.exception("Pipeline failed, starting cleanup…")
        finally:
            # Execute a reverse‐order cleanup for completed stages
            for s in reversed(completed):
                try:
                    s.cleanup()
                except Exception:
                    self.logger.exception(f"Cleanup error in {s.name}")
