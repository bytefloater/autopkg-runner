from pathlib import Path
import subprocess

from libs.stage import Stage
from libs.run_command import run_cmd


class TrustVerification(Stage):
    name = "Trust Verification"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        self.autopkg_fpath: Path    = config.autopkg.bin_path
        self.recipe_fpath: Path     = config.autopkg.recipe_list

    def run(self) -> list:
        recipes = []

        with open(self.recipe_fpath, 'r', encoding='utf-8') as recipe_file:
            for recipe in recipe_file:
                recipes.append(recipe.strip())
        self.logger.info(f"Loaded {len(recipes)} recipe(s)")

        self.logger.info("Starting trust information verification...")
        needs_update = []
        for recipe in recipes:
            try:
                run_cmd([
                    self.autopkg_fpath,
                    "verify-trust-info",
                    recipe
                ], self.logger)
            except subprocess.CalledProcessError:
                needs_update.append(recipe)

        if needs_update:
            self.logger.info(f"{len(needs_update)} recipe(s) failed verification, updating...")
            for recipe in needs_update:
                try:
                    run_cmd([
                        self.autopkg_fpath,
                        "update-trust-info",
                        recipe
                    ], self.logger)
                except subprocess.CalledProcessError as err:
                    raise RuntimeError("Failed to update trust information") from err

        return needs_update
