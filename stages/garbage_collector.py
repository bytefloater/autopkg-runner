from datetime import datetime, timedelta
import glob
import os
from pathlib import Path
import re
import shutil

from libs.stage import Stage


class GarbageCollector(Stage):
    name = "Garbage Collector"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        self.cache_dir: Path        = config.autopkg.cache_path
        self.local_mnt: Path        = config.repository.mount_path
        self.report_dir: str        = config.repository.report_dir
        collector_settings: dict    = config.module_settings.garbage_collector

        self.retention: str         = collector_settings["retention_period"]
        self.will_clear_cache: bool = collector_settings["clear_autopkg_cache"]
        self.will_clear_temp: bool  = collector_settings["clear_temp_files"]
        self.will_clear_old_reports: bool = collector_settings["clear_old_reports"]

    def _parse_retention(self, retention: str) -> timedelta:
        """
        Parse a retention string like '7d', '12h', '1w' into a timedelta.
        Supports:
        h = hours
        d = days
        w = weeks
        """
        m = re.fullmatch(r'(\d+)([hdw])', retention)
        if not m:
            raise ValueError(
                f"Invalid retention '{retention}'. Must be e.g. '12h', '7d' or '1w'."
            )

        value, unit = int(m.group(1)), m.group(2)
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

        self.logger.info(f"Found {len(reports)} reports(s) on the repository")
        for entry in reports:
            modify_time = datetime.fromtimestamp(os.path.getmtime(entry))
            if modify_time < cutoff:
                expired.append(entry)
        
        self.logger.info(f"Marked {len(expired)} item(s) for deletion")
        for entry in expired:
            self.logger.debug(f"Removing '{entry}'")
            try:
                # os.remove(entry)
                pass
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

    def run(self):
        if self.will_clear_cache:
            self.clear_autopkg_cache(self.retention)
        if self.will_clear_temp:
            self.clear_temp_files()
        if self.will_clear_old_reports:
            self.clear_old_reports(self.retention)