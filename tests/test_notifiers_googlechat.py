"""Tests for notifiers.googlechat."""
from __future__ import annotations

import json
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


class TestGoogleChatSend:
    _cfg = {'webhook_url': 'https://chat.googleapis.com/v1/spaces/X/messages?key=abc'}

    def _send(self, conn, **kwargs):
        with patch('http.client.HTTPSConnection', return_value=conn), \
             patch('notifiers.googlechat.ssl_context'):
            from notifiers.googlechat import send
            send(configuration=self._cfg, **kwargs)

    def test_basic_message(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Hello Chat')
        body = json.loads(conn.request.call_args[0][2])
        assert 'Hello Chat' in body['text']

    def test_title_prepended_as_bold(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Done', title='Run complete')
        body = json.loads(conn.request.call_args[0][2])
        assert '*Run complete*' in body['text']

    def test_url_appended_as_markdown_link(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Done', url='https://example.com', url_title='See it')
        body = json.loads(conn.request.call_args[0][2])
        assert '[See it](https://example.com)' in body['text']

    def test_url_without_title_uses_default_label(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Done', url='https://example.com')
        body = json.loads(conn.request.call_args[0][2])
        assert '[View report](https://example.com)' in body['text']

    def test_query_string_preserved_in_path(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Hi')
        path = conn.request.call_args[0][1]
        assert 'key=abc' in path

    def test_all_parts_combined(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Body', title='Title', url='https://x.com', url_title='X')
        body = json.loads(conn.request.call_args[0][2])
        text = body['text']
        assert '*Title*' in text and 'Body' in text and '[X](https://x.com)' in text

    def test_non_2xx_raises_runtime_error(self):
        conn = _mock_connection(_mock_http_response(403, b'Forbidden'))
        with pytest.raises(RuntimeError, match='403'):
            self._send(conn, message='Hi')
