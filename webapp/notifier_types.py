"""
Registry of supported notifier types.

To add a new notifier type, add an entry to NOTIFIER_TYPES:
  label  — human-readable name shown in the UI
  fields — ordered list of field descriptors:
    key      — the dict key in Notifier.config
    label    — display label
    type     — 'text' | 'password' | 'bool' | 'select'
    required — whether the field must be non-empty to save (default False)
    default  — value to pre-fill when type is first selected (optional)
    options  — [(value, label), ...] for 'select' type
"""

NOTIFIER_TYPES: dict[str, dict] = {
    'pushover': {
        'label': 'Pushover',
        'fields': [
            {'key': 'app_token',     'label': 'App Token',     'type': 'password', 'required': True},
            {'key': 'user_token',    'label': 'User Token',    'type': 'password', 'required': True},
            {'key': 'supports_html', 'label': 'HTML Messages', 'type': 'bool',     'default': True},
        ],
    },
    'discord': {
        'label': 'Discord',
        'fields': [
            {'key': 'webhook_id',    'label': 'Webhook ID',    'type': 'text',     'required': True},
            {'key': 'webhook_token', 'label': 'Webhook Token', 'type': 'password', 'required': True},
        ],
    },
}


def type_choices() -> list[tuple[str, str]]:
    """Return [(value, label), ...] suitable for a <select> element."""
    return [(k, v['label']) for k, v in NOTIFIER_TYPES.items()]


def get_schema(notifier_type: str) -> dict:
    """Return the schema dict for a notifier type, or {} if unknown."""
    return NOTIFIER_TYPES.get(notifier_type, {})
