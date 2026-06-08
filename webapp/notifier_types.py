"""
Registry of supported notifier types.

To add a new notifier type, add an entry to NOTIFIER_TYPES:
  label  - human-readable name shown in the UI
  fields - ordered list of field descriptors:
    key      - the dict key in Notifier.config
    label    - display label (English fallback)
    t_key    - NOTIFICATIONS_VIEW translation key for the label
    type     - 'text' | 'password' | 'bool'
    required - whether the field must be non-empty to save (default False)
    default  - value to pre-fill when type is first selected (optional)
"""

NOTIFIER_TYPES: dict[str, dict] = {
    'pushover': {
        'label': 'Pushover',
        'fields': [
            {'key': 'app_token',     'label': 'App Token',     't_key': 'OPT_APP_TOKEN',     'type': 'password', 'required': True},
            {'key': 'user_token',    'label': 'User Token',    't_key': 'OPT_USER_TOKEN',    'type': 'password', 'required': True},
            {'key': 'supports_html', 'label': 'HTML Messages', 't_key': 'OPT_SUPPORTS_HTML', 'type': 'bool',     'default': True},
        ],
    },
    'discord': {
        'label': 'Discord',
        'fields': [
            {'key': 'webhook_id',    'label': 'Webhook ID',    't_key': 'OPT_WEBHOOK_ID',    'type': 'text',     'required': True},
            {'key': 'webhook_token', 'label': 'Webhook Token', 't_key': 'OPT_WEBHOOK_TOKEN', 'type': 'password', 'required': True},
        ],
    },
    'webpush': {
        'label': 'Web Push',
        # No configuration fields - subscriptions are managed per-device via
        # the browser's Push API.  The notifier edit page shows a dedicated
        # subscription-management UI when this type is selected.
        'fields': [],
    },
    'email': {
        'label': 'Email (SMTP)',
        'fields': [
            {'key': 'from_address', 'label': 'From Address',  't_key': 'OPT_FROM_ADDRESS',    'type': 'text',     'required': True},
            {'key': 'recipients',   'label': 'Recipients',    't_key': 'OPT_RECIPIENTS',      'type': 'text',     'required': True},
            {'key': 'smtp_server',  'label': 'SMTP Server',   't_key': 'OPT_SMTP_SERVER',     'type': 'text',     'required': True},
            {'key': 'smtp_port',    'label': 'SMTP Port',     't_key': 'OPT_SMTP_PORT',       'type': 'text',     'default': '587'},
            {'key': 'use_ssl',      'label': 'Use SSL',       't_key': 'OPT_USE_SSL',         'type': 'bool',     'default': False},
            {'key': 'use_auth',     'label': 'Authentication','t_key': 'OPT_USE_AUTH',        'type': 'bool',     'default': True},
            {'key': 'username',       'label': 'Username',       't_key': 'OPT_USERNAME',        'type': 'text'},
            {'key': 'password',       'label': 'Password',       't_key': 'OPT_SMTP_PASSWORD',   'type': 'password'},
            {'key': 'email_template', 'label': 'Email Template', 't_key': 'OPT_EMAIL_TEMPLATE',  'type': 'text'},
        ],
    },
    'slack': {
        'label': 'Slack',
        'fields': [
            {'key': 'webhook_url', 'label': 'Webhook URL', 't_key': 'OPT_WEBHOOK_URL', 'type': 'text', 'required': True},
        ],
    },
    'msteams': {
        'label': 'Microsoft Teams',
        'fields': [
            {'key': 'webhook_url', 'label': 'Webhook URL', 't_key': 'OPT_WEBHOOK_URL', 'type': 'text', 'required': True},
        ],
    },
    'googlechat': {
        'label': 'Google Chat',
        'fields': [
            {'key': 'webhook_url', 'label': 'Webhook URL', 't_key': 'OPT_WEBHOOK_URL', 'type': 'text', 'required': True},
        ],
    },
    'systemnotify': {
        'label': 'System Notification',
        # No configuration - fires osascript (macOS) or notify-send (Linux)
        # on the host running AutoPkg Runner.
        'fields': [],
    },
}


def type_choices() -> list[tuple[str, str]]:
    """Return [(value, label), ...] suitable for a <select> element."""
    return [(k, v['label']) for k, v in NOTIFIER_TYPES.items()]


def get_schema(notifier_type: str) -> dict:
    """Return the schema dict for a notifier type, or {} if unknown."""
    return NOTIFIER_TYPES.get(notifier_type, {})
