import datetime
import os
from pathlib import Path
import plistlib

import django
import django.conf
import django.template.loader

from libs.stage import Stage
from stages import TrustVerification
from __info__ import TEMPLATE_DIR


class GenerateReport(Stage):
    name = "Generate HTML Report"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        gen_settings: dict          = config.module_settings.generate_report
        self.report_fpath: Path     = config.autopkg.report_plist
        self.local_mnt: Path        = config.repository.mount_path
        self.repo_report_dir: str   = config.repository.report_dir
        self.public_url: str        = config.repository.public_url
        self.ctx: dict              = ctx

        # Setup Django interpretor
        TEMPLATES = [{
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [f'{os.getcwd()}/{TEMPLATE_DIR}'],
        }]
        django.conf.settings.configure(TEMPLATES=TEMPLATES)
        django.setup()

        self.template = django.template.loader.get_template(f"{os.getcwd()}/{TEMPLATE_DIR}/{gen_settings.get('template')}")


    def pre_check(self):
        with open(self.report_fpath, 'rb') as report_plist:
            self.plist_data = plistlib.load(report_plist)
            if not self.plist_data:
                return False
        return True

    def run(self) -> str:
        self.logger.info("Generating report")

        updated_recipes: list  = self.ctx.get("stage_outputs", {}).get(TrustVerification)
        context = StandardisedContext(
            self.plist_data,
            updated_recipes
        ).context

        file_path = f"{self.local_mnt}/{self.repo_report_dir}/{context['unix_time']}.html"
        with open(file_path, mode="w", encoding="utf-8") as html_report:
            self.logger.info(f"Writing report file to: {file_path}")
            html_report.write(self.template.render(context))

        report_url = f"{self.public_url}/{self.repo_report_dir}/{context['unix_time']}.html"
        self.logger.info(f"Report available at: {report_url}")
        return report_url


class StandardisedContext:
    def __init__(self, plist_data, trust_updated_recipes):
        tz_now = datetime.datetime.now()
        ux_now = datetime.datetime.now(datetime.timezone.utc)

        self.plist_data = plist_data
        self.context = {
            "gen_date": tz_now.strftime("%d/%m/%Y"),
            "gen_time": tz_now.strftime("%H:%M:%S"),
            "unix_time": ux_now.strftime("%s"),
            "failures": self._get_failures(),
            "deprecations": self._get_deprecations(),
            "munki_imports": self._get_munki_imports(),
            "packages_copied": self._get_packages_copied(),
            "updated_trust_info": self._get_updated_trust_info(trust_updated_recipes), 
            "urls_downloaded": self._get_urls_downloaded()
        }

    def _get_updated_trust_info(self, recipes):
        if not isinstance(recipes, list):
            return []

        if len(recipes) > 0:
            transform = []
            for recipe in recipes:
                transform.append({
                    "recipe": recipe
                })

            return {
                "summary_text": "The following recipes have updated trust information:",
                "data_rows": transform
            }
        return []

    def _get_failures(self):
        _object = self.plist_data["failures"]
        return {
            "summary_text": "The following failures occured:",
            "data_rows": _object
        }

    def _get_deprecations(self):
        try:
            _object = self.plist_data["summary_results"]["deprecation_summary_result"]
            return {
                "summary_text": _object["summary_text"],
                "data_rows": _object["data_rows"]
            }
        except KeyError:
            return []

    def _get_munki_imports(self):
        try:
            _object = self.plist_data["summary_results"]["munki_importer_summary_result"]
            return {
                "summary_text": _object["summary_text"],
                "data_rows": _object["data_rows"]
            }
        except KeyError:
                return []
    
    def _get_packages_copied(self):
        try:
            _object = self.plist_data["summary_results"]["pkg_copier_summary_result"]
            return {
                "summary_text": _object["summary_text"],
                "data_rows": _object["data_rows"]
            }
        except KeyError:
                return []

    def _get_urls_downloaded(self):
        try:
            _object = self.plist_data["summary_results"]["url_downloader_summary_result"]
            return {
                "summary_text": _object["summary_text"],
                "data_rows": _object["data_rows"]
            }
        except KeyError:
            return []