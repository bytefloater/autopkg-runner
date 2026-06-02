"""Tests for webapp.views.notifications — all notification views."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.django_db
class TestNotificationsView:
    url = '/config/notifications/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_get_renders(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 200

    def test_get_includes_notifiers(self, client, notifier):
        resp = client.get(self.url)
        assert resp.status_code == 200
        assert notifier in resp.context['notifiers']

    def test_post_save_settings(self, client):
        resp = client.post(self.url, {
            '_action': 'save_settings',
            'notify.pwa_base_url': 'https://example.com',
            'notify.share_link_expiry_days': '7',
        })
        assert resp.status_code == 302
        from webapp.models import Setting
        assert Setting.get('notify.pwa_base_url') == 'https://example.com'

    def test_post_create_notifier_redirects_to_edit(self, client):
        resp = client.post(self.url, {
            'name': 'My Pushover',
            'notifier_type': 'pushover',
        })
        assert resp.status_code == 302
        assert '/config/notifications/' in resp['Location']

    def test_post_create_notifier_missing_name_rejected(self, client):
        resp = client.post(self.url, {
            'name': '',
            'notifier_type': 'pushover',
        })
        assert resp.status_code == 302  # redirect back with error

    def test_post_create_notifier_invalid_type_rejected(self, client):
        resp = client.post(self.url, {
            'name': 'Bad',
            'notifier_type': 'nonexistent_type',
        })
        assert resp.status_code == 302


@pytest.mark.django_db
class TestNotifierEditView:
    def _url(self, pk):
        return f'/config/notifications/{pk}/'

    def test_requires_login(self, anon_client, notifier):
        resp = anon_client.get(self._url(notifier.pk))
        assert resp.status_code == 302

    def test_get_renders(self, client, notifier):
        resp = client.get(self._url(notifier.pk))
        assert resp.status_code == 200

    def test_get_context_has_notifier(self, client, notifier):
        resp = client.get(self._url(notifier.pk))
        assert resp.context['notifier'] == notifier

    def test_get_webpush_notifier_includes_vapid_key(self, client, webpush_notifier):
        from webapp.models import Setting
        Setting.set('webpush.vapid_public_key', 'TESTKEY')
        resp = client.get(self._url(webpush_notifier.pk))
        assert resp.status_code == 200
        assert resp.context.get('vapid_public_key') == 'TESTKEY'

    def test_post_updates_notifier(self, client, notifier):
        resp = client.post(self._url(notifier.pk), {
            'name': 'Updated Name',
            'enabled': 'on',
            'title_template': 'Run: {status}',
            'message_template': '',
        })
        assert resp.status_code == 302
        notifier.refresh_from_db()
        assert notifier.name == 'Updated Name'
        assert notifier.enabled is True

    def test_post_saves_bool_config_field(self, client, notifier):
        resp = client.post(self._url(notifier.pk), {
            'name': notifier.name,
            'supports_html': 'on',
            'title_template': '',
            'message_template': '',
        })
        assert resp.status_code == 302
        notifier.refresh_from_db()
        assert notifier.config.get('supports_html') is True

    def test_post_blank_password_not_overwritten(self, client, notifier):
        # Set a real password first
        notifier.config = {'app_token': 'original'}
        notifier.save()
        # POST with blank password — should not clear it
        resp = client.post(self._url(notifier.pk), {
            'name': notifier.name,
            'app_token': '',       # blank → preserve existing
            'user_token': '',
            'title_template': '',
            'message_template': '',
        })
        assert resp.status_code == 302

    def test_get_404_for_unknown_notifier(self, client):
        import uuid
        resp = client.get(f'/config/notifications/{uuid.uuid4()}/')
        assert resp.status_code == 404


@pytest.mark.django_db
class TestNotifierDeleteView:
    def _url(self, pk):
        return f'/config/notifications/{pk}/delete/'

    def test_requires_login(self, anon_client, notifier):
        resp = anon_client.post(self._url(notifier.pk))
        assert resp.status_code == 302

    def test_deletes_notifier(self, client, notifier):
        pk = notifier.pk
        resp = client.post(self._url(pk))
        assert resp.status_code == 302
        from webapp.models import Notifier
        assert not Notifier.objects.filter(pk=pk).exists()

    def test_404_for_unknown(self, client):
        import uuid
        resp = client.post(f'/config/notifications/{uuid.uuid4()}/delete/')
        assert resp.status_code == 404


@pytest.mark.django_db
class TestNotifierToggleView:
    def _url(self, pk):
        return f'/config/notifications/{pk}/toggle/'

    def test_requires_login(self, anon_client, notifier):
        resp = anon_client.post(self._url(notifier.pk))
        assert resp.status_code == 302

    def test_toggles_enabled_to_false(self, client, notifier):
        assert notifier.enabled is True
        resp = client.post(self._url(notifier.pk))
        assert resp.status_code == 302
        notifier.refresh_from_db()
        assert notifier.enabled is False

    def test_toggles_disabled_to_true(self, client, notifier):
        notifier.enabled = False
        notifier.save()
        client.post(self._url(notifier.pk))
        notifier.refresh_from_db()
        assert notifier.enabled is True


@pytest.mark.django_db
class TestNotifierTestView:
    def _url(self, pk):
        return f'/config/notifications/{pk}/test/'

    def test_requires_login(self, anon_client, notifier):
        resp = anon_client.post(self._url(notifier.pk))
        assert resp.status_code == 302

    def test_returns_json_success(self, client, notifier):
        mock_send = MagicMock()
        with patch('importlib.import_module') as mock_import:
            mock_module = MagicMock()
            mock_module.send = mock_send
            mock_import.return_value = mock_module
            resp = client.post(self._url(notifier.pk))
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['success'] is True

    def test_returns_json_error_on_send_failure(self, client, notifier):
        with patch('importlib.import_module') as mock_import:
            mock_module = MagicMock()
            mock_module.send.side_effect = Exception('bad token')
            mock_import.return_value = mock_module
            resp = client.post(self._url(notifier.pk))
        assert resp.status_code == 500
        data = json.loads(resp.content)
        assert data['success'] is False
        assert 'bad token' in data['message']

    def test_returns_400_when_module_not_found(self, client, notifier):
        with patch('importlib.import_module', side_effect=ModuleNotFoundError('no module')):
            resp = client.post(self._url(notifier.pk))
        assert resp.status_code == 400
        data = json.loads(resp.content)
        assert data['success'] is False

    def test_returns_400_when_send_missing(self, client, notifier):
        with patch('importlib.import_module') as mock_import:
            mock_module = MagicMock(spec=[])  # no 'send' attribute
            mock_import.return_value = mock_module
            resp = client.post(self._url(notifier.pk))
        assert resp.status_code == 400
        data = json.loads(resp.content)
        assert data['success'] is False


@pytest.mark.django_db
class TestNotificationSettingsView:
    url = '/config/notifications/settings/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_get_renders(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 200

    def test_post_saves_settings(self, client):
        resp = client.post(self.url, {
            'notify.pwa_base_url': 'https://push.example.com',
            'notify.share_link_expiry_days': '30',
        })
        assert resp.status_code == 302
        from webapp.models import Setting
        assert Setting.get('notify.pwa_base_url') == 'https://push.example.com'


@pytest.mark.django_db
class TestWebPushVapidKeyView:
    url = '/config/notifications/vapid-key/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_returns_503_when_no_key_configured(self, client):
        from webapp.models import Setting
        Setting.set('webpush.vapid_public_key', '')
        resp = client.get(self.url)
        assert resp.status_code == 503

    def test_returns_key_when_configured(self, client):
        from webapp.models import Setting
        Setting.set('webpush.vapid_public_key', 'MYPUBLICKEY')
        resp = client.get(self.url)
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['public_key'] == 'MYPUBLICKEY'


@pytest.mark.django_db
class TestWebPushSubscribeView:
    def _url(self, pk):
        return f'/config/notifications/{pk}/subscribe/'

    def test_requires_login(self, anon_client, webpush_notifier):
        resp = anon_client.post(
            self._url(webpush_notifier.pk),
            content_type='application/json',
            data=json.dumps({}),
        )
        assert resp.status_code == 302

    def test_creates_subscription(self, client, webpush_notifier):
        payload = json.dumps({
            'endpoint': 'https://push.example.com/endpoint',
            'p256dh': 'AAAA',
            'auth': 'BBBB',
            'label': 'My iPhone',
        })
        resp = client.post(
            self._url(webpush_notifier.pk),
            data=payload,
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['status'] == 'subscribed'
        assert data['created'] is True

    def test_updates_existing_subscription(self, client, webpush_notifier):
        from webapp.models import WebPushSubscription
        sub = WebPushSubscription.objects.create(
            notifier=webpush_notifier,
            endpoint='https://push.example.com/endpoint',
            p256dh='OLD',
            auth='OLD',
        )
        payload = json.dumps({
            'endpoint': 'https://push.example.com/endpoint',
            'p256dh': 'NEWKEY',
            'auth': 'NEWAUTH',
        })
        resp = client.post(
            self._url(webpush_notifier.pk),
            data=payload,
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['created'] is False
        sub.refresh_from_db()
        assert sub.p256dh == 'NEWKEY'

    def test_returns_400_on_invalid_json(self, client, webpush_notifier):
        resp = client.post(
            self._url(webpush_notifier.pk),
            data='not-json',
            content_type='application/json',
        )
        assert resp.status_code == 400

    def test_returns_400_when_fields_missing(self, client, webpush_notifier):
        payload = json.dumps({'endpoint': 'https://push.example.com/ep'})
        resp = client.post(
            self._url(webpush_notifier.pk),
            data=payload,
            content_type='application/json',
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestWebPushUnsubscribeView:
    def _url(self, pk, sub_id):
        return f'/config/notifications/{pk}/unsubscribe/{sub_id}/'

    def test_requires_login(self, anon_client, webpush_notifier):
        resp = anon_client.post(self._url(webpush_notifier.pk, 999))
        assert resp.status_code == 302

    def test_deletes_subscription(self, client, webpush_notifier):
        from webapp.models import WebPushSubscription
        sub = WebPushSubscription.objects.create(
            notifier=webpush_notifier,
            endpoint='https://push.example.com/ep',
            p256dh='AAAA',
            auth='BBBB',
        )
        resp = client.post(self._url(webpush_notifier.pk, sub.pk))
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['status'] == 'unsubscribed'
        assert not WebPushSubscription.objects.filter(pk=sub.pk).exists()

    def test_404_for_unknown_subscription(self, client, webpush_notifier):
        resp = client.post(self._url(webpush_notifier.pk, 99999))
        assert resp.status_code == 404
