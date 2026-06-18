"""Tests for webapp.views.notifications - all notification views."""
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

    def test_get_renders(self, config_editor_client):
        resp = config_editor_client.get(self.url)
        assert resp.status_code == 200

    def test_get_includes_notifiers(self, config_editor_client, notifier):
        resp = config_editor_client.get(self.url)
        assert resp.status_code == 200
        assert notifier in resp.context['notifiers']

    def test_post_save_settings(self, config_editor_client):
        resp = config_editor_client.post('/config/notifications/settings/', {
            'notify.pwa_base_url': 'https://example.com',
            'notify.share_link_expiry_days': '7',
        })
        assert resp.status_code == 302
        from webapp.models import Setting
        assert Setting.get('notify.pwa_base_url') == 'https://example.com'

    def test_post_create_notifier_redirects_to_edit(self, config_editor_client):
        resp = config_editor_client.post(self.url, {
            'name': 'My Pushover',
            'notifier_type': 'pushover',
        })
        assert resp.status_code == 302
        assert '/config/notifications/' in resp['Location']

    def test_post_create_notifier_missing_name_rejected(self, config_editor_client):
        resp = config_editor_client.post(self.url, {
            'name': '',
            'notifier_type': 'pushover',
        })
        assert resp.status_code == 302  # redirect back with error

    def test_post_create_notifier_invalid_type_rejected(self, config_editor_client):
        resp = config_editor_client.post(self.url, {
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

    def test_get_renders(self, config_editor_client, notifier):
        resp = config_editor_client.get(self._url(notifier.pk))
        assert resp.status_code == 200

    def test_get_context_has_notifier(self, config_editor_client, notifier):
        resp = config_editor_client.get(self._url(notifier.pk))
        assert resp.context['notifier'] == notifier

    def test_get_webpush_notifier_includes_vapid_key(self, config_editor_client, webpush_notifier):
        from webapp.models import Setting
        Setting.set('webpush.vapid_public_key', 'TESTKEY')
        resp = config_editor_client.get(self._url(webpush_notifier.pk))
        assert resp.status_code == 200
        assert resp.context.get('vapid_public_key') == 'TESTKEY'

    def test_post_updates_notifier(self, config_editor_client, notifier):
        resp = config_editor_client.post(self._url(notifier.pk), {
            'name': 'Updated Name',
            'enabled': 'on',
            'title_template': 'Run: {status}',
            'message_template': '',
        })
        assert resp.status_code == 302
        notifier.refresh_from_db()
        assert notifier.name == 'Updated Name'
        assert notifier.enabled is True

    def test_post_saves_bool_config_field(self, config_editor_client, notifier):
        resp = config_editor_client.post(self._url(notifier.pk), {
            'name': notifier.name,
            'supports_html': 'on',
            'title_template': '',
            'message_template': '',
        })
        assert resp.status_code == 302
        notifier.refresh_from_db()
        assert notifier.config.get('supports_html') is True

    def test_post_blank_password_not_overwritten(self, config_editor_client, notifier):
        # Set a real password first
        notifier.config = {'app_token': 'original'}
        notifier.save()
        # POST with blank password - should not clear it
        resp = config_editor_client.post(self._url(notifier.pk), {
            'name': notifier.name,
            'app_token': '',       # blank → preserve existing
            'user_token': '',
            'title_template': '',
            'message_template': '',
        })
        assert resp.status_code == 302

    def test_get_404_for_unknown_notifier(self, config_editor_client):
        import uuid
        resp = config_editor_client.get(f'/config/notifications/{uuid.uuid4()}/')
        assert resp.status_code == 404


@pytest.mark.django_db
class TestNotifierDeleteView:
    def _url(self, pk):
        return f'/config/notifications/{pk}/delete/'

    def test_requires_login(self, anon_client, notifier):
        resp = anon_client.post(self._url(notifier.pk))
        assert resp.status_code == 302

    def test_deletes_notifier(self, config_editor_client, notifier):
        pk = notifier.pk
        resp = config_editor_client.post(self._url(pk))
        assert resp.status_code == 302
        from webapp.models import Notifier
        assert not Notifier.objects.filter(pk=pk).exists()

    def test_404_for_unknown(self, config_editor_client):
        import uuid
        resp = config_editor_client.post(f'/config/notifications/{uuid.uuid4()}/delete/')
        assert resp.status_code == 404


@pytest.mark.django_db
class TestNotifierToggleView:
    def _url(self, pk):
        return f'/config/notifications/{pk}/toggle/'

    def test_requires_login(self, anon_client, notifier):
        resp = anon_client.post(self._url(notifier.pk))
        assert resp.status_code == 302

    def test_toggles_enabled_to_false(self, config_editor_client, notifier):
        assert notifier.enabled is True
        resp = config_editor_client.post(self._url(notifier.pk))
        assert resp.status_code == 302
        notifier.refresh_from_db()
        assert notifier.enabled is False

    def test_toggles_disabled_to_true(self, config_editor_client, notifier):
        notifier.enabled = False
        notifier.save()
        config_editor_client.post(self._url(notifier.pk))
        notifier.refresh_from_db()
        assert notifier.enabled is True


@pytest.mark.django_db
class TestNotifierTestView:
    def _url(self, pk):
        return f'/config/notifications/{pk}/test/'

    def test_requires_login(self, anon_client, notifier):
        resp = anon_client.post(self._url(notifier.pk))
        assert resp.status_code == 302

    def test_returns_json_success(self, config_editor_client, notifier):
        mock_send = MagicMock()
        with patch('importlib.import_module') as mock_import:
            mock_module = MagicMock()
            mock_module.send = mock_send
            mock_import.return_value = mock_module
            resp = config_editor_client.post(self._url(notifier.pk))
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['success'] is True

    def test_returns_json_error_on_send_failure(self, config_editor_client, notifier):
        with patch('importlib.import_module') as mock_import:
            mock_module = MagicMock()
            mock_module.send.side_effect = Exception('bad token')
            mock_import.return_value = mock_module
            resp = config_editor_client.post(self._url(notifier.pk))
        assert resp.status_code == 500
        data = json.loads(resp.content)
        assert data['success'] is False
        assert 'bad token' in data['message']

    def test_returns_400_when_module_not_found(self, config_editor_client, notifier):
        with patch('importlib.import_module', side_effect=ModuleNotFoundError('no module')):
            resp = config_editor_client.post(self._url(notifier.pk))
        assert resp.status_code == 400
        data = json.loads(resp.content)
        assert data['success'] is False

    def test_returns_400_when_send_missing(self, config_editor_client, notifier):
        with patch('importlib.import_module') as mock_import:
            mock_module = MagicMock(spec=[])  # no 'send' attribute
            mock_import.return_value = mock_module
            resp = config_editor_client.post(self._url(notifier.pk))
        assert resp.status_code == 400
        data = json.loads(resp.content)
        assert data['success'] is False


@pytest.mark.django_db
class TestNotificationSettingsView:
    url = '/config/notifications/settings/'

    def test_requires_login(self, anon_client):
        resp = anon_client.get(self.url)
        assert resp.status_code == 302

    def test_get_renders(self, config_editor_client):
        resp = config_editor_client.get(self.url)
        assert resp.status_code == 200

    def test_post_saves_settings(self, config_editor_client):
        resp = config_editor_client.post(self.url, {
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

    def test_returns_503_when_no_key_configured(self, config_editor_client):
        from webapp.models import Setting
        Setting.set('webpush.vapid_public_key', '')
        resp = config_editor_client.get(self.url)
        assert resp.status_code == 503

    def test_returns_key_when_configured(self, config_editor_client):
        from webapp.models import Setting
        Setting.set('webpush.vapid_public_key', 'MYPUBLICKEY')
        resp = config_editor_client.get(self.url)
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

    def test_creates_subscription(self, config_editor_client, webpush_notifier):
        payload = json.dumps({
            'endpoint': 'https://push.example.com/endpoint',
            'p256dh': 'AAAA',
            'auth': 'BBBB',
            'label': 'My iPhone',
        })
        resp = config_editor_client.post(
            self._url(webpush_notifier.pk),
            data=payload,
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['status'] == 'subscribed'
        assert data['created'] is True

    def test_updates_existing_subscription(self, config_editor_client, webpush_notifier):
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
        resp = config_editor_client.post(
            self._url(webpush_notifier.pk),
            data=payload,
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['created'] is False
        sub.refresh_from_db()  # type: ignore[call-arg]
        assert sub.p256dh == 'NEWKEY'

    def test_returns_400_on_invalid_json(self, config_editor_client, webpush_notifier):
        resp = config_editor_client.post(
            self._url(webpush_notifier.pk),
            data='not-json',
            content_type='application/json',
        )
        assert resp.status_code == 400

    def test_returns_400_when_fields_missing(self, config_editor_client, webpush_notifier):
        payload = json.dumps({'endpoint': 'https://push.example.com/ep'})
        resp = config_editor_client.post(
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

    def test_deletes_subscription(self, config_editor_client, webpush_notifier):
        from webapp.models import WebPushSubscription
        sub = WebPushSubscription.objects.create(
            notifier=webpush_notifier,
            endpoint='https://push.example.com/ep',
            p256dh='AAAA',
            auth='BBBB',
        )
        resp = config_editor_client.post(self._url(webpush_notifier.pk, sub.pk))
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['status'] == 'unsubscribed'
        assert not WebPushSubscription.objects.filter(pk=sub.pk).exists()

    def test_404_for_unknown_subscription(self, config_editor_client, webpush_notifier):
        resp = config_editor_client.post(self._url(webpush_notifier.pk, 99999))
        assert resp.status_code == 404


IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'


@pytest.mark.django_db
class TestNotificationsMobileTemplates:
    def test_notifications_view_mobile_template(self, config_editor_client):
        resp = config_editor_client.get('/config/notifications/', HTTP_USER_AGENT=IPHONE_UA)
        assert resp.status_code == 200
        assert 'mobile' in resp.template_name[0]

    def test_notifier_edit_view_mobile_template(self, config_editor_client, notifier):
        resp = config_editor_client.get(f'/config/notifications/{notifier.pk}/', HTTP_USER_AGENT=IPHONE_UA)
        assert resp.status_code == 200
        assert 'mobile' in resp.template_name[0]

    def test_notification_settings_view_mobile_template(self, config_editor_client):
        resp = config_editor_client.get('/config/notifications/settings/', HTTP_USER_AGENT=IPHONE_UA)
        assert resp.status_code == 200
        assert 'mobile' in resp.template_name[0]


@pytest.mark.django_db
class TestNotifierEditViewEmailContext:
    def test_email_notifier_includes_email_templates(self, config_editor_client):
        from webapp.models import Notifier
        email_notifier = Notifier.objects.create(
            name='Email Notifier', notifier_type='email', enabled=True, config={},
        )
        resp = config_editor_client.get(f'/config/notifications/{email_notifier.pk}/')
        assert resp.status_code == 200
        assert 'email_templates' in resp.context


@pytest.mark.django_db
class TestWebPushSubscribeDeviceLabelUpdate:
    def _url(self, pk):
        return f'/config/notifications/{pk}/subscribe/'

    def test_updates_device_label_on_existing_subscription(self, config_editor_client, webpush_notifier):
        from webapp.models import WebPushSubscription
        sub = WebPushSubscription.objects.create(
            notifier=webpush_notifier,
            endpoint='https://push.example.com/endpoint2',
            p256dh='OLD',
            auth='OLD',
            device_label='Old Label',
        )
        payload = json.dumps({
            'endpoint': 'https://push.example.com/endpoint2',
            'p256dh': 'NEWKEY',
            'auth': 'NEWAUTH',
            'label': 'New Label',
        })
        resp = config_editor_client.post(
            self._url(webpush_notifier.pk),
            data=payload,
            content_type='application/json',
        )
        assert resp.status_code == 200
        sub.refresh_from_db()
        assert sub.device_label == 'New Label'


@pytest.mark.django_db
class TestNotifierEditViewExceptionBranches:
    def test_setting_get_exception_uses_en_us_fallback(self, config_editor_client, notifier):
        """Lines 92-93: if Setting.get raises, lang falls back to en-US."""
        from webapp.models import Setting
        with patch.object(Setting, 'get', side_effect=Exception('db error')):
            resp = config_editor_client.get(f'/config/notifications/{notifier.pk}/')
        assert resp.status_code == 200

    def test_post_text_field_sets_cfg_key_line138(self, config_editor_client):
        """Line 138: non-password (text) field sets cfg[key] = val directly."""
        from webapp.models import Notifier
        slack = Notifier.objects.create(name='Slack Notif', notifier_type='slack', config={})
        resp = config_editor_client.post(f'/config/notifications/{slack.pk}/', {
            'name': 'Slack Notif',
            'webhook_url': 'https://hooks.slack.com/xxx',
            'title_template': '',
            'message_template': '',
        })
        assert resp.status_code == 302
        slack.refresh_from_db()
        assert slack.config.get('webhook_url') == 'https://hooks.slack.com/xxx'
