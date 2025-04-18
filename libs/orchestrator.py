from logbook import Logger

from libs.stage import Stage
from libs.config import PipelineConfig
from stages import (
    EnvironmentCheck, TrustVerification, MountRepository, RunAutoPkg,
    GenerateReport, GarbageCollector, NotifyOnCompletion
)

class Orchestrator:
    def __init__(self, config: PipelineConfig, logger: Logger):
        # Shared “scratch‐space” between stages
        self.config = config
        self.ctx: dict = {}
        self.logger: Logger = logger

        # Instantiate each stage with the same configuration
        self.stages: list[Stage] = [
            EnvironmentCheck(config, self.ctx, self.logger),
            TrustVerification(config, self.ctx, self.logger),
            MountRepository(config, self.ctx, self.logger),
            RunAutoPkg(config, self.ctx, self.logger),
            GenerateReport(config, self.ctx, self.logger),
            GarbageCollector(config, self.ctx, self.logger),
            NotifyOnCompletion(config, self.ctx, self.logger)
        ]

    def execute(self):
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
