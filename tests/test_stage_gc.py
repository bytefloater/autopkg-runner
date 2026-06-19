"""Tests for stages.garbage_collector.GarbageCollector."""
from __future__ import annotations

import os
import subprocess
import time
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


class TestClearAutopkgCache:
    def test_removes_expired_directories(self, tmp_path):
        gc = _make_gc()
        gc.cache_dir = tmp_path

        old_dir = tmp_path / 'OldRecipe'
        old_dir.mkdir()
        stale = time.time() - (10 * 86400)  # 10 days ago
        os.utime(old_dir, (stale, stale))

        new_dir = tmp_path / 'NewRecipe'
        new_dir.mkdir()

        gc.clear_autopkg_cache('7d')

        assert not old_dir.exists()
        assert new_dir.exists()

    def test_skips_files_not_dirs(self, tmp_path):
        gc = _make_gc()
        gc.cache_dir = tmp_path

        old_file = tmp_path / 'stale.plist'
        old_file.write_text('data')
        stale = time.time() - (10 * 86400)
        os.utime(old_file, (stale, stale))

        gc.clear_autopkg_cache('7d')

        # Non-directory entries must not be removed
        assert old_file.exists()

    def test_nothing_removed_when_all_fresh(self, tmp_path):
        gc = _make_gc()
        gc.cache_dir = tmp_path

        fresh = tmp_path / 'FreshRecipe'
        fresh.mkdir()
        # default mtime is now — within the 7d window

        gc.clear_autopkg_cache('7d')
        assert fresh.exists()


class TestGarbageCollectorRun:
    def test_calls_clear_temp_when_flag_true(self):
        gc = _make_gc()
        gc.will_clear_temp = True
        gc.will_clean_repo = False
        with patch.object(gc, 'clear_temp_files') as mock_temp, \
             patch.object(gc, 'clean_repo') as mock_clean:
            gc.run()
        mock_temp.assert_called_once()
        mock_clean.assert_not_called()

    def test_calls_clean_repo_when_flag_true(self):
        gc = _make_gc()
        gc.will_clear_temp = False
        gc.will_clean_repo = True
        with patch.object(gc, 'clear_temp_files') as mock_temp, \
             patch.object(gc, 'clean_repo') as mock_clean:
            gc.run()
        mock_clean.assert_called_once()
        mock_temp.assert_not_called()

    def test_calls_both_when_both_flags_true(self):
        gc = _make_gc()
        gc.will_clear_temp = True
        gc.will_clean_repo = True
        with patch.object(gc, 'clear_temp_files') as mock_temp, \
             patch.object(gc, 'clean_repo') as mock_clean:
            gc.run()
        mock_temp.assert_called_once()
        mock_clean.assert_called_once()
