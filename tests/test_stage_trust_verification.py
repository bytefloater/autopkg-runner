"""Tests for stages.trust_verification.TrustVerification."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_stage(recipe_file_path=None):
    from stages.trust_verification import TrustVerification
    config = MagicMock()
    config.autopkg.bin_path = Path('/usr/local/bin/autopkg')
    config.autopkg.recipe_list = recipe_file_path or '/tmp/recipes.txt'
    ctx = {'stage_outputs': {}}
    logger = MagicMock()
    return TrustVerification(config, ctx, logger)


class TestTrustVerificationInit:
    def test_sets_paths(self):
        stage = _make_stage('/some/path/recipes.txt')
        assert stage.autopkg_fpath == Path('/usr/local/bin/autopkg')
        assert stage.recipe_fpath == '/some/path/recipes.txt'


class TestTrustVerificationRun:
    def test_all_pass_returns_empty_list(self, tmp_path):
        rfile = tmp_path / 'recipes.txt'
        rfile.write_text('Firefox.munki\nChrome.pkg\n')
        stage = _make_stage(str(rfile))
        with patch('stages.trust_verification.run_cmd') as mock_cmd:
            result = stage.run()
        assert result == []
        assert mock_cmd.call_count == 2

    def test_empty_file_returns_empty_list(self, tmp_path):
        rfile = tmp_path / 'recipes.txt'
        rfile.write_text('')
        stage = _make_stage(str(rfile))
        with patch('stages.trust_verification.run_cmd') as mock_cmd:
            result = stage.run()
        assert result == []
        mock_cmd.assert_not_called()

    def test_failed_verify_triggers_update(self, tmp_path):
        rfile = tmp_path / 'recipes.txt'
        rfile.write_text('Firefox.munki\n')
        stage = _make_stage(str(rfile))

        def _cmd(args, logger):
            if 'verify-trust-info' in args:
                raise subprocess.CalledProcessError(1, args)
            # update-trust-info succeeds silently

        with patch('stages.trust_verification.run_cmd', side_effect=_cmd):
            result = stage.run()
        assert result == ['Firefox.munki']

    def test_failed_update_raises_runtime_error(self, tmp_path):
        rfile = tmp_path / 'recipes.txt'
        rfile.write_text('Firefox.munki\n')
        stage = _make_stage(str(rfile))
        # Both verify and update fail
        with patch('stages.trust_verification.run_cmd',
                   side_effect=subprocess.CalledProcessError(1, 'autopkg')):
            with pytest.raises(RuntimeError, match='trust information'):
                stage.run()

    def test_multiple_failures_all_updated(self, tmp_path):
        rfile = tmp_path / 'recipes.txt'
        rfile.write_text('Firefox.munki\nChrome.pkg\n')
        stage = _make_stage(str(rfile))
        update_calls = []

        def _cmd(args, logger):
            if 'verify-trust-info' in args:
                raise subprocess.CalledProcessError(1, args)
            update_calls.append(args[-1])  # last arg is the recipe name

        with patch('stages.trust_verification.run_cmd', side_effect=_cmd):
            result = stage.run()
        assert set(result) == {'Firefox.munki', 'Chrome.pkg'}
        assert len(update_calls) == 2

    def test_only_failed_recipes_in_result(self, tmp_path):
        rfile = tmp_path / 'recipes.txt'
        rfile.write_text('Firefox.munki\nChrome.pkg\n')
        stage = _make_stage(str(rfile))

        def _cmd(args, logger):
            # Only Firefox fails verify
            if 'verify-trust-info' in args and 'Firefox' in args[-1]:
                raise subprocess.CalledProcessError(1, args)

        with patch('stages.trust_verification.run_cmd', side_effect=_cmd):
            result = stage.run()
        assert result == ['Firefox.munki']
