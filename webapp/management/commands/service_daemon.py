"""
manage.py service_daemon
------------------------
Install or remove the autopkg-runner launchd system daemon.

Usage:
    python manage.py service_daemon --install --user <username>
    python manage.py service_daemon --install --user autopkg --port 8000 --bind 127.0.0.1
    sudo python manage.py service_daemon --install --user autopkg
    python manage.py service_daemon --remove

Can be run as a normal user; a native macOS authentication dialog will appear
to request administrator credentials for privileged writes.  Run under sudo to
skip the dialog.

Note on --workers:
    APScheduler starts inside each gunicorn worker process.  Running more than
    one worker will cause duplicate scheduled AutoPkg runs.  The default of 1
    is strongly recommended unless you disable the built-in scheduler.
"""

import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from __info__ import BUNDLE_ID, APP_NAME

PLIST_LABEL   = BUNDLE_ID
PLIST_DEST    = Path('/Library/LaunchDaemons') / f'{PLIST_LABEL}.plist'
LOG_DIR       = Path(f'/var/log/{PLIST_LABEL}')
PROJECT_ROOT  = Path(__file__).resolve().parents[3]
TEMPLATE_PATH = PROJECT_ROOT / 'resources' / f'{PLIST_LABEL}.plist'


class Command(BaseCommand):
    help = 'Install or remove the autopkg-runner launchd system daemon'

    def add_arguments(self, parser):
        action = parser.add_mutually_exclusive_group(required=True)
        action.add_argument(
            '--install',
            action='store_true',
            help='Install the launchd system daemon.',
        )
        action.add_argument(
            '--remove',
            action='store_true',
            help='Remove the launchd system daemon.',
        )

        parser.add_argument(
            '--user',
            metavar='USERNAME',
            help='macOS username the service process will run as (required with --install).',
        )
        parser.add_argument(
            '--bind',
            default='127.0.0.1',
            metavar='ADDRESS',
            help='Address gunicorn will bind to (default: 127.0.0.1).',
        )
        parser.add_argument(
            '--port',
            default='8000',
            metavar='PORT',
            help='Port gunicorn will listen on (default: 8000).',
        )
        parser.add_argument(
            '--workers',
            default='1',
            metavar='N',
            help=(
                'Number of gunicorn worker processes (default: 1). '
                'Increasing this will cause duplicate scheduled runs.'
            ),
        )
        parser.add_argument(
            '--threads',
            default='8',
            metavar='N',
            help='Number of threads per gunicorn worker (default: 8).',
        )

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        if options['install']:
            if not options.get('user'):
                raise CommandError('--user is required when using --install.')
            self._do_install(options)
        else:
            self._do_remove()

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def _do_install(self, options):
        user    = options['user']
        bind    = options['bind']
        port    = options['port']
        workers = options['workers']
        threads = options['threads']

        self._validate_user(user)
        self._validate_port(port)
        self._validate_workers(workers)
        self._validate_threads(threads)
        self._validate_project_location(user)
        self._validate_project_ownership(user)

        frozen = getattr(sys, 'frozen', False)
        if frozen:
            prog_args = [sys.executable, 'serve',
                         '--bind', bind, '--port', port,
                         '--workers', workers, '--threads', threads]
        else:
            gunicorn_prefix = self._find_gunicorn()
            prog_args = gunicorn_prefix + [
                '--chdir', str(PROJECT_ROOT),
                'autopkgrunner.wsgi:application',
                '--bind', f'{bind}:{port}',
                '--workers', str(workers),
                '--threads', str(threads),
                '--timeout', '120',
            ]

        content = self._render_plist(user=user, prog_args=prog_args)

        self.stdout.write('')
        self.stdout.write('  Service configuration')
        self.stdout.write(f'  ├─ label    : {PLIST_LABEL}')
        self.stdout.write(f'  ├─ user     : {user}')
        self.stdout.write(f'  ├─ binary   : {prog_args[0]}')
        self.stdout.write(f'  ├─ bind     : {bind}:{port}')
        self.stdout.write(f'  ├─ workers  : {workers}')
        self.stdout.write(f'  ├─ threads  : {threads}')
        self.stdout.write(f'  └─ plist    : {PLIST_DEST}')
        self.stdout.write('')

        if os.geteuid() == 0:
            self._install_direct(content, user)
        else:
            self.stdout.write(
                '  Administrator privileges are required to install the service.\n'
                '  A macOS authentication dialog will appear.\n'
            )
            self._install_escalated(content, user)

        from __info__ import APP_NAME
        runner = APP_NAME if frozen else 'python run.py'
        self.stdout.write(self.style.SUCCESS(
            f'\n  ✓ Service installed and started.\n'
            f'\n  Plist   : {PLIST_DEST}'
            f'\n  Logs    : {LOG_DIR}/server.log'
            f'\n'
            f'\n  Useful commands:'
            f'\n    Status  : launchctl print system/{PLIST_LABEL}'
            f'\n    Stop    : launchctl bootout system/{PLIST_LABEL}  (requires admin)'
            f'\n    Remove  : {runner} service_daemon --remove'
        ))

    def _install_direct(self, content: str, user: str):
        self._prepare_log_dir_as_root(user)

        if PLIST_DEST.exists():
            self.stdout.write(self.style.WARNING(
                '  Existing installation found — stopping before reinstalling…'
            ))
            subprocess.run(
                ['launchctl', 'bootout', f'system/{PLIST_LABEL}'],
                capture_output=True,
            )

        PLIST_DEST.write_text(content)
        os.chmod(PLIST_DEST, 0o644)
        shutil.chown(PLIST_DEST, user='root', group='wheel')

        result = subprocess.run(
            ['launchctl', 'bootstrap', 'system', str(PLIST_DEST)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            PLIST_DEST.unlink(missing_ok=True)
            raise CommandError(
                f'launchctl bootstrap failed (exit {result.returncode}):\n'
                f'{result.stderr.strip()}\n\n'
                'The plist has been removed. Fix the error and try again.'
            )

    def _install_escalated(self, content: str, user: str):
        tmp_plist = tmp_script = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.plist',
                prefix='autopkg-runner-', delete=False, dir='/private/tmp',
            ) as f:
                f.write(content)
                tmp_plist = f.name

            script_body = '\n'.join([
                '#!/bin/bash',
                "cd /",
                'set -e',
                '',
                f"launchctl bootout system/{PLIST_LABEL} 2>/dev/null || true",
                '',
                f"mkdir -p '{LOG_DIR}'",
                f"chmod 755 '{LOG_DIR}'",
                f"chown '{user}' '{LOG_DIR}'",
                '',
                f"cp '{tmp_plist}' '{PLIST_DEST}'",
                f"chmod 644 '{PLIST_DEST}'",
                f"chown root:wheel '{PLIST_DEST}'",
                '',
                f"launchctl bootstrap system '{PLIST_DEST}'",
                '',
                f"rm -f '{tmp_plist}'",
            ])

            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.sh',
                prefix='autopkg-runner-install-', delete=False, dir='/private/tmp',
            ) as f:
                f.write(script_body)
                tmp_script = f.name

            os.chmod(tmp_script, 0o755)

            self._run_via_osascript(
                script_path=tmp_script,
                prompt='AutoPkg Runner needs administrator access to install the system service.',
            )

        finally:
            for p in (tmp_script, tmp_plist):
                if p:
                    try:
                        os.unlink(p)
                    except FileNotFoundError:
                        pass

    # ------------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------------

    def _do_remove(self):
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
            f'\n  Note: log files in {LOG_DIR}/ were left in place.'
        ))

    def _remove_direct(self):
        self.stdout.write('  Stopping service…')
        result = subprocess.run(
            ['launchctl', 'bootout', f'system/{PLIST_LABEL}'],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            self.stdout.write(self.style.WARNING(
                f'  launchctl bootout returned non-zero '
                f'(service may already be stopped): {result.stderr.strip()}'
            ))
        else:
            self.stdout.write('  Service stopped.')

        self.stdout.write(f'  Removing {PLIST_DEST}…')
        PLIST_DEST.unlink()

    def _remove_escalated(self):
        script_body = '\n'.join([
            '#!/bin/bash',
            'cd /',
            'set -e',
            '',
            f"launchctl bootout system/{PLIST_LABEL} 2>/dev/null || true",
            '',
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

    # ------------------------------------------------------------------
    # Shared helpers
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
                raise CommandError('Operation cancelled — no changes were made.')
            raise CommandError(
                f'Privileged operation failed:\n{stderr or result.stdout.strip()}'
            )

    def _prepare_log_dir_as_root(self, user: str):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(LOG_DIR, 0o755)
        shutil.chown(LOG_DIR, user=user)

    def _validate_user(self, user: str):
        try:
            pwd.getpwnam(user)
        except KeyError:
            raise CommandError(
                f"User '{user}' does not exist on this system.\n"
                'Create the account first, then re-run this command.'
            )

    def _validate_port(self, port: str):
        try:
            n = int(port)
            if not 1 <= n <= 65535:
                raise ValueError
        except ValueError:
            raise CommandError(
                f"Invalid port '{port}'. Must be an integer between 1 and 65535."
            )

    def _validate_workers(self, workers: str):
        try:
            n = int(workers)
            if n < 1:
                raise ValueError
        except ValueError:
            raise CommandError(
                f"Invalid --workers value '{workers}'. Must be a positive integer."
            )
        if n > 1:
            self.stdout.write(self.style.WARNING(
                f'\n  ⚠ Warning: --workers {n} was requested.\n'
                '  APScheduler runs inside every gunicorn worker, so multiple workers\n'
                '  will fire duplicate AutoPkg runs.  Use --workers 1 unless you have\n'
                '  disabled the built-in scheduler.\n'
            ))

    def _validate_threads(self, threads: str):
        try:
            n = int(threads)
            if n < 1:
                raise ValueError
        except ValueError:
            raise CommandError(
                f"Invalid --threads value '{threads}'. Must be a positive integer."
            )

    def _validate_project_location(self, user: str):
        """Verify the project root won't be blocked by macOS TCC at runtime.

        A launchd system daemon runs headlessly and cannot prompt for consent,
        so it is blocked from reading TCC-protected directories (~/Desktop,
        ~/Documents, ~/Downloads, ~/Movies, ~/Music, ~/Pictures) unless Full
        Disk Access has been explicitly granted.

        Safe locations (/Applications/, /opt/, /usr/local/, etc.) pass without
        a TCC database check.
        """
        protected = self._tcc_protected_paths()
        blocking = next(
            (p for p in protected if PROJECT_ROOT.is_relative_to(p)), None
        )
        if blocking is None:
            return  # path is outside all TCC-protected directories

        # Path is TCC-protected — check whether FDA has already been granted.
        if self._has_full_disk_access():
            self.stdout.write(self.style.WARNING(
                f'\n  ⚠ Project is under a TCC-protected directory ({blocking}).\n'
                '    Full Disk Access is granted — the daemon should work.\n'
                '    Consider moving to /Applications/ or /opt/ for a cleaner setup.\n'
            ))
            return

        raise CommandError(
            f"Project root '{PROJECT_ROOT}' is inside a TCC-protected directory:\n"
            f'  {blocking}\n'
            '\n'
            '  macOS TCC blocks system daemon processes from reading protected\n'
            '  user directories (Desktop, Documents, Downloads, Movies, Music,\n'
            '  Pictures) unless Full Disk Access is explicitly granted.\n'
            '\n'
            '  Options:\n'
            '  1. Move the project to a safe location (recommended):\n'
            f'       sudo mv {PROJECT_ROOT} /Applications/autopkg-runner\n'
            f'       sudo chown -R {user} /Applications/autopkg-runner\n'
            '  2. Grant Full Disk Access to the app, then re-run:\n'
            '       System Settings › Privacy & Security › Full Disk Access\n'
        )

    @staticmethod
    def _tcc_protected_paths() -> list[Path]:
        """Return the TCC-protected subdirectories for every real user account."""
        _PROTECTED_SUBDIRS = (
            'Desktop', 'Documents', 'Downloads',
            'Movies', 'Music', 'Pictures',
        )
        paths: list[Path] = []
        for entry in pwd.getpwall():
            if entry.pw_uid < 500:
                continue  # skip system accounts
            home = Path(entry.pw_dir)
            for sub in _PROTECTED_SUBDIRS:
                paths.append(home / sub)
        return paths

    @staticmethod
    def _has_full_disk_access() -> bool:
        """Check the TCC database for a Full Disk Access grant for this app."""
        import sqlite3
        from __info__ import BUNDLE_ID

        # Candidates: bundle ID (frozen .app) or the Python executable (dev).
        clients = [BUNDLE_ID, sys.executable]
        tcc_dbs = [
            Path('/Library/Application Support/com.apple.TCC/TCC.db'),
            Path.home() / 'Library/Application Support/com.apple.TCC/TCC.db',
        ]
        for db_path in tcc_dbs:
            if not db_path.exists():
                continue
            try:
                conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
                for client in clients:
                    row = conn.execute(
                        "SELECT 1 FROM access "
                        "WHERE service='kTCCServiceSystemPolicyAllFiles' "
                        "AND client=? AND auth_value=2",
                        (client,),
                    ).fetchone()
                    if row:
                        conn.close()
                        return True
                conn.close()
            except (sqlite3.OperationalError, PermissionError, OSError):
                continue
        return False

    def _validate_project_ownership(self, user: str):
        uid = pwd.getpwnam(user).pw_uid
        offenders: list[str] = []

        for dirpath, _dirnames, filenames in os.walk(PROJECT_ROOT):
            for path in [dirpath] + [os.path.join(dirpath, f) for f in filenames]:
                try:
                    if os.stat(path).st_uid != uid:
                        offenders.append(path)
                except OSError:
                    continue
            if len(offenders) >= 5:
                break

        if offenders:
            preview = '\n'.join(f'    {p}' for p in offenders[:5])
            raise CommandError(
                f"Not all files under '{PROJECT_ROOT}' are owned by '{user}'.\n"
                '\n'
                '  The daemon runs as this user and must own the project files.\n'
                '  Fix with:\n'
                '\n'
                f'    sudo chown -R {user} {PROJECT_ROOT}\n'
                '\n'
                '  First offending path(s):\n'
                + preview
                + ('\n    … (more)' if len(offenders) == 5 else '')
            )

    def _find_gunicorn(self) -> list[str]:
        candidate = Path(sys.executable).parent / 'gunicorn'
        if candidate.exists():
            return [str(candidate)]

        found = shutil.which('gunicorn')
        if found:
            return [found]

        probe = subprocess.run(
            [sys.executable, '-m', 'gunicorn', '--version'],
            capture_output=True,
        )
        if probe.returncode == 0:
            return [sys.executable, '-m', 'gunicorn']

        raise CommandError(
            'gunicorn was not found.\n\n'
            '  Install it with:  pip install gunicorn\n'
        )

    def _render_plist(self, *, user: str, prog_args: list[str]) -> str:
        if not TEMPLATE_PATH.exists():
            raise CommandError(
                f'Plist template not found: {TEMPLATE_PATH}\n'
                'Ensure the resources/ directory was not removed from the project.'
            )

        arg_lines = '\n\t\t'.join(f'<string>{a}</string>' for a in prog_args)

        content = TEMPLATE_PATH.read_text()
        content = content.replace('{{bundle_id}}', PLIST_LABEL)
        content = content.replace('{{run_as_user}}', user)
        content = content.replace('{{working_dir}}', str(PROJECT_ROOT))
        content = content.replace('{{program_args}}', arg_lines)
        content = content.replace('{{environment_vars}}', '')
        return content
