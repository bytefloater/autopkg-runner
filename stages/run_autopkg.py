import os
import plistlib
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Any

from libs.stage import Stage
from libs.run_command import run_cmd
from stages import TrustVerification


class RunAutoPkg(Stage):
    name = "Run AutoPkg"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        self.autopkg_fpath: Path = config.autopkg.bin_path
        self.recipe_fpath: Path  = config.autopkg.recipe_list
        self.local_mnt: Path     = config.repository.mount_path

        # Temporary file used for autopkg's --report-plist output.
        # Created fresh each run; cleaned up in cleanup().
        self._tmp_plist = None

    def run(self) -> Optional[Any]:
        recipes = []
        with open(self.recipe_fpath, 'r', encoding='utf-8') as recipe_file:
            for recipe in recipe_file:
                recipes.append(recipe.strip())
        if not recipes:
            raise RuntimeError("Unable to load recipe(s)")

        # Use a named temp file so autopkg can write to it by path.
        # delete=False because autopkg writes it; we read it afterwards.
        self._tmp_plist = tempfile.NamedTemporaryFile(
            suffix='.plist', delete=False
        )
        self._tmp_plist.close()

        run_id = self.ctx.get('run_id')
        try:
            from webapp.runner import register_active_proc, unregister_active_proc

            def _on_proc(proc):
                if run_id:
                    register_active_proc(str(run_id), proc)

            run_cmd([
                str(self.autopkg_fpath),
                "run",
                *recipes,
                "--report-plist",
                self._tmp_plist.name,
                "-q",
                "-k",
                f"MUNKI_REPO={self.local_mnt}"
            ], self.logger, on_proc=_on_proc)
        except subprocess.CalledProcessError as err:
            self.logger.error("Some recipes failed to execute: " + str(err))
        finally:
            if run_id:
                unregister_active_proc(str(run_id))

        self._write_recipe_results()

    def _write_recipe_results(self):
        """Parse the autopkg report plist and write RecipeResult rows to the DB."""
        run_id = self.ctx.get('run_id')
        if not run_id or not self._tmp_plist:
            return

        try:
            with open(self._tmp_plist.name, 'rb') as f:
                plist_data = plistlib.load(f)
        except Exception as exc:
            self.logger.warning(f'Could not read autopkg report plist: {exc}')
            return

        if not plist_data:
            return

        try:
            from webapp.models import RecipeResult

            updated_recipes = self.ctx.get('stage_outputs', {}).get(TrustVerification)

            def _section(key):
                try:
                    obj = plist_data['summary_results'][key]
                    return {'summary_text': obj['summary_text'], 'data_rows': obj['data_rows']}
                except KeyError:
                    return {}

            def _trust_section():
                if not isinstance(updated_recipes, list) or not updated_recipes:
                    return {}
                return {
                    'summary_text': 'The following recipes have updated trust information:',
                    'data_rows': [{'recipe': r} for r in updated_recipes],
                }

            type_map = {
                'failure':        {'summary_text': 'The following failures occurred:',
                                   'data_rows': plist_data.get('failures', [])},
                'munki_import':   _section('munki_importer_summary_result'),
                'pkg_copied':     _section('pkg_copier_summary_result'),
                'url_downloaded': _section('url_downloader_summary_result'),
                'deprecation':    _section('deprecation_summary_result'),
                'trust_updated':  _trust_section(),
            }

            for result_type, section in type_map.items():
                rows = section.get('data_rows', []) if isinstance(section, dict) else []
                if rows:
                    RecipeResult.objects.create(
                        run_id=run_id,
                        result_type=result_type,
                        data=rows,
                    )
        except Exception as exc:
            self.logger.warning(f'Could not write recipe results to DB: {exc}')

    def cleanup(self):
        if self._tmp_plist and os.path.exists(self._tmp_plist.name):
            try:
                os.unlink(self._tmp_plist.name)
            except OSError:
                pass
        self._tmp_plist = None
