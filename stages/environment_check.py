import os
from pathlib import Path
import urllib

import psutil
from libs.stage import Stage


class EnvironmentCheck(Stage):
    name = "Environment Check"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        self.autopkg_fpath: Path    = config.autopkg.bin_path
        self.recipe_fpath: Path     = config.autopkg.recipe_list
        self.server_share: str      = config.repository.server_share
        self.host: str              = config.repository.host
        self.error_flag: bool       = False

    def run(self):
        CHECKS = [
            self.autopkg_exists(),
            self.recipe_file_exists(),
            self.is_no_mount_conflict()
        ]
        if False in CHECKS:
            self.error_flag = True

    def is_no_mount_conflict(self) -> bool:
        CHECKS = {
            "device": urllib.parse.quote(self.server_share),
        }
        conflicts: list[dict] = []
        disks = psutil.disk_partitions(all=True)
        for disk in disks:
            for key, check in CHECKS.items():
                if check in disk._asdict()[key]:
                    conflicts.append(disk._asdict())

        if conflicts:
            for conflict in conflicts:
                self.logger.error(f"Conflicts: {conflict}")
            return False
        self.logger.info("No mounting conflicts found")
        return True
    
    def autopkg_exists(self) -> bool:
        if not os.path.exists(self.autopkg_fpath):
            self.logger.error("AutoPkg could not be found")
            return False

        self.logger.info(f"AutoPkg found at: {self.autopkg_fpath}")
        return True

    def recipe_file_exists(self) -> bool:
        if not os.path.exists(self.recipe_fpath):
            self.logger.error("Recipe file could not be found")
            return False

        self.logger.info(f"Receipe file found at: {self.recipe_fpath}")
        return True

    def post_check(self):
        if self.error_flag:
            self.logger.error("One or more check(s) have failed, check logs for details")
            return False
        self.logger.info("All checks passed")
        return True
