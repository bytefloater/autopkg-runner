import atexit
import logging
import os
import shutil
import sys

from dotenv import load_dotenv
load_dotenv()  # Load .env before Django reads settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autopkgrunner.settings')

# -- Static-file collection ----------------------------------------------------
# Must happen *before* get_wsgi_application() so that WhiteNoise finds the
# files when it scans STATIC_ROOT during middleware initialisation.
# This also means files are ready before the first request is served.

import django
django.setup()

from django.conf import settings
from django.core.management import call_command

logger = logging.getLogger('autopkg_runner')

# Detect whether we were loaded by manage.py (dev server) vs a WSGI server
# (gunicorn).  Must be set before the setup guard below.
_via_manage = (
    sys.argv and os.path.basename(sys.argv[0]) in ('manage.py', 'manage')
    or os.environ.get('AUTOPKG_MODE') == 'manage'
)

# Only collect static files when loaded directly by a WSGI server (gunicorn).
# The dev server serves static files itself, so collectstatic is not needed.
if not _via_manage:
    _static_root = settings.STATIC_ROOT

    logger.info('Collecting static files…')
    call_command('collectstatic', '--noinput', verbosity=0)

    _file_count = sum(1 for _ in _static_root.rglob('*') if _.is_file()) if _static_root.exists() else 0
    logger.info('Static files ready (%d files in %s).', _file_count, _static_root)

    def _cleanup_static():
        """Remove collected static files on process exit so the next startup
        always starts from a clean slate (no stale renamed/deleted assets)."""
        if _static_root.exists():
            shutil.rmtree(_static_root, ignore_errors=True)

    atexit.register(_cleanup_static)

# -- WSGI application ----------------------------------------------------------
# WhiteNoise middleware initialises here and scans the now-populated STATIC_ROOT.

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
