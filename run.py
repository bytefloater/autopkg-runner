#!/usr/bin/env python3
"""
Entrypoint for the AutoPkg Runner .app bundle.

Usage (via the binary inside the .app):
  autopkg-runner          — start the gunicorn server (default)
  autopkg-runner serve    — start the gunicorn server
  autopkg-runner migrate  — run Django management commands
  autopkg-runner <cmd>    — any other Django management command

When launched via Finder (double-click, no TTY) a dialog is shown explaining
how to use the app from the command line.
"""
import os
import sys
from pathlib import Path


def _gui_dialog(msg: str) -> None:
    import subprocess
    escaped = msg.replace('"', '\\"')
    subprocess.run(
        ['osascript', '-e', f'display dialog "{escaped}" buttons {{"OK"}} default button "OK"'],
        check=False,
    )


def _check_setup_or_exit() -> None:
    """Verify the app has been initialised. Must be called before gunicorn forks
    workers — if the check runs inside wsgi.py it fires in every worker and
    gunicorn replaces each exiting worker indefinitely."""
    import django
    django.setup()

    from pathlib import Path
    from django.conf import settings
    from django.db import OperationalError, ProgrammingError

    db_name = str(settings.DATABASES.get('default', {}).get('NAME', ''))
    is_memory = db_name == ':memory:' or 'mode=memory' in db_name

    setup_ok = False
    if is_memory or not db_name or Path(db_name).exists():
        try:
            from webapp.models import Schedule
            Schedule.objects.get(pk=1)
            setup_ok = True
        except (OperationalError, ProgrammingError, Schedule.DoesNotExist):
            pass

    if not setup_ok:
        frozen = getattr(sys, 'frozen', False)
        setup_cmd = 'autopkg-runner setup' if frozen else 'python manage.py setup'
        print(
            f'[✗] AutoPkg Runner has not been set up.\n'
            f'\n'
            f'    Run the following command first:\n'
            f'\n'
            f'      {setup_cmd}\n',
            file=sys.stderr,
        )
        sys.exit(0 if frozen else 1)


def main() -> None:
    frozen = getattr(sys, 'frozen', False)

    if frozen:
        from libs.bundled_config import load_plist_config
        load_plist_config()

        # Launched via Finder: no TTY, no CLI arguments → show instructions
        if not sys.stdout.isatty() and len(sys.argv) < 2:
            binary = sys.executable
            _gui_dialog(
                "AutoPkg Runner is a background service and is managed via launchd.\\n\\n"
                f"Binary: {binary}\\n\\n"
                "To start the server:\\n"
                "  autopkg-runner serve\\n\\n"
                "To run management commands:\\n"
                "  autopkg-runner migrate\\n"
                "  autopkg-runner createsuperuser"
            )
            return
    else:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent / '.env')

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autopkgrunner.settings')

    cmd = sys.argv[1] if len(sys.argv) > 1 else 'serve'

    if cmd == 'serve':
        # Check setup before starting gunicorn. If the check runs inside wsgi.py
        # instead, it fires in each worker process — gunicorn then sees the worker
        # exit and spawns a replacement, creating an infinite restart loop.
        _check_setup_or_exit()

        import logging

        class _NoWinch(logging.Filter):
            def filter(self, record):
                return 'winch' not in record.getMessage().lower()

        # Filter is attached to the logger object before gunicorn's Logger.setup()
        # runs. setup() replaces handlers but leaves logger-level filters intact,
        # so this survives into the master process and all forked workers.
        logging.getLogger('gunicorn.error').addFilter(_NoWinch())

        os.environ['AUTOPKG_MODE'] = 'server'
        from gunicorn.app.wsgiapp import run as gunicorn_run
        sys.argv = [sys.argv[0], 'autopkgrunner.wsgi:application',
                    '--bind', '0.0.0.0:8000', '--workers', '2']
        gunicorn_run()
    else:
        os.environ['AUTOPKG_MODE'] = 'manage'
        from django.core.management import execute_from_command_line
        execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
