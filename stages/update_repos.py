from pathlib import Path
import re
import subprocess

from libs.stage import Stage
from libs.run_command import run_cmd
from libs.intercept_logger import InterceptLogger


class UpdateRepos(Stage):
    name = "Update AutoPkg Repositories"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        self.autopkg_fpath: Path          = config.autopkg.bin_path
        self.update_before_each_run: bool = config.update_repos
        self.error_flag: bool             = False

    def run(self) -> list:
        if not self.update_before_each_run:
            self.logger.info("'update_before_each_run' flag set to False. Skipping...")
            return

        cmd_out = InterceptLogger()
        repo_urls = []

        # Capture the repo-list command output
        try:
            run_cmd([
                str(self.autopkg_fpath),
                "repo-list"
            ], cmd_out)
        except subprocess.CalledProcessError:
            self.logger.error("Could not retreive repo list")

        # Extract repo URLs
        for entry in cmd_out.entries():
            match = re.search(r'\(([^)]*)\)', entry.get("msg"))
            if match:
                # Inside parenthesis
                repo_urls.append(match.group(1))
        
        self.logger.info(f"Found {len(repo_urls)} repository URL(s)")
        self.logger.info("Updating from remote repositories...")

        # Update remote repos
        try:
            for url in repo_urls:
                run_cmd([
                    str(self.autopkg_fpath),
                    "repo-update",
                    url
                ], self.logger)
        except subprocess.CalledProcessError:
            self.logger.error(f"Failed to update repository {url}")
    
    def post_check(self):
        if self.update_before_each_run:
            if self.error_flag:
                self.logger.error("One or more repo(s) have failed to update, check logs for details")
                return False
            self.logger.info("Repo(s) updated successfully")
        return True
