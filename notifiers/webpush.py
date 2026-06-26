"""
WebPush notifier - sends a push notification to all subscribed devices.

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
import logging
import time
import urllib.parse
from typing import Any, Optional

logger = logging.getLogger('autopkg_runner')

# Push services that do NOT support HTTP/2 and must fall back to HTTP/1.1.
# All other services use HTTP/2 (required by APNs; preferred for FCM/WNS/Mozilla).
_HTTP1_ONLY_HOSTS: frozenset[str] = frozenset()


def send(configuration: dict, message: str, title: Optional[str] = None,
         url: Optional[str] = None, url_title: Optional[str] = None) -> None:
    """
    Send a push notification to all WebPushSubscription rows attached to
    the calling Notifier.

    ``configuration`` is the notifier's decrypted_config dict - for WebPush
    this is always empty (subscriptions are stored in the DB, not here).  The
    notifier_pk is injected by NotifyOnCompletion when calling this function.

    Raises RuntimeError if VAPID keys are not configured.
    """
    import httpx
    from py_vapid import Vapid
    from pywebpush import WebPusher, WebPushException
    from webapp.models import Setting, WebPushSubscription

    private_key  = Setting.get('webpush.vapid_private_key', '').strip()
    public_key   = Setting.get('webpush.vapid_public_key',  '').strip()
    contact      = Setting.get('webpush.vapid_contact',     '').strip()
    pwa_base_url = Setting.get('notify.pwa_base_url',       '').strip()

    if not private_key or not public_key:
        raise RuntimeError(
            'WebPush VAPID keys are not configured. '
            'Run: python manage.py generate_vapid_keys'
        )

    notifier_pk = configuration.get('_notifier_pk')
    if not notifier_pk:
        raise RuntimeError('Internal error: notifier_pk not passed in configuration.')

    # Build a valid VAPID sub claim (RFC 8292: mailto: or https: URI).
    # APNs rejects mailto:admin@localhost (non-routable domain) with BadJwtToken.
    # Prefer the operator contact email, then the app base URL, then a safe fallback.
    if contact:
        sub_claim = contact if contact.startswith(('mailto:', 'https://', 'http://')) else f'mailto:{contact}'
    elif pwa_base_url:
        sub_claim = pwa_base_url.rstrip('/')
    else:
        sub_claim = 'mailto:admin@example.com'

    subscriptions = WebPushSubscription.objects.filter(notifier_id=notifier_pk)
    if not subscriptions.exists():
        raise RuntimeError('No devices have subscribed to this notifier yet.')

    payload: dict[str, Any] = {'title': title or 'AutoPkg Runner', 'body': message}
    if url:
        payload['url'] = url

    # Warn if the private key doesn't match the stored public key — this would
    # cause all pushes to fail with a VAPID key mismatch error on the push service.
    try:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        import base64
        _v = Vapid.from_string(private_key)
        if _v.public_key is not None:
            _derived = base64.urlsafe_b64encode(
                _v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
            ).decode().rstrip('=')
            logger.debug('WebPush signing with public key: %s', _derived)
            logger.debug('WebPush stored  public key:     %s', public_key)
            if _derived != public_key:
                logger.warning('WebPush KEY MISMATCH: derived=%s stored=%s', _derived, public_key)
    except Exception as _e:
        logger.debug('WebPush key check failed: %s', _e)

    logger.debug('WebPush sub claim: %s', sub_claim)
    logger.debug('WebPush sending payload: %s', json.dumps(payload))

    encoded_payload = json.dumps(payload).encode()

    vv = Vapid.from_string(private_key)
    vv.conf['no-strict'] = True  # allow https:/http: sub claims (RFC 8292 permits both)

    errors: list[str] = []
    sent = 0

    for sub in subscriptions:
        label = sub.device_label or sub.endpoint[:60]
        logger.debug('WebPush → %s  endpoint=%s  p256dh=%s…  auth=%s…',
                     label, sub.endpoint,
                     sub.p256dh[:12] if sub.p256dh else '(none)',
                     sub.auth[:8] if sub.auth else '(none)')
        try:
            parsed = urllib.parse.urlparse(sub.endpoint)
            aud = f"{parsed.scheme}://{parsed.netloc}"

            vapid_headers = vv.sign({
                'sub': sub_claim,
                'aud': aud,
                'exp': int(time.time()) + 43200,
            })
            # py_vapid emits "vapid t=<jwt>,k=<key>" but RFC 8292 / APNs require
            # a space before k=: "vapid t=<jwt>, k=<key>".
            auth_header = vapid_headers.get('Authorization', '').replace(',k=', ', k=')

            pusher = WebPusher(subscription_info={
                'endpoint': sub.endpoint,
                'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
            })
            send_params = pusher._prepare_send_data(
                encoded_payload,
                headers={'Authorization': auth_header, 'Urgency': 'high', 'Content-Type': 'application/octet-stream'},
                ttl=86400,
                content_encoding='aes128gcm',
            )
            req_headers = dict(send_params['headers'])
            req_body: bytes = send_params['data'] or b''
            endpoint = send_params['endpoint']

            logger.debug('WebPush request  %s  headers=%s  body=%d bytes',
                         label, req_headers, len(req_body))

            use_http2 = parsed.netloc not in _HTTP1_ONLY_HOSTS
            if use_http2:
                with httpx.Client(http2=True) as client:
                    hx_resp = client.post(endpoint, content=req_body, headers=req_headers)
                status = hx_resp.status_code
                body   = hx_resp.text
                logger.debug('WebPush %s %s  status=%s  proto=%s  body=%r',
                             '✓' if status <= 202 else '✗', label,
                             status, hx_resp.http_version, body[:200])
                if status > 202:
                    # Map to permanent-failure codes so we can clean up stale subscriptions.
                    _fake_resp = _HttpResponse(status, body)
                    raise WebPushException(
                        f"Push failed: {status}\nResponse body:{body}",
                        response=_fake_resp,
                    )
            else:
                resp = pusher.requests_method.post(
                    endpoint, data=req_body, headers=req_headers, timeout=10
                )
                logger.debug('WebPush %s %s  status=%s  body=%r',
                             '✓' if resp.status_code <= 202 else '✗', label,
                             resp.status_code, resp.text[:200])
                if resp.status_code > 202:
                    raise WebPushException(
                        f"Push failed: {resp.status_code}\nResponse body:{resp.text}",
                        response=resp,
                    )
            sent += 1

        except WebPushException as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            logger.warning('WebPush failed for %s: status=%s  %s', label, status_code, exc)
            # 401/403 (VAPID key mismatch) and 410 Gone mean the subscription is
            # permanently invalid — remove it so it stops accumulating silently.
            # 400 is NOT included: it means a malformed request, not an invalid subscription.
            if status_code in (401, 403, 410):
                sub.delete()
                logger.info('WebPush removed stale subscription for %s (HTTP %s)', label, status_code)
            else:
                errors.append(f'{label}: {exc}')

        except Exception as exc:  # noqa: BLE001
            logger.warning('WebPush failed for %s: %r', label, exc)
            errors.append(f'{label}: {exc}')

    if errors:
        raise RuntimeError(
            f'Sent to {sent} device(s) but {len(errors)} failed: '
            + '; '.join(errors)
        )


class _HttpResponse:
    """Minimal requests.Response-like wrapper for httpx responses."""

    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text
        self.headers: dict[str, str] = {}
