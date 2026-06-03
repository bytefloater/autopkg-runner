from pathlib import Path
from typing import Optional

from libs.stage import Stage
from libs.hosts import BaseHost, SmbHost, SftpHost, RemoteRepositoryMounter


def _build_host(repo) -> BaseHost:
    """Factory: return the correct BaseHost for the configured connection type."""
    ct = repo.connection_type
    if ct == 'smb':
        return SmbHost(
            host=repo.host,
            share=repo.server_share,
            username=repo.username,
            password=repo.password,
        )
    elif ct == 'sftp':
        return SftpHost(
            host=repo.host,
            share=repo.server_share,
            username=repo.username,
            password=repo.password,
        )
    else:
        raise ValueError(
            f"Unsupported connection_type: {repo.connection_type!r}. "
            f"Expected 'smb' or 'sftp'."
        )


class MountRepository(Stage):
    name = "Mount Repository"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        repo = config.repository
        self.repo_type  = repo.repo_type      # 'local' | 'remote'
        self.local_path = repo.local_path     # used when repo_type == 'local'
        self.mounter: Optional[RemoteRepositoryMounter] = None

        if not self._is_local():
            self.mounter = RemoteRepositoryMounter(
                mount_point=repo.mount_path,
                host=_build_host(repo),
                logger=logger,
            )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _is_local(self) -> bool:
        return self.repo_type == "local"

    def _check_local_path(self) -> bool:
        self.logger.info(f"Checking local repository path: {self.local_path}")
        if not self.local_path.is_dir():
            self.logger.error(
                f"Local repository path does not exist or is not a directory: {self.local_path}"
            )
            return False
        self.logger.info("Local repository path is accessible.")
        return True

    # ── Stage interface ───────────────────────────────────────────────────────

    def pre_check(self) -> bool:
        if self._is_local():
            return self._check_local_path()
        assert self.mounter is not None  # set in __init__ when not local
        return (
            self.mounter.is_reachable()
            and self.mounter.is_mount_point_available()
        )

    def run(self):
        if self._is_local():
            self.logger.info(
                f"Using local repository at {self.local_path} - no mounting required."
            )
            return
        assert self.mounter is not None  # set in __init__ when not local
        self.mounter.mount()

    def post_check(self) -> bool:
        """Verify the mounted/local repository is accessible as a directory."""
        if self._is_local():
            base: Path = self.local_path
        else:
            assert self.mounter is not None  # set in __init__ when not local
            base = self.mounter.mount_point

        self.logger.info("Starting repository structure check...")
        if not base.is_dir():
            self.logger.error(f"Repository base path is not accessible: {base}")
            return False

        self.logger.info("Repository structure check succeeded.")
        return True

    def cleanup(self):
        if self._is_local():
            return
        assert self.mounter is not None  # set in __init__ when not local
        self.mounter.unmount()
