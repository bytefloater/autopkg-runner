"""
manage.py remove_service_daemon
---------------------------------
Unloads and removes the autopkg-runner launchd system daemon installed
by install_service_daemon.

Can be run as a normal user; a native macOS authentication dialog will
appear to request administrator credentials for the privileged writes.
Alternatively, run the whole command under sudo.

Usage:
    python3 manage.py remove_service_daemon
    sudo python3 manage.py remove_service_daemon   # skips the auth dialog

The log directory (/var/log/autopkg-runner/) is left in place so that
log files can still be reviewed after removal.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


from __info__ import BUNDLE_ID
PLIST_LABEL = BUNDLE_ID
PLIST_DEST  = Path('/Library/LaunchDaemons') / f'{PLIST_LABEL}.plist'


class Command(BaseCommand):
    help = 'Remove the autopkg-runner launchd system daemon'

    def handle(self, *args, **options):
        if not PLIST_DEST.exists():
            self.stdout.write(self.style.WARNING(
                f'\n  Service plist not found at {PLIST_DEST}\n'
                '  Nothing to remove — the service may not be installed.\n'
            ))
            return

        self.stdout.write('')

        if os.geteuid() == 0:
            self._remove_direct()
        else:
            self.stdout.write(
                '  Administrator privileges are required to remove the service.\n'
                '  A macOS authentication dialog will appear.\n'
            )
            self._remove_escalated()

        self.stdout.write(self.style.SUCCESS(
            '\n  ✓ Service removed.\n'
            '\n  Note: log files in /var/log/autopkg-runner/ were left in place.'
        ))

    # ------------------------------------------------------------------

    def _remove_direct(self):
        """Remove when already running as root."""
        self.stdout.write('  Stopping service…')
        result = subprocess.run(
            ['launchctl', 'unload', str(PLIST_DEST)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            self.stdout.write(self.style.WARNING(
                f'  launchctl unload returned non-zero '
                f'(service may already be stopped): {result.stderr.strip()}'
            ))
        else:
            self.stdout.write('  Service stopped.')

        self.stdout.write(f'  Removing {PLIST_DEST}…')
        PLIST_DEST.unlink()

    def _remove_escalated(self):
        """Remove as a standard user via an osascript-driven auth dialog."""
        script_body = '\n'.join([
            '#!/bin/bash',
            '# Switch to a safe cwd before set -e: the elevated shell inherits',
            '# the caller\'s cwd which may be on a TCC-restricted volume.',
            'cd /',
            'set -e',
            '',
            '# Unload the service (non-fatal if already stopped)',
            f"launchctl unload '{PLIST_DEST}' 2>/dev/null || true",
            '',
            '# Remove the plist',
            f"rm -f '{PLIST_DEST}'",
        ])

        tmp_script = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.sh',
                prefix='autopkg-runner-remove-', delete=False, dir='/private/tmp',
            ) as f:
                f.write(script_body)
                tmp_script = f.name

            os.chmod(tmp_script, 0o755)

            self._run_via_osascript(
                script_path=tmp_script,
                prompt='AutoPkg Runner needs administrator access to remove the system service.',
            )

        finally:
            if tmp_script:
                try:
                    os.unlink(tmp_script)
                except FileNotFoundError:
                    pass

    @staticmethod
    def _run_via_osascript(script_path: str, prompt: str):
        safe_path   = script_path.replace('"', '\\"')
        safe_prompt = prompt.replace('"', '\\"')

        applescript = (
            f'do shell script "{safe_path}" '
            f'with administrator privileges '
            f'with prompt "{safe_prompt}"'
        )

        result = subprocess.run(
            ['osascript', '-e', applescript],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if '-128' in stderr or 'User canceled' in stderr:
                raise CommandError('Removal cancelled — no changes were made.')
            raise CommandError(
                f'Privileged removal failed:\n{stderr or result.stdout.strip()}'
            )
