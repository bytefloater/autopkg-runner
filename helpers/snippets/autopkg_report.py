"""See README.md for autopkg_report"""
import plistlib
from datetime import datetime
import django
from django.conf import settings
from django.template.loader import get_template
from autopkg_runner import logger

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': ['/Users/localadmin/Documents/AutoPkgRunner'],
}]
settings.configure(TEMPLATES=TEMPLATES)
django.setup()

report_plist = open("autopkg_report_1.plist", 'rb')
report_data = plistlib.load(report_plist)

now = datetime.now()
date_string = now.strftime("%d/%m/%Y")
time_string = now.strftime("%H:%M:%S")

template = get_template('autopkg-new-template.html')
context = {
    "generator_name": "ByteFloater",
    "generation_time": time_string,
    "generation_date": date_string
}


"""
Generate the context information

All fields are read from the plist report provided.
Missing fields are not included in the report.
"""
if len(report_data["failures"]) > 0:
    context["failures"] = report_data["failures"]

summary_results = report_data["summary_results"]
if summary_results.get("url_downloader_summary_result", None):
    url_downloader = summary_results["url_downloader_summary_result"]
    context["url_downloader_summary_text"] = url_downloader["summary_text"]
    context["url_downloader_data_rows"] = url_downloader["data_rows"]
else:
    logger("URL Downloader Not Found, Skipping...")

if summary_results.get("pkg_copier_summary_result", None):
    pkg_copier = summary_results["pkg_copier_summary_result"]
    context["pkg_copier_summary_text"] = pkg_copier["summary_text"]
    context["pkg_copier_data_rows"] = pkg_copier["data_rows"]
else:
    logger("Pkg Copier Not Found, Skipping...")

if summary_results.get("munki_importer_summary_result", None):
    munki_importer = summary_results["munki_importer_summary_result"]
    context["munki_importer_summary_text"] = munki_importer["summary_text"]
    context["munki_importer_data_rows"] = munki_importer["data_rows"]
else:
    logger("Munki Reporter Not Found, Skipping...")


html_f = open("output.html", "w", encoding="utf-8")
html_f.write(template.render(context))
html_f.close()
