"""
Management command: generate_vapid_keys

Generates a fresh VAPID key pair and stores it in the database Settings table.
The public key is printed (needed to initialise the browser Push API) and the
private key is stored encrypted.

Usage:
    python manage.py generate_vapid_keys [--contact mailto:admin@example.com]
    python manage.py generate_vapid_keys --force   # overwrite existing keys
"""

import base64

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate VAPID keys for WebPush notifications and store them in Settings.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--contact',
            default='',
            help='VAPID contact URI (mailto: or https:).  Stored in Settings.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing VAPID keys.',
        )

    def handle(self, *args, **options):
        from webapp.models import Setting

        existing_priv = Setting.get('webpush.vapid_private_key', '').strip()
        if existing_priv and not options['force']:
            self.stdout.write(self.style.WARNING(
                'VAPID keys already exist.  Use --force to overwrite.'
            ))
            pub = Setting.get('webpush.vapid_public_key', '').strip()
            self.stdout.write(f'\nPublic key (applicationServerKey):\n{pub}\n')
            return

        try:
            from py_vapid import Vapid
        except ImportError:
            self.stderr.write(self.style.ERROR(
                'pywebpush is not installed.  Run: pip install pywebpush'
            ))
            return

        v = Vapid()
        v.generate_keys()

        # Encode private key as URL-safe base64 (no padding).
        # private_bytes_raw() was added in cryptography 40; use private_numbers()
        # to extract the raw 32-byte scalar — works on all versions.
        priv_int = v.private_key.private_numbers().private_value
        priv_raw = priv_int.to_bytes(32, 'big')
        priv_b64  = base64.urlsafe_b64encode(priv_raw).decode().rstrip('=')

        # Public key: uncompressed point (65 bytes), base64url-encoded
        from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        pub_bytes = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        pub_b64   = base64.urlsafe_b64encode(pub_bytes).decode().rstrip('=')

        Setting.set('webpush.vapid_private_key', priv_b64)
        Setting.set('webpush.vapid_public_key',  pub_b64)

        contact = options['contact'].strip()
        if contact:
            Setting.set('webpush.vapid_contact', contact)

        self.stdout.write(self.style.SUCCESS('\n✅  VAPID keys generated and stored.\n'))
        self.stdout.write(f'Public key (use as applicationServerKey in browser):\n{pub_b64}\n')
        if contact:
            self.stdout.write(f'Contact: {contact}\n')
        self.stdout.write(
            '\nThe private key is encrypted in the database. '
            'Regenerating keys will invalidate all existing push subscriptions.\n'
        )
