"""
WebPush notifier — sends a push notification to all subscribed devices.

Requires pywebpush and VAPID keys configured in the application settings.
VAPID keys can be generated from the django management shell:

    from py_vapid import Vapid
    v = Vapid()
    v.generate_keys()
    # private key (base64url-encoded):
    import base64
    priv = base64.urlsafe_b64encode(v.private_key.private_bytes_raw()).decode()
    pub  = v.public_key.public_bytes_raw()
    pub_b64 = base64.urlsafe_b64encode(pub).decode()

Or use the management command:
    python manage.py generate_vapid_keys
"""

import json
from typing import Any


def send(configuration: dict, message: str, title: str | None = None,
         url: str | None = None, url_title: str | None = None) -> None:
    """
    Send a push notification to all WebPushSubscription rows attached to
    the calling Notifier.

    ``configuration`` is the notifier's decrypted_config dict — for WebPush
    this is always empty (subscriptions are stored in the DB, not here).  The
    notifier_pk is injected by NotifyOnCompletion when calling this function.

    Raises RuntimeError if VAPID keys are not configured.
    """
    from pywebpush import webpush, WebPushException
    from webapp.models import Setting, WebPushSubscription

    private_key = Setting.get('webpush.vapid_private_key', '').strip()
    public_key  = Setting.get('webpush.vapid_public_key',  '').strip()
    contact     = Setting.get('webpush.vapid_contact',     '').strip()

    if not private_key or not public_key:
        raise RuntimeError(
            'WebPush VAPID keys are not configured. '
            'Run: python manage.py generate_vapid_keys'
        )

    notifier_pk = configuration.get('_notifier_pk')
    if not notifier_pk:
        raise RuntimeError('Internal error: notifier_pk not passed in configuration.')

    subscriptions = WebPushSubscription.objects.filter(notifier_id=notifier_pk)
    if not subscriptions.exists():
        raise RuntimeError('No devices have subscribed to this notifier yet.')

    payload: dict[str, Any] = {
        'title': title or 'AutoPkg Runner',
        'body':  message,
    }
    if url:
        payload['url'] = url

    encoded_payload = json.dumps(payload)

    errors: list[str] = []
    sent = 0

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {
                        'p256dh': sub.p256dh,
                        'auth':   sub.auth,
                    },
                },
                data=encoded_payload,
                vapid_private_key=private_key,
                vapid_claims={
                    'sub': contact or 'mailto:admin@localhost',
                },
                content_encoding='aes128gcm',
            )
            sent += 1
        except WebPushException as exc:
            # A 410 Gone means the subscription is no longer valid — remove it.
            if exc.response is not None and exc.response.status_code == 410:
                sub.delete()
            else:
                errors.append(f'{sub.device_label or sub.endpoint[:40]}: {exc}')
        except Exception as exc:  # noqa: BLE001
            errors.append(f'{sub.device_label or sub.endpoint[:40]}: {exc}')

    if errors:
        raise RuntimeError(
            f'Sent to {sent} device(s) but {len(errors)} failed: '
            + '; '.join(errors)
        )
