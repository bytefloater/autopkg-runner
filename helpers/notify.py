"""
AutoPkg Runner: Notification Helper Module


"""
import os
import time
from datetime import datetime
import webbrowser

import django
from django.conf import settings
from django.template.loader import get_template

from . import pushover
from .logger import logger

# Django Configuration
TEMPLATES_DIR = f'{os.getcwd()}/templates'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [TEMPLATES_DIR],
}]
settings.configure(TEMPLATES=TEMPLATES)
django.setup()

OPEN_IN_BROWSER = False


def generate_report(data, global_prefs, send_pushover: bool = False):
    """
    Produce an HTML report from the provided data, and sending notifications
    to the enabled sources
    """
    local_mount_point = global_prefs['LocalMountPoint']

    logger("Generating report...")
    now = datetime.now()
    date_string = now.strftime("%d/%m/%Y")
    time_string = now.strftime("%H:%M:%S")

    template = get_template(f"{TEMPLATES_DIR}/bootstrap_template.html")
    context = {
        "generator_name": "ByteFloater",
        "generation_time": time_string,
        "generation_date": date_string
    }

    # Generate Django Context
    # Fields read from provided plist data, missing keys are ignored
    try:
        if len(data["failures"]) > 0:
            context["failures"] = data["failures"]
    except KeyError:
        logger("Key 'failures' not found, skipping...", 1)

    try:
        if len(data["updated_applications"]) > 0:
            context["updated_applications"] = data["updated_applications"]
    except KeyError:
        logger("Key 'dected_versions' not found, skipping...", 1)

    summary_results = data["summary_results"]
    if summary_results.get("url_downloader_summary_result", None):
        url_downloader = summary_results["url_downloader_summary_result"]
        context["url_downloader_summary_text"] = url_downloader["summary_text"]
        context["url_downloader_data_rows"] = url_downloader["data_rows"]
    else:
        logger("URL Downloader not found, skipping...", 1)

    if summary_results.get("pkg_copier_summary_result", None):
        pkg_copier = summary_results["pkg_copier_summary_result"]
        context["pkg_copier_summary_text"] = pkg_copier["summary_text"]
        context["pkg_copier_data_rows"] = pkg_copier["data_rows"]
    else:
        logger("Pkg Copier not found, skipping...", 1)

    if summary_results.get("munki_importer_summary_result", None):
        munki_importer = summary_results["munki_importer_summary_result"]
        context["munki_importer_summary_text"] = munki_importer["summary_text"]
        context["munki_importer_data_rows"] = munki_importer["data_rows"]
    else:
        logger("Munki Importer not found, skipping...", 1)

    # Report names are the unix timecode of their creation
    report_filename = f"{str(time.time()).split('.', maxsplit=1)[0]}.html"
    report_path = f"{local_mount_point}/reports/{report_filename}"
    
    # Use Django to generate an HTML report from the template
    with open(report_path, "w", encoding="utf-8") as html_report:
        html_report.write(template.render(context))
        html_report.close()
        logger(f"Report saved: {report_filename}", 1)

    report_base_url = global_prefs["ScriptSettings"]["ReportBaseURL"]
    report_link = f"{report_base_url}/reports/{report_filename}"
    if OPEN_IN_BROWSER:
        webbrowser.open(report_link, new=0)


    if send_pushover:
        logger("Sending noticiation...", 1)
        po_settings = global_prefs["PushoverSettings"]
        pushover.send(
            token=po_settings["ApplicationKey"],
            user=po_settings["UserKey"],
            message=f'The latest AutoPkg Report is available <a href="{report_link}">here</a>.'
        )
    else:
        logger("Notifications disabled, skipping...", 1)
