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

    # -- Helpers --------------------------------------------------------------

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

    # -- Stage interface -------------------------------------------------------

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
        """Verify the mounted/local repository is accessible and readable.

        Checks more than just directory existence: after mounting, the mount-point
        directory is always stat-able (it was created by os.mkdir before the mount),
        so is_dir() alone gives a false positive when the SMB session cannot actually
        deliver file content.  We therefore also verify that the directory can be
        listed and that at least one file inside it is openable.
        """
        if self._is_local():
            base: Path = self.local_path
        else:
            assert self.mounter is not None  # set in __init__ when not local
            base = self.mounter.mount_point

        self.logger.info("Starting repository structure check...")
        if not base.is_dir():
            self.logger.error(f"Repository base path is not accessible: {base}")
            return False

        # Resolve symlinks before any VFS operation.  /tmp is a symlink to
        # /private/tmp on macOS; resolving ensures consistent path handling.
        resolved = base.resolve()

        # Verify we can list the directory contents (not just stat the root).
        try:
            entries = list(resolved.iterdir())
        except OSError as exc:
            self.logger.error(f"Repository is mounted but its contents cannot be listed: {exc}")
            return False

        # Verify we can open and read at least one file from within the share.
        # This catches permission issues that only materialise on actual I/O,
        # not on directory stat calls.
        #
        # Munki repos have no files at the root (only catalogs/, pkgs/, etc.),
        # so fall back to a one-level-deep search when the root itself is file-free.
        first_file = next((e for e in entries if e.is_file()), None)
        if first_file is None:
            for subdir in (e for e in entries if e.is_dir()):
                try:
                    first_file = next(
                        (e for e in subdir.iterdir() if e.is_file()),
                        None,
                    )
                except OSError:
                    continue
                if first_file is not None:
                    break

        if first_file is not None:
            try:
                with first_file.open('rb') as fh:
                    fh.read(1)
            except OSError as exc:
                self.logger.error(f"Repository is mounted but files cannot be read: {exc}")
                return False

        self.logger.info("Repository structure check succeeded.")
        return True

    def cleanup(self):
        if self._is_local():
            return
        assert self.mounter is not None  # set in __init__ when not local
        self.mounter.unmount()
