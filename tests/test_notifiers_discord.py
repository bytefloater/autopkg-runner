"""Tests for notifiers.discord."""
from __future__ import annotations

import json
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


class TestDiscordSend:
    def _send(self, conn_mock, **kwargs):
        from notifiers.discord import send
        config = {'webhook_id': 'WID', 'webhook_token': 'WTOK'}
        with patch('notifiers.discord.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn_mock):
            send(config, 'Hello Discord', **kwargs)

    def test_send_posts_to_webhook_url(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn)
        url = conn.request.call_args[0][1]
        assert 'WID' in url and 'WTOK' in url

    def test_url_and_title_embedded_as_markdown(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, url='https://example.com', url_title='Click here')
        body = json.loads(conn.request.call_args[0][2])
        import re
        from urllib.parse import urlparse
        md_urls = re.findall(r'\(([^)]+)\)', body.get('content', ''))
        assert any(urlparse(u).netloc == 'example.com' for u in md_urls)

    def test_204_success_does_not_raise(self):
        """Discord webhooks return 204 No Content on success."""
        conn = _mock_connection(_mock_http_response(204))
        self._send(conn)

    def test_non_2xx_raises_runtime_error(self):
        conn = _mock_connection(_mock_http_response(401, b'{"message": "401: Unauthorized"}'))
        from notifiers.discord import send
        config = {'webhook_id': 'WID', 'webhook_token': 'WTOK'}
        with patch('notifiers.discord.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            with pytest.raises(RuntimeError, match='401'):
                send(config, 'Hello')

    def test_404_raises_with_status_in_message(self):
        conn = _mock_connection(_mock_http_response(404, b'{"message": "Unknown Webhook"}'))
        from notifiers.discord import send
        config = {'webhook_id': 'BAD', 'webhook_token': 'BAD'}
        with patch('notifiers.discord.ssl_context', return_value=ssl.create_default_context()), \
             patch('http.client.HTTPSConnection', return_value=conn):
            with pytest.raises(RuntimeError) as exc_info:
                send(config, 'Hello')
        assert '404' in str(exc_info.value)

    def test_200_ok_also_accepted(self):
        """Some proxy setups may return 200 instead of 204 - treat all 2xx as success."""
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn)
