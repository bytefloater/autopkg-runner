"""Tests for notifiers.msteams."""
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


class TestMSTeamsSend:
    _cfg = {'webhook_url': 'https://outlook.office.com/webhook/A/B'}

    def _send(self, conn, **kwargs):
        with patch('http.client.HTTPSConnection', return_value=conn), \
             patch('notifiers.msteams.ssl_context'):
            from notifiers.msteams import send
            send(configuration=self._cfg, **kwargs)

    def test_basic_message_uses_messagecard_type(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Hello Teams')
        body = json.loads(conn.request.call_args[0][2])
        assert body['@type'] == 'MessageCard'
        assert body['sections'][0]['activityText'] == 'Hello Teams'

    def test_title_sets_card_title(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Hi', title='Custom Title')
        body = json.loads(conn.request.call_args[0][2])
        assert body['sections'][0]['activityTitle'] == 'Custom Title'

    def test_no_title_uses_default(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Hi')
        body = json.loads(conn.request.call_args[0][2])
        assert body['sections'][0]['activityTitle'] == 'AutoPkg Runner'

    def test_url_adds_open_uri_action(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Done', url='https://example.com', url_title='Go')
        body = json.loads(conn.request.call_args[0][2])
        action = body['potentialAction'][0]
        assert action['@type'] == 'OpenUri'
        assert action['name'] == 'Go'
        assert action['targets'][0]['uri'] == 'https://example.com'

    def test_url_without_title_uses_default_label(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Done', url='https://example.com')
        body = json.loads(conn.request.call_args[0][2])
        assert body['potentialAction'][0]['name'] == 'View report'

    def test_no_url_omits_potential_action(self):
        conn = _mock_connection(_mock_http_response(200))
        self._send(conn, message='Done')
        body = json.loads(conn.request.call_args[0][2])
        assert 'potentialAction' not in body

    def test_non_2xx_raises_runtime_error(self):
        conn = _mock_connection(_mock_http_response(429, b'Too Many Requests'))
        with pytest.raises(RuntimeError, match='429'):
            self._send(conn, message='Hi')
