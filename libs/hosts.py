"""
libs/hosts.py
-------------
Protocol-agnostic host abstractions for remote repository mounting.

Classes
-------
BaseHost            ABC - common interface for all host types.
SmbHost             SMB/CIFS via macOS mount_smbfs.
SftpHost            SFTP via sshfs (requires macFUSE + sshfs-mac).
RemoteRepositoryMounter
                    Wraps a BaseHost; manages mount-point directory lifecycle
                    so MountRepository stays protocol-agnostic.
"""

import ipaddress
import os
import socket
import subprocess
import urllib.parse
from abc import ABC, abstractmethod
from pathlib import Path

from libs.mdns import ZeroConfigResolver, is_ipv4
from libs.run_command import run_cmd


# -- Base interface ------------------------------------------------------------

class BaseHost(ABC):
    """Common interface that every remote-host type must implement."""

    @abstractmethod
    def resolve(self, logger) -> str:
        """Resolve the configured hostname to a routable IPv4 address string."""

    @abstractmethod
    def is_reachable(self, logger) -> bool:
        """Return True if the server's primary port is open and connectable."""

    @abstractmethod
    def connect(self, mount_point: Path, logger) -> None:
        """Mount the remote share at *mount_point*.

        Raises RuntimeError (or a subclass) on failure.  The caller is
        responsible for creating the mount-point directory beforehand.
        """

    @abstractmethod
    def disconnect(self, mount_point: Path, logger) -> None:
        """Unmount the remote share.

        Must not raise - log warnings instead so cleanup always completes.
        """


# -- SMB -----------------------------------------------------------------------

class SmbHost(BaseHost):
    """SMB/CIFS repository host.

    Mounts using macOS's built-in ``mount_smbfs`` command.  Host resolution
    supports both raw IPv4 addresses and zero-config mDNS names via the
    ``_smb._tcp`` service type.
    """

    _SERVICE_TYPE = "_smb._tcp"
    _PORT = 445

    def __init__(self, host: str, share: str, username: str, password: str) -> None:
        self.host     = host
        self.share    = share
        self.username = username
        self.password = password

    # -- BaseHost interface ----------------------------------------------------

    def resolve(self, logger) -> str:
        if is_ipv4(self.host):
            return self.host

        resolver = ZeroConfigResolver()
        all_results = resolver.resolve_service(
            name=self.host,
            service_type=self._SERVICE_TYPE,
        )
        result  = resolver.pick_best_result(all_results)
        address = next(iter(result.get("addresses", [])), "")
        return address

    def is_reachable(self, logger) -> bool:
        if is_ipv4(self.host):
            logger.info("Detected IPv4 address, skipping zero-config resolution...")
            addr = self.host
        else:
            logger.info(f"Checking if the server host can be resolved... ({self.host})")
            addr = self.resolve(logger)
            if not is_ipv4(addr):
                logger.error("Resolution failed.")
                return False
            logger.info(f"Resolution succeeded, will use '{addr}' to connect...")

        return self._check_port(addr, logger)

    def connect(self, mount_point: Path, logger) -> None:
        addr = self.resolve(logger)
        try:
            run_cmd([
                "mount_smbfs",
                self._build_url(addr),
                str(mount_point),
            ], logger)
        except subprocess.CalledProcessError as err:
            raise RuntimeError("mount_smbfs failed") from err

    def disconnect(self, mount_point: Path, logger) -> None:
        try:
            logger.info("Unmounting SMB share...")
            run_cmd(["umount", str(mount_point)], logger)
        except subprocess.CalledProcessError as err:
            logger.warning(str(err))

    # -- Helpers --------------------------------------------------------------

    def _check_port(self, addr_str: str, logger, timeout: int = 10) -> bool:
        addr = ipaddress.ip_address(addr_str)
        if not isinstance(addr, ipaddress.IPv4Address):
            raise TypeError("Connection address must be of type ipaddress.IPv4Address")

        logger.info(f"Checking server availability... ({addr_str}:{self._PORT})")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex((addr_str, self._PORT))
        except socket.timeout:
            logger.error(
                f"Server '{addr_str}' is not reachable: connection timed out after {timeout}s"
            )
            return False
        finally:
            sock.close()

        if result == 0:
            logger.info(f"Server '{addr_str}' is available.")
            return True

        logger.error(
            f"Server '{addr_str}' is not reachable on port {self._PORT} (error code {result})"
        )
        return False

    def _build_url(self, addr: str) -> str:
        repo_url = f"//{self.username}:{self.password}@{addr}/{self.share}"
        return urllib.parse.quote(repo_url, safe="/:@")


# -- SFTP ----------------------------------------------------------------------

class SftpHost(BaseHost):
    """SFTP repository host.

    Mounts using ``sshfs`` (from the macFUSE + ``gromgit/fuse/sshfs-mac``
    Homebrew packages).  Run ``python manage.py install_sftp_deps`` to install
    these dependencies.

    Host resolution supports both raw IPv4 addresses and zero-config mDNS names
    via the ``_ssh._tcp`` service type.

    Password authentication is handled by passing the password through the
    ``SSHPASS`` environment variable with the ``sshpass`` helper, or via
    ``SSH_ASKPASS`` when ``sshpass`` is not available.  SSH key auth can be
    added later via an optional ``key_path`` constructor argument.
    """

    _SERVICE_TYPE = "_ssh._tcp"

    def __init__(
        self,
        host: str,
        share: str,
        username: str,
        password: str,
        port: int = 22,
    ) -> None:
        self.host     = host
        self.share    = share
        self.username = username
        self.password = password
        self.port     = port

    # -- BaseHost interface ----------------------------------------------------

    def resolve(self, logger) -> str:
        if is_ipv4(self.host):
            return self.host

        resolver = ZeroConfigResolver()
        all_results = resolver.resolve_service(
            name=self.host,
            service_type=self._SERVICE_TYPE,
        )
        result  = resolver.pick_best_result(all_results)
        address = next(iter(result.get("addresses", [])), "")
        return address

    def is_reachable(self, logger) -> bool:
        if is_ipv4(self.host):
            logger.info("Detected IPv4 address, skipping zero-config resolution...")
            addr = self.host
        else:
            logger.info(f"Checking if the server host can be resolved... ({self.host})")
            addr = self.resolve(logger)
            if not is_ipv4(addr):
                logger.error("Resolution failed.")
                return False
            logger.info(f"Resolution succeeded, will use '{addr}' to connect...")

        return self._check_port(addr, logger)

    def connect(self, mount_point: Path, logger) -> None:
        addr    = self.resolve(logger)
        remote  = f"{self.username}@{addr}:{self.share}"
        env     = os.environ.copy()
        env["SSHPASS"] = self.password

        try:
            run_cmd([
                "sshpass", "-e",          # read password from SSHPASS env var
                "sshfs",
                remote,
                str(mount_point),
                "-p", str(self.port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
            ], logger)
        except subprocess.CalledProcessError as err:
            raise RuntimeError("sshfs mount failed") from err

    def disconnect(self, mount_point: Path, logger) -> None:
        try:
            logger.info("Unmounting SFTP share...")
            run_cmd(["umount", str(mount_point)], logger)
        except subprocess.CalledProcessError as err:
            logger.warning(str(err))

    # -- Helpers --------------------------------------------------------------

    def _check_port(self, addr_str: str, logger, timeout: int = 10) -> bool:
        logger.info(f"Checking server availability... ({addr_str}:{self.port})")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex((addr_str, self.port))
        except socket.timeout:
            logger.error(
                f"Server '{addr_str}' is not reachable: connection timed out after {timeout}s"
            )
            return False
        finally:
            sock.close()

        if result == 0:
            logger.info(f"Server '{addr_str}' is available.")
            return True

        logger.error(
            f"Server '{addr_str}' is not reachable on port {self.port} (error code {result})"
        )
        return False


# -- Mounter -------------------------------------------------------------------

class RemoteRepositoryMounter:
    """Protocol-agnostic coordinator for remote repository mounting.

    Wraps a *BaseHost* and owns the mount-point directory lifecycle:
    - ``mount()``   creates the directory then delegates to ``host.connect()``
    - ``unmount()`` delegates to ``host.disconnect()`` then removes the directory

    Used by ``MountRepository`` (Stage) so no protocol-specific logic lives in
    the stage itself.
    """

    def __init__(self, mount_point: Path, host: BaseHost, logger) -> None:
        self.mount_point = mount_point
        self.host        = host
        self.logger      = logger

    def is_reachable(self) -> bool:
        return self.host.is_reachable(self.logger)

    def is_mount_point_available(self) -> bool:
        self.logger.info("Checking if mount point exists...")
        if os.path.exists(self.mount_point):
            self.logger.error("Mount point already exists.")
            return False
        self.logger.info("Mount point is available.")
        return True

    def mount(self) -> None:
        os.mkdir(self.mount_point)
        try:
            self.host.connect(self.mount_point, self.logger)
        except Exception:
            # tidy up the empty directory before re-raising
            try:
                os.rmdir(self.mount_point)
            except OSError:
                pass
            raise

    def unmount(self) -> None:
        self.host.disconnect(self.mount_point, self.logger)
        try:
            self.logger.info("Removing temporary mount point...")
            os.rmdir(self.mount_point)
        except FileNotFoundError:
            self.logger.warning("Mount point was not found!")
        except OSError:
            self.logger.error(
                "The mount point is not empty - please delete it manually."
            )
