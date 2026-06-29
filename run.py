#!/usr/bin/env python3
# On macOS the ObjC runtime reads OBJC_DISABLE_INITIALIZE_FORK_SAFETY once at
# process startup, before any Python code runs.  Setting it inside Python with
# os.environ has no effect because ObjC has already cached the value.  When
# it is absent the gunicorn master→worker fork triggers an ObjC fork-safety
# SIGSEGV in every worker.  Re-exec immediately (before any non-stdlib imports)
# so the variable is present from the start of the next invocation.
import os as _os, sys as _sys
from pathlib import Path as _Path
if _sys.platform == 'darwin' and not _os.environ.get('OBJC_DISABLE_INITIALIZE_FORK_SAFETY'):
    _os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'
    if getattr(_sys, 'frozen', False):
        # Bundled (PyInstaller) mode: argv[0] is the compiled executable
        _os.execv(_sys.argv[0], _sys.argv)
    else:
        # Dev mode: resolve script path and re-exec with Python interpreter
        _script = _Path(_sys.argv[0]).resolve()
        _os.execv(_sys.executable, [_sys.executable, str(_script)] + _sys.argv[1:])

"""
Entrypoint for the AutoPkg Runner .app bundle.

Usage (via the binary inside the .app):
  autopkg-runner          — show this help
  autopkg-runner serve    — start the development server
  autopkg-runner setup    — first-time initialisation
  autopkg-runner <cmd>    — run a management command

When launched via Finder (double-click, no TTY) a dialog is shown explaining
how to use the app from the command line.
"""
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Curated command list
# ---------------------------------------------------------------------------

_COL = 30  # left column width for alignment

_HELP_COMMANDS = [
    ('serve', 'Start the server (gunicorn + uvicorn)', [
        ('--bind ADDRESS', 'Bind address (default: 0.0.0.0)'),
        ('--port PORT', 'Port (default: 8000)'),
        ('--workers N', 'Worker processes (default: 2)'),
    ]),
    ('setup', 'First-time initialisation', [
        ('--username USER', 'Admin username (default: admin)'),
        ('--no-input', 'Non-interactive; skip account creation prompts'),
        ('--skip-superuser', 'Skip admin account creation'),
    ]),
    ('migrate', 'Apply database migrations', []),
    ('createsuperuser', 'Create a new admin account', []),
    ('resetpassword <user>', "Reset a user's password", []),
    ('service_daemon', 'Manage the launchd system daemon', [
        ('--install', 'Install the daemon'),
        ('--remove', 'Remove the daemon'),
        ('--user USERNAME', 'Run as this macOS user (required with --install)'),
        ('--port PORT', 'Port (default: 8000)'),
        ('--bind ADDRESS', 'Bind address (default: 127.0.0.1)'),
        ('--workers N', 'Gunicorn worker processes (default: 1)'),
    ]),
    ('purge', 'Remove all app artefacts (plist, DB, logs)', [
        ('--keep-data', 'Preserve the database and Application Support directories'),
        ('--force, -f', 'Skip confirmation prompt'),
    ]),
    ('generate_vapid_keys', 'Generate WebPush VAPID keys', [
        ('--contact URI', 'Contact URI (mailto: or https:)'),
        ('--force', 'Overwrite existing keys'),
    ]),
    ('install_sftp_deps', 'Install macFUSE and sshfs for SFTP connections', []),
]

# Commands accepted by the entrypoint (derived from the table above plus bare
# Django builtins that need no advertising).
_KNOWN_COMMANDS: set[str] = {
    row[0].split()[0] for row in _HELP_COMMANDS
} | {'changepassword'}


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

def _print_help() -> None:
    from __info__ import FRIENDLY_APP_NAME, APP_NAME
    flag_indent = ' ' * 4
    lines = [
        f'{FRIENDLY_APP_NAME}',
        '',
        'Usage:',
        f'  {APP_NAME} <command> [options]',
        '',
        'Commands:',
    ]
    for cmd, desc, flags in _HELP_COMMANDS:
        lines.append(f'  {cmd:<{_COL - 2}}{desc}')
        for flag, fdesc in flags:
            lines.append(f'{flag_indent}{flag:<{_COL - 4}}{fdesc}')
        if flags:
            lines.append('')
    lines.append('')
    lines.append(f"Run '{APP_NAME} <command> --help' for full details on any command.")
    print('\n'.join(lines))


# ---------------------------------------------------------------------------
# Bundle helpers
# ---------------------------------------------------------------------------

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

    from django.conf import settings
    from django.db import OperationalError, ProgrammingError

    db_name = str(settings.DATABASES.get('default', {}).get('NAME', ''))
    is_memory = db_name == ':memory:' or 'mode=memory' in db_name

    setup_ok = False
    if is_memory or not db_name or Path(db_name).exists():
        from webapp.models import Schedule
        try:
            Schedule.objects.get(pk=1)
            setup_ok = True
        except (OperationalError, ProgrammingError, Schedule.DoesNotExist):
            pass

    if not setup_ok:
        frozen = getattr(sys, 'frozen', False)
        setup_cmd = 'autopkg-runner setup' if frozen else 'python run.py setup'
        print(
            f'[✗] AutoPkg Runner has not been set up.\n'
            f'\n'
            f'    Run the following command first:\n'
            f'\n'
            f'      {setup_cmd}\n',
            file=sys.stderr,
        )
        sys.exit(0 if frozen else 1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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

    cmd = sys.argv[1] if len(sys.argv) > 1 else None

    # Help / no-args
    if cmd is None or cmd in ('--help', '-h', 'help'):
        _print_help()
        return

    # Guard against undocumented / internal Django commands
    if cmd not in _KNOWN_COMMANDS:
        print(f"Unknown command: '{cmd}'\n", file=sys.stderr)
        _print_help()
        sys.exit(1)

    if cmd == 'serve':
        # Must be set before _check_setup_or_exit() calls django.setup(), which
        # triggers WebappConfig.ready().  ready() checks AUTOPKG_MODE to decide
        # whether to start background services; if the var isn't set yet it will
        # start the scheduler in the master process before gunicorn forks workers.
        os.environ['AUTOPKG_MODE'] = 'server'

        # Check setup before starting gunicorn. If the check runs inside wsgi.py
        # instead, it fires in each worker process — gunicorn then sees the worker
        # exit and spawns a replacement, creating an infinite restart loop.
        _check_setup_or_exit()

        import argparse
        import logging

        p = argparse.ArgumentParser(prog=f'{sys.argv[0]} serve', add_help=True)
        p.add_argument('--bind', default='0.0.0.0', metavar='ADDRESS')
        p.add_argument('--port', default='8000', metavar='PORT')
        p.add_argument('--workers', default='2', metavar='N')
        opts = p.parse_args(sys.argv[2:])

        class _NoWinch(logging.Filter):
            def filter(self, record):
                return 'winch' not in record.getMessage().lower()

        # Filter is attached to the logger object before gunicorn's Logger.setup()
        # runs. setup() replaces handlers but leaves logger-level filters intact,
        # so this survives into the master process and all forked workers.
        logging.getLogger('gunicorn.error').addFilter(_NoWinch())
        # Defence-in-depth for subprocess.run() calls from worker threads:
        # if a worker thread has initialised ObjC and another thread calls
        # subprocess.run() (which does fork+exec), the subprocess child would
        # crash without this flag.  The master→worker fork is safe without it
        # (the post_fork hook keeps the master thread-free), but subprocess calls
        # from within workers are not, so we keep it here.
        os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'
        from gunicorn.app.wsgiapp import run as gunicorn_run
        sys.argv = [
            sys.argv[0], 'autopkgrunner.asgi:application',
            '--config', 'python:autopkgrunner.gunicorn_conf',
            '--bind', f'{opts.bind}:{opts.port}',
            '--workers', opts.workers,
        ]
        gunicorn_run()
    else:
        os.environ['AUTOPKG_MODE'] = 'manage'
        from django.core.management import execute_from_command_line
        execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
