"""Tests for stages.environment_check.EnvironmentCheck."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_stage():
    from stages.environment_check import EnvironmentCheck
    config = MagicMock()
    config.autopkg.bin_path = '/usr/local/bin/autopkg'
    config.autopkg.recipe_list = '/tmp/recipe_list.txt'
    config.repository.server_share = 'Munki'
    config.repository.host = '192.168.1.1'
    ctx = {'stage_outputs': {}}
    logger: MagicMock = MagicMock()
    return EnvironmentCheck(config, ctx, logger), logger


class TestInit:
    def test_sets_attributes(self):
        stage, _ = _make_stage()
        assert stage.autopkg_fpath == '/usr/local/bin/autopkg'
        assert stage.recipe_fpath == '/tmp/recipe_list.txt'
        assert stage.server_share == 'Munki'
        assert stage.host == '192.168.1.1'
        assert stage.error_flag is False


class TestRun:
    def test_all_pass_error_flag_stays_false(self):
        stage, _ = _make_stage()
        with patch.object(stage, 'autopkg_exists', return_value=True), \
             patch.object(stage, 'recipe_file_exists', return_value=True), \
             patch.object(stage, 'is_no_mount_conflict', return_value=True):
            stage.run()
        assert stage.error_flag is False

    def test_one_failure_sets_error_flag(self):
        stage, _ = _make_stage()
        with patch.object(stage, 'autopkg_exists', return_value=False), \
             patch.object(stage, 'recipe_file_exists', return_value=True), \
             patch.object(stage, 'is_no_mount_conflict', return_value=True):
            stage.run()
        assert stage.error_flag is True

    def test_all_fail_sets_error_flag(self):
        stage, _ = _make_stage()
        with patch.object(stage, 'autopkg_exists', return_value=False), \
             patch.object(stage, 'recipe_file_exists', return_value=False), \
             patch.object(stage, 'is_no_mount_conflict', return_value=False):
            stage.run()
        assert stage.error_flag is True


class TestAutopkgExists:
    def test_returns_true_when_found(self):
        stage, logger = _make_stage()
        with patch('os.path.exists', return_value=True):
            assert stage.autopkg_exists() is True
        logger.info.assert_called()

    def test_returns_false_when_missing(self):
        stage, logger = _make_stage()
        with patch('os.path.exists', return_value=False):
            assert stage.autopkg_exists() is False
        logger.error.assert_called()


class TestRecipeFileExists:
    def test_returns_true_when_found(self):
        stage, logger = _make_stage()
        with patch('os.path.exists', return_value=True):
            assert stage.recipe_file_exists() is True
        logger.info.assert_called()

    def test_returns_false_when_missing(self):
        stage, logger = _make_stage()
        with patch('os.path.exists', return_value=False):
            assert stage.recipe_file_exists() is False
        logger.error.assert_called()


class TestIsNoMountConflict:
    def _disk(self, device):
        disk = MagicMock()
        disk._asdict.return_value = {'device': device, 'mountpoint': '/mnt'}
        return disk

    def test_no_conflict_returns_true(self):
        stage, logger = _make_stage()
        with patch('psutil.disk_partitions', return_value=[self._disk('/dev/disk1s1')]):
            assert stage.is_no_mount_conflict() is True
        logger.info.assert_called()

    def test_conflict_returns_false(self):
        stage, logger = _make_stage()
        # device contains the URL-encoded server_share ('Munki')
        with patch('psutil.disk_partitions', return_value=[self._disk('//server/Munki')]):
            assert stage.is_no_mount_conflict() is False
        logger.error.assert_called()

    def test_multiple_disks_no_conflict(self):
        stage, _ = _make_stage()
        disks = [self._disk('/dev/disk1'), self._disk('/dev/disk2')]
        with patch('psutil.disk_partitions', return_value=disks):
            assert stage.is_no_mount_conflict() is True


class TestPostCheck:
    def test_returns_true_when_no_error(self):
        stage, logger = _make_stage()
        stage.error_flag = False
        assert stage.post_check() is True
        logger.info.assert_called()

    def test_returns_false_when_error(self):
        stage, logger = _make_stage()
        stage.error_flag = True
        assert stage.post_check() is False
        logger.error.assert_called()
