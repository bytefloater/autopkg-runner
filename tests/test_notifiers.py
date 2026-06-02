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

    def test_html_param_sent_when_supports_html_true(self):
        resp = _mock_http_response(200)
        conn = _mock_connection(resp)
        from notifiers.pushover import send
        config = {'app_token': 'APP', 'user_token': 'USR', 'supports_html': True}
        with patch('notifiers.pushover.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            send(config, '<b>Hello</b>')
        body = conn.request.call_args[0][2]
        assert 'html=1' in body

    def test_html_param_absent_when_supports_html_false(self):
        resp = _mock_http_response(200)
        conn = _mock_connection(resp)
        from notifiers.pushover import send
        config = {'app_token': 'APP', 'user_token': 'USR', 'supports_html': False}
        with patch('notifiers.pushover.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            send(config, 'Plain text message')
        body = conn.request.call_args[0][2]
        assert 'html=' not in body

    def test_html_param_absent_when_supports_html_not_set(self):
        resp = _mock_http_response(200)
        conn = _mock_connection(resp)
        from notifiers.pushover import send
        config = {'app_token': 'APP', 'user_token': 'USR'}
        with patch('notifiers.pushover.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            send(config, 'No HTML flag')
        body = conn.request.call_args[0][2]
        assert 'html=' not in body


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

    def test_204_success_does_not_raise(self):
        """Discord webhooks return 204 No Content on success."""
        resp = _mock_http_response(204)
        conn = _mock_connection(resp)
        self._send(conn)  # must not raise

    def test_non_2xx_raises_runtime_error(self):
        resp = _mock_http_response(401, b'{"message": "401: Unauthorized"}')
        conn = _mock_connection(resp)
        from notifiers.discord import send
        config = {'webhook_id': 'WID', 'webhook_token': 'WTOK'}
        with patch('notifiers.discord.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            with pytest.raises(RuntimeError, match='401'):
                send(config, 'Hello')

    def test_404_raises_with_status_in_message(self):
        resp = _mock_http_response(404, b'{"message": "Unknown Webhook"}')
        conn = _mock_connection(resp)
        from notifiers.discord import send
        config = {'webhook_id': 'BAD', 'webhook_token': 'BAD'}
        with patch('notifiers.discord.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            with pytest.raises(RuntimeError) as exc_info:
                send(config, 'Hello')
        assert '404' in str(exc_info.value)

    def test_200_ok_also_accepted(self):
        """Some proxy setups may return 200 instead of 204 — treat all 2xx as success."""
        resp = _mock_http_response(200)
        conn = _mock_connection(resp)
        self._send(conn)  # must not raise


# ---------------------------------------------------------------------------
# SSL context
# ---------------------------------------------------------------------------

class TestSSLContext:
    def test_certifi_available_uses_certifi_cafile(self):
        """When certifi is installed ssl_context() builds a context with its CA bundle."""
        import importlib
        import notifiers._ssl as ssl_mod
        importlib.reload(ssl_mod)
        ctx = ssl_mod.ssl_context()
        # certifi is a transitive dep — it will be present in the test env
        assert isinstance(ctx, ssl.SSLContext)

    def test_falls_back_to_default_when_certifi_missing(self):
        """When certifi is not installed ssl_context() falls back to the built-in default."""
        import sys
        import importlib
        import notifiers._ssl as ssl_mod
        with patch.dict(sys.modules, {'certifi': None}):
            importlib.reload(ssl_mod)
            ctx = ssl_mod.ssl_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_pip_system_certs_patch_is_respected(self):
        """If pip-system-certs patches certifi.where(), that patched path is used."""
        import importlib
        import notifiers._ssl as ssl_mod
        mock_certifi = MagicMock()
        mock_certifi.where.return_value = '/patched/system/certs.pem'
        with patch.dict('sys.modules', {'certifi': mock_certifi}):
            importlib.reload(ssl_mod)
            # The function should call certifi.where() — if pip-system-certs has
            # patched it, the system cert bundle path would be returned here.
            # We just verify that certifi.where() is called (not hardcoded).
            try:
                ssl_mod.ssl_context()
            except Exception:
                pass  # cafile path may not exist on disk; that's fine
        mock_certifi.where.assert_called_once()
