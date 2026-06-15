"""
manage.py serve
---------------
Thin wrapper around Django's `runserver` that makes the bind address explicit
and handles the ALLOWED_HOSTS requirement when serving to the network.

Usage:
    python manage.py serve                      # 127.0.0.1:8000 (default)
    python manage.py serve --network            # 0.0.0.0:8000
    python manage.py serve --port 9000          # 127.0.0.1:9000
    python manage.py serve --host 0.0.0.0       # 0.0.0.0:8000
    python manage.py serve --network --noreload # no auto-reload
"""
import os

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Start the development server (defaults to localhost:8000)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--host',
            default='127.0.0.1',
            metavar='HOST',
            help='Address to bind to (default: 127.0.0.1).',
        )
        parser.add_argument(
            '--port',
            default='8000',
            metavar='PORT',
            help='Port to listen on (default: 8000).',
        )
        parser.add_argument(
            '--network',
            action='store_true',
            help='Bind to 0.0.0.0 - makes the server reachable on all local interfaces.',
        )
        parser.add_argument(
            '--noreload',
            action='store_true',
            help='Disable the auto-reloader (required for SSE in the built-in dev server).',
        )

    def handle(self, *args, **options):
        from django.conf import settings
        from webapp.management.commands._checks import require_setup

        # -- Setup guard -------------------------------------------------------
        require_setup(self)

        host = '0.0.0.0' if options['network'] else options['host']
        port = options['port']

        # Validate port
        try:
            port_int = int(port)
            if not 1 <= port_int <= 65535:
                raise ValueError
        except ValueError:
            raise CommandError(f"Invalid port: '{port}'. Must be an integer between 1 and 65535.")

        # When binding to all interfaces Django's dev server will receive
        # requests with the machine's LAN IP as the Host header, which fails
        # the ALLOWED_HOSTS check unless we relax it.  This is only safe (and
        # only done) in DEBUG mode; in production use a real WSGI server.
        if host == '0.0.0.0':
            if not settings.DEBUG:
                raise CommandError(
                    '--network / --host 0.0.0.0 requires DEBUG=True.\n'
                    'For production, use gunicorn or another WSGI server instead.'
                )
            if '*' not in settings.ALLOWED_HOSTS:
                settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['*']

            # Only print once — the StatReloader re-runs handle() in the child
            # process with RUN_MAIN=true; suppress output there.
            if not os.environ.get('RUN_MAIN'):
                self.stdout.write('')
                self.stdout.write(
                    self.style.WARNING(f'  Binding to 0.0.0.0:{port} — reachable on all local interfaces.')
                )
                self.stdout.write(
                    self.style.WARNING('  ALLOWED_HOSTS temporarily set to [*] (DEBUG mode).')
                )
                self.stdout.write('')

        kwargs: dict[str, object] = {'addrport': f'{host}:{port}'}
        if options['noreload']:
            kwargs['use_reloader'] = False

        call_command('runserver', **kwargs)
