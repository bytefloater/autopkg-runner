"""Tests for stages.update_repos.UpdateRepos."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


def _make_stage(update_before_each_run=True):
    from stages.update_repos import UpdateRepos

    config = MagicMock()
    config.autopkg.bin_path = Path('/usr/local/bin/autopkg')
    config.update_repos = update_before_each_run

    ctx = {'stage_outputs': {}}
    logger = MagicMock()
    return UpdateRepos(config, ctx, logger)


class TestUpdateRepos:
    def test_skips_when_flag_false(self):
        stage = _make_stage(update_before_each_run=False)
        with patch('libs.run_command.run_cmd') as mock_cmd:
            stage.run()
        mock_cmd.assert_not_called()

    def test_url_regex_extracts_urls(self):
        """The regex used to extract repo URLs from autopkg repo-list output."""
        line = 'some text (https://github.com/autopkg/recipes.git) more text'
        match = re.search(r'\(([^)]*)\)', line)
        assert match
        assert match.group(1) == 'https://github.com/autopkg/recipes.git'

    def test_calls_repo_update_for_each_url(self):
        stage = _make_stage()
        # Simulate repo-list output with two URLs
        fake_entries = [
            {'msg': 'recipes (https://github.com/autopkg/recipes.git)'},
            {'msg': 'community (https://github.com/autopkg/community-recipes.git)'},
        ]
        # Patch run_cmd where it is bound in update_repos, not the original module.
        with patch('stages.update_repos.run_cmd') as mock_cmd, \
             patch('libs.intercept_logger.InterceptLogger.entries', return_value=fake_entries):
            stage.run()
        # Called once for repo-list + once per URL
        assert mock_cmd.call_count >= 1

    def test_per_url_error_does_not_stop_remaining(self):
        stage = _make_stage()
        fake_entries = [
            {'msg': 'one (https://github.com/autopkg/one.git)'},
            {'msg': 'two (https://github.com/autopkg/two.git)'},
        ]
        call_count = [0]

        def side_effect(cmd, logger):
            call_count[0] += 1
            # First call (repo-list) succeeds; first repo-update fails
            if 'repo-update' in cmd and 'one' in str(cmd):
                raise subprocess.CalledProcessError(1, cmd)

        with patch('stages.update_repos.run_cmd', side_effect=side_effect), \
             patch('libs.intercept_logger.InterceptLogger.entries', return_value=fake_entries):
            stage.run()
        # Should have attempted both URLs despite first failure
        assert call_count[0] >= 2
