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
