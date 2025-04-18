from abc import ABC, abstractmethod

from logbook import Logger
from libs.config import PipelineConfig

class Stage(ABC):
    """Base class for one step in the pipeline."""
    name = "unnamed‑stage"
    logger: Logger
    config: PipelineConfig
    ctx: dict[str, any]

    def __init__(self, config: PipelineConfig, ctx: dict[str, any], logger: Logger):
        self.config = config  # your typed config object
        self.ctx    = ctx     # shared dict for passing state around
        self.logger = logger

    def __call__(self):
        self.logger.info(f"Starting stage: {self.name}")
        if not self.pre_check():
            raise RuntimeError(f"Pre‑check failed for {self.name}")

        # Capture the stages return value
        result = self.run()

        # Store this in context for later use
        outputs = self.ctx.setdefault("stage_outputs", {})
        outputs[self.__class__.__name__] = result

        if not self.post_check():
            raise RuntimeError(f"Post‑check failed for {self.name}")

    def pre_check(self) -> bool:
        """Return True if it’s OK to run."""
        return True

    @abstractmethod
    def run(self):
        """Do the work of this stage."""

    def post_check(self) -> bool:
        """Return True if the work succeeded."""
        return True

    def cleanup(self):
        """Reverse any side‑effects (called if something downstream fails)."""