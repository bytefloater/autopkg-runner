import os
from pathlib import Path

from libs.stage import Stage


class EnvironmentCheck(Stage):
    name = "Environment Check"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        self.autopkg_fpath: Path    = config.autopkg.bin_path
        self.recipe_fpath: Path     = config.autopkg.recipe_list


    def run(self):
        if not os.path.exists(self.autopkg_fpath):
            raise EnvironmentError("AutoPkg could not be found")
        self.logger.info(f"AutoPkg found at: {self.autopkg_fpath}")

        if not os.path.exists(self.recipe_fpath):
            raise EnvironmentError("Recipe file could not be found")
        self.logger.info(f"Receipe file found at: {self.recipe_fpath}")