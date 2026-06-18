"""Tests for notifiers.slack."""
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


class TestSlackSend:
    _cfg = {'webhook_url': 'https://hooks.slack.com/services/A/B/C'}

    def _send(self, conn, cfg=None, **kwargs):
        with patch('http.client.HTTPSConnection', return_value=conn), \
             patch('notifiers.slack.ssl_context'):
            from notifiers.slack import send
            send(configuration=cfg or self._cfg, **kwargs)

    def test_basic_message(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Hello Slack')
        body = json.loads(conn.request.call_args[0][2])
        assert body['text'] == 'Hello Slack'

    def test_url_appended_as_mrkdwn_link(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Done', url='https://example.com', url_title='Report')
        body = json.loads(conn.request.call_args[0][2])
        assert '<https://example.com|Report>' in body['text']

    def test_url_without_title_uses_default_label(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Done', url='https://example.com')
        body = json.loads(conn.request.call_args[0][2])
        assert '<https://example.com|View report>' in body['text']

    def test_url_only_no_message(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='', url='https://example.com', url_title='Link')
        body = json.loads(conn.request.call_args[0][2])
        assert '<https://example.com|Link>' in body['text']

    def test_title_sets_username(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Hi', title='SlackBot')
        body = json.loads(conn.request.call_args[0][2])
        assert body['username'] == 'SlackBot'

    def test_no_title_omits_username_field(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Hi')
        body = json.loads(conn.request.call_args[0][2])
        assert 'username' not in body

    def test_webhook_url_query_string_preserved_in_path(self):
        conn = _mock_connection(_mock_http_response(200))
        cfg = {'webhook_url': 'https://hooks.slack.com/services/A/B/C?token=xyz'}
        self._send(conn, cfg=cfg, message='Hi')
        path = conn.request.call_args[0][1]
        assert 'token=xyz' in path

    def test_non_2xx_raises_runtime_error(self):
        conn = _mock_connection(_mock_http_response(500, b'Server Error'))
        with pytest.raises(RuntimeError, match='500'):
            self._send(conn, message='Hi')
