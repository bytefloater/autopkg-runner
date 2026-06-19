"""
manage.py purge
---------------
Remove all files and directories created by the autopkg-runner .app bundle
outside the bundle itself:

  - /Library/LaunchDaemons/<bundle-id>.plist       (system daemon)
  - ~/Library/LaunchAgents/<bundle-id>.plist       (user agent)
  - /Library/Application Support/<bundle-id>/      (system DB + staticfiles)
  - ~/Library/Application Support/<bundle-id>/     (user DB + staticfiles)
  - /Library/Preferences/<bundle-id>.plist         (system config / secret key)
  - ~/Library/Preferences/<bundle-id>.plist        (user config / secret key)
  - /var/log/<bundle-id>/                          (server logs)

Paths that require root are handled via a native macOS authentication dialog
(osascript) unless the command is already running under sudo.

Usage:
    autopkg-runner purge
    autopkg-runner purge --keep-data     # skip Application Support directories
    autopkg-runner purge --force         # skip confirmation prompt
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from __info__ import BUNDLE_ID, FRIENDLY_APP_NAME

# ---------------------------------------------------------------------------
# Well-known paths derived from BUNDLE_ID so nothing is hard-coded here.
# ---------------------------------------------------------------------------

_SYSTEM_DAEMON  = Path('/Library/LaunchDaemons')  / f'{BUNDLE_ID}.plist'
_USER_AGENT     = Path.home() / 'Library/LaunchAgents' / f'{BUNDLE_ID}.plist'
_SYSTEM_SUPPORT = Path('/Library/Application Support') / BUNDLE_ID
_USER_SUPPORT   = Path.home() / 'Library/Application Support' / BUNDLE_ID
_SYSTEM_PREFS   = Path('/Library/Preferences') / f'{BUNDLE_ID}.plist'
_USER_PREFS     = Path.home() / 'Library/Preferences' / f'{BUNDLE_ID}.plist'
_LOG_DIR        = Path(f'/var/log/{BUNDLE_ID}')

_PRIVILEGED = {_SYSTEM_DAEMON, _SYSTEM_SUPPORT, _SYSTEM_PREFS, _LOG_DIR}


class Command(BaseCommand):
    help = f'Remove all files and services created by the {FRIENDLY_APP_NAME} bundle'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-data',
            action='store_true',
            help='Skip removal of Application Support directories (preserves the database).',
        )
        parser.add_argument(
            '--force', '-f',
            action='store_true',
            help='Skip the confirmation prompt.',
        )

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        keep_data = options['keep_data']
        force = options['force']

        self._banner(FRIENDLY_APP_NAME, 'Purge Artefacts')
        self._info('Checking for artefacts...')

        # Candidates as (label, path) so label and path stay separate for formatting.
        candidates = [
            ('System LaunchDaemon', _SYSTEM_DAEMON),
            ('User LaunchAgent',    _USER_AGENT),
            ('System Preferences',  _SYSTEM_PREFS),
            ('User Preferences',    _USER_PREFS),
            ('Log directory',       _LOG_DIR),
        ]
        if not keep_data:
            candidates += [
                ('System App Support', _SYSTEM_SUPPORT),
                ('User App Support',   _USER_SUPPORT),
            ]

        targets = [(label, path) for label, path in candidates if path.exists()]

        if not targets:
            self._info(f'Nothing to remove — no {FRIENDLY_APP_NAME} artefacts found.')
            return

        col = max(len(label) for label, _ in targets)
        self.stdout.write('\n  The following will be permanently removed:')
        for label, path in targets:
            self.stdout.write(f'    - {label:<{col}}  ({path})')
        self.stdout.write('')

        if not force:
            try:
                confirm = input('Remove all of the above? [y/N] ').strip().lower()
            except (EOFError, KeyboardInterrupt):
                self.stdout.write('\n  Aborted.')
                return
            if confirm != 'y':
                self.stdout.write('  Aborted.')
                return

        self._info('Starting artefact purge...')

        # Stop any running launchd services before touching their plists.
        for _, plist in targets:
            if plist in (_SYSTEM_DAEMON, _USER_AGENT) and plist.exists():
                self._launchctl_unload(plist)

        user_targets = [(l, p) for l, p in targets if p not in _PRIVILEGED]
        root_targets = [(l, p) for l, p in targets if p in _PRIVILEGED]

        for label, path in user_targets:
            self._remove(label, path, col)

        if root_targets:
            if os.geteuid() == 0:
                for label, path in root_targets:
                    self._remove(label, path, col)
            else:
                self.stdout.write(
                    '\n  Some paths require administrator privileges.\n'
                    '  A macOS authentication dialog will appear.\n'
                )
                self._remove_privileged(root_targets, col)

        msg = f'{FRIENDLY_APP_NAME} purge complete.'
        bar = '━' * (len(msg) + 2)
        self.stdout.write(self.style.SUCCESS(f'\n┏{bar}┓'))
        self.stdout.write(self.style.SUCCESS(f'┃ {msg} ┃'))
        self.stdout.write(self.style.SUCCESS(f'┗{bar}┛\n'))

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _banner(self, *lines: str):
        width = max(32, max(len(l) for l in lines) + 4)
        sep = '═' * width
        self.stdout.write(sep)
        for line in lines:
            self.stdout.write(f'  {line}')
        self.stdout.write(sep)

    def _info(self, msg: str):
        self.stdout.write(f'[I] {msg}')

    # ------------------------------------------------------------------
    # Removal helpers
    # ------------------------------------------------------------------

    def _remove(self, label: str, path: Path, col: int = 0):
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            self.stdout.write(self.style.SUCCESS(f'[✓] Removed {label:<{col}}  ({path})'))
        except PermissionError:
            self.stdout.write(self.style.ERROR(
                f'[✗] Permission denied: {label:<{col}}  ({path})  — re-run with sudo'
            ))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'[✗] {label:<{col}}  ({path}): {exc}'))

    def _remove_privileged(self, targets: list, col: int = 0):
        """Remove root-owned paths via a privileged shell invoked through osascript."""
        rm_lines = []
        for _, path in targets:
            if path.is_dir():
                rm_lines.append(f"rm -rf '{path}'")
            else:
                rm_lines.append(f"rm -f '{path}'")

        script_body = '\n'.join([
            '#!/bin/bash',
            'cd /',
            'set -e',
            *rm_lines,
        ])

        tmp_script = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.sh',
                prefix='autopkg-runner-purge-', delete=False, dir='/private/tmp',
            ) as f:
                f.write(script_body)
                tmp_script = f.name

            os.chmod(tmp_script, 0o755)
            self._run_via_osascript(
                script_path=tmp_script,
                prompt=f'{FRIENDLY_APP_NAME} needs administrator access to remove system files.',
            )

            for label, path in targets:
                if not path.exists():
                    self.stdout.write(self.style.SUCCESS(f'[✓] Removed {label:<{col}}  ({path})'))
                else:
                    self.stdout.write(self.style.ERROR(f'[✗] Still exists: {label:<{col}}  ({path})'))

        finally:
            if tmp_script:
                try:
                    os.unlink(tmp_script)
                except FileNotFoundError:
                    pass

    # ------------------------------------------------------------------
    # launchd
    # ------------------------------------------------------------------

    def _launchctl_unload(self, plist: Path):
        result = subprocess.run(
            ['launchctl', 'unload', str(plist)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            self.stdout.write(f'[I] Stopped launchd service ({plist.name})')
        else:
            self.stdout.write(f'[I] Service not loaded or already stopped ({plist.name})')

    # ------------------------------------------------------------------
    # Privilege escalation
    # ------------------------------------------------------------------

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
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if '-128' in stderr or 'User canceled' in stderr:
                raise CommandError('Purge cancelled — no privileged paths were removed.')
            raise CommandError(
                f'Privileged removal failed:\n{stderr or result.stdout.strip()}'
            )
