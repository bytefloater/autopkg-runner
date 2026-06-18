"""Tests for notifiers.pushover."""
from __future__ import annotations

import ssl
from http.client import HTTPResponse
from unittest.mock import MagicMock, patch

import pytest


def _mock_http_response(status: int, body: bytes = b'{}'):
    resp = MagicMock(spec=HTTPResponse)
    resp.status = status
    resp.read.return_value = body
    return resp


def _mock_connection(response: HTTPResponse):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.getresponse.return_value = response
    return conn


class TestPushoverSend:
    def _send(self, conn_mock, **kwargs):
        from notifiers.pushover import send
        config = {'app_token': 'APP', 'user_token': 'USR'}
        with patch('notifiers.pushover.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn_mock):
            send(config, 'Test message', **kwargs)

    def test_send_posts_to_correct_host(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn)
        conn.request.assert_called_once()
        url = conn.request.call_args[0][1]
        assert url == '/1/messages.json'

    def test_send_includes_tokens_in_body(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn)
        body = conn.request.call_args[0][2]
        assert 'APP' in body
        assert 'USR' in body

    def test_send_http_200_does_not_raise(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn)

    def test_send_http_400_raises_runtime_error(self):
        conn = _mock_connection(_mock_http_response(400))
        from notifiers.pushover import send
        config = {'app_token': 'APP', 'user_token': 'USR'}
        with patch('notifiers.pushover.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            with pytest.raises(RuntimeError):
                send(config, 'message')

    def test_url_none_not_in_body(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, url=None)
        body = conn.request.call_args[0][2]
        assert 'url=None' not in body

    def test_html_param_sent_when_supports_html_true(self):
        conn = _mock_connection(_mock_http_response(200))
        from notifiers.pushover import send
        config = {'app_token': 'APP', 'user_token': 'USR', 'supports_html': True}
        with patch('notifiers.pushover.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            send(config, '<b>Hello</b>')
        body = conn.request.call_args[0][2]
        assert 'html=1' in body

    def test_html_param_absent_when_supports_html_false(self):
        conn = _mock_connection(_mock_http_response(200))
        from notifiers.pushover import send
        config = {'app_token': 'APP', 'user_token': 'USR', 'supports_html': False}
        with patch('notifiers.pushover.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            send(config, 'Plain text message')
        body = conn.request.call_args[0][2]
        assert 'html=' not in body

    def test_html_param_absent_when_supports_html_not_set(self):
        conn = _mock_connection(_mock_http_response(200))
        from notifiers.pushover import send
        config = {'app_token': 'APP', 'user_token': 'USR'}
        with patch('notifiers.pushover.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            send(config, 'No HTML flag')
        body = conn.request.call_args[0][2]
        assert 'html=' not in body
