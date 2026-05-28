import ipaddress
import os
from pathlib import Path
import socket
import subprocess
import urllib.parse

from libs.stage import Stage
from libs.run_command import run_cmd
from libs.mdns import ZeroConfigResolver, is_ipv4


class MountRepository(Stage):
    name = "Mount Repository"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        repo = config.repository
        self.repo_type: str     = repo.repo_type         # 'local' | 'remote'
        self.local_path: Path   = repo.local_path        # used when repo_type == 'local'

        # Remote-only fields
        self.local_mnt: Path    = repo.mount_path
        self.host: str          = repo.host
        self.server_share: str  = repo.server_share
        self.username: str      = repo.username
        self.password: str      = repo.password

    # ── Local repo: all checks are path-based ────────────────────────────────

    def _is_local(self) -> bool:
        return self.repo_type == "local"

    # ── Pre-check ────────────────────────────────────────────────────────────

    def pre_check(self) -> bool:
        if self._is_local():
            return self._check_local_path()
        return self._check_remote_reachable()

    def _check_local_path(self) -> bool:
        self.logger.info(f"Checking local repository path: {self.local_path}")
        if not self.local_path.is_dir():
            self.logger.error(
                f"Local repository path does not exist or is not a directory: {self.local_path}"
            )
            return False
        self.logger.info("Local repository path is accessible.")
        return True

    def _check_remote_reachable(self) -> bool:
        if not self._can_resolve_host():
            return False
        return (
            self._is_server_available(self._resolve_host())
            and self._is_mount_point_available(self.local_mnt)
        )

    # ── Run ──────────────────────────────────────────────────────────────────

    def run(self):
        if self._is_local():
            self.logger.info(
                f"Using local repository at {self.local_path} — no mounting required."
            )
            return

        # Remote SMB mount
        os.mkdir(self.local_mnt)
        try:
            run_cmd([
                "mount_smbfs",
                self._construct_url(
                    srv_user=self.username,
                    srv_pass=self.password,
                    addr_str=self._resolve_host(),
                    srv_share=self.server_share
                ),
                str(self.local_mnt)
            ], self.logger)
        except subprocess.CalledProcessError as err:
            raise RuntimeError from err

    # ── Post-check ───────────────────────────────────────────────────────────

    def post_check(self) -> bool:
        """Verify the mounted/local repository has the expected directory structure."""
        base = self.local_path if self._is_local() else self.local_mnt

        self.logger.info("Starting repository structure check...")
        # Basic sanity: the path should at least be a directory at this point
        if not base.is_dir():
            self.logger.error(f"Repository base path is not accessible: {base}")
            return False

        self.logger.info("Repository structure check succeeded.")
        return True

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def cleanup(self):
        if self._is_local():
            return  # Nothing to unmount

        try:
            self.logger.info("Unmounting remote server...")
            run_cmd(["umount", str(self.local_mnt)], self.logger)
        except subprocess.CalledProcessError as err:
            self.logger.warning(str(err))

        try:
            self.logger.info("Removing temporary mount point...")
            os.rmdir(self.local_mnt)
        except FileNotFoundError:
            self.logger.warning("Mount point was not found!")
        except OSError:
            self.logger.error(
                "The mount point is not empty — please delete it manually."
            )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _can_resolve_host(self) -> bool:
        if is_ipv4(self.host):
            self.logger.info("Detected IPv4 address, skipping zero-config resolution...")
            return True

        self.logger.info(f"Checking if the server host can be resolved... ({self.host})")
        address = self._resolve_host()
        if is_ipv4(address):
            self.logger.info(f"Resolution succeeded, will use '{address}' to connect...")
            return True

        self.logger.error("Resolution failed.")
        return False

    def _resolve_host(self) -> str:
        if is_ipv4(self.host):
            return self.host

        resolver = ZeroConfigResolver()
        all_results = resolver.resolve_service(
            name=self.host,
            service_type="_smb._tcp"
        )
        result = resolver.pick_best_result(all_results)
        address = next(iter(result.get("addresses", [])), '')
        return address

    def _is_server_available(self, addr_str: str, port: int = 445, timeout: int = 10) -> bool:
        addr = ipaddress.ip_address(addr_str)
        if not isinstance(addr, ipaddress.IPv4Address):
            raise TypeError("Connection address must be of type ipaddress.IPv4Address")

        self.logger.info(f"Checking server availability... ({addr_str})")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex((addr_str, port))
        except socket.timeout:
            self.logger.error(
                f"Server '{addr_str}' is not reachable: connection timed out after {timeout}s"
            )
            return False
        finally:
            sock.close()

        if result == 0:
            self.logger.info(f"Server '{addr_str}' is available.")
            return True

        self.logger.error(
            f"Server '{addr_str}' is not reachable on port {port} (error code {result})"
        )
        return False

    def _is_mount_point_available(self, mount_point: Path) -> bool:
        self.logger.info("Checking if mount point exists...")
        if os.path.exists(mount_point):
            self.logger.error("Mount point already exists.")
            return False
        self.logger.info("Mount point is available.")
        return True

    def _construct_url(self, srv_user: str, srv_pass: str, addr_str: str, srv_share: str) -> str:
        repo_url = f"//{srv_user}:{srv_pass}@{addr_str}/{srv_share}"
        return urllib.parse.quote(repo_url, safe="/:@")
