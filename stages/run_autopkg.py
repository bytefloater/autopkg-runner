from pathlib import Path
import subprocess

from libs.stage import Stage
from libs.run_command import run_cmd


class RunAutoPkg(Stage):
    name = "Run AutoPkg"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        self.autopkg_fpath: Path    = config.autopkg.bin_path
        self.recipe_fpath: Path     = config.autopkg.recipe_list
        self.report_fpath: Path     = config.autopkg.report_plist
        self.local_mnt: Path        = config.repository.mount_path

    def run(self):
        recipes = []
        with open(self.recipe_fpath, 'r', encoding='utf-8') as recipe_file:
            for recipe in recipe_file:
                recipes.append(recipe.strip())
        if not recipes:
            raise RuntimeError("Unable to load recipe(s)")

        try:
            run_cmd([
                self.autopkg_fpath,
                "run",
                *recipes,
                "--report-plist",
                self.report_fpath,
                "-q",
                "-k",
                f"MUNKI_REPO={self.local_mnt}"
            ], self.logger)
        except subprocess.CalledProcessError as err:
            self.logger.error("Some recipes failed to execute: " + str(err))
