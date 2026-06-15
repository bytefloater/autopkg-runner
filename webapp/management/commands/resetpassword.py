"""
manage.py resetpassword
-----------------------
Generate and set a new random password for an admin account.

Use this when the web UI password has been forgotten.
The new password is printed to stdout; it is not stored in plain text.
"""
import secrets
import sys

from django.core.management.base import BaseCommand, CommandError

_PASSWORD_BYTES = 16   # secrets.token_urlsafe(16) → ~22 printable chars


def _generate_password() -> str:
    return secrets.token_urlsafe(_PASSWORD_BYTES)


class Command(BaseCommand):
    help = 'Reset the password for an admin account and display the new password'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            help='Username of the superuser account whose password should be reset.',
        )

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        username = options['username']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"No user found with username '{username}'.")
        if not user.is_superuser:
            raise CommandError(
                f"User '{username}' is not a superuser. "
                'Only superuser passwords can be reset with this command.'
            )

        password = _generate_password()
        user.set_password(password)
        user.save(update_fields=['password'])

        width = 60
        inner = width - 6  # chars available between '  │  ' and '│'

        def box_line(text=''):
            return f'  │  {text:<{inner}}│'

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('  ┌' + '-' * (width - 4) + '┐'))
        self.stdout.write(self.style.SUCCESS(box_line('Password reset')))
        self.stdout.write(self.style.SUCCESS(f'  │  Username : {user.username:<{inner - 11}}│'))
        self.stdout.write(self.style.SUCCESS(f'  │  Password : {password:<{inner - 11}}│'))
        self.stdout.write(self.style.SUCCESS(box_line()))
        self.stdout.write(self.style.SUCCESS(box_line('Save this password - it is not stored in plain text.')))
        self.stdout.write(self.style.SUCCESS('  └' + '-' * (width - 4) + '┘'))
        self.stdout.write('')
