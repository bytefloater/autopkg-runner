"""Django settings for the test suite.

Identical to the production settings except ``DJANGO_SECRET_KEY`` is
pre-populated so tests can run without a ``.env`` file.  The env var is set
here (before importing the real settings module) so the bare
``os.environ['DJANGO_SECRET_KEY']`` lookup in settings.py succeeds.
"""
import os

os.environ.setdefault('DJANGO_SECRET_KEY', 'test-secret-key-not-for-production')
os.environ.setdefault('DJANGO_DEBUG', 'true')

from autopkgrunner.settings import *  # noqa: F401, F403, E402

# Use an in-memory SQLite database for speed.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Prevent WebappConfig.ready() from spawning background threads during tests.
# The scheduler and stale-run cleanup are not needed and they trigger
# pytest-django's database-access guard (PytestUnhandledThreadExceptionWarning).
from webapp.apps import WebappConfig  # noqa: E402
WebappConfig.ready = lambda self: None
