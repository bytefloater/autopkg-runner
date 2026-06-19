"""Tests for notifiers.email."""
from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest


def _decode_mime_body(raw: str) -> str:
    """Decode a MIME message, returning all text parts concatenated."""
    import email as _email
    msg = _email.message_from_string(raw)
    parts = []
    for part in msg.walk():
        ct = part.get_content_type()
        if ct in ('text/plain', 'text/html'):
            payload = part.get_payload(decode=True)
            if payload:
                parts.append(payload.decode(part.get_content_charset() or 'utf-8', errors='replace'))
    return '\n'.join(parts) if parts else raw


class TestStripHtml:
    def test_strips_tags(self):
        from notifiers.email import _strip_html
        assert _strip_html('<p>Hello <b>world</b></p>') == 'Hello world'

    def test_br_becomes_newline(self):
        from notifiers.email import _strip_html
        assert _strip_html('Line1<br>Line2') == 'Line1\nLine2'

    def test_br_self_closing(self):
        from notifiers.email import _strip_html
        assert _strip_html('A<br/>B') == 'A\nB'

    def test_decodes_html_entities(self):
        from notifiers.email import _strip_html
        assert _strip_html('a &amp; b &lt;3&gt; &quot;x&quot;') == 'a & b <3> "x"'

    def test_plain_text_unchanged(self):
        from notifiers.email import _strip_html
        assert _strip_html('plain text') == 'plain text'

    def test_nbsp_becomes_space(self):
        from notifiers.email import _strip_html
        assert _strip_html('a&nbsp;b') == 'a b'


class TestApplyTemplate:
    def test_missing_template_returns_message_unchanged(self, tmp_path):
        from notifiers.email import _apply_template
        with patch('notifiers.email._TEMPLATES_DIR', tmp_path):
            assert _apply_template('nonexistent', 'my message') == 'my message'

    def test_existing_template_replaces_placeholder(self, tmp_path):
        from notifiers.email import _apply_template
        (tmp_path / 'mytemplate.html').write_text('<html>{{ content }}</html>')
        with patch('notifiers.email._TEMPLATES_DIR', tmp_path):
            assert _apply_template('mytemplate', 'hello') == '<html>hello</html>'


class TestEmailSend:
    _cfg = {
        'from_address': 'sender@example.com',
        'recipients':   'alice@example.com, bob@example.com',
        'smtp_server':  'smtp.example.com',
        'smtp_port':    '587',
        'use_ssl':      False,
        'use_auth':     False,
    }

    def _make_smtp(self):
        smtp = MagicMock()
        smtp.starttls = MagicMock()
        return smtp

    def _send(self, smtp, cfg=None, **kwargs):
        with patch('smtplib.SMTP', return_value=smtp), \
             patch('notifiers.email.ssl_context'):
            from notifiers.email import send
            send(configuration=cfg or self._cfg, **kwargs)

    def test_sends_to_all_recipients(self):
        smtp = self._make_smtp()
        self._send(smtp, message='Hello')
        recipients = smtp.sendmail.call_args[0][1]
        assert 'alice@example.com' in recipients
        assert 'bob@example.com' in recipients

    def test_subject_from_title(self):
        smtp = self._make_smtp()
        self._send(smtp, message='Hi', title='My Subject')
        assert 'My Subject' in smtp.sendmail.call_args[0][2]

    def test_default_subject_when_no_title(self):
        smtp = self._make_smtp()
        self._send(smtp, message='Hi')
        assert 'AutoPkg Runner Notification' in smtp.sendmail.call_args[0][2]

    def test_url_appended_to_body(self):
        smtp = self._make_smtp()
        self._send(smtp, message='Hi', url='https://example.com', url_title='Link')
        body = _decode_mime_body(smtp.sendmail.call_args[0][2])
        from urllib.parse import urlparse
        urls_in_body = [w.strip('<>()') for w in body.split() if urlparse(w.strip('<>(),')).scheme in ('http', 'https')]
        assert any(urlparse(u).netloc == 'example.com' for u in urls_in_body)
        assert 'Link' in body

    def test_url_without_title_uses_default_label(self):
        smtp = self._make_smtp()
        self._send(smtp, message='Hi', url='https://example.com')
        assert 'View report' in _decode_mime_body(smtp.sendmail.call_args[0][2])

    def test_starttls_called_for_plain_smtp(self):
        smtp = self._make_smtp()
        self._send(smtp, message='Hi')
        smtp.starttls.assert_called_once()

    def test_starttls_not_supported_is_swallowed(self):
        smtp = self._make_smtp()
        smtp.starttls.side_effect = smtplib.SMTPNotSupportedError
        self._send(smtp, message='Hi')
        smtp.sendmail.assert_called_once()

    def test_ssl_uses_smtp_ssl_class(self):
        smtp = self._make_smtp()
        cfg = {**self._cfg, 'use_ssl': True, 'smtp_port': '465'}
        with patch('smtplib.SMTP_SSL', return_value=smtp) as mock_ssl, \
             patch('notifiers.email.ssl_context'):
            from notifiers.email import send
            send(configuration=cfg, message='Hi')
        mock_ssl.assert_called_once()

    def test_auth_calls_login(self):
        smtp = self._make_smtp()
        cfg = {**self._cfg, 'use_auth': True, 'username': 'user', 'password': 'pass'}
        self._send(smtp, cfg=cfg, message='Hi')
        smtp.login.assert_called_once_with('user', 'pass')

    def test_no_auth_skips_login(self):
        smtp = self._make_smtp()
        self._send(smtp, message='Hi')
        smtp.login.assert_not_called()

    def test_quit_called_even_on_send_error(self):
        smtp = self._make_smtp()
        smtp.sendmail.side_effect = RuntimeError('send failed')
        with pytest.raises(RuntimeError):
            self._send(smtp, message='Hi')
        smtp.quit.assert_called_once()

    def test_no_recipients_raises_value_error(self):
        from notifiers.email import send
        cfg = {**self._cfg, 'recipients': ''}
        with pytest.raises(ValueError, match='no recipients'):
            send(configuration=cfg, message='Hi')

    def test_html_message_stripped_for_plain_text_part(self):
        smtp = self._make_smtp()
        self._send(smtp, message='<p>Hello <b>world</b></p>')
        assert 'Hello world' in _decode_mime_body(smtp.sendmail.call_args[0][2])

    def test_template_applied_when_configured(self, tmp_path):
        smtp = self._make_smtp()
        (tmp_path / 'mytemplate.html').write_text('<html>{{ content }}</html>')
        cfg = {**self._cfg, 'email_template': 'mytemplate'}
        with patch('smtplib.SMTP', return_value=smtp), \
             patch('notifiers.email.ssl_context'), \
             patch('notifiers.email._TEMPLATES_DIR', tmp_path):
            from notifiers.email import send
            send(configuration=cfg, message='body content')
        assert '<html>' in _decode_mime_body(smtp.sendmail.call_args[0][2])
