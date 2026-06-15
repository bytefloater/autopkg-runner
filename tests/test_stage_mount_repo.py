"""Tests for stages.mount_repo: _build_host and MountRepository."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# -- _build_host ---------------------------------------------------------------

class TestBuildHost:
    def _repo(self, connection_type):
        repo = MagicMock()
        repo.connection_type = connection_type
        repo.host = '192.168.1.1'
        repo.server_share = 'Munki'
        repo.username = 'user'
        repo.password = 'pass'
        return repo

    def test_smb_returns_smb_host(self):
        from stages.mount_repo import _build_host
        from libs.hosts import SmbHost
        result = _build_host(self._repo('smb'))
        assert isinstance(result, SmbHost)

    def test_sftp_returns_sftp_host(self):
        from stages.mount_repo import _build_host
        from libs.hosts import SftpHost
        result = _build_host(self._repo('sftp'))
        assert isinstance(result, SftpHost)

    def test_unknown_raises_value_error(self):
        from stages.mount_repo import _build_host
        with pytest.raises(ValueError, match='Unsupported'):
            _build_host(self._repo('nfs'))


# -- MountRepository -----------------------------------------------------------

def _make_local_stage(local_path=None, tmp_path=None):
    from stages.mount_repo import MountRepository
    config = MagicMock()
    config.repository.repo_type = 'local'
    config.repository.local_path = local_path or (tmp_path or Path('/Volumes/Munki'))
    config.repository.mount_path = Path('/tmp/munki-mount')
    ctx = {'stage_outputs': {}}
    logger: MagicMock = MagicMock()
    return MountRepository(config, ctx, logger), logger


def _make_remote_stage(tmp_path):
    from stages.mount_repo import MountRepository
    config = MagicMock()
    config.repository.repo_type = 'smb'
    config.repository.local_path = tmp_path
    config.repository.mount_path = tmp_path / 'mount'
    config.repository.connection_type = 'smb'
    config.repository.host = '192.168.1.1'
    config.repository.server_share = 'Munki'
    config.repository.username = 'user'
    config.repository.password = 'pass'
    ctx = {'stage_outputs': {}}
    logger: MagicMock = MagicMock()
    mounter: MagicMock = MagicMock()
    with patch('stages.mount_repo.RemoteRepositoryMounter') as MockMounter, \
         patch('stages.mount_repo._build_host'):
        MockMounter.return_value = mounter
        stage = MountRepository(config, ctx, logger)
        stage.mounter = mounter
    return stage, logger, mounter


class TestInit:
    def test_local_repo_has_no_mounter(self, tmp_path):
        stage, _ = _make_local_stage(tmp_path)
        assert stage.mounter is None
        assert stage._is_local() is True

    def test_remote_repo_creates_mounter(self, tmp_path):
        stage, _, mounter = _make_remote_stage(tmp_path)
        assert mounter is not None

    def test_is_local_false_for_smb(self, tmp_path):
        stage, _, _ = _make_remote_stage(tmp_path)
        assert stage._is_local() is False


class TestCheckLocalPath:
    def test_returns_true_for_existing_dir(self, tmp_path):
        stage, _ = _make_local_stage(tmp_path)
        assert stage._check_local_path() is True

    def test_returns_false_for_missing_dir(self, tmp_path):
        stage, logger = _make_local_stage(tmp_path / 'nonexistent')
        assert stage._check_local_path() is False
        logger.error.assert_called()


class TestPreCheck:
    def test_local_existing_path_returns_true(self, tmp_path):
        stage, _ = _make_local_stage(tmp_path)
        assert stage.pre_check() is True

    def test_local_missing_path_returns_false(self, tmp_path):
        stage, _ = _make_local_stage(tmp_path / 'missing')
        assert stage.pre_check() is False

    def test_remote_delegates_to_mounter(self, tmp_path):
        stage, _, mounter = _make_remote_stage(tmp_path)
        mounter.is_reachable.return_value = True
        mounter.is_mount_point_available.return_value = True
        assert stage.pre_check() is True
        mounter.is_reachable.assert_called_once()

    def test_remote_not_reachable_returns_false(self, tmp_path):
        stage, _, mounter = _make_remote_stage(tmp_path)
        mounter.is_reachable.return_value = False
        mounter.is_mount_point_available.return_value = True
        assert stage.pre_check() is False


class TestRun:
    def test_local_logs_no_mount_required(self, tmp_path):
        stage, logger = _make_local_stage(tmp_path)
        stage.run()
        logger.info.assert_called()
        # mounter.mount() must not be called
        assert stage.mounter is None

    def test_remote_calls_mounter_mount(self, tmp_path):
        stage, _, mounter = _make_remote_stage(tmp_path)
        stage.run()
        mounter.mount.assert_called_once()


class TestPostCheck:
    def test_local_accessible_returns_true(self, tmp_path):
        stage, _ = _make_local_stage(tmp_path)
        assert stage.post_check() is True

    def test_local_missing_returns_false(self, tmp_path):
        stage, logger = _make_local_stage(tmp_path / 'missing')
        assert stage.post_check() is False
        logger.error.assert_called()

    def test_remote_accessible_mount_point_returns_true(self, tmp_path):
        stage, _, mounter = _make_remote_stage(tmp_path)
        mounter.mount_point = tmp_path
        assert stage.post_check() is True

    def test_remote_inaccessible_mount_point_returns_false(self, tmp_path):
        stage, _, mounter = _make_remote_stage(tmp_path)
        mounter.mount_point = tmp_path / 'nonexistent'
        assert stage.post_check() is False


class TestCleanup:
    def test_local_cleanup_is_noop(self, tmp_path):
        stage, _ = _make_local_stage(tmp_path)
        stage.cleanup()  # must not raise
        assert stage.mounter is None

    def test_remote_calls_unmount(self, tmp_path):
        stage, _, mounter = _make_remote_stage(tmp_path)
        stage.cleanup()
        mounter.unmount.assert_called_once()
