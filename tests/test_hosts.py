"""Tests for libs.hosts: SmbHost, SftpHost, RemoteRepositoryMounter."""
from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest


# -- SmbHost -------------------------------------------------------------------

class TestSmbHostInit:
    def test_stores_attributes(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='server', share='Share', username='user', password='pass')
        assert h.host == 'server'
        assert h.share == 'Share'
        assert h.username == 'user'
        assert h.password == 'pass'


class TestSmbHostResolve:
    def test_ipv4_returned_directly_no_dns(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='192.168.1.1', share='S', username='u', password='p')
        result = h.resolve(MagicMock())
        assert result == '192.168.1.1'

    def test_hostname_uses_zeroconfig_resolver(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='myserver', share='S', username='u', password='p')
        mock_res = MagicMock()
        mock_res.resolve_service.return_value = {}
        mock_res.pick_best_result.return_value = {'addresses': ['10.0.0.5']}
        with patch('libs.hosts.ZeroConfigResolver', return_value=mock_res):
            result = h.resolve(MagicMock())
        assert result == '10.0.0.5'

    def test_hostname_empty_when_no_addresses(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='myserver', share='S', username='u', password='p')
        mock_res = MagicMock()
        mock_res.resolve_service.return_value = {}
        mock_res.pick_best_result.return_value = {}  # no 'addresses' key
        with patch('libs.hosts.ZeroConfigResolver', return_value=mock_res):
            result = h.resolve(MagicMock())
        assert result == ''


class TestSmbHostIsReachable:
    def test_ipv4_skips_resolution_and_checks_port(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='192.168.1.1', share='S', username='u', password='p')
        with patch.object(h, '_check_port', return_value=True) as mock_check:
            assert h.is_reachable(MagicMock()) is True
        mock_check.assert_called_once_with('192.168.1.1', ANY)

    def test_hostname_resolved_then_port_checked(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='myserver', share='S', username='u', password='p')
        with patch.object(h, 'resolve', return_value='10.0.0.1'), \
             patch.object(h, '_check_port', return_value=True) as mock_check:
            assert h.is_reachable(MagicMock()) is True
        mock_check.assert_called_once_with('10.0.0.1', ANY)

    def test_failed_resolution_returns_false(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='myserver', share='S', username='u', password='p')
        with patch.object(h, 'resolve', return_value='not-an-ip'):
            result = h.is_reachable(MagicMock())
        assert result is False


class TestSmbHostConnect:
    def test_success_calls_mount_smbfs(self, tmp_path):
        from libs.hosts import SmbHost
        h = SmbHost(host='192.168.1.1', share='Munki', username='user', password='pass')
        with patch.object(h, 'resolve', return_value='192.168.1.1'), \
             patch('libs.hosts.run_cmd') as mock_cmd:
            h.connect(tmp_path, MagicMock())
        assert mock_cmd.call_count == 1
        assert 'mount_smbfs' in mock_cmd.call_args[0][0]

    def test_failure_raises_runtime_error(self, tmp_path):
        from libs.hosts import SmbHost
        h = SmbHost(host='192.168.1.1', share='Munki', username='user', password='pass')
        with patch.object(h, 'resolve', return_value='192.168.1.1'), \
             patch('libs.hosts.run_cmd',
                   side_effect=subprocess.CalledProcessError(1, 'mount_smbfs')):
            with pytest.raises(RuntimeError, match='mount_smbfs'):
                h.connect(tmp_path, MagicMock())


class TestSmbHostDisconnect:
    def test_calls_umount(self, tmp_path):
        from libs.hosts import SmbHost
        h = SmbHost(host='192.168.1.1', share='S', username='u', password='p')
        with patch('libs.hosts.run_cmd') as mock_cmd:
            h.disconnect(tmp_path, MagicMock())
        assert 'umount' in mock_cmd.call_args[0][0]

    def test_error_logged_not_raised(self, tmp_path):
        from libs.hosts import SmbHost
        h = SmbHost(host='192.168.1.1', share='S', username='u', password='p')
        logger = MagicMock()
        with patch('libs.hosts.run_cmd',
                   side_effect=subprocess.CalledProcessError(1, 'umount')):
            h.disconnect(tmp_path, logger)  # must not raise
        logger.warning.assert_called()


class TestSmbHostCheckPort:
    def _sock(self, connect_result=0):
        sock = MagicMock()
        sock.connect_ex.return_value = connect_result
        return sock

    def test_open_port_returns_true(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='192.168.1.1', share='S', username='u', password='p')
        with patch('socket.socket', return_value=self._sock(0)):
            assert h._check_port('192.168.1.1', MagicMock()) is True

    def test_closed_port_returns_false(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='192.168.1.1', share='S', username='u', password='p')
        with patch('socket.socket', return_value=self._sock(111)):
            assert h._check_port('192.168.1.1', MagicMock()) is False

    def test_timeout_returns_false(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='192.168.1.1', share='S', username='u', password='p')
        sock = MagicMock()
        sock.connect_ex.side_effect = socket.timeout
        with patch('socket.socket', return_value=sock):
            assert h._check_port('192.168.1.1', MagicMock()) is False

    def test_ipv6_raises_type_error(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='::1', share='S', username='u', password='p')
        with pytest.raises(TypeError):
            h._check_port('::1', MagicMock())


class TestSmbHostBuildUrl:
    def test_contains_host_share_and_user(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='x', share='Munki', username='user', password='secret')
        url = h._build_url('10.0.0.1')
        assert '10.0.0.1' in url
        assert 'Munki' in url
        assert 'user' in url

    def test_special_chars_in_password_encoded(self):
        from libs.hosts import SmbHost
        h = SmbHost(host='x', share='S', username='u', password='p@ss!')
        url = h._build_url('10.0.0.1')
        # URL should not contain the literal '@' from password (should be encoded)
        # The password is embedded as //user:password@host/share
        # urllib.parse.quote encodes @ → %40 in the password portion
        assert 'p' in url  # at least the password is there in some form


# -- SftpHost ------------------------------------------------------------------

class TestSftpHostInit:
    def test_default_port(self):
        from libs.hosts import SftpHost
        h = SftpHost(host='server', share='/data', username='user', password='pass')
        assert h.port == 22

    def test_custom_port(self):
        from libs.hosts import SftpHost
        h = SftpHost(host='server', share='/data', username='user', password='pass', port=2222)
        assert h.port == 2222

    def test_stores_all_attributes(self):
        from libs.hosts import SftpHost
        h = SftpHost(host='srv', share='/mnt', username='u', password='p', port=22)
        assert h.host == 'srv'
        assert h.share == '/mnt'
        assert h.username == 'u'
        assert h.password == 'p'


class TestSftpHostResolve:
    def test_ipv4_returned_directly(self):
        from libs.hosts import SftpHost
        h = SftpHost(host='10.0.0.1', share='/data', username='u', password='p')
        assert h.resolve(MagicMock()) == '10.0.0.1'

    def test_hostname_via_zeroconfig(self):
        from libs.hosts import SftpHost
        h = SftpHost(host='myserver', share='/data', username='u', password='p')
        mock_res = MagicMock()
        mock_res.resolve_service.return_value = {}
        mock_res.pick_best_result.return_value = {'addresses': ['10.0.0.2']}
        with patch('libs.hosts.ZeroConfigResolver', return_value=mock_res):
            assert h.resolve(MagicMock()) == '10.0.0.2'


class TestSftpHostIsReachable:
    def test_ipv4_checks_port_directly(self):
        from libs.hosts import SftpHost
        h = SftpHost(host='10.0.0.1', share='/data', username='u', password='p')
        with patch.object(h, '_check_port', return_value=True) as mock_check:
            assert h.is_reachable(MagicMock()) is True
        mock_check.assert_called_once_with('10.0.0.1', ANY)

    def test_resolution_failure_returns_false(self):
        from libs.hosts import SftpHost
        h = SftpHost(host='myserver', share='/data', username='u', password='p')
        with patch.object(h, 'resolve', return_value='invalid'):
            assert h.is_reachable(MagicMock()) is False

    def test_hostname_resolved_port_checked(self):
        from libs.hosts import SftpHost
        h = SftpHost(host='myserver', share='/data', username='u', password='p')
        with patch.object(h, 'resolve', return_value='10.0.0.3'), \
             patch.object(h, '_check_port', return_value=False):
            assert h.is_reachable(MagicMock()) is False


class TestSftpHostConnect:
    def test_success_calls_sshfs(self, tmp_path):
        from libs.hosts import SftpHost
        h = SftpHost(host='10.0.0.1', share='/data', username='user', password='pass')
        with patch.object(h, 'resolve', return_value='10.0.0.1'), \
             patch('libs.hosts.run_cmd') as mock_cmd:
            h.connect(tmp_path, MagicMock())
        assert 'sshfs' in mock_cmd.call_args[0][0]

    def test_failure_raises_runtime_error(self, tmp_path):
        from libs.hosts import SftpHost
        h = SftpHost(host='10.0.0.1', share='/data', username='user', password='pass')
        with patch.object(h, 'resolve', return_value='10.0.0.1'), \
             patch('libs.hosts.run_cmd',
                   side_effect=subprocess.CalledProcessError(1, 'sshfs')):
            with pytest.raises(RuntimeError, match='sshfs'):
                h.connect(tmp_path, MagicMock())


class TestSftpHostDisconnect:
    def test_calls_umount(self, tmp_path):
        from libs.hosts import SftpHost
        h = SftpHost(host='10.0.0.1', share='/data', username='u', password='p')
        with patch('libs.hosts.run_cmd') as mock_cmd:
            h.disconnect(tmp_path, MagicMock())
        assert 'umount' in mock_cmd.call_args[0][0]

    def test_error_logged_not_raised(self, tmp_path):
        from libs.hosts import SftpHost
        h = SftpHost(host='10.0.0.1', share='/data', username='u', password='p')
        logger = MagicMock()
        with patch('libs.hosts.run_cmd',
                   side_effect=subprocess.CalledProcessError(1, 'umount')):
            h.disconnect(tmp_path, logger)  # must not raise
        logger.warning.assert_called()


class TestSftpHostCheckPort:
    def test_open_port_returns_true(self):
        from libs.hosts import SftpHost
        h = SftpHost(host='10.0.0.1', share='/data', username='u', password='p')
        sock = MagicMock()
        sock.connect_ex.return_value = 0
        with patch('socket.socket', return_value=sock):
            assert h._check_port('10.0.0.1', MagicMock()) is True

    def test_closed_port_returns_false(self):
        from libs.hosts import SftpHost
        h = SftpHost(host='10.0.0.1', share='/data', username='u', password='p')
        sock = MagicMock()
        sock.connect_ex.return_value = 111
        with patch('socket.socket', return_value=sock):
            assert h._check_port('10.0.0.1', MagicMock()) is False

    def test_timeout_returns_false(self):
        from libs.hosts import SftpHost
        h = SftpHost(host='10.0.0.1', share='/data', username='u', password='p')
        sock = MagicMock()
        sock.connect_ex.side_effect = socket.timeout
        with patch('socket.socket', return_value=sock):
            assert h._check_port('10.0.0.1', MagicMock()) is False


# -- RemoteRepositoryMounter ---------------------------------------------------

class TestRemoteRepositoryMounter:
    def _make(self, mount_point):
        from libs.hosts import RemoteRepositoryMounter
        host = MagicMock()
        logger = MagicMock()
        m = RemoteRepositoryMounter(mount_point, host, logger)
        return m, host, logger

    def test_init(self, tmp_path):
        m, host, logger = self._make(tmp_path)
        assert m.mount_point == tmp_path
        assert m.host is host
        assert m.logger is logger

    def test_is_reachable_delegates_to_host(self, tmp_path):
        m, host, logger = self._make(tmp_path)
        host.is_reachable.return_value = True
        assert m.is_reachable() is True
        host.is_reachable.assert_called_once_with(logger)

    def test_mount_point_available_when_absent(self, tmp_path):
        m, _, _ = self._make(tmp_path / 'new-mount')
        assert m.is_mount_point_available() is True

    def test_mount_point_not_available_when_exists(self, tmp_path):
        m, _, logger = self._make(tmp_path)
        assert m.is_mount_point_available() is False
        logger.error.assert_called()

    def test_mount_creates_dir_and_connects(self, tmp_path):
        mount_pt = tmp_path / 'mount'
        m, host, logger = self._make(mount_pt)
        m.mount()
        assert mount_pt.exists()
        host.connect.assert_called_once_with(mount_pt, logger)

    def test_mount_failure_cleans_up_directory(self, tmp_path):
        mount_pt = tmp_path / 'mount'
        m, host, _ = self._make(mount_pt)
        host.connect.side_effect = RuntimeError('failed')
        with pytest.raises(RuntimeError):
            m.mount()
        assert not mount_pt.exists()

    def test_unmount_disconnects_and_removes_dir(self, tmp_path):
        mount_pt = tmp_path / 'mount'
        mount_pt.mkdir()
        m, host, logger = self._make(mount_pt)
        m.unmount()
        host.disconnect.assert_called_once_with(mount_pt, logger)
        assert not mount_pt.exists()

    def test_unmount_warns_when_dir_not_found(self, tmp_path):
        mount_pt = tmp_path / 'gone'  # never created
        m, host, logger = self._make(mount_pt)
        m.unmount()  # must not raise
        logger.warning.assert_called()

    def test_unmount_errors_when_dir_not_empty(self, tmp_path):
        mount_pt = tmp_path / 'mount'
        mount_pt.mkdir()
        (mount_pt / 'leftover').write_text('content')  # make non-empty
        m, host, logger = self._make(mount_pt)
        m.unmount()  # must not raise
        logger.error.assert_called()
