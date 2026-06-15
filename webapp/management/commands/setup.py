"""
manage.py setup
---------------
One-shot initialisation for a fresh AutoPkg Runner deployment.

Runs in order:
  1. Apply all database migrations
  2. Create the singleton Schedule row
  3. Create the admin account with a generated password
  4. Print next-step instructions
"""
import secrets
import sys

from django.core.management import call_command
from django.core.management.base import BaseCommand

_PASSWORD_BYTES = 16   # secrets.token_urlsafe(16) → ~22 printable chars


def _generate_password() -> str:
    return secrets.token_urlsafe(_PASSWORD_BYTES)


class Command(BaseCommand):
    help = 'Initialise a fresh AutoPkg Runner database (migrations → defaults → admin account)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            default='admin',
            help='Username for the admin account (default: admin).',
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            dest='no_input',
            help='Skip all interactive prompts; only run migrations and create defaults.',
        )
        parser.add_argument(
            '--skip-superuser',
            action='store_true',
            help='Skip admin account creation.',
        )

    def handle(self, *args, **options):
        from __info__ import FRIENDLY_APP_NAME

        no_input       = options['no_input']
        skip_superuser = options['skip_superuser'] or no_input
        username       = options['username']

        width = 60

        self.stdout.write(self.style.SUCCESS('═' * width))
        self.stdout.write(self.style.SUCCESS(f'  {FRIENDLY_APP_NAME}'))
        self.stdout.write(self.style.SUCCESS('  First-Time Setup'))
        self.stdout.write(self.style.SUCCESS('═' * width))

        # -- Step 1: Migrations ------------------------------------
        self._step('1', 'Running database migrations')
        try:
            call_command('migrate', '--run-syncdb', verbosity=1, interactive=False)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'  Migration failed: {exc}'))
            sys.exit(1)

        # -- Step 2: Singleton defaults ----------------------------
        self._step('2', 'Creating default schedule row')
        try:
            from webapp.models import Schedule
            Schedule.get()
            self._ok('Schedule row ready')
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'  Failed to create defaults: {exc}'))
            sys.exit(1)

        # -- Step 3: Admin account ---------------------------------
        if skip_superuser:
            self._step('3', 'Create initial administrator account  (skipped)')
        else:
            self._step('3', 'Create initial administrator account')
            from django.contrib.auth import get_user_model
            User = get_user_model()

            if User.objects.filter(is_superuser=True).exists():
                self._ok('A superuser already exists — skipping')
                self._warn('Forgotten your password? Run: python manage.py resetpassword')
            else:
                password = _generate_password()
                try:
                    User.objects.create_superuser(
                        username=username,
                        email='',
                        password=password,
                    )
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f'  Failed to create admin account: {exc}'))
                    sys.exit(1)

                self._ok('Account created')
                self._credentials_box(username, password)

        # -- Done --------------------------------------------------
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * width))
        self.stdout.write(self.style.SUCCESS('  Setup complete!'))
        self.stdout.write(self.style.SUCCESS('═' * width))
        self.stdout.write('')
        self.stdout.write('  Configure AutoPkg Runner via the web UI after starting.')
        self.stdout.write('')
        self.stdout.write('  Start the development server:')
        self.stdout.write(self.style.MIGRATE_HEADING('    python manage.py serve'))
        self.stdout.write('  To bind to all interfaces (LAN access):')
        self.stdout.write(self.style.MIGRATE_HEADING('    python manage.py serve --network'))
        self.stdout.write('')
        self.stdout.write('  For production (SSE / real-time logs require threading):')
        self.stdout.write(self.style.MIGRATE_HEADING(
            '    gunicorn autopkgrunner.wsgi:application --workers 1 --threads 8'
        ))
        self.stdout.write('')
        self.stdout.write('  Protect the database file (contains credentials):')
        self.stdout.write(self.style.MIGRATE_HEADING('    chmod 600 db.sqlite3'))
        self.stdout.write('')

    # -- Helpers ---------------------------------------------------

    def _step(self, number, description):
        self.stdout.write(f'\n[STAGE {number}] {description}')

    def _ok(self, message):
        self.stdout.write(f'  {self.style.SUCCESS("✓")} {message}')

    def _warn(self, message):
        self.stdout.write(f'  {self.style.WARNING("⚠")} {message}')

    def _credentials_box(self, username: str, password: str):
        disclaimer = 'Save this password - it is not stored in plain text.'
        label_col  = 11   # width of '  Username ' / '  Password '
        value_col  = 44   # width of ' admin...'
        full_width = label_col + 1 + value_col  # 56; the +1 is the ┳/┻ column

        w = self.stdout.write
        S = self.style.SUCCESS
        w(S(f'  ┏{"━" * label_col}┳{"━" * value_col}┓'))
        w(S(f'  ┃  {"Username":<{label_col - 2}}┃ {username:<{value_col - 1}}┃'))
        w(S(f'  ┃  {"Password":<{label_col - 2}}┃ {password:<{value_col - 1}}┃'))
        w(S(f'  ┣{"━" * label_col}┻{"━" * value_col}┫'))
        w(S(f'  ┃  {disclaimer:<{full_width - 2}}┃'))
        w(S(f'  ┗{"━" * full_width}┛'))
