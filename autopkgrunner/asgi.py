import atexit
import fcntl
import logging
import os
import shutil
import sys
import tempfile
import warnings

from dotenv import load_dotenv
load_dotenv()  # Load .env before Django reads settings

# Django 4.2 bug: StreamingHttpResponse.__aiter__ issues this warning whenever
# a sync iterator (e.g. WhiteNoise FileResponse, GZipMiddleware output) is
# async-iterated by the ASGI handler. The fallback path works correctly; the
# warning is spurious. Fixed in Django 5.x.
warnings.filterwarnings(
    'ignore',
    message='StreamingHttpResponse must consume synchronous iterators',
    category=Warning,
)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autopkgrunner.settings')

# -- Static-file collection ----------------------------------------------------
# Must happen before get_asgi_application() so WhiteNoise finds the files when
# it scans STATIC_ROOT during middleware initialisation.
#
# A file lock ensures only the first worker to boot runs collectstatic; the
# rest wait for the lock, see the files already exist, and skip it.
# This avoids the ObjC fork-safety crash that occurs when django.setup() is
# called in the gunicorn master (on_starting) before workers are forked.

_via_manage = (
    sys.argv and os.path.basename(sys.argv[0]) in ('manage.py', 'manage')
    or os.environ.get('AUTOPKG_MODE') == 'manage'
)

if not _via_manage:
    import django
    django.setup()

    from django.conf import settings
    from django.core.management import call_command

    logger = logging.getLogger('autopkg_runner')
    _static_root = settings.STATIC_ROOT

    _lock_path = os.path.join(tempfile.gettempdir(), 'autopkg-runner-collectstatic.lock')
    with open(_lock_path, 'w') as _lf:
        fcntl.flock(_lf.fileno(), fcntl.LOCK_EX)
        try:
            if not _static_root.exists() or not any(_static_root.iterdir()):
                logger.info('Collecting static files…')
                call_command('collectstatic', '--noinput', verbosity=0)
                _file_count = sum(1 for _ in _static_root.rglob('*') if _.is_file())
                logger.info('Static files ready (%d files in %s).', _file_count, _static_root)

                def _cleanup_static():
                    if _static_root.exists():
                        shutil.rmtree(_static_root, ignore_errors=True)

                atexit.register(_cleanup_static)
        finally:
            fcntl.flock(_lf.fileno(), fcntl.LOCK_UN)

# -- ASGI application ----------------------------------------------------------

from django.core.asgi import get_asgi_application
application = get_asgi_application()
