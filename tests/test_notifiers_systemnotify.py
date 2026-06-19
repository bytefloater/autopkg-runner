"""Tests for notifiers.systemnotify."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestSystemNotifySend:
    def _run_ok(self):
        r = MagicMock()
        r.returncode = 0
        r.stderr = b''
        return r

    def _run_fail(self, stderr=b'error msg'):
        r = MagicMock()
        r.returncode = 1
        r.stderr = stderr
        return r

    def test_macos_calls_osascript(self):
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run', return_value=self._run_ok()) as mock_run:
            from notifiers.systemnotify import send
            send(configuration={}, message='Hello')
        assert mock_run.call_args[0][0][0] == 'osascript'

    def test_macos_message_in_script(self):
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run', return_value=self._run_ok()) as mock_run:
            from notifiers.systemnotify import send
            send(configuration={}, message='Hello macOS')
        assert 'Hello macOS' in mock_run.call_args[0][0][2]

    def test_macos_title_in_script(self):
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run', return_value=self._run_ok()) as mock_run:
            from notifiers.systemnotify import send
            send(configuration={}, message='Hi', title='My App')
        assert 'My App' in mock_run.call_args[0][0][2]

    def test_macos_default_title(self):
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run', return_value=self._run_ok()) as mock_run:
            from notifiers.systemnotify import send
            send(configuration={}, message='Hi')
        assert 'AutoPkg Runner' in mock_run.call_args[0][0][2]

    def test_macos_url_appended_to_body(self):
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run', return_value=self._run_ok()) as mock_run:
            from notifiers.systemnotify import send
            send(configuration={}, message='Done', url='https://example.com', url_title='Go')
        assert 'Go: https://example.com' in mock_run.call_args[0][0][2]

    def test_macos_nonzero_exit_raises(self):
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run', return_value=self._run_fail(b'AppleScript error')):
            from notifiers.systemnotify import send
            with pytest.raises(RuntimeError, match='osascript failed'):
                send(configuration={}, message='Hi')

    def test_macos_special_chars_escaped(self):
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run', return_value=self._run_ok()) as mock_run:
            from notifiers.systemnotify import send
            send(configuration={}, message='Say "hello"')
        assert '\\"hello\\"' in mock_run.call_args[0][0][2]

    def test_linux_calls_notify_send(self):
        with patch('platform.system', return_value='Linux'), \
             patch('subprocess.run', return_value=self._run_ok()) as mock_run:
            from notifiers.systemnotify import send
            send(configuration={}, message='Hello Linux')
        assert mock_run.call_args[0][0][0] == 'notify-send'

    def test_linux_nonzero_exit_raises(self):
        with patch('platform.system', return_value='Linux'), \
             patch('subprocess.run', return_value=self._run_fail(b'bus error')):
            from notifiers.systemnotify import send
            with pytest.raises(RuntimeError, match='notify-send failed'):
                send(configuration={}, message='Hi')

    def test_unsupported_platform_raises(self):
        with patch('platform.system', return_value='Windows'):
            from notifiers.systemnotify import send
            with pytest.raises(RuntimeError, match='not supported'):
                send(configuration={}, message='Hi')

    def test_url_only_no_message(self):
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run', return_value=self._run_ok()) as mock_run:
            from notifiers.systemnotify import send
            send(configuration={}, message='', url='https://example.com', url_title='Link')
        assert 'Link: https://example.com' in mock_run.call_args[0][0][2]
