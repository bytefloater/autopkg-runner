"""Tests for notifiers.webpush."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


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

    def test_raises_when_vapid_keys_missing(self):
        self._set_vapid(priv='', pub='')
        with pytest.raises(RuntimeError, match='VAPID keys'):
            self._send(self._make_notifier(), message='Hi')

    def test_raises_when_notifier_pk_missing(self):
        self._set_vapid()
        from notifiers.webpush import send
        with pytest.raises(RuntimeError, match='notifier_pk'):
            send(configuration={}, message='Hi')

    def test_raises_when_no_subscriptions(self):
        self._set_vapid()
        with pytest.raises(RuntimeError, match='No devices'):
            self._send(self._make_notifier(), message='Hi')

    def test_sends_to_each_subscription(self):
        self._set_vapid()
        notifier = self._make_notifier()
        self._make_sub(notifier, endpoint='https://push.example.com/ep1')
        self._make_sub(notifier, endpoint='https://push.example.com/ep2')
        with patch('pywebpush.webpush') as mock_wp:
            self._send(notifier, message='Hello', title='Title')
        assert mock_wp.call_count == 2
        payload = json.loads(mock_wp.call_args_list[0][1]['data'])
        assert payload['body'] == 'Hello' and payload['title'] == 'Title'

    def test_url_included_in_payload(self):
        self._set_vapid()
        notifier = self._make_notifier()
        self._make_sub(notifier)
        with patch('pywebpush.webpush') as mock_wp:
            self._send(notifier, message='Hi', url='https://example.com/run/1')
        assert json.loads(mock_wp.call_args[1]['data'])['url'] == 'https://example.com/run/1'

    def test_no_url_omitted_from_payload(self):
        self._set_vapid()
        notifier = self._make_notifier()
        self._make_sub(notifier)
        with patch('pywebpush.webpush') as mock_wp:
            self._send(notifier, message='Hi')
        assert 'url' not in json.loads(mock_wp.call_args[1]['data'])

    def test_410_gone_deletes_subscription(self):
        from pywebpush import WebPushException
        from webapp.models import WebPushSubscription
        self._set_vapid()
        notifier = self._make_notifier()
        sub = self._make_sub(notifier)
        gone_resp = MagicMock()
        gone_resp.status_code = 410
        with patch('pywebpush.webpush', side_effect=WebPushException('Gone', response=gone_resp)):
            self._send(notifier, message='Hi')  # 410 is handled gracefully, not re-raised
        assert not WebPushSubscription.objects.filter(pk=sub.pk).exists()

    def test_non_410_webpush_exception_accumulates_error(self):
        from pywebpush import WebPushException
        self._set_vapid()
        notifier = self._make_notifier()
        self._make_sub(notifier)
        resp = MagicMock()
        resp.status_code = 500
        with patch('pywebpush.webpush', side_effect=WebPushException('Server error', response=resp)):
            with pytest.raises(RuntimeError, match='failed'):
                self._send(notifier, message='Hi')

    def test_generic_exception_accumulates_error(self):
        self._set_vapid()
        notifier = self._make_notifier()
        self._make_sub(notifier)
        with patch('pywebpush.webpush', side_effect=OSError('network down')):
            with pytest.raises(RuntimeError, match='failed'):
                self._send(notifier, message='Hi')

    def test_contact_used_in_vapid_claims(self):
        self._set_vapid(contact='mailto:admin@example.com')
        notifier = self._make_notifier()
        self._make_sub(notifier)
        with patch('pywebpush.webpush') as mock_wp:
            self._send(notifier, message='Hi')
        assert mock_wp.call_args[1]['vapid_claims']['sub'] == 'mailto:admin@example.com'

    def test_no_contact_uses_localhost_fallback(self):
        self._set_vapid(contact='')
        notifier = self._make_notifier()
        self._make_sub(notifier)
        with patch('pywebpush.webpush') as mock_wp:
            self._send(notifier, message='Hi')
        assert 'localhost' in mock_wp.call_args[1]['vapid_claims']['sub']
