"""
Shared pre-flight checks for management commands.
"""
import sys
from pathlib import Path


def require_setup(command) -> None:
    """Exit with a formatted error if the application has not been initialised.

    Checks the SQLite file exists before opening any connection — SQLite
    creates the file on first connect, so we must avoid that side-effect.
    The presence of the Schedule singleton (pk=1) is the canonical signal that
    `manage.py setup` has completed — migrations applied, defaults created.
    """
    from django.conf import settings
    from django.db import OperationalError, ProgrammingError

    # Bail early if the database file doesn't exist yet.  Attempting a query
    # against a missing SQLite file causes Django/SQLite to create an empty
    # one, which then looks like a half-initialised state to future checks.
    # Skip for in-memory SQLite (plain ':memory:' or the shared-cache URI
    # form Django's test runner uses: 'file:memorydb_...?mode=memory&...').
    db_name = str(settings.DATABASES.get('default', {}).get('NAME', ''))
    is_memory = db_name == ':memory:' or 'mode=memory' in db_name
    if not is_memory and db_name and not Path(db_name).exists():
        _fail(command)
        return

    from webapp.models import Schedule

    ok = False
    try:
        Schedule.objects.get(pk=1)
        ok = True
    except (OperationalError, ProgrammingError, Schedule.DoesNotExist):
        pass

    if not ok:
        _fail(command)


def _fail(command) -> None:
    frozen = getattr(sys, 'frozen', False)
    setup_cmd = 'autopkg-runner setup' if frozen else 'python manage.py setup'
    command.stderr.write(command.style.ERROR(
        '[✗] AutoPkg Runner has not been set up.\n'
        '\n'
        '    Run the following command first:\n'
        '\n'
        f'      {setup_cmd}\n'
    ))
    # Exit 0 when frozen so launchd (KeepAlive SuccessfulExit=false) does not
    # treat this as a crash and restart the process in a tight loop.
    sys.exit(0 if frozen else 1)
