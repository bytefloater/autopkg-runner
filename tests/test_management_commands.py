"""Tests for all webapp management commands."""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch, call

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


# -- generate_vapid_keys -------------------------------------------------------

@pytest.mark.django_db
class TestGenerateVapidKeys:
    def test_warns_if_keys_already_exist(self):
        from webapp.models import Setting
        Setting.set('webpush.vapid_private_key', 'existing-private-key')
        out = io.StringIO()
        call_command('generate_vapid_keys', stdout=out, stderr=io.StringIO())
        output = out.getvalue()
        assert 'already exist' in output.lower() or 'VAPID keys already exist' in output

    def test_shows_existing_public_key_when_skipping(self):
        from webapp.models import Setting
        Setting.set('webpush.vapid_private_key', 'some-private')
        Setting.set('webpush.vapid_public_key', 'MYPUBKEY')
        out = io.StringIO()
        call_command('generate_vapid_keys', stdout=out, stderr=io.StringIO())
        assert 'MYPUBKEY' in out.getvalue()

    def test_error_when_pywebpush_not_installed(self):
        import sys
        from webapp.models import Setting
        Setting.set('webpush.vapid_private_key', '')
        out = io.StringIO()
        err = io.StringIO()
        # Remove py_vapid from sys.modules so 'from py_vapid import Vapid' raises ImportError
        original = sys.modules.pop('py_vapid', ...)
        try:
            with patch.dict('sys.modules', {'py_vapid': None}):
                call_command('generate_vapid_keys', stdout=out, stderr=err)
        finally:
            if original is not ...:
                sys.modules['py_vapid'] = original
        assert 'pywebpush' in err.getvalue().lower() or 'not installed' in err.getvalue().lower()

    def test_generates_and_stores_keys_with_force(self):
        from webapp.models import Setting
        Setting.set('webpush.vapid_private_key', 'existing')

        mock_vapid = MagicMock()
        mock_key = MagicMock()
        mock_key.private_numbers.return_value.private_value = int.from_bytes(b'\x01' * 32, 'big')
        mock_vapid.private_key = mock_key

        mock_pub_key = MagicMock()
        mock_pub_bytes = b'\x04' + b'\x02' * 32 + b'\x03' * 32  # uncompressed point
        mock_pub_key.public_bytes.return_value = mock_pub_bytes
        mock_vapid.public_key = mock_pub_key

        VapidClass = MagicMock(return_value=mock_vapid)

        with patch.dict('sys.modules', {'py_vapid': MagicMock(Vapid=VapidClass)}):
            out = io.StringIO()
            call_command('generate_vapid_keys', '--force', stdout=out, stderr=io.StringIO())

        # Keys should have been updated
        assert Setting.get('webpush.vapid_private_key') != 'existing'

    def test_stores_contact_when_provided(self):
        from webapp.models import Setting
        Setting.set('webpush.vapid_private_key', '')

        mock_vapid = MagicMock()
        mock_key = MagicMock()
        mock_key.private_numbers.return_value.private_value = int.from_bytes(b'\x01' * 32, 'big')
        mock_vapid.private_key = mock_key
        mock_pub_key = MagicMock()
        mock_pub_key.public_bytes.return_value = b'\x04' + b'\x02' * 32 + b'\x03' * 32
        mock_vapid.public_key = mock_pub_key

        VapidClass = MagicMock(return_value=mock_vapid)
        with patch.dict('sys.modules', {'py_vapid': MagicMock(Vapid=VapidClass)}):
            call_command(
                'generate_vapid_keys',
                '--contact', 'mailto:admin@example.com',
                stdout=io.StringIO(), stderr=io.StringIO(),
            )
        assert Setting.get('webpush.vapid_contact') == 'mailto:admin@example.com'


# -- resetpassword -------------------------------------------------------------

@pytest.mark.django_db
class TestResetPassword:
    def test_resets_password_for_superuser(self, superuser):
        old_hash = superuser.password
        out = io.StringIO()
        call_command('resetpassword', superuser.username, stdout=out, stderr=io.StringIO())
        superuser.refresh_from_db()
        assert superuser.password != old_hash
        assert 'Password' in out.getvalue()

    def test_raises_for_nonexistent_user(self):
        with pytest.raises(CommandError, match="No user found"):
            call_command('resetpassword', 'nosuchuser', stdout=io.StringIO(), stderr=io.StringIO())

    def test_raises_for_non_superuser(self, user):
        with pytest.raises(CommandError, match="not a superuser"):
            call_command('resetpassword', user.username, stdout=io.StringIO(), stderr=io.StringIO())

    def test_output_contains_username(self, superuser):
        out = io.StringIO()
        call_command('resetpassword', superuser.username, stdout=out, stderr=io.StringIO())
        assert superuser.username in out.getvalue()


# -- serve ---------------------------------------------------------------------

@pytest.mark.django_db
class TestServeCommand:
    def test_invalid_port_raises_error(self):
        with pytest.raises(CommandError, match="Invalid port"):
            call_command('serve', '--port', 'abc', stdout=io.StringIO(), stderr=io.StringIO())

    def test_port_out_of_range_raises_error(self):
        with pytest.raises(CommandError, match="Invalid port"):
            call_command('serve', '--port', '99999', stdout=io.StringIO(), stderr=io.StringIO())

    def test_network_flag_in_production_raises_error(self):
        from django.conf import settings
        original = settings.DEBUG
        settings.DEBUG = False
        try:
            with pytest.raises(CommandError, match="DEBUG"):
                call_command('serve', '--network', stdout=io.StringIO(), stderr=io.StringIO())
        finally:
            settings.DEBUG = original

    def test_default_localhost_binding(self):
        with patch('webapp.management.commands.serve.call_command') as mock_call:
            with patch('django.db.migrations.executor.MigrationExecutor') as mock_exec:
                mock_exec.return_value.migration_plan.return_value = []
                call_command('serve', stdout=io.StringIO(), stderr=io.StringIO())
        mock_call.assert_called_with('runserver', addrport='127.0.0.1:8000')

    def test_custom_port(self):
        with patch('webapp.management.commands.serve.call_command') as mock_call:
            with patch('django.db.migrations.executor.MigrationExecutor') as mock_exec:
                mock_exec.return_value.migration_plan.return_value = []
                call_command('serve', '--port', '9000', stdout=io.StringIO(), stderr=io.StringIO())
        mock_call.assert_called_with('runserver', addrport='127.0.0.1:9000')

    def test_noreload_flag(self):
        with patch('webapp.management.commands.serve.call_command') as mock_call:
            with patch('django.db.migrations.executor.MigrationExecutor') as mock_exec:
                mock_exec.return_value.migration_plan.return_value = []
                call_command('serve', '--noreload', stdout=io.StringIO(), stderr=io.StringIO())
        mock_call.assert_called_with('runserver', addrport='127.0.0.1:8000', use_reloader=False)

    def test_network_flag_with_debug(self):
        from django.conf import settings as dj_settings
        with patch('webapp.management.commands.serve.call_command') as mock_call, \
             patch('django.db.migrations.executor.MigrationExecutor') as mock_exec, \
             patch.object(type(dj_settings), 'DEBUG', new=True, create=True):
            mock_exec.return_value.migration_plan.return_value = []
            # Temporarily make DEBUG True so --network doesn't raise
            original_debug = dj_settings.DEBUG
            dj_settings.DEBUG = True
            try:
                call_command('serve', '--network', stdout=io.StringIO(), stderr=io.StringIO())
            finally:
                dj_settings.DEBUG = original_debug
        mock_call.assert_called_with('runserver', addrport='0.0.0.0:8000')

    def test_pending_migrations_are_applied(self):
        with patch('webapp.management.commands.serve.call_command') as mock_call:
            with patch('django.db.migrations.executor.MigrationExecutor') as mock_exec:
                mock_exec.return_value.migration_plan.return_value = [('app', 'migration')]
                out = io.StringIO()
                call_command('serve', stdout=out, stderr=io.StringIO())
        calls = [str(c) for c in mock_call.call_args_list]
        assert any('migrate' in c for c in calls)


# -- setup ---------------------------------------------------------------------

@pytest.mark.django_db
class TestSetupCommand:
    def test_no_input_skips_superuser(self):
        """With --no-input, superuser creation is skipped."""
        with patch('django.core.management.call_command') as mock_call:
            out = io.StringIO()
            call_command('setup', '--no-input', stdout=out, stderr=io.StringIO())
        assert 'Setup complete' in out.getvalue()
        # migrate was called
        calls = [str(c) for c in mock_call.call_args_list]
        assert any('migrate' in c for c in calls)

    def test_skip_superuser_flag(self):
        with patch('django.core.management.call_command'):
            out = io.StringIO()
            call_command('setup', '--skip-superuser', stdout=out, stderr=io.StringIO())
        assert 'Setup complete' in out.getvalue()

    def test_creates_superuser_when_none_exists(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        # Ensure no superusers exist
        User.objects.filter(is_superuser=True).delete()

        with patch('django.core.management.call_command'):
            out = io.StringIO()
            call_command('setup', '--username', 'testadmin', stdout=out, stderr=io.StringIO())
        assert User.objects.filter(username='testadmin', is_superuser=True).exists()

    def test_skips_superuser_if_one_already_exists(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_superuser(username='existing_admin', password='pass', email='')

        with patch('django.core.management.call_command'):
            out = io.StringIO()
            call_command('setup', stdout=out, stderr=io.StringIO())
        assert 'already exists' in out.getvalue()

    def test_creates_schedule_singleton(self):
        with patch('django.core.management.call_command'):
            call_command('setup', '--no-input', stdout=io.StringIO(), stderr=io.StringIO())
        from webapp.models import Schedule
        assert Schedule.objects.filter(pk=1).exists()


# -- install_sftp_deps ---------------------------------------------------------

@pytest.mark.django_db
class TestInstallSftpDeps:
    def test_exits_early_when_sshfs_present(self):
        with patch('shutil.which', return_value='/usr/bin/sshfs'):
            out = io.StringIO()
            call_command('install_sftp_deps', stdout=out, stderr=io.StringIO())
        assert 'already installed' in out.getvalue()

    def test_runs_brew_install_when_sshfs_missing_brew_present(self):
        def which(cmd):
            if cmd == 'sshfs':
                return None
            if cmd == 'brew':
                return '/usr/local/bin/brew'
            return None

        mock_run = MagicMock()
        mock_run.return_value.returncode = 0

        with patch('shutil.which', side_effect=which), \
             patch('subprocess.run', return_value=MagicMock()) as mock_sp:
            out = io.StringIO()
            call_command('install_sftp_deps', stdout=out, stderr=io.StringIO())

        # brew install --cask macfuse and brew install gromgit/fuse/sshfs-mac were called
        calls = [str(c) for c in mock_sp.call_args_list]
        assert any('macfuse' in c for c in calls)
        assert any('sshfs-mac' in c for c in calls)

    def test_installs_homebrew_when_missing(self):
        def which(cmd):
            return None  # neither sshfs nor brew present

        with patch('shutil.which', side_effect=which), \
             patch('subprocess.run', return_value=MagicMock()) as mock_sp:
            out = io.StringIO()
            call_command('install_sftp_deps', stdout=out, stderr=io.StringIO())

        calls = [str(c) for c in mock_sp.call_args_list]
        assert any('curl' in c or 'install.sh' in c or '/bin/bash' in c for c in calls)
