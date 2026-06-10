"""
Migration: zero-knowledge auth models + APIToken split.

Step 1 — Add AuthChallenge and UsedNonce models.
Step 2 — Add token_id (nullable) and token_secret (nullable) to APIToken.
Step 3 — Backfill new fields for any existing tokens (token_id from os.urandom,
          token_secret freshly generated and encrypted), then make non-nullable.
Step 4 — Remove the old 'key' field.
"""
import binascii
import os
import secrets

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def _backfill_tokens(apps, schema_editor):
    from webapp.encryption import encrypt
    APIToken = apps.get_model('webapp', 'APIToken')
    for token in APIToken.objects.filter(token_id__isnull=True):
        token.token_id = binascii.hexlify(os.urandom(16)).decode()
        token.token_secret = encrypt(secrets.token_hex(32))
        token.save(update_fields=['token_id', 'token_secret'])


class Migration(migrations.Migration):

    dependencies = [
        ('webapp', '0003_webpush_subscription'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- AuthChallenge -------------------------------------------------------
        migrations.CreateModel(
            name='AuthChallenge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('challenge_id', models.CharField(db_index=True, max_length=64, unique=True)),
                ('nonce', models.CharField(max_length=64)),
                ('username', models.CharField(max_length=150)),
                ('expires_at', models.DateTimeField()),
                ('used', models.BooleanField(default=False)),
            ],
            options={'verbose_name': 'Auth Challenge'},
        ),
        # --- UsedNonce -----------------------------------------------------------
        migrations.CreateModel(
            name='UsedNonce',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_id', models.CharField(db_index=True, max_length=32)),
                ('nonce', models.CharField(max_length=32)),
                ('used_at', models.DateTimeField()),
            ],
            options={'verbose_name': 'Used Nonce', 'unique_together': {('token_id', 'nonce')}},
        ),
        # --- APIToken: add new fields (nullable for backfill) --------------------
        migrations.AddField(
            model_name='apitoken',
            name='token_id',
            field=models.CharField(db_index=True, editable=False, max_length=32, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='apitoken',
            name='token_secret',
            field=models.CharField(editable=False, max_length=200, null=True),
        ),
        # --- Backfill existing tokens -------------------------------------------
        migrations.RunPython(_backfill_tokens, migrations.RunPython.noop),
        # --- Make non-nullable --------------------------------------------------
        migrations.AlterField(
            model_name='apitoken',
            name='token_id',
            field=models.CharField(db_index=True, editable=False, max_length=32, unique=True),
        ),
        migrations.AlterField(
            model_name='apitoken',
            name='token_secret',
            field=models.CharField(editable=False, max_length=200),
        ),
        # --- Remove old 'key' field ---------------------------------------------
        migrations.RemoveField(
            model_name='apitoken',
            name='key',
        ),
    ]
