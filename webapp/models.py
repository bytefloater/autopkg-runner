from __future__ import annotations

import binascii
import os
import secrets
import uuid
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.db import models


# -- Key-value settings store ---------------------------------------------------

class Setting(models.Model):
    """
    One row per configuration value, addressed by a dot-notation key.
    All values are stored as strings; use the typed helpers (.get_bool, etc.)
    to coerce them at read time.

    Keys listed in SENSITIVE_KEYS are transparently encrypted at rest using
    Fernet symmetric encryption (see webapp/encryption.py).  The plaintext is
    always what callers see - encryption/decryption happens only in get/set.
    """

    # Keys whose values are encrypted before being written to the database.
    SENSITIVE_KEYS: frozenset[str] = frozenset({
        'repository.password',
        'webpush.vapid_private_key',
    })

    DEFAULTS: dict[str, str] = {
        # AutoPkg
        'autopkg.bin_path':      '/usr/local/bin/autopkg',
        'autopkg.cache_path':    '~/Library/AutoPkg/Cache',
        'autopkg.recipe_list':   '~/Library/Application Support/AutoPkgr/recipe_list.txt',
        'autopkg.overrides_dir': '~/Library/AutoPkg/RecipeOverrides',
        'autopkg.recipe_repos_dir': '~/Library/AutoPkg/RecipeRepos',
        # Workflow
        'workflow.update_repos': 'true',
        # Repository
        'repository.type':            'remote',   # local | remote
        'repository.connection_type': 'smb',      # smb | sftp  (remote only)
        'repository.local_path':      '',          # local type only
        'repository.host':            '',
        'repository.share':           '',
        'repository.mount_path':      '/tmp/Munki',
        'repository.public_url':      '',
        'repository.username':        '',
        'repository.password':        '',
        # Garbage Collector
        'gc.keep_versions':     '3',
        'gc.clear_temp':        'true',
        'gc.clean_repo':        'true',
        'gc.repoclean_bin_path':'/usr/local/munki/repoclean',
        # Logging
        'logging.level':     'INFO',
        'logging.to_file':   'false',
        'logging.file_path': '~/logs/autopkg-runner',
        # Notifications
        'notify.pwa_base_url': '',          # Base URL for share links (e.g. https://autopkg.example.com)
        'notify.share_link_expiry_days': '', # Days after which share links expire; blank = never
        # WebPush
        'webpush.vapid_private_key': '',
        'webpush.vapid_public_key':  '',
        'webpush.vapid_contact':     '',
        # User Interface
        'ui.language': 'en-US',
    }

    key   = models.CharField(max_length=200, unique=True)
    value = models.TextField(blank=True, default='')

    class Meta:
        ordering  = ['key']
        db_table  = 'webapp_settings'

    def __str__(self):
        return f'{self.key} = {self.value[:60]}'

    # -- Class-level helpers ----------------------------------------------------

    @classmethod
    def get(cls, key: str, default: Optional[str]=None) -> str:
        try:
            raw = cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default if default is not None else cls.DEFAULTS.get(key, '')
        if key in cls.SENSITIVE_KEYS:
            from webapp.encryption import decrypt
            return decrypt(raw)
        return raw

    @classmethod
    def set(cls, key: str, value: str) -> None:
        if key in cls.SENSITIVE_KEYS and value:
            from webapp.encryption import encrypt, is_encrypted
            if not is_encrypted(value):
                value = encrypt(value)
        cls.objects.update_or_create(key=key, defaults={'value': str(value)})

    @classmethod
    def get_bool(cls, key: str) -> bool:
        return cls.get(key).lower() in ('true', '1', 'yes', 'on')

    @classmethod
    def get_int(cls, key: str, fallback: int = 0) -> int:
        try:
            return int(cls.get(key, str(fallback)))
        except ValueError:
            return fallback

    @classmethod
    def get_all(cls) -> dict[str, str]:
        """Merge DB values on top of defaults; returns a complete settings dict with sensitive keys decrypted."""
        from webapp.encryption import decrypt
        result = dict(cls.DEFAULTS)
        for s in cls.objects.all():
            result[s.key] = s.value
        for key in cls.SENSITIVE_KEYS:
            if key in result:
                result[key] = decrypt(result[key])
        return result


# -- Notifiers ------------------------------------------------------------------

def _notifier_sensitive_keys(notifier_type: str) -> frozenset[str]:
    """Return the set of config keys that are 'password' type for *notifier_type*."""
    from webapp.notifier_types import NOTIFIER_TYPES
    schema = NOTIFIER_TYPES.get(notifier_type, {})
    return frozenset(f['key'] for f in schema.get('fields', []) if f.get('type') == 'password')


class Notifier(models.Model):
    """
    A named, user-configured notification destination.

    Password-type fields inside *config* are stored encrypted.
    Always use the ``decrypted_config`` property when reading credentials for
    pipeline / notifier use.  The raw ``config`` dict (with ``enc:`` prefixes)
    is intentionally kept internal.
    """

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name             = models.CharField(max_length=100)
    notifier_type    = models.CharField(max_length=50)
    enabled          = models.BooleanField(default=True)
    config           = models.JSONField(default=dict,
                                        help_text='Type-specific key/value settings (passwords encrypted)')
    title_template   = models.TextField(blank=True, default='',
                                        help_text='Custom notification title. Leave blank for default.')
    message_template = models.TextField(blank=True, default='',
                                        help_text=(
                                            'Custom message body. Available variables: '
                                            '{status}, {status_emoji}, {imports}, {failures}, '
                                            '{downloads}, {duration}, {share_url}, {run_id}, '
                                            '{triggered_by}, {date}, {time}. '
                                            'Leave blank to use the auto-generated message.'
                                        ))
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        status = 'on' if self.enabled else 'off'
        return f'{self.name} [{self.notifier_type}:{status}]'

    def save(self, *args, **kwargs):
        """Encrypt password-type config fields before writing to the database."""
        from webapp.encryption import encrypt, is_encrypted
        sensitive = _notifier_sensitive_keys(self.notifier_type)
        cfg = dict(self.config or {})
        for key in sensitive:
            val = cfg.get(key, '')
            if val and not is_encrypted(val):
                cfg[key] = encrypt(val)
        self.config = cfg
        super().save(*args, **kwargs)

    @property
    def decrypted_config(self) -> dict:
        """Return a copy of *config* with all password fields decrypted."""
        from webapp.encryption import decrypt
        sensitive = _notifier_sensitive_keys(self.notifier_type)
        cfg = dict(self.config or {})
        for key in sensitive:
            if key in cfg:
                cfg[key] = decrypt(cfg[key])
        return cfg



class Schedule(models.Model):
    """Cron schedule for automatic pipeline runs (single row, pk=1)."""
    enabled      = models.BooleanField(default=False)
    minute       = models.CharField(max_length=20, default='0')
    hour         = models.CharField(max_length=20, default='2')
    day_of_week  = models.CharField(max_length=20, default='*')
    day_of_month = models.CharField(max_length=20, default='*')
    month        = models.CharField(max_length=20, default='*')

    class Meta:
        verbose_name = 'Schedule'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> tuple[int, dict[str, int]]:
        # Singleton row - deletion is intentionally a no-op.
        return 0, {}

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        status = 'enabled' if self.enabled else 'disabled'
        return f'Schedule ({status}: {self.minute} {self.hour} {self.day_of_week} {self.day_of_month} {self.month})'


# -- Pipeline runs --------------------------------------------------------------

class Run(models.Model):
    PENDING   = 'pending'
    RUNNING   = 'running'
    SUCCESS   = 'success'
    FAILED    = 'failed'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (PENDING,   'Pending'),
        (RUNNING,   'Running'),
        (SUCCESS,   'Success'),
        (FAILED,    'Failed'),
        (CANCELLED, 'Cancelled'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    triggered_by    = models.CharField(max_length=50, default='manual')
    started_at      = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at    = models.DateTimeField(null=True, blank=True)
    config_snapshot = models.JSONField(default=dict)

    # Reverse relations - declared for type checkers (django-stubs does not
    # synthesise related managers from related_name automatically).
    if TYPE_CHECKING:
        stage_executions : models.Manager[StageExecution]
        log_entries      : models.Manager[LogEntry]
        recipe_results   : models.Manager[RecipeResult]
        tasks            : models.Manager[Task]
        share_token      : RunShareToken

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'Run {self.id} [{self.status}]'

    @property
    def duration(self):
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


class StageExecution(models.Model):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED  = 'failed'
    SKIPPED = 'skipped'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (RUNNING, 'Running'),
        (SUCCESS, 'Success'),
        (FAILED,  'Failed'),
        (SKIPPED, 'Skipped'),
    ]

    run          = models.ForeignKey(Run, on_delete=models.CASCADE, related_name='stage_executions')
    name         = models.CharField(max_length=100)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    order        = models.PositiveIntegerField(default=0)
    started_at   = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.name} [{self.status}]'

    @property
    def duration(self):
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


class LogEntry(models.Model):
    LEVEL_CHOICES = [
        ('DEBUG',   'Debug'),
        ('INFO',    'Info'),
        ('WARNING', 'Warning'),
        ('ERROR',   'Error'),
        ('CRITICAL','Critical'),
        ('NOTICE',  'Notice'),
    ]

    id         : int  # Django auto-field; declared for type checkers
    run        = models.ForeignKey(Run, on_delete=models.CASCADE, related_name='log_entries')
    timestamp  = models.DateTimeField(db_index=True)
    level      = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='INFO')
    message    = models.TextField()
    stage_name = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['timestamp']
        indexes = [models.Index(fields=['run', 'timestamp'])]

    def __str__(self):
        return f'[{self.level}] {self.message[:80]}'


class RecipeResult(models.Model):
    RESULT_TYPES = [
        ('failure',      'Failure'),
        ('munki_import', 'Munki Import'),
        ('pkg_copied',   'Package Copied'),
        ('url_downloaded','URL Downloaded'),
        ('trust_updated','Trust Updated'),
        ('deprecation',  'Deprecation'),
    ]

    run         = models.ForeignKey(Run, on_delete=models.CASCADE, related_name='recipe_results')
    run_id: uuid.UUID  # synthesised by Django from the ForeignKey; declared for type checkers
    result_type = models.CharField(max_length=30, choices=RESULT_TYPES)
    data        = models.JSONField(default=list)

    def __str__(self):
        return f'{self.result_type} for run {self.run_id}'


class RunShareToken(models.Model):
    """
    Obscure, unauthenticated-access token for a completed run's share report.

    The token is a cryptographically random URL-safe string.  It is generated
    on first use (at notification dispatch time) and deleted automatically when
    its parent Run is deleted.  The share report intentionally omits log entries
    and stack traces - it shows only stage statuses and AutoPkg output.
    """

    token      = models.CharField(max_length=86, unique=True, db_index=True)
    run        = models.OneToOneField(Run, on_delete=models.CASCADE, related_name='share_token')
    run_id: uuid.UUID  # synthesised by Django from the OneToOneField; declared for type checkers
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Run Share Token'

    def __str__(self):
        return f'ShareToken({self.token[:12]}…) → Run {self.run_id}'

    @classmethod
    def get_or_create_for_run(cls, run: 'Run') -> 'RunShareToken':
        """Return the existing share token for *run*, or create one."""
        import secrets
        try:
            return cls.objects.get(run=run)
        except cls.DoesNotExist:
            return cls.objects.create(
                run=run,
                token=secrets.token_urlsafe(48),  # 48 bytes → 64 URL-safe chars
            )


class WebPushSubscription(models.Model):
    """
    A single browser push subscription for a WebPush-type notifier.

    Each browser/device that subscribes to push notifications for a given
    notifier gets its own row.  The endpoint, p256dh, and auth fields come
    directly from the browser's PushSubscription object.
    """

    notifier     = models.ForeignKey('Notifier', on_delete=models.CASCADE, related_name='webpush_subscriptions')
    endpoint     = models.TextField(unique=True)
    p256dh       = models.CharField(max_length=300)
    auth         = models.CharField(max_length=100)
    device_label = models.CharField(max_length=100, blank=True,
                                    help_text='Human-readable label, e.g. "iPhone 15 Pro - Safari"')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'WebPush Subscription'

    def __str__(self):
        label = self.device_label or self.endpoint[:60]
        return f'WebPush({label}) → {self.notifier.name}'


class Task(models.Model):
    PENDING   = 'pending'
    RUNNING   = 'running'
    SUCCESS   = 'success'
    FAILED    = 'failed'
    TYPE_CHOICES   = [('pipeline_run', 'Pipeline Run'), ('db_cleanup', 'DB Cleanup')]
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (RUNNING, 'Running'),
        (SUCCESS, 'Success'),
        (FAILED,  'Failed'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_type    = models.CharField(max_length=30, choices=TYPE_CHOICES)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    run          = models.ForeignKey(Run, null=True, blank=True, on_delete=models.SET_NULL, related_name='tasks')
    run_id       : Optional[uuid.UUID] # synthesised by Django from the ForeignKey; declared for type checkers
    created_at   = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error        = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Task {self.id} [{self.task_type}:{self.status}]'


# -- Authentication challenges --------------------------------------------------

class AuthChallenge(models.Model):
    """
    Short-lived one-time challenge used in zero-knowledge login.

    The client requests a challenge, uses it to compute an HMAC response
    without sending the password, then the server verifies and marks it used.
    """
    challenge_id = models.CharField(max_length=64, unique=True, db_index=True)
    nonce        = models.CharField(max_length=64)
    username     = models.CharField(max_length=150)
    expires_at   = models.DateTimeField()
    used         = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Auth Challenge'


class UsedNonce(models.Model):
    """
    Records nonces consumed by HMAC-signed API requests.

    Prevents replay attacks within the timestamp tolerance window.
    Rows older than the window can be pruned periodically.
    """
    token_id   = models.CharField(max_length=32, db_index=True)
    nonce      = models.CharField(max_length=32)
    used_at    = models.DateTimeField()

    class Meta:
        verbose_name = 'Used Nonce'
        unique_together = [('token_id', 'nonce')]


# -- API tokens -----------------------------------------------------------------

class APIToken(models.Model):
    """
    Named API token for HMAC-signed requests.

    token_id     — public identifier sent in the Authorization header Credential= field
    token_secret — 32-byte secret (encrypted at rest) used as the HMAC key; shown once at creation
    """

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_tokens')
    name         = models.CharField(max_length=100, verbose_name='Token name')
    token_id     = models.CharField(max_length=32, unique=True, db_index=True, editable=False)
    token_secret = models.CharField(max_length=200, editable=False)  # encrypted at rest
    created      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']
        verbose_name = 'API Token'

    def save(self, *args, **kwargs):
        from webapp.encryption import encrypt, is_encrypted
        if not self.token_id:
            self.token_id = binascii.hexlify(os.urandom(16)).decode()
        if not self.token_secret:
            raw_secret = secrets.token_hex(32)
            self.token_secret = encrypt(raw_secret)
        elif self.token_secret and not is_encrypted(self.token_secret):
            self.token_secret = encrypt(self.token_secret)
        super().save(*args, **kwargs)

    @property
    def decrypted_secret(self) -> str:
        from webapp.encryption import decrypt
        return decrypt(self.token_secret)

    def __str__(self):
        return f'{self.user.username} / {self.name}'


# -- User permissions -----------------------------------------------------------

class UserPermission(models.Model):
    """
    Granular permission flags for a single user.

    Superusers bypass all checks and never need a row here.
    Absence of a row is equivalent to all flags being False.
    """
    user             = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='permissions_ext',
    )
    can_manage_users = models.BooleanField(default=False)
    can_trigger_runs = models.BooleanField(default=False)
    can_edit_config  = models.BooleanField(default=False)
    can_view_runs    = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'User Permission'

    def __str__(self):
        return f'Permissions for {self.user.username}'
