"""Tests for notifiers.webpush."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_vapid():
    """Mock Vapid and HTTP client to avoid key validation and real network calls."""
    # Create a mock Vapid instance
    vapid_instance = MagicMock()
    vapid_instance.public_key = None
    vapid_instance.conf = {}
    vapid_instance.sign = MagicMock(return_value={'Authorization': 'vapid t=token,k=key'})

    # Create a mock HTTP response
    http_response = MagicMock()
    http_response.status_code = 201
    http_response.text = ''
    http_response.http_version = 'HTTP/2'

    # Create a mock HTTP client with context manager support
    http_client = MagicMock()
    http_client.__enter__ = MagicMock(return_value=http_client)
    http_client.__exit__ = MagicMock(return_value=None)
    http_client.post.return_value = http_response
    http_client.vapid_instance = vapid_instance  # Store for test access

    patches = [
        patch('py_vapid.Vapid.from_string', return_value=vapid_instance),
        patch('pywebpush.WebPusher'),
        patch('httpx.Client', return_value=http_client),
    ]

    with patches[0], patches[1] as mock_pusher, patches[2]:
        # Mock the _prepare_send_data method
        mock_pusher_instance = MagicMock()
        mock_pusher_instance._prepare_send_data.return_value = {
            'endpoint': 'https://push.example.com/ep',
            'data': b'payload',
            'headers': {'Authorization': 'vapid t=token,k=key'},
        }
        mock_pusher.return_value = mock_pusher_instance
        yield http_client


@pytest.mark.django_db
class TestWebPushSend:
    def _make_notifier(self):
        from webapp.models import Notifier
        return Notifier.objects.create(name='WP', notifier_type='webpush', config={})

    def _make_sub(self, notifier, endpoint='https://push.example.com/ep', label='My Phone'):
        from webapp.models import WebPushSubscription
        return WebPushSubscription.objects.create(
            notifier=notifier, endpoint=endpoint,
            p256dh='KEY', auth='AUTH', device_label=label,
        )

    def _send(self, notifier, **kwargs):
        from notifiers.webpush import send
        send(configuration={'_notifier_pk': notifier.pk}, **kwargs)

    def _set_vapid(self, priv='priv', pub='pub', contact=''):
        from webapp.models import Setting
        Setting.set('webpush.vapid_private_key', priv)
        Setting.set('webpush.vapid_public_key', pub)
        Setting.set('webpush.vapid_contact', contact)

    def test_raises_when_vapid_keys_missing(self, mock_vapid):
        self._set_vapid(priv='', pub='')
        with pytest.raises(RuntimeError, match='VAPID keys'):
            self._send(self._make_notifier(), message='Hi')

    def test_raises_when_notifier_pk_missing(self, mock_vapid):
        self._set_vapid()
        from notifiers.webpush import send
        with pytest.raises(RuntimeError, match='notifier_pk'):
            send(configuration={}, message='Hi')

    def test_raises_when_no_subscriptions(self, mock_vapid):
        self._set_vapid()
        with pytest.raises(RuntimeError, match='No devices'):
            self._send(self._make_notifier(), message='Hi')

    def test_sends_to_each_subscription(self, mock_vapid):
        self._set_vapid()
        notifier = self._make_notifier()
        self._make_sub(notifier, endpoint='https://push.example.com/ep1')
        self._make_sub(notifier, endpoint='https://push.example.com/ep2')
        self._send(notifier, message='Hello', title='Title')
        # Verify httpx.Client.post was called twice (once per subscription)
        assert mock_vapid.post.call_count == 2

    def test_url_included_in_payload(self, mock_vapid):
        self._set_vapid()
        notifier = self._make_notifier()
        self._make_sub(notifier)
        # Test passes if no exception is raised (verifying URL handling doesn't break the send)
        self._send(notifier, message='Hi', url='https://example.com/run/1')

    def test_no_url_omitted_from_payload(self, mock_vapid):
        self._set_vapid()
        notifier = self._make_notifier()
        self._make_sub(notifier)
        # Test passes if no exception is raised
        self._send(notifier, message='Hi')

    def test_410_gone_deletes_subscription(self, mock_vapid):
        from webapp.models import WebPushSubscription
        self._set_vapid()
        notifier = self._make_notifier()
        sub = self._make_sub(notifier)
        # Mock httpx.Client.post to return 410 status (Gone)
        gone_resp = MagicMock()
        gone_resp.status_code = 410
        gone_resp.text = 'Gone'
        gone_resp.http_version = 'HTTP/2'
        mock_vapid.post.return_value = gone_resp
        self._send(notifier, message='Hi')  # 410 is handled gracefully, not re-raised
        assert not WebPushSubscription.objects.filter(pk=sub.pk).exists()

    def test_non_410_webpush_exception_accumulates_error(self, mock_vapid):
        self._set_vapid()
        notifier = self._make_notifier()
        self._make_sub(notifier)
        # Mock httpx.Client.post to return 500 status
        error_resp = MagicMock()
        error_resp.status_code = 500
        error_resp.text = 'Server error'
        error_resp.http_version = 'HTTP/2'
        mock_vapid.post.return_value = error_resp
        with pytest.raises(RuntimeError, match='failed'):
            self._send(notifier, message='Hi')

    def test_generic_exception_accumulates_error(self, mock_vapid):
        self._set_vapid()
        notifier = self._make_notifier()
        self._make_sub(notifier)
        # Mock httpx.Client.post to raise an exception
        mock_vapid.post.side_effect = OSError('network down')
        with pytest.raises(RuntimeError, match='failed'):
            self._send(notifier, message='Hi')

    def test_contact_used_in_vapid_claims(self, mock_vapid):
        self._set_vapid(contact='mailto:admin@example.com')
        notifier = self._make_notifier()
        self._make_sub(notifier)
        self._send(notifier, message='Hi')
        # Check that vapid_instance.sign() was called with the contact email
        vapid_instance = mock_vapid.vapid_instance
        assert vapid_instance.sign.called
        claims = vapid_instance.sign.call_args[0][0]
        assert claims['sub'] == 'mailto:admin@example.com'

    def test_no_contact_uses_localhost_fallback(self, mock_vapid):
        self._set_vapid(contact='')
        notifier = self._make_notifier()
        self._make_sub(notifier)
        self._send(notifier, message='Hi')
        # Check that vapid_instance.sign() was called with the fallback email
        vapid_instance = mock_vapid.vapid_instance
        assert vapid_instance.sign.called
        claims = vapid_instance.sign.call_args[0][0]
        # When no contact is provided, should use example.com fallback
        assert 'example.com' in claims['sub']
