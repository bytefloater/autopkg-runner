"""Tests for stages.garbage_collector.GarbageCollector."""
from __future__ import annotations

import subprocess
from datetime import timedelta
from typing import cast
from unittest.mock import MagicMock
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


def _make_gc(config_overrides=None):
    """Return a GarbageCollector with a mocked config."""
    from stages.garbage_collector import GarbageCollector

    config = MagicMock()
    config.autopkg.cache_path = Path('/tmp/autopkg-cache')
    config.repository.mount_path = Path('/tmp/munki')
    config.garbage_collector.repoclean_bin_path = '/usr/local/munki/repoclean'
    config.garbage_collector.keep_versions = 3
    config.garbage_collector.clear_temp = True
    config.garbage_collector.clean_repo = True

    if config_overrides:
        for attr_path, value in config_overrides.items():
            parts = attr_path.split('.')
            obj = config
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], value)

    ctx = {'stage_outputs': {}}
    logger = MagicMock()
    gc = GarbageCollector(config, ctx, logger)
    return gc


class TestParseRetention:
    def _call(self, retention):
        gc = _make_gc()
        return gc._parse_retention(retention)

    def test_days(self):
        assert self._call('7d') == timedelta(days=7)

    def test_hours(self):
        assert self._call('12h') == timedelta(hours=12)

    def test_weeks(self):
        assert self._call('2w') == timedelta(weeks=2)

    def test_single_day(self):
        assert self._call('1d') == timedelta(days=1)

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError):
            self._call('bad')

    def test_invalid_unit_raises_value_error(self):
        with pytest.raises(ValueError):
            self._call('5m')  # minutes not supported

    def test_no_number_raises_value_error(self):
        with pytest.raises(ValueError):
            self._call('d')


class TestClearTempFiles:
    def test_removes_matching_files(self):
        gc = _make_gc()
        with patch('glob.glob', return_value=['/tmp/munki-abc123', '/tmp/munki-def456']), \
             patch('os.path.isdir', return_value=False), \
             patch('os.remove') as mock_remove, \
             patch('os.rmdir') as mock_rmdir:
            gc.clear_temp_files()
        assert mock_remove.call_count == 2

    def test_removes_matching_dirs(self):
        gc = _make_gc()
        with patch('glob.glob', return_value=['/tmp/munki-dir']), \
             patch('os.path.isdir', return_value=True), \
             patch('os.rmdir') as mock_rmdir, \
             patch('os.remove') as mock_remove:
            gc.clear_temp_files()
        mock_rmdir.assert_called_once_with('/tmp/munki-dir')
        mock_remove.assert_not_called()

    def test_oserror_on_removal_is_caught(self):
        gc = _make_gc()
        with patch('glob.glob', return_value=['/tmp/munki-locked']), \
             patch('os.path.isdir', return_value=False), \
             patch('os.remove', side_effect=OSError('locked')):
            # Should not raise; should log a warning
            gc.clear_temp_files()
        cast(MagicMock, gc.logger).warning.assert_called()


class TestCleanRepo:
    def test_skips_if_binary_not_found(self):
        gc = _make_gc()
        # Patch run_cmd in the module where it is imported, not the original.
        with patch('os.path.exists', return_value=False), \
             patch('stages.garbage_collector.run_cmd') as mock_cmd:
            gc.clean_repo()
        mock_cmd.assert_not_called()
        cast(MagicMock, gc.logger).warning.assert_called()

    def test_calls_repoclean_with_correct_args(self):
        gc = _make_gc()
        with patch('os.path.exists', return_value=True), \
             patch('stages.garbage_collector.run_cmd') as mock_cmd:
            gc.clean_repo()
        mock_cmd.assert_called_once()
        cmd_args = mock_cmd.call_args[0][0]
        assert '--keep=3' in cmd_args
        assert '--auto' in cmd_args

    def test_called_process_error_is_caught(self):
        gc = _make_gc()
        with patch('os.path.exists', return_value=True), \
             patch('stages.garbage_collector.run_cmd', side_effect=subprocess.CalledProcessError(1, 'repoclean')):
            gc.clean_repo()  # should not raise
        cast(MagicMock, gc.logger).error.assert_called()
