from datetime import datetime, timedelta
import glob
import os
from pathlib import Path
import re
import subprocess
import shutil

from libs.stage import Stage
from libs.run_command import run_cmd


class GarbageCollector(Stage):
    name = "Garbage Collector"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        self.cache_dir: Path        = config.autopkg.cache_path
        self.local_mnt: Path        = config.repository.mount_path
        self.report_dir: str        = config.repository.report_dir
        collector_settings: dict    = config.module_settings.garbage_collector
        self.repoclean_fpath: str   = collector_settings["repoclean_bin_path"]
        retention: dict             = collector_settings["retention"]
        targets: dict               = collector_settings["targets"]

        # Retention settings
        self.retention_period: str        = retention["period"]
        self.keep_versions: int           = collector_settings.get("keep_versions", 3) 

        # Cleanup target flags
        self.will_clear_cache: bool       = targets.get("autopkg_cache", False)
        self.will_clear_temp: bool        = targets.get("temp_files", False)
        self.will_clear_old_reports: bool = targets.get("old_reports", False)
        self.will_clean_repo: bool        = targets.get("repository_index", False)

    def _parse_retention(self, retention: str) -> timedelta:
        """
        Parse a retention string like '7d', '12h', '1w' into a timedelta.
        Supports:
        h = hours
        d = days
        w = weeks
        """
        match = re.fullmatch(r'(\d+)([hdw])', retention)
        if not match:
            raise ValueError(
                f"Invalid retention '{retention}'. Must be e.g. '12h', '7d' or '1w'."
            )

        value, unit = int(match.group(1)), match.group(2)
        unit_map = {
            "h": lambda: timedelta(hours=value),
            "d": lambda: timedelta(days=value),
            "w": lambda: timedelta(weeks=value)
        }
        return unit_map[unit]

    def clear_autopkg_cache(self, retention: str):
        self.logger.info(f"Clearing AutoPkg Cache... ({retention})")

        dirs = list(os.scandir(self.cache_dir))
        cutoff = datetime.now() - self._parse_retention(retention)()
        expired = []

        self.logger.info(f"Found {len(dirs)} item(s) in cache")
        for entry in dirs:
            if not entry.is_dir():
                continue

            modify_time = datetime.fromtimestamp(entry.stat().st_mtime)
            if modify_time < cutoff:
                expired.append(entry.path)
        
        self.logger.info(f"Marked {len(expired)} item(s) for deletion")
        for entry in expired:
            self.logger.debug(f"Removing '{entry}'")
            shutil.rmtree(entry)
    
    def clear_old_reports(self, retention: str):
        self.logger.info(f"Clearing old reports... ({retention})")

        pattern = f"{self.local_mnt}/{self.report_dir}/[0-9]*.html"
        reports = glob.glob(pattern, recursive=False)
        
        cutoff = datetime.now() - self._parse_retention(retention)()
        expired = []

        self.logger.info(f"Found {len(reports)} report(s) on the repository")
        for entry in reports:
            modify_time = datetime.fromtimestamp(os.path.getmtime(entry))
            if modify_time < cutoff:
                expired.append(entry)
        
        self.logger.info(f"Marked {len(expired)} item(s) for deletion")
        for entry in expired:
            self.logger.debug(f"Removing '{entry}'")
            try:
                os.remove(entry)
            except OSError:
                self.logger.exception(f"Could not remove: '{entry}'")

    def clear_temp_files(self):
        self.logger.info("Checking for leftover temporary files...")

        pattern = "/tmp/munki-*"
        items_to_delete = glob.glob(pattern, recursive=True)

        self.logger.info(f"Found {len(items_to_delete)} item(s) to delete")
        for item in items_to_delete:
            try:
                self.logger.debug(f"Removing '{str(item)}'")
                if os.path.isdir(item):
                    os.rmdir(item)
                else:
                    os.remove(item)
            except OSError:
                self.logger.warning(f"Unable to delete '{item}'")

    def clean_repo(self):
        if not os.path.exists(self.repoclean_fpath):
            self.logger.warning("Cannot run 'repoclean', binary not found")
            return

        self.logger.info("Cleaning previous version(s) from repo...")
        try:
            run_cmd([
                self.repoclean_fpath,
                f"--keep={self.keep_versions}",
                "--auto", # Bypass confirmation prompts on deletion
                self.local_mnt
            ], self.logger)
        except subprocess.CalledProcessError:
            self.logger.error("Failed to clean repo, check your configuration!")

    def run(self):
        actions = {
            'will_clear_cache': lambda: self.clear_autopkg_cache(self.retention_period),
            'will_clear_temp': self.clear_temp_files,
            'will_clear_old_reports': lambda: self.clear_old_reports(self.retention_period),
            'will_clean_repo': self.clean_repo,
        }

        for flag, action in actions.items():
            if getattr(self, flag, False):
                action()
