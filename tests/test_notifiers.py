"""Tests for notifiers.pushover, notifiers.discord, notifiers._ssl."""
from __future__ import annotations

import json
import ssl
from http.client import HTTPResponse
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Pushover
# ---------------------------------------------------------------------------

class TestPushoverSend:
    def _send(self, conn_mock, **kwargs):
        from notifiers.pushover import send
        config = {'app_token': 'APP', 'user_token': 'USR'}
        with patch('notifiers.pushover.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn_mock):
            send(config, 'Test message', **kwargs)

    def test_send_posts_to_correct_host(self):
        resp = _mock_http_response(200)
        conn = _mock_connection(resp)
        self._send(conn)
        conn.request.assert_called_once()
        url = conn.request.call_args[0][1]
        assert url == '/1/messages.json'

    def test_send_includes_tokens_in_body(self):
        resp = _mock_http_response(200)
        conn = _mock_connection(resp)
        self._send(conn)
        # urlencode() returns a str, not bytes
        body = conn.request.call_args[0][2]
        assert 'APP' in body
        assert 'USR' in body

    def test_send_http_200_does_not_raise(self):
        resp = _mock_http_response(200)
        conn = _mock_connection(resp)
        self._send(conn)  # no exception

    def test_send_http_400_raises_runtime_error(self):
        resp = _mock_http_response(400)
        conn = _mock_connection(resp)
        from notifiers.pushover import send
        config = {'app_token': 'APP', 'user_token': 'USR'}
        with patch('notifiers.pushover.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            with pytest.raises(RuntimeError):
                send(config, 'message')

    def test_url_none_not_in_body(self):
        resp = _mock_http_response(200)
        conn = _mock_connection(resp)
        self._send(conn, url=None)
        body = conn.request.call_args[0][2]
        # urlencode() returns a str; None-valued keys are stripped before encoding
        assert 'url=None' not in body


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------

class TestDiscordSend:
    def _send(self, conn_mock, **kwargs):
        from notifiers.discord import send
        config = {'webhook_id': 'WID', 'webhook_token': 'WTOK'}
        with patch('notifiers.discord.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn_mock):
            send(config, 'Hello Discord', **kwargs)

    def test_send_posts_to_webhook_url(self):
        resp = _mock_http_response(200)
        conn = _mock_connection(resp)
        self._send(conn)
        url = conn.request.call_args[0][1]
        assert 'WID' in url and 'WTOK' in url

    def test_url_and_title_embedded_as_markdown(self):
        resp = _mock_http_response(200)
        conn = _mock_connection(resp)
        self._send(conn, url='https://example.com', url_title='Click here')
        body_bytes = conn.request.call_args[0][2]
        body = json.loads(body_bytes)
        content = body.get('content', '')
        assert 'https://example.com' in content


# ---------------------------------------------------------------------------
# SSL context
# ---------------------------------------------------------------------------

class TestSSLContext:
    def test_truststore_available_returns_truststore_context(self):
        mock_ctx = MagicMock(spec=ssl.SSLContext)
        mock_truststore = MagicMock()
        mock_truststore.SSLContext.return_value = mock_ctx
        import sys
        with patch.dict(sys.modules, {'truststore': mock_truststore}):
            import importlib
            import notifiers._ssl as ssl_mod
            importlib.reload(ssl_mod)
            ctx = ssl_mod.ssl_context()
        assert ctx is mock_ctx

    def test_falls_back_when_truststore_missing(self):
        import sys
        # Remove truststore from modules to simulate ImportError
        saved = sys.modules.pop('truststore', None)
        try:
            import importlib
            import notifiers._ssl as ssl_mod
            importlib.reload(ssl_mod)
            with patch.dict(sys.modules, {'truststore': None}):
                ctx = ssl_mod.ssl_context()
            assert isinstance(ctx, ssl.SSLContext)
        finally:
            if saved:
                sys.modules['truststore'] = saved
