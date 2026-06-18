"""Tests for webapp.models: Setting, Schedule, Run, RunShareToken, APIToken, Notifier."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest


# ---------------------------------------------------------------------------
# Setting
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSetting:
    def test_get_returns_default_when_absent(self):
        from webapp.models import Setting
        assert Setting.get('autopkg.bin_path') == '/usr/local/bin/autopkg'

    def test_get_returns_supplied_default_when_absent(self):
        from webapp.models import Setting
        assert Setting.get('nonexistent.key', 'my-default') == 'my-default'

    def test_set_and_get_round_trip(self):
        from webapp.models import Setting
        Setting.set('autopkg.bin_path', '/opt/autopkg')
        assert Setting.get('autopkg.bin_path') == '/opt/autopkg'

    def test_set_encrypts_sensitive_key(self):
        from webapp.models import Setting
        from webapp.encryption import is_encrypted
        Setting.set('repository.password', 's3cr3t')
        raw = Setting.objects.get(key='repository.password').value
        assert is_encrypted(raw), "Sensitive key should be stored encrypted"

    def test_get_decrypts_sensitive_key(self):
        from webapp.models import Setting
        Setting.set('repository.password', 'hunter2')
        assert Setting.get('repository.password') == 'hunter2'

    def test_get_bool_true_values(self):
        from webapp.models import Setting
        for val in ('true', 'True', 'TRUE', '1', 'yes', 'on'):
            Setting.objects.update_or_create(key='workflow.update_repos', defaults={'value': val})
            assert Setting.get_bool('workflow.update_repos') is True

    def test_get_bool_false_for_false_string(self):
        from webapp.models import Setting
        Setting.objects.update_or_create(key='workflow.update_repos', defaults={'value': 'false'})
        assert Setting.get_bool('workflow.update_repos') is False

    def test_get_bool_false_when_absent(self):
        from webapp.models import Setting
        # 'logging.to_file' default is 'false'
        assert Setting.get_bool('logging.to_file') is False

    def test_get_int_valid(self):
        from webapp.models import Setting
        Setting.objects.update_or_create(key='gc.keep_versions', defaults={'value': '7'})
        assert Setting.get_int('gc.keep_versions') == 7

    def test_get_int_fallback_on_non_integer(self):
        from webapp.models import Setting
        Setting.objects.update_or_create(key='gc.keep_versions', defaults={'value': 'banana'})
        assert Setting.get_int('gc.keep_versions', fallback=3) == 3

    def test_get_all_merges_defaults(self):
        from webapp.models import Setting
        result = Setting.get_all()
        assert 'autopkg.bin_path' in result
        assert 'gc.keep_versions' in result

    def test_get_all_decrypts_sensitive_fields(self):
        from webapp.models import Setting
        Setting.set('repository.password', 'plaintext-pw')
        result = Setting.get_all()
        assert result['repository.password'] == 'plaintext-pw'

    def test_get_all_db_values_override_defaults(self):
        from webapp.models import Setting
        Setting.objects.update_or_create(key='autopkg.bin_path', defaults={'value': '/custom/autopkg'})
        result = Setting.get_all()
        assert result['autopkg.bin_path'] == '/custom/autopkg'


# ---------------------------------------------------------------------------
# Schedule (singleton)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSchedule:
    def test_get_creates_singleton(self):
        from webapp.models import Schedule
        s = Schedule.get()
        assert s.pk == 1

    def test_get_returns_same_object_on_second_call(self):
        from webapp.models import Schedule
        s1 = Schedule.get()
        s2 = Schedule.get()
        assert s1.pk == s2.pk == 1

    def test_save_forces_pk_to_1(self):
        from webapp.models import Schedule
        s = Schedule(pk=99, enabled=True)
        s.save()
        assert s.pk == 1
        assert Schedule.objects.count() == 1

    def test_delete_is_noop(self):
        from webapp.models import Schedule
        s = Schedule.get()
        result = s.delete()
        assert result == (0, {})
        assert Schedule.objects.filter(pk=1).exists()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRun:
    def test_duration_is_none_when_not_completed(self):
        from webapp.models import Run
        r = Run.objects.create(status='running', config_snapshot={})
        assert r.duration is None

    def test_duration_returns_timedelta(self):
        from webapp.models import Run
        now = datetime.now(timezone.utc)
        # started_at is auto_now_add=True so we must set it via update().
        r = Run.objects.create(status='success', config_snapshot={})
        Run.objects.filter(pk=r.pk).update(
            started_at=now - timedelta(minutes=3),
            completed_at=now,
        )
        r.refresh_from_db()
        assert r.duration == timedelta(minutes=3)


# ---------------------------------------------------------------------------
# RunShareToken
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRunShareToken:
    def test_get_or_create_generates_token(self, run):
        from webapp.models import RunShareToken
        token = RunShareToken.get_or_create_for_run(run)
        assert len(token.token) > 0

    def test_token_is_url_safe_string(self, run):
        from webapp.models import RunShareToken
        token = RunShareToken.get_or_create_for_run(run)
        # URL-safe base64 chars: A-Z a-z 0-9 - _
        import re
        assert re.fullmatch(r'[A-Za-z0-9_\-]+', token.token)

    def test_second_call_returns_same_token(self, run):
        from webapp.models import RunShareToken
        t1 = RunShareToken.get_or_create_for_run(run)
        t2 = RunShareToken.get_or_create_for_run(run)
        assert t1.token == t2.token

    def test_different_runs_produce_different_tokens(self, db):
        from webapp.models import Run, RunShareToken
        r1 = Run.objects.create(status='success', config_snapshot={})
        r2 = Run.objects.create(status='success', config_snapshot={})
        t1 = RunShareToken.get_or_create_for_run(r1)
        t2 = RunShareToken.get_or_create_for_run(r2)
        assert t1.token != t2.token


# ---------------------------------------------------------------------------
# APIToken
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAPIToken:
    def test_save_autogenerates_token_id_and_secret(self, user):
        from webapp.models import APIToken
        t = APIToken.objects.create(user=user, name='My Token')
        assert len(t.token_id) == 32
        assert t.token_id.isalnum()
        # Secret is stored encrypted; decrypted form is a 64-char hex string
        assert len(t.decrypted_secret) == 64
        assert t.decrypted_secret.isalnum()

    def test_token_secret_stored_encrypted(self, user):
        from webapp.models import APIToken
        from webapp.encryption import is_encrypted
        t = APIToken.objects.create(user=user, name='Enc Token')
        assert is_encrypted(t.token_secret)


# ---------------------------------------------------------------------------
# Notifier encryption
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNotifier:
    def test_save_encrypts_password_fields(self):
        from webapp.models import Notifier
        from webapp.encryption import is_encrypted
        n = Notifier.objects.create(
            name='Test Pushover',
            notifier_type='pushover',
            config={'app_token': 'abc123', 'user_token': 'xyz789', 'supports_html': True},
        )
        # app_token and user_token are password-type for pushover
        assert is_encrypted(n.config['app_token'])
        assert is_encrypted(n.config['user_token'])

    def test_decrypted_config_returns_plaintext(self):
        from webapp.models import Notifier
        n = Notifier.objects.create(
            name='Test Pushover',
            notifier_type='pushover',
            config={'app_token': 'abc123', 'user_token': 'xyz789', 'supports_html': True},
        )
        decrypted = n.decrypted_config
        assert decrypted['app_token'] == 'abc123'
        assert decrypted['user_token'] == 'xyz789'

    def test_non_password_fields_not_encrypted(self):
        from webapp.models import Notifier
        from webapp.encryption import is_encrypted
        n = Notifier.objects.create(
            name='Test Discord',
            notifier_type='discord',
            config={'webhook_id': 'my-id', 'webhook_token': 'tok123'},
        )
        # webhook_id is text type - should not be encrypted
        assert not is_encrypted(n.config['webhook_id'])
        # webhook_token is password type - should be encrypted
        assert is_encrypted(n.config['webhook_token'])


# ---------------------------------------------------------------------------
# __str__ methods and misc properties
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestModelStrMethods:
    def test_setting_str(self):
        from webapp.models import Setting
        s = Setting.objects.create(key='test.key', value='myvalue')
        assert 'test.key' in str(s)
        assert 'myvalue' in str(s)

    def test_notifier_str_enabled(self):
        from webapp.models import Notifier
        n = Notifier.objects.create(name='MyNotifier', notifier_type='pushover', enabled=True, config={})
        assert 'MyNotifier' in str(n)
        assert 'on' in str(n)

    def test_notifier_str_disabled(self):
        from webapp.models import Notifier
        n = Notifier.objects.create(name='MyNotifier', notifier_type='pushover', enabled=False, config={})
        assert 'off' in str(n)

    def test_schedule_str(self):
        from webapp.models import Schedule
        s = Schedule.get()
        result = str(s)
        assert 'Schedule' in result

    def test_run_str(self):
        from webapp.models import Run
        r = Run.objects.create(status='success', triggered_by='manual', config_snapshot={})
        assert 'success' in str(r)

    def test_stage_execution_str(self, run):
        from webapp.models import StageExecution
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        s = StageExecution.objects.create(run=run, name='UpdateRepos', status='success', order=0,
                                          started_at=now, completed_at=now)
        assert 'UpdateRepos' in str(s)
        assert 'success' in str(s)

    def test_stage_execution_duration_property(self, run):
        from webapp.models import StageExecution
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        s = StageExecution.objects.create(run=run, name='Stage', status='success', order=0,
                                          started_at=now - timedelta(seconds=30), completed_at=now)
        assert s.duration is not None
        assert s.duration.total_seconds() == pytest.approx(30, abs=1)

    def test_stage_execution_duration_none_when_incomplete(self, run):
        from webapp.models import StageExecution
        s = StageExecution.objects.create(run=run, name='Stage', status='running', order=0)
        assert s.duration is None

    def test_log_entry_str(self, run):
        from webapp.models import LogEntry
        from datetime import datetime, timezone
        e = LogEntry.objects.create(run=run, level='INFO', message='hello world',
                                    stage_name='', timestamp=datetime.now(timezone.utc))
        assert 'INFO' in str(e)
        assert 'hello' in str(e)

    def test_recipe_result_str(self, run):
        from webapp.models import RecipeResult
        r = RecipeResult.objects.create(run=run, result_type='munki_import', data=[])
        assert 'munki_import' in str(r)

    def test_run_share_token_str(self, run):
        from webapp.models import RunShareToken
        t = RunShareToken.get_or_create_for_run(run)
        assert 'ShareToken' in str(t)

    def test_task_str(self):
        from webapp.models import Task
        t = Task.objects.create(task_type='pipeline', status='pending')
        assert 'pipeline' in str(t)

    def test_api_token_str(self, user):
        from webapp.models import APIToken
        t = APIToken.objects.create(user=user, name='MyToken')
        assert user.username in str(t)
        assert 'MyToken' in str(t)

    def test_api_token_save_encrypts_existing_plaintext_secret(self, user):
        from webapp.models import APIToken
        from webapp.encryption import is_encrypted, ENCRYPTED_PREFIX
        token = APIToken.objects.create(user=user, name='TestToken')
        # Directly write a plaintext secret and re-save
        APIToken.objects.filter(pk=token.pk).update(token_secret='plaintext-secret')
        token.refresh_from_db()
        token.save()
        token.refresh_from_db()
        assert is_encrypted(token.token_secret)

    def test_user_permission_str(self, user):
        from webapp.models import UserPermission
        p, _ = UserPermission.objects.get_or_create(user=user)
        assert user.username in str(p)

    def test_web_push_subscription_str_with_device_label(self, user):
        from webapp.models import Notifier, WebPushSubscription
        notifier = Notifier.objects.create(name='PushNotifier', notifier_type='webpush', config={})
        sub = WebPushSubscription.objects.create(
            notifier=notifier,
            endpoint='https://push.example.com/ep',
            p256dh='KEY',
            auth='AUTH',
            device_label='My iPhone',
        )
        result = str(sub)
        assert 'My iPhone' in result
        assert 'PushNotifier' in result

    def test_web_push_subscription_str_without_device_label(self, user):
        from webapp.models import Notifier, WebPushSubscription
        notifier = Notifier.objects.create(name='PushNotifier2', notifier_type='webpush', config={})
        sub = WebPushSubscription.objects.create(
            notifier=notifier,
            endpoint='https://push.example.com/some-endpoint-path',
            p256dh='KEY',
            auth='AUTH',
            device_label='',
        )
        result = str(sub)
        assert 'push.example.com' in result


# ---------------------------------------------------------------------------
# notifier_types
# ---------------------------------------------------------------------------

class TestGetSchema:
    def test_known_type_returns_schema(self):
        from webapp.notifier_types import get_schema
        result = get_schema('pushover')
        assert 'label' in result
        assert 'fields' in result

    def test_unknown_type_returns_empty_dict(self):
        from webapp.notifier_types import get_schema
        assert get_schema('nonexistent_type') == {}
