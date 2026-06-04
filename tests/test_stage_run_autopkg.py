"""Tests for stages.run_autopkg.RunAutoPkg."""
from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_stage(tmp_path, recipe_lines='Firefox.munki\n'):
    from stages.run_autopkg import RunAutoPkg
    rfile = tmp_path / 'recipes.txt'
    rfile.write_text(recipe_lines)
    config = MagicMock()
    config.autopkg.bin_path = Path('/usr/local/bin/autopkg')
    config.autopkg.recipe_list = str(rfile)
    config.repository.mount_path = Path('/tmp/munki-repo')
    ctx = {'stage_outputs': {}}
    logger = MagicMock()
    return RunAutoPkg(config, ctx, logger)


# -- __init__ ------------------------------------------------------------------

class TestInit:
    def test_attributes_set(self, tmp_path):
        stage = _make_stage(tmp_path)
        assert stage.autopkg_fpath == Path('/usr/local/bin/autopkg')
        assert stage._tmp_plist is None


# -- run() ---------------------------------------------------------------------

class TestRun:
    def test_calls_autopkg_with_recipes(self, tmp_path):
        stage = _make_stage(tmp_path, 'Firefox.munki\n')
        with patch('stages.run_autopkg.run_cmd') as mock_cmd, \
             patch.object(stage, '_write_recipe_results'):
            stage.run()
        assert mock_cmd.call_count == 1
        cmd_args = mock_cmd.call_args[0][0]
        assert 'run' in cmd_args
        assert 'Firefox.munki' in cmd_args

    def test_empty_recipe_file_raises(self, tmp_path):
        stage = _make_stage(tmp_path, '')
        with pytest.raises(RuntimeError, match='recipe'):
            stage.run()

    def test_blank_lines_stripped(self, tmp_path):
        stage = _make_stage(tmp_path, 'Firefox.munki\n\nChrome.pkg\n')
        with patch('stages.run_autopkg.run_cmd') as mock_cmd, \
             patch.object(stage, '_write_recipe_results'):
            stage.run()
        cmd_args = mock_cmd.call_args[0][0]
        # Empty string from blank line should still be there (stripping is internal)
        assert 'Firefox.munki' in cmd_args

    def test_called_process_error_is_logged_not_raised(self, tmp_path):
        stage = _make_stage(tmp_path)
        with patch('stages.run_autopkg.run_cmd',
                   side_effect=subprocess.CalledProcessError(1, 'autopkg')), \
             patch.object(stage, '_write_recipe_results'):
            stage.run()  # must not raise
        stage.logger.error.assert_called()

    def test_tmp_plist_created_and_passed_to_autopkg(self, tmp_path):
        stage = _make_stage(tmp_path)
        with patch('stages.run_autopkg.run_cmd') as mock_cmd, \
             patch.object(stage, '_write_recipe_results'):
            stage.run()
        cmd_args = mock_cmd.call_args[0][0]
        assert '--report-plist' in cmd_args


# -- _write_recipe_results() ---------------------------------------------------

class TestWriteRecipeResults:
    def test_returns_early_without_run_id(self, tmp_path):
        stage = _make_stage(tmp_path)
        stage._tmp_plist = MagicMock()
        # ctx has no 'run_id'
        stage._write_recipe_results()  # should not raise or write to DB

    def test_returns_early_without_plist(self, tmp_path):
        stage = _make_stage(tmp_path)
        stage.ctx['run_id'] = 'some-id'
        stage._tmp_plist = None
        stage._write_recipe_results()  # should not raise

    def test_handles_unreadable_plist(self, tmp_path):
        stage = _make_stage(tmp_path)
        stage.ctx['run_id'] = 'some-id'
        tmp = MagicMock()
        tmp.name = str(tmp_path / 'nonexistent.plist')
        stage._tmp_plist = tmp
        stage._write_recipe_results()  # should log warning
        stage.logger.warning.assert_called()

    def test_returns_early_on_empty_plist(self, tmp_path):
        stage = _make_stage(tmp_path)
        stage.ctx['run_id'] = 'some-id'
        pfile = tmp_path / 'report.plist'
        with open(pfile, 'wb') as f:
            plistlib.dump({}, f)
        tmp = MagicMock()
        tmp.name = str(pfile)
        stage._tmp_plist = tmp
        stage._write_recipe_results()  # no DB writes expected; no DB access needed

    @pytest.mark.django_db
    def test_writes_failures_and_imports_to_db(self, tmp_path):
        from webapp.models import Run, RecipeResult
        run = Run.objects.create(status='running', triggered_by='test', config_snapshot={})
        stage = _make_stage(tmp_path)
        stage.ctx['run_id'] = run.pk
        plist_data = {
            'failures': [{'recipe_id': 'Broken.munki', 'message': 'oops'}],
            'summary_results': {
                'munki_importer_summary_result': {
                    'summary_text': 'Imported:',
                    'data_rows': [{'name': 'Firefox', 'version': '120.0'}],
                },
                'url_downloader_summary_result': {
                    'summary_text': 'Downloaded:',
                    'data_rows': [{'url': 'https://example.com/file.dmg'}],
                },
            },
        }
        pfile = tmp_path / 'report.plist'
        with open(pfile, 'wb') as f:
            plistlib.dump(plist_data, f)
        tmp = MagicMock()
        tmp.name = str(pfile)
        stage._tmp_plist = tmp
        stage._write_recipe_results()
        types = set(RecipeResult.objects.filter(run=run).values_list('result_type', flat=True))
        assert 'failure' in types
        assert 'munki_import' in types
        assert 'url_downloaded' in types

    @pytest.mark.django_db
    def test_trust_section_written_when_recipes_updated(self, tmp_path):
        from webapp.models import Run, RecipeResult
        from stages import TrustVerification
        run = Run.objects.create(status='running', triggered_by='test', config_snapshot={})
        stage = _make_stage(tmp_path)
        stage.ctx['run_id'] = run.pk
        stage.ctx['stage_outputs'] = {TrustVerification: ['Firefox.munki']}
        pfile = tmp_path / 'report.plist'
        with open(pfile, 'wb') as f:
            plistlib.dump({'summary_results': {}}, f)
        tmp = MagicMock()
        tmp.name = str(pfile)
        stage._tmp_plist = tmp
        stage._write_recipe_results()
        types = set(RecipeResult.objects.filter(run=run).values_list('result_type', flat=True))
        assert 'trust_updated' in types


# -- cleanup() -----------------------------------------------------------------

class TestCleanup:
    def test_removes_temp_file(self, tmp_path):
        stage = _make_stage(tmp_path)
        pfile = tmp_path / 'report.plist'
        pfile.write_bytes(b'')
        tmp = MagicMock()
        tmp.name = str(pfile)
        stage._tmp_plist = tmp
        stage.cleanup()
        assert not pfile.exists()
        assert stage._tmp_plist is None

    def test_handles_already_removed_file(self, tmp_path):
        stage = _make_stage(tmp_path)
        tmp = MagicMock()
        tmp.name = str(tmp_path / 'gone.plist')  # never existed
        stage._tmp_plist = tmp
        stage.cleanup()  # must not raise
        assert stage._tmp_plist is None

    def test_noop_when_no_plist(self, tmp_path):
        stage = _make_stage(tmp_path)
        stage._tmp_plist = None
        stage.cleanup()  # must not raise
        assert stage._tmp_plist is None
