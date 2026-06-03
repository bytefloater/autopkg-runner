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
    def test_save_autogenerates_key(self, user):
        from webapp.models import APIToken
        t = APIToken.objects.create(user=user, name='My Token')
        assert len(t.key) == 40
        assert t.key.isalnum()

    def test_explicit_key_preserved(self, user):
        # APIToken.key is editable=False so we set it via direct field assignment
        from webapp.models import APIToken
        t = APIToken(user=user, name='Fixed Token', key='a' * 40)
        t.save()
        assert t.key == 'a' * 40


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
