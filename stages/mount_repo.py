import ipaddress
import os
from pathlib import Path
import socket
import subprocess
import urllib.parse

from libs.stage import Stage
from libs.run_command import run_cmd


class MountRepository(Stage):
    name = "Mount Remote Repository"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        self.local_mnt: Path        = config.repository.mount_path
        self.server_addr: str       = config.repository.server_address
        self.server_share: str      = config.repository.server_share
        self.username: str          = config.repository.username
        self.password: str          = config.repository.password
        self.check_dirs: list       = config.repository.check_dirs

    def pre_check(self) -> bool:
        self.conditions = [
            self._is_server_available(self.server_addr),
            self._is_mount_point_available(self.local_mnt)
        ]
        return all(self.conditions)
    
    def run(self):
        os.mkdir(self.local_mnt)
        try:
            run_cmd([
                "mount_smbfs",
                self._construct_url(
                    srv_user=self.username,
                    srv_pass=self.password,
                    addr_str=self.server_addr,
                    srv_share=self.server_share
                ),
                self.local_mnt
            ], self.logger)
        except subprocess.CalledProcessError as err:
            raise RuntimeError from err

    def post_check(self):
        """Check for the presence of the directories that the remote repository should have"""
        self.logger.info("Starting repository structure check...")

        for _dir in self.check_dirs:
            self.logger.debug(f"Checking for: /{_dir}")

            test_path = f"{self.local_mnt}/{_dir}"
            if not os.path.isdir(test_path):
                self.logger.error(f"Unable to find: {_dir}")
                return False

        self.logger.info("Repository structure check succeeded")
        return True

    def cleanup(self):
        try:
            self.logger.info("Unmounting remote server...")
            run_cmd([
                "umount",
                self.local_mnt
            ], self.logger)
        except subprocess.CalledProcessError as err:
            self.logger.warning(str(err))

        try:
            self.logger.info("Removing temporary mount point...")
            os.rmdir(self.local_mnt)
        except FileNotFoundError:
            self.logger.warning("Mount point was not found!")
        except OSError:
            self.logger.error("The mount point specified is not an empty directory, please delete it manually.")

    def _is_server_available(self, addr_str: str, port=445) -> bool:
        addr = ipaddress.ip_address(addr_str)
        if not isinstance(addr, ipaddress.IPv4Address):
            raise TypeError("Connection address must be of type ipaddress.IPv4Address")

        self.logger.info(f"Checking server availability... ({addr_str})")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((addr_str, port))

        if result == 0:
            self.logger.info(f"Server '{addr_str}' is available")
            return True
        return False

    def _is_mount_point_available(self, mount_point) -> bool:
        self.logger.info("Checking if mount point exists...")
        if os.path.exists(mount_point):
            self.logger.error("Mount point already exists")
            return False

        self.logger.info("Mount point not in use")
        return True
    
    def _construct_url(self, srv_user, srv_pass, addr_str, srv_share):
        repo_url = f"//{srv_user}:{srv_pass}@{addr_str}/{srv_share}"
        return urllib.parse.quote(repo_url, safe="/:@")